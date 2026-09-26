import asyncio
import logging
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from ai_spot_trader.agent import (
    LLMHTTPError,
    LLMNetworkError,
    LLMQuotaError,
    LLMRateLimitError,
    LLMServerError,
    LLMTimeoutError,
    OpenAIResponsesClient,
    STRATEGIC_DECISION_SCHEMA,
)
from ai_spot_trader.core.retry import RetryPolicy
from ai_spot_trader.domain.enums import LLMModel

API_KEY = "test-only-openai-secret"
OUTPUT = '{"action":"HOLD","symbol":"BTC/EUR","proposed_quantity":null,"rationale":null}'


def completed() -> dict[str, Any]:
    return {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": OUTPUT}]}]}


async def call(client: OpenAIResponsesClient) -> str:
    return await client.generate_structured_decision(model=LLMModel.LUNA, instructions="system", input_text="{}", schema=STRATEGIC_DECISION_SCHEMA)


def client_for(http_client: httpx.AsyncClient, sleeps: list[float], *, attempts: int = 3) -> OpenAIResponsesClient:
    async def sleep(delay: float) -> None:
        sleeps.append(delay)
    return OpenAIResponsesClient(api_key=SecretStr(API_KEY), http_client=http_client, retry_policy=RetryPolicy(max_attempts=attempts, base_delay_seconds=1, max_delay_seconds=4), sleep=sleep)


def test_transient_429_honors_retry_after_then_succeeds() -> None:
    calls = 0
    sleeps: list[float] = []
    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "2.5"}, json={"error": {"type": "rate_limit_error", "code": None, "message": "secret ignored"}})
        return httpx.Response(200, json=completed())
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            assert await call(client_for(http, sleeps)) == OUTPUT
    asyncio.run(scenario())
    assert calls == 2
    assert sleeps == [2.5]


def test_429_without_retry_after_uses_bounded_exponential_backoff() -> None:
    calls = 0
    sleeps: list[float] = []
    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 3:
            return httpx.Response(429, json={"error": {"type": "rate_limit_error", "code": None}})
        return httpx.Response(200, json=completed())
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            await call(client_for(http, sleeps))
    asyncio.run(scenario())
    assert sleeps == [1.0, 2.0]


def test_invalid_retry_after_falls_back_to_backoff() -> None:
    sleeps: list[float] = []
    calls = 0
    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429 if calls == 1 else 200, headers={"Retry-After": "not-a-delay"}, json={"error": {"type": "rate_limit_error"}} if calls == 1 else completed())
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            await call(client_for(http, sleeps))
    asyncio.run(scenario())
    assert sleeps == [1.0]


@pytest.mark.parametrize("code", ["credit_balance_exhausted", "organization_usage_limit_exceeded", "organization_spend_limit_exceeded", "project_spend_limit_exceeded"])
def test_documented_quota_and_spend_codes_are_not_retried(code: str) -> None:
    calls = 0
    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, json={"error": {"type": "insufficient_quota", "code": code, "message": API_KEY}})
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with pytest.raises(LLMQuotaError) as exc:
                await call(client_for(http, []))
            assert exc.value.provider_error_code == code
            assert API_KEY not in str(exc.value)
    asyncio.run(scenario())
    assert calls == 1


def test_malformed_429_payload_remains_safely_retryable_and_sanitized(caplog: pytest.LogCaptureFixture) -> None:
    calls = 0
    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, text="not-json")
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with pytest.raises(LLMRateLimitError) as exc:
                await call(client_for(http, [], attempts=2))
            assert exc.value.provider_error_type is None and exc.value.provider_error_code is None
    with caplog.at_level(logging.WARNING, logger="ai_spot_trader.retry"):
        asyncio.run(scenario())
    assert calls == 2
    assert API_KEY not in caplog.text


@pytest.mark.parametrize(("status", "error_type"), [(408, LLMTimeoutError), (500, LLMServerError), (503, LLMServerError)])
def test_transient_http_errors_exhaust_bounded_attempts(status: int, error_type: type[Exception]) -> None:
    calls = 0
    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status, json={"error": {"type": "server_error"}})
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with pytest.raises(error_type):
                await call(client_for(http, [], attempts=2))
    asyncio.run(scenario())
    assert calls == 2


def test_network_error_is_retryable_and_bounded() -> None:
    calls = 0
    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("offline", request=request)
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with pytest.raises(LLMNetworkError):
                await call(client_for(http, [], attempts=2))
    asyncio.run(scenario())
    assert calls == 2


def test_http_timeout_is_retryable_and_bounded() -> None:
    calls = 0
    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("slow", request=request)
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with pytest.raises(LLMTimeoutError):
                await call(client_for(http, [], attempts=2))
    asyncio.run(scenario())
    assert calls == 2


def test_permanent_http_error_is_not_retried() -> None:
    calls = 0
    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={"error": {"type": "authentication_error", "message": API_KEY}})
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with pytest.raises(LLMHTTPError):
                await call(client_for(http, []))
    asyncio.run(scenario())
    assert calls == 1
