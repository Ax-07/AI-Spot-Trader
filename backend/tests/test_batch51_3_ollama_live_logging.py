import asyncio
import json
import logging
import re
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import httpx
import pytest

import ai_spot_trader.agent.ollama_client as ollama_module
import ai_spot_trader.agent.strategic_thesis as strategic_thesis_module
from ai_spot_trader.agent.errors import (
    LLMNetworkError,
    LLMProviderError,
    LLMTimeoutError,
)
from ai_spot_trader.agent.llm_audit import llm_audit_context
from ai_spot_trader.agent.ollama_client import OllamaStructuredDecisionClient
from ai_spot_trader.core.retry import RetryPolicy

SESSION_ID = UUID("51300000-0000-0000-0000-000000000001")
CYCLE_ID = UUID("51300000-0000-0000-0000-000000000002")
NO_RETRY = RetryPolicy(max_attempts=1, base_delay_seconds=0, max_delay_seconds=0)
SCHEMA = {
    "type": "object",
    "properties": {"action": {"type": "string"}},
    "required": ["action"],
    "additionalProperties": False,
}


def _ollama_message(
    content: str,
    *,
    tool_calls: object | None = None,
    thinking: str | None = None,
) -> dict[str, object]:
    message: dict[str, object] = {"role": "assistant", "content": content}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    if thinking is not None:
        message["thinking"] = thinking
    return {"model": "qwen3.5:9b", "message": message, "done": True}


async def _run_simple_client(
    handler: httpx.MockTransport,
    *,
    retry_policy: RetryPolicy = NO_RETRY,
    sleep: Any = asyncio.sleep,
    input_text: str = "{}",
) -> str:
    async with httpx.AsyncClient(transport=handler) as http_client:
        client = OllamaStructuredDecisionClient(
            http_client=http_client,
            retry_policy=retry_policy,
            sleep=sleep,
        )
        with llm_audit_context(session_id=SESSION_ID, cycle_id=CYCLE_ID):
            return await client.generate_structured_decision(
                model="qwen3.5:9b",
                instructions="safe system instructions",
                input_text=input_text,
                schema=SCHEMA,
            )


def _messages(caplog: pytest.LogCaptureFixture, prefix: str) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.getMessage().startswith(prefix)]


def test_ollama_live_log_starts_before_success_and_contains_only_safe_metadata(
    caplog: pytest.LogCaptureFixture,
) -> None:
    prompt_marker = "PROMPT-MUST-NOT-APPEAR"
    raw_response_marker = "RAW-RESPONSE-MUST-NOT-APPEAR"
    secret_marker = "sk-secret-value-123456789"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_ollama_message(
                json.dumps({"action": "HOLD", "marker": raw_response_marker}),
                thinking="PRIVATE-THINKING-MUST-NOT-APPEAR",
            ),
        )

    caplog.set_level(logging.INFO)
    result = asyncio.run(
        _run_simple_client(
            httpx.MockTransport(handler),
            input_text=json.dumps(
                {"marker": prompt_marker, "api_key": secret_marker},
                separators=(",", ":"),
            ),
        )
    )

    assert raw_response_marker in result
    starts = _messages(caplog, "llm_request_started")
    successes = _messages(caplog, "llm_request_succeeded")
    assert len(starts) == 1
    assert len(successes) == 1
    assert caplog.messages.index(starts[0]) < caplog.messages.index(successes[0])

    expected_metadata = (
        "provider=OLLAMA",
        "model=qwen3.5:9b",
        f"session_id={SESSION_ID}",
        f"cycle_id={CYCLE_ID}",
        "attempt=1",
    )
    for value in expected_metadata:
        assert value in starts[0]
        assert value in successes[0]
    assert re.search(r"call_id=[0-9a-f]{12}", starts[0])
    assert re.search(r"latency_ms=\d+", successes[0])

    rendered = "\n".join(
        record.getMessage()
        for record in caplog.records
        if record.name == "ai_spot_trader.agent.ollama"
    )
    for forbidden in (
        prompt_marker,
        raw_response_marker,
        secret_marker,
        "PRIVATE-THINKING-MUST-NOT-APPEAR",
        "safe system instructions",
        "/api/chat",
        "localhost:11434",
    ):
        assert forbidden not in rendered


@pytest.mark.parametrize(
    ("kind", "expected_exception", "error_type"),
    [
        ("timeout", LLMTimeoutError, "LLMTimeoutError"),
        ("network", LLMNetworkError, "LLMNetworkError"),
        ("provider", LLMProviderError, "LLMProviderError"),
    ],
)
def test_ollama_live_log_reports_timeout_transport_and_provider_errors(
    caplog: pytest.LogCaptureFixture,
    kind: str,
    expected_exception: type[Exception],
    error_type: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if kind == "timeout":
            raise httpx.ReadTimeout("slow raw transport detail", request=request)
        if kind == "network":
            raise httpx.ConnectError("offline raw transport detail", request=request)
        return httpx.Response(200, content=b"not-json-provider-response")

    caplog.set_level(logging.INFO)
    with pytest.raises(expected_exception):
        asyncio.run(_run_simple_client(httpx.MockTransport(handler)))

    failures = _messages(caplog, "llm_request_failed")
    assert len(failures) == 1
    failure = failures[0]
    assert f"error_type={error_type}" in failure
    assert f"session_id={SESSION_ID}" in failure
    assert f"cycle_id={CYCLE_ID}" in failure
    assert "model=qwen3.5:9b" in failure
    assert "attempt=1" in failure
    assert re.search(r"call_id=[0-9a-f]{12}", failure)
    assert re.search(r"latency_ms=\d+", failure)
    assert "raw transport detail" not in failure
    assert "not-json-provider-response" not in failure


def test_ollama_retry_reuses_call_id_and_increments_attempt(
    caplog: pytest.LogCaptureFixture,
) -> None:
    responses = [
        httpx.Response(503, json={"error": "temporary server detail"}),
        httpx.Response(200, json=_ollama_message('{"action":"HOLD"}')),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    async def no_sleep(delay: float) -> None:
        assert delay == 0

    caplog.set_level(logging.INFO)
    result = asyncio.run(
        _run_simple_client(
            httpx.MockTransport(handler),
            retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0, max_delay_seconds=0),
            sleep=no_sleep,
        )
    )
    assert result == '{"action":"HOLD"}'

    starts = _messages(caplog, "llm_request_started")
    failures = _messages(caplog, "llm_request_failed")
    successes = _messages(caplog, "llm_request_succeeded")
    retries = _messages(caplog, "network_retry")
    assert len(starts) == 2
    assert len(failures) == 1
    assert len(successes) == 1
    assert len(retries) == 1

    call_ids = [re.search(r"call_id=([0-9a-f]{12})", item).group(1) for item in starts]  # type: ignore[union-attr]
    assert call_ids[0] == call_ids[1]
    assert "attempt=1" in starts[0]
    assert "attempt=2" in starts[1]
    assert f"call_id={call_ids[0]}" in failures[0]
    assert f"call_id={call_ids[0]}" in successes[0]
    assert "attempt=1" in failures[0]
    assert "attempt=2" in successes[0]
    assert "operation=ollama_chat" in retries[0]
    assert "temporary server detail" not in "\n".join(caplog.messages)


def test_ollama_tool_rounds_have_distinct_network_call_ids(
    caplog: pytest.LogCaptureFixture,
) -> None:
    responses = [
        _ollama_message(
            "",
            tool_calls=[
                {"function": {"name": "facts", "arguments": {"symbol": "BTC/USD"}}}
            ],
        ),
        _ollama_message('{"action":"HOLD"}'),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=responses.pop(0))

    class Registry:
        openai_tools = (
            {
                "type": "function",
                "name": "facts",
                "description": "read only facts",
                "parameters": {
                    "type": "object",
                    "properties": {"symbol": {"type": "string"}},
                    "required": ["symbol"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        )

        async def execute(self, *, call_id: str, name: str, arguments_json: str) -> Any:
            return SimpleNamespace(
                trace=SimpleNamespace(call_id=call_id),
                function_output='{"ok":true}',
            )

    async def scenario() -> str:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OllamaStructuredDecisionClient(
                http_client=http_client,
                retry_policy=NO_RETRY,
            )
            with llm_audit_context(session_id=SESSION_ID, cycle_id=CYCLE_ID):
                loop = await client.generate_structured_decision_with_tools(
                    model="qwen3.5:9b",
                    instructions="tools",
                    input_text="{}",
                    schema=SCHEMA,
                    tool_registry=cast(Any, Registry()),
                    max_tool_calls=2,
                )
                return loop.output_text

    caplog.set_level(logging.INFO)
    assert asyncio.run(scenario()) == '{"action":"HOLD"}'

    starts = _messages(caplog, "llm_request_started")
    successes = _messages(caplog, "llm_request_succeeded")
    assert len(starts) == 2
    assert len(successes) == 2
    call_ids = [re.search(r"call_id=([0-9a-f]{12})", item).group(1) for item in starts]  # type: ignore[union-attr]
    assert call_ids[0] != call_ids[1]
    assert all("attempt=1" in item for item in starts)
    assert all(f"session_id={SESSION_ID}" in item for item in starts)
    assert all(f"cycle_id={CYCLE_ID}" in item for item in starts)


def test_validated_agent_plan_summary_counts_buy_sell_hold(
    caplog: pytest.LogCaptureFixture,
) -> None:
    plan = SimpleNamespace(
        cycle_id=CYCLE_ID,
        decisions=(
            SimpleNamespace(action=SimpleNamespace(value="BUY")),
            SimpleNamespace(action=SimpleNamespace(value="SELL")),
            SimpleNamespace(action=SimpleNamespace(value="HOLD")),
            SimpleNamespace(action=SimpleNamespace(value="HOLD")),
        ),
    )

    caplog.set_level(logging.INFO, logger="ai_spot_trader.agent.planner")
    with llm_audit_context(session_id=SESSION_ID, cycle_id=CYCLE_ID):
        strategic_thesis_module._log_agent_plan_completed(cast(Any, plan))

    summaries = _messages(caplog, "agent_plan_completed")
    assert summaries == [
        f"agent_plan_completed session_id={SESSION_ID} cycle_id={CYCLE_ID} "
        "decisions=4 buy=1 sell=1 hold=2"
    ]


def test_logging_failure_never_changes_ollama_result(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ollama_message('{"action":"HOLD"}'))

    def broken_log(*args: object, **kwargs: object) -> None:
        raise RuntimeError("logging backend unavailable")

    monkeypatch.setattr(ollama_module.logger, "info", broken_log)
    monkeypatch.setattr(ollama_module.logger, "error", broken_log)

    assert asyncio.run(_run_simple_client(httpx.MockTransport(handler))) == '{"action":"HOLD"}'
