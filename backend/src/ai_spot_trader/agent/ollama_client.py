from __future__ import annotations

import asyncio
import json
import math
from time import perf_counter
from typing import Any, cast

import httpx

from ai_spot_trader.agent.errors import (
    LLMHTTPError,
    LLMNetworkError,
    LLMProviderError,
    LLMRateLimitError,
    LLMServerError,
    LLMTimeoutError,
    LLMTransientError,
    LLMTransportError,
)
from ai_spot_trader.agent.llm_audit import GLOBAL_LLM_AUDIT_STORE
from ai_spot_trader.core.retry import LLM_PRE_DECISION_RETRY_POLICY, RetryPolicy, Sleep, retry_async
from ai_spot_trader.domain.enums import LLMModel
from ai_spot_trader.domain.models import AgentToolTrace
from ai_spot_trader.tools.read_only import (
    ReadOnlyToolRegistry,
    ToolCallBudgetExceededError,
    ToolLoopResult,
)


class OllamaStructuredDecisionClient:
    """Ollama `/api/chat` adapter behind the canonical structured-decision boundary.

    The adapter owns transport conversion only. Domain JSON is still parsed and validated by the
    existing Agent providers before a DecisionCandidate/CycleDecisionPlan can reach Risk.
    """

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        timeout_seconds: float = 60.0,
        http_client: httpx.AsyncClient | None = None,
        retry_policy: RetryPolicy = LLM_PRE_DECISION_RETRY_POLICY,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        normalized_url = base_url.strip().rstrip("/")
        if not normalized_url.startswith(("http://", "https://")):
            raise ValueError("Ollama base_url must use http:// or https://")
        if timeout_seconds <= 0:
            raise ValueError("Ollama timeout_seconds must be positive")
        self._base_url = normalized_url
        self._timeout_seconds = timeout_seconds
        self._http_client = http_client
        self._retry_policy = retry_policy
        self._sleep = sleep
        self._last_tool_traces: tuple[AgentToolTrace, ...] = ()

    @property
    def last_tool_traces(self) -> tuple[AgentToolTrace, ...]:
        return self._last_tool_traces

    async def generate_structured_decision(
        self,
        *,
        model: LLMModel | str,
        instructions: str,
        input_text: str,
        schema: dict[str, Any],
    ) -> str:
        request = self._request(
            model=model,
            instructions=instructions,
            messages=[{"role": "user", "content": input_text}],
            schema=schema,
        )
        response = await self._chat(request)
        message = _message(response)
        if _tool_calls(message):
            raise LLMProviderError("Ollama returned an unexpected tool call")
        return _message_content(message)

    async def generate_structured_decision_with_tools(
        self,
        *,
        model: LLMModel | str,
        instructions: str,
        input_text: str,
        schema: dict[str, Any],
        tool_registry: ReadOnlyToolRegistry,
        max_tool_calls: int,
    ) -> ToolLoopResult:
        if isinstance(max_tool_calls, bool) or max_tool_calls <= 0:
            raise ValueError("max_tool_calls must be a positive integer")

        self._last_tool_traces = ()
        messages: list[dict[str, Any]] = [{"role": "user", "content": input_text}]
        traces: list[AgentToolTrace] = []
        next_call_index = 1
        tools = _ollama_tools(tool_registry)

        while True:
            request = self._request(
                model=model,
                instructions=instructions,
                messages=messages,
                schema=schema,
                tools=tools,
            )
            response = await self._chat(request)
            message = _message(response)
            calls = _tool_calls(message)
            if not calls:
                return ToolLoopResult(
                    output_text=_message_content(message),
                    traces=tuple(traces),
                )

            if len(traces) + len(calls) > max_tool_calls:
                raise ToolCallBudgetExceededError(
                    "Ollama response exceeded the configured read-only tool-call budget"
                )

            messages.append(_assistant_history_message(message))
            for name, arguments_json in calls:
                call_id = f"ollama-tool-{next_call_index}"
                next_call_index += 1
                execution = await tool_registry.execute(
                    call_id=call_id,
                    name=name,
                    arguments_json=arguments_json,
                )
                traces.append(execution.trace)
                self._last_tool_traces = tuple(traces)
                messages.append(
                    {
                        "role": "tool",
                        "tool_name": name,
                        "content": execution.function_output,
                    }
                )

    def _request(
        self,
        *,
        model: LLMModel | str,
        instructions: str,
        messages: list[dict[str, Any]],
        schema: dict[str, Any],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        request_messages = [{"role": "system", "content": instructions}, *messages]
        request: dict[str, Any] = {
            "model": _model_name(model),
            "messages": request_messages,
            "stream": False,
            # Structured AI Spot Trader calls consume only message.content. Disable provider-side
            # reasoning output so no hidden chain-of-thought is produced for the application.
            "think": False,
            "format": schema,
        }
        if tools:
            request["tools"] = tools
        return request

    async def _chat(self, request: dict[str, Any]) -> dict[str, Any]:
        started = perf_counter()
        try:
            response = await self._post(
                f"{self._base_url}/api/chat",
                json=request,
            )
            try:
                payload = response.json()
            except ValueError as exc:
                raise LLMProviderError("Ollama response body is not valid JSON") from exc
            if not isinstance(payload, dict):
                raise LLMProviderError("Ollama response body must be a JSON object")
            typed_payload = cast(dict[str, Any], payload)
            if typed_payload.get("done") is not True:
                raise LLMProviderError("Ollama response did not complete")
        except Exception as exc:
            self._audit(
                request=request,
                response={},
                status="ERROR",
                error_type=type(exc).__name__,
                latency_ms=(perf_counter() - started) * 1000,
            )
            raise

        self._audit(
            request=request,
            response=typed_payload,
            status="SUCCESS",
            error_type=None,
            latency_ms=(perf_counter() - started) * 1000,
        )
        return typed_payload

    async def _post(self, url: str, *, json: dict[str, Any]) -> httpx.Response:
        async def operation() -> httpx.Response:
            try:
                if self._http_client is not None:
                    response = await self._http_client.post(
                        url,
                        json=json,
                        timeout=self._timeout_seconds,
                    )
                else:
                    async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                        response = await client.post(url, json=json)
            except httpx.TimeoutException as exc:
                raise LLMTimeoutError("Ollama request timed out") from exc
            except httpx.TransportError as exc:
                raise LLMNetworkError("Ollama network request failed") from exc
            except httpx.HTTPError as exc:
                raise LLMTransportError("Ollama request failed") from exc

            error = _http_error(response)
            if error is not None:
                raise error
            return response

        return await retry_async(
            operation,
            policy=self._retry_policy,
            operation_name="ollama_chat",
            is_retryable=lambda exc: isinstance(exc, LLMTransientError),
            sleep=self._sleep,
        )

    @staticmethod
    def _audit(
        *,
        request: dict[str, Any],
        response: dict[str, Any],
        status: str,
        error_type: str | None,
        latency_ms: float,
    ) -> None:
        try:
            GLOBAL_LLM_AUDIT_STORE.append(
                request=cast(dict[str, object], request),
                response=cast(dict[str, object], response),
                provider="OLLAMA",
                status=cast(Any, status),
                error_type=error_type,
                latency_ms=latency_ms,
            )
        except Exception:
            # Observability must never change the strategic execution path.
            pass


def _model_name(model: LLMModel | str) -> str:
    value = model.value if isinstance(model, LLMModel) else str(model)
    normalized = value.strip()
    if not normalized:
        raise ValueError("Ollama model cannot be empty")
    return normalized


def _http_error(response: httpx.Response) -> LLMTransportError | None:
    status_code = response.status_code
    if status_code < 400:
        return None
    metadata = {
        "status_code": status_code,
        "provider_error_type": "ollama_http_error",
        "provider_error_code": "model_not_found" if status_code == 404 else None,
    }
    if status_code in {408, 504}:
        return LLMTimeoutError("Ollama request timed out", **metadata)
    if status_code == 429:
        return LLMRateLimitError(
            "Ollama request was rate limited",
            retry_after_seconds=_retry_after_seconds(response.headers.get("Retry-After")),
            **metadata,
        )
    if 500 <= status_code <= 599:
        return LLMServerError("Ollama request returned a server error", **metadata)
    return LLMHTTPError("Ollama request returned a permanent HTTP error", **metadata)



def _retry_after_seconds(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        delay = float(value.strip())
    except ValueError:
        return None
    if not math.isfinite(delay) or delay < 0:
        return None
    return delay

def _message(response: dict[str, Any]) -> dict[str, Any]:
    value = response.get("message")
    if not isinstance(value, dict):
        raise LLMProviderError("Ollama response contains no message object")
    return cast(dict[str, Any], value)


def _message_content(message: dict[str, Any]) -> str:
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise LLMProviderError("Ollama response must contain non-empty message content")
    return content


def _tool_calls(message: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    raw_calls = message.get("tool_calls")
    if raw_calls in (None, []):
        return ()
    if not isinstance(raw_calls, list):
        raise LLMProviderError("Ollama tool_calls must be a list")

    calls: list[tuple[str, str]] = []
    for raw_call in raw_calls:
        if not isinstance(raw_call, dict):
            raise LLMProviderError("Ollama tool call must be an object")
        function = raw_call.get("function")
        if not isinstance(function, dict):
            raise LLMProviderError("Ollama tool call is missing function")
        name = function.get("name")
        arguments = function.get("arguments")
        if not isinstance(name, str) or not name.strip():
            raise LLMProviderError("Ollama tool call is missing function name")
        if isinstance(arguments, str):
            try:
                decoded = json.loads(arguments)
            except json.JSONDecodeError as exc:
                raise LLMProviderError("Ollama tool arguments are invalid JSON") from exc
            if not isinstance(decoded, dict):
                raise LLMProviderError("Ollama tool arguments must be a JSON object")
            arguments_json = json.dumps(
                decoded,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        elif isinstance(arguments, dict):
            arguments_json = json.dumps(
                arguments,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        else:
            raise LLMProviderError("Ollama tool arguments must be an object")
        calls.append((name, arguments_json))
    return tuple(calls)


def _assistant_history_message(message: dict[str, Any]) -> dict[str, Any]:
    history: dict[str, Any] = {
        "role": "assistant",
        "content": message.get("content") if isinstance(message.get("content"), str) else "",
    }
    raw_calls = message.get("tool_calls")
    if isinstance(raw_calls, list) and raw_calls:
        history["tool_calls"] = raw_calls
    return history


def _ollama_tools(tool_registry: ReadOnlyToolRegistry) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for tool in tool_registry.openai_tools:
        name = tool.get("name")
        parameters = tool.get("parameters")
        if not isinstance(name, str) or not isinstance(parameters, dict):
            raise ValueError("read-only tool definition is not compatible with Ollama")
        function: dict[str, Any] = {
            "name": name,
            "parameters": parameters,
        }
        description = tool.get("description")
        if isinstance(description, str):
            function["description"] = description
        converted.append({"type": "function", "function": function})
    return converted
