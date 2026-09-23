import asyncio
from typing import Any, cast

import httpx
from pydantic import SecretStr

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
from ai_spot_trader.core.retry import (
    LLM_PRE_DECISION_RETRY_POLICY,
    RetryPolicy,
    Sleep,
    retry_async,
)
from ai_spot_trader.domain.enums import LLMModel
from ai_spot_trader.domain.models import AgentToolTrace
from ai_spot_trader.tools.read_only import (
    ReadOnlyToolRegistry,
    ToolCallBudgetExceededError,
    ToolLoopResult,
)


class OpenAIResponsesClient:
    """Minimal OpenAI Responses API adapter for strategic and conversational calls."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 30.0,
        http_client: httpx.AsyncClient | None = None,
        retry_policy: RetryPolicy = LLM_PRE_DECISION_RETRY_POLICY,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        if not api_key.get_secret_value():
            raise ValueError("OpenAI API key cannot be empty")
        if timeout_seconds <= 0:
            raise ValueError("OpenAI timeout_seconds must be positive")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._http_client = http_client
        self._retry_policy = retry_policy
        self._sleep = sleep
        self._last_tool_traces: tuple[AgentToolTrace, ...] = ()

    @property
    def last_tool_traces(self) -> tuple[AgentToolTrace, ...]:
        """Tool traces completed by the latest strategic tool loop, including partial failure."""

        return self._last_tool_traces

    async def generate_structured_decision(
        self,
        *,
        model: LLMModel,
        instructions: str,
        input_text: str,
        schema: dict[str, Any],
    ) -> str:
        request = self._structured_request(
            model=model,
            instructions=instructions,
            input_value=input_text,
            schema=schema,
        )
        response = await self._responses(request)
        return _extract_output_text(response)

    async def generate_structured_decision_with_tools(
        self,
        *,
        model: LLMModel,
        instructions: str,
        input_text: str,
        schema: dict[str, Any],
        tool_registry: ReadOnlyToolRegistry,
        max_tool_calls: int,
    ) -> ToolLoopResult:
        if isinstance(max_tool_calls, bool) or max_tool_calls <= 0:
            raise ValueError("max_tool_calls must be a positive integer")

        self._last_tool_traces = ()
        input_items: list[dict[str, Any]] = [
            {"role": "user", "content": input_text}
        ]
        traces: list[AgentToolTrace] = []
        seen_call_ids: set[str] = set()

        while True:
            request = self._structured_request(
                model=model,
                instructions=instructions,
                input_value=input_items,
                schema=schema,
            )
            request["tools"] = list(tool_registry.openai_tools)
            request["parallel_tool_calls"] = False
            response = await self._responses(request)
            output_items = _extract_output_items(response)
            function_calls = _extract_function_calls(output_items)
            if not function_calls:
                return ToolLoopResult(
                    output_text=_extract_output_text(response),
                    traces=tuple(traces),
                )

            if len(traces) + len(function_calls) > max_tool_calls:
                raise ToolCallBudgetExceededError(
                    "OpenAI response exceeded the configured read-only tool-call budget"
                )

            # store=false is kept. The causal conversation is explicitly replayed using
            # the prior Responses output items plus our function_call_output items.
            input_items.extend(dict(item) for item in output_items)
            for call_id, name, arguments_json in function_calls:
                if call_id in seen_call_ids:
                    raise LLMProviderError("OpenAI returned a duplicate function call_id")
                seen_call_ids.add(call_id)
                execution = await tool_registry.execute(
                    call_id=call_id,
                    name=name,
                    arguments_json=arguments_json,
                )
                traces.append(execution.trace)
                self._last_tool_traces = tuple(traces)
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": execution.function_output,
                    }
                )

    async def generate_text_response(
        self,
        *,
        model: LLMModel,
        instructions: str,
        input_text: str,
    ) -> str:
        request = {
            "model": model.value,
            "instructions": instructions,
            "input": input_text,
            "store": False,
        }
        response = await self._responses(request)
        return _extract_output_text(response)

    def _structured_request(
        self,
        *,
        model: LLMModel,
        instructions: str,
        input_value: str | list[dict[str, Any]],
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "model": model.value,
            "instructions": instructions,
            "input": input_value,
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "agent_decision_v1",
                    "strict": True,
                    "schema": schema,
                }
            },
        }

    async def _responses(self, request: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        response = await self._post(
            f"{self._base_url}/responses",
            headers=headers,
            json=request,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise LLMProviderError("OpenAI response body is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise LLMProviderError("OpenAI response body must be a JSON object")
        return cast(dict[str, Any], payload)

    async def _post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
    ) -> httpx.Response:
        async def operation() -> httpx.Response:
            try:
                if self._http_client is not None:
                    response = await self._http_client.post(
                        url,
                        headers=headers,
                        json=json,
                        timeout=self._timeout_seconds,
                    )
                else:
                    async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                        response = await client.post(url, headers=headers, json=json)
            except httpx.TimeoutException as exc:
                raise LLMTimeoutError("OpenAI request timed out") from exc
            except httpx.TransportError as exc:
                raise LLMNetworkError("OpenAI network request failed") from exc
            except httpx.HTTPError as exc:
                raise LLMTransportError("OpenAI request failed") from exc

            error = _http_error(response.status_code)
            if error is not None:
                raise error
            return response

        return await retry_async(
            operation,
            policy=self._retry_policy,
            operation_name="openai_responses",
            is_retryable=lambda exc: isinstance(exc, LLMTransientError),
            sleep=self._sleep,
        )


def _http_error(status_code: int) -> LLMTransportError | None:
    if status_code < 400:
        return None
    if status_code == 408:
        return LLMTimeoutError("OpenAI request timed out", status_code=status_code)
    if status_code == 429:
        return LLMRateLimitError("OpenAI request was rate limited", status_code=status_code)
    if 500 <= status_code <= 599:
        return LLMServerError("OpenAI request returned a server error", status_code=status_code)
    return LLMHTTPError(
        "OpenAI request returned a permanent HTTP error",
        status_code=status_code,
    )


def _extract_output_items(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("status") != "completed":
        raise LLMProviderError("OpenAI response did not complete")
    output = response.get("output")
    if not isinstance(output, list) or not output:
        raise LLMProviderError("OpenAI response contains no output items")
    items: list[dict[str, Any]] = []
    for item in output:
        if not isinstance(item, dict):
            raise LLMProviderError("OpenAI output item must be an object")
        items.append(cast(dict[str, Any], item))
    return items


def _extract_function_calls(
    output_items: list[dict[str, Any]],
) -> tuple[tuple[str, str, str], ...]:
    calls: list[tuple[str, str, str]] = []
    for item in output_items:
        if item.get("type") != "function_call":
            continue
        call_id = item.get("call_id")
        name = item.get("name")
        arguments = item.get("arguments")
        if not isinstance(call_id, str) or not call_id.strip():
            raise LLMProviderError("OpenAI function_call is missing call_id")
        if not isinstance(name, str) or not name.strip():
            raise LLMProviderError("OpenAI function_call is missing name")
        if not isinstance(arguments, str):
            raise LLMProviderError("OpenAI function_call arguments must be JSON text")
        calls.append((call_id, name, arguments))
    return tuple(calls)


def _extract_output_text(response: dict[str, Any]) -> str:
    output = _extract_output_items(response)
    texts: list[str] = []
    for item in output:
        if item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "refusal":
                raise LLMProviderError("OpenAI refused the request")
            if part.get("type") != "output_text":
                continue
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text)
    if len(texts) != 1:
        raise LLMProviderError("OpenAI response must contain exactly one output_text")
    return texts[0]
