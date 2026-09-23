import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from ai_spot_trader.agent.errors import (
    LLMHTTPError,
    LLMProviderError,
    LLMServerError,
    LLMTimeoutError,
)
from ai_spot_trader.agent.openai_client import OpenAIResponsesClient
from ai_spot_trader.core.retry import RetryPolicy
from ai_spot_trader.domain.enums import DerivativeContractKind, LLMModel, MarketType
from ai_spot_trader.domain.models import DerivativeInstrument
from ai_spot_trader.integrations.kraken.derivatives import KrakenDerivativesPublicClient
from ai_spot_trader.integrations.kraken.errors import (
    KrakenHTTPError,
    KrakenPayloadError,
    KrakenServerError,
    KrakenTimeoutError,
)
from ai_spot_trader.integrations.kraken.resilience import (
    RetryingKrakenDerivativesRestSource,
    RetryingKrakenSpotRestSource,
)
from ai_spot_trader.integrations.kraken.rest import KrakenPublicRestClient

NO_DELAY_THREE_ATTEMPTS = RetryPolicy(
    max_attempts=3,
    base_delay_seconds=0,
    max_delay_seconds=0,
)
NO_DELAY_TWO_ATTEMPTS = RetryPolicy(
    max_attempts=2,
    base_delay_seconds=0,
    max_delay_seconds=0,
)
NOW = datetime(2026, 9, 23, 8, 0, tzinfo=UTC)
API_KEY = "test-only-openai-secret"
OUTPUT_TEXT = (
    '{"action":"HOLD","symbol":"BTC/EUR",'
    '"proposed_quantity":null,"rationale":null}'
)


async def _no_sleep(_: float) -> None:
    return None


def _asset_pairs_payload() -> dict[str, object]:
    return {
        "error": [],
        "result": {
            "BTC/EUR": {
                "altname": "XBTEUR",
                "wsname": "XBT/EUR",
                "status": "online",
            }
        },
    }


def _completed_response() -> dict[str, Any]:
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": OUTPUT_TEXT}],
            }
        ],
    }


def _linear_perpetual() -> DerivativeInstrument:
    return DerivativeInstrument(
        symbol="BTC/USD",
        venue_symbol="PF_XBTUSD",
        market_type=MarketType.PERPETUAL,
        contract_kind=DerivativeContractKind.LINEAR,
        underlying_asset="BTC",
        quote_asset="USD",
        contract_size=Decimal("1"),
        tick_size=Decimal("1"),
        min_order_quantity=Decimal("0.0001"),
        max_position_quantity=Decimal("1000"),
        initial_margin_rate=Decimal("0.1"),
        maintenance_margin_rate=Decimal("0.05"),
        max_leverage=Decimal("10"),
        funding_interval_seconds=Decimal("3600"),
    )


def _run_openai(client: OpenAIResponsesClient) -> str:
    return asyncio.run(
        client.generate_structured_decision(
            model=LLMModel.LUNA,
            instructions="system prompt",
            input_text="{}",
            schema={
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        )
    )


def test_kraken_spot_success_does_not_retry() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=_asset_pairs_payload())

    async def scenario() -> None:
        async with httpx.AsyncClient(
            base_url="https://api.kraken.test",
            transport=httpx.MockTransport(handler),
        ) as http_client:
            source = RetryingKrakenSpotRestSource(
                KrakenPublicRestClient("https://api.kraken.test", client=http_client),
                retry_policy=NO_DELAY_THREE_ATTEMPTS,
                sleep=_no_sleep,
            )
            registry = await source.fetch_pair_registry()
            assert registry.normalize("BTC/EUR") == "BTC/EUR"

    asyncio.run(scenario())
    assert calls == 1


def test_kraken_spot_timeout_then_success_is_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("temporary timeout", request=request)
        return httpx.Response(200, json=_asset_pairs_payload())

    async def scenario() -> None:
        async with httpx.AsyncClient(
            base_url="https://api.kraken.test",
            transport=httpx.MockTransport(handler),
        ) as http_client:
            source = RetryingKrakenSpotRestSource(
                KrakenPublicRestClient("https://api.kraken.test", client=http_client),
                retry_policy=NO_DELAY_THREE_ATTEMPTS,
                sleep=_no_sleep,
            )
            await source.fetch_pair_registry()

    asyncio.run(scenario())
    assert calls == 2


@pytest.mark.parametrize("status_code", [429, 500, 503])
def test_kraken_spot_retryable_http_then_success(status_code: int) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(status_code, json={"error": "transient"})
        return httpx.Response(200, json=_asset_pairs_payload())

    async def scenario() -> None:
        async with httpx.AsyncClient(
            base_url="https://api.kraken.test",
            transport=httpx.MockTransport(handler),
        ) as http_client:
            source = RetryingKrakenSpotRestSource(
                KrakenPublicRestClient("https://api.kraken.test", client=http_client),
                retry_policy=NO_DELAY_THREE_ATTEMPTS,
                sleep=_no_sleep,
            )
            await source.fetch_pair_registry()

    asyncio.run(scenario())
    assert calls == 2


def test_kraken_spot_retry_budget_exhaustion_is_typed() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"error": "unavailable"})

    async def scenario() -> None:
        async with httpx.AsyncClient(
            base_url="https://api.kraken.test",
            transport=httpx.MockTransport(handler),
        ) as http_client:
            source = RetryingKrakenSpotRestSource(
                KrakenPublicRestClient("https://api.kraken.test", client=http_client),
                retry_policy=NO_DELAY_THREE_ATTEMPTS,
                sleep=_no_sleep,
            )
            with pytest.raises(KrakenServerError) as exc_info:
                await source.fetch_pair_registry()
            assert exc_info.value.status_code == 503

    asyncio.run(scenario())
    assert calls == 3


def test_kraken_spot_permanent_http_does_not_retry() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400, json={"error": "bad request"})

    async def scenario() -> None:
        async with httpx.AsyncClient(
            base_url="https://api.kraken.test",
            transport=httpx.MockTransport(handler),
        ) as http_client:
            source = RetryingKrakenSpotRestSource(
                KrakenPublicRestClient("https://api.kraken.test", client=http_client),
                retry_policy=NO_DELAY_THREE_ATTEMPTS,
                sleep=_no_sleep,
            )
            with pytest.raises(KrakenHTTPError) as exc_info:
                await source.fetch_pair_registry()
            assert exc_info.value.status_code == 400

    asyncio.run(scenario())
    assert calls == 1


def test_kraken_invalid_payload_fails_closed_without_retry() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=b"not-json")

    async def scenario() -> None:
        async with httpx.AsyncClient(
            base_url="https://api.kraken.test",
            transport=httpx.MockTransport(handler),
        ) as http_client:
            source = RetryingKrakenSpotRestSource(
                KrakenPublicRestClient("https://api.kraken.test", client=http_client),
                retry_policy=NO_DELAY_THREE_ATTEMPTS,
                sleep=_no_sleep,
            )
            with pytest.raises(KrakenPayloadError):
                await source.fetch_pair_registry()

    asyncio.run(scenario())
    assert calls == 1


def test_kraken_derivatives_public_read_retries_before_snapshot_side_effects() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, json={"error": "temporary"})
        return httpx.Response(
            200,
            json={
                "candles": [
                    {
                        "time": int((NOW - timedelta(minutes=2)).timestamp() * 1000),
                        "close": "65000",
                    }
                ],
                "more_candles": False,
            },
        )

    async def scenario() -> None:
        async with httpx.AsyncClient(
            base_url="https://futures.kraken.test/derivatives/api/v3",
            transport=httpx.MockTransport(handler),
        ) as http_client:
            source = RetryingKrakenDerivativesRestSource(
                KrakenDerivativesPublicClient(
                    "https://futures.kraken.test/derivatives/api/v3",
                    client=http_client,
                ),
                retry_policy=NO_DELAY_THREE_ATTEMPTS,
                sleep=_no_sleep,
            )
            history = await source.fetch_mark_history(
                _linear_perpetual(),
                since=NOW - timedelta(minutes=5),
                until=NOW,
            )
            assert len(history) == 1

    asyncio.run(scenario())
    assert calls == 2


def test_openai_success_does_not_retry() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=_completed_response())

    async def scenario() -> str:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OpenAIResponsesClient(
                api_key=SecretStr(API_KEY),
                http_client=http_client,
                retry_policy=NO_DELAY_TWO_ATTEMPTS,
                sleep=_no_sleep,
            )
            return await client.generate_structured_decision(
                model=LLMModel.LUNA,
                instructions="system prompt",
                input_text="{}",
                schema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            )

    assert asyncio.run(scenario()) == OUTPUT_TEXT
    assert calls == 1


def test_openai_timeout_then_success_is_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("temporary timeout", request=request)
        return httpx.Response(200, json=_completed_response())

    async def scenario() -> str:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OpenAIResponsesClient(
                api_key=SecretStr(API_KEY),
                http_client=http_client,
                retry_policy=NO_DELAY_TWO_ATTEMPTS,
                sleep=_no_sleep,
            )
            return await client.generate_structured_decision(
                model=LLMModel.LUNA,
                instructions="system prompt",
                input_text="{}",
                schema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            )

    assert asyncio.run(scenario()) == OUTPUT_TEXT
    assert calls == 2


@pytest.mark.parametrize("status_code", [429, 500, 503])
def test_openai_retryable_http_then_success(status_code: int) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(status_code, json={"error": {"message": "transient"}})
        return httpx.Response(200, json=_completed_response())

    async def scenario() -> str:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OpenAIResponsesClient(
                api_key=SecretStr(API_KEY),
                http_client=http_client,
                retry_policy=NO_DELAY_TWO_ATTEMPTS,
                sleep=_no_sleep,
            )
            return await client.generate_structured_decision(
                model=LLMModel.LUNA,
                instructions="system prompt",
                input_text="{}",
                schema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            )

    assert asyncio.run(scenario()) == OUTPUT_TEXT
    assert calls == 2


def test_openai_retry_budget_exhaustion_is_typed() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"error": {"message": API_KEY}})

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OpenAIResponsesClient(
                api_key=SecretStr(API_KEY),
                http_client=http_client,
                retry_policy=NO_DELAY_TWO_ATTEMPTS,
                sleep=_no_sleep,
            )
            with pytest.raises(LLMServerError) as exc_info:
                await client.generate_structured_decision(
                    model=LLMModel.LUNA,
                    instructions="system prompt",
                    input_text="{}",
                    schema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                )
            assert exc_info.value.status_code == 503
            assert API_KEY not in str(exc_info.value)

    asyncio.run(scenario())
    assert calls == 2


def test_openai_permanent_http_does_not_retry() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OpenAIResponsesClient(
                api_key=SecretStr(API_KEY),
                http_client=http_client,
                retry_policy=NO_DELAY_TWO_ATTEMPTS,
                sleep=_no_sleep,
            )
            with pytest.raises(LLMHTTPError) as exc_info:
                await client.generate_structured_decision(
                    model=LLMModel.LUNA,
                    instructions="system prompt",
                    input_text="{}",
                    schema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                )
            assert exc_info.value.status_code == 400

    asyncio.run(scenario())
    assert calls == 1


def test_openai_invalid_json_fails_closed_without_retry() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=b"not-json")

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OpenAIResponsesClient(
                api_key=SecretStr(API_KEY),
                http_client=http_client,
                retry_policy=NO_DELAY_TWO_ATTEMPTS,
                sleep=_no_sleep,
            )
            with pytest.raises(LLMProviderError):
                await client.generate_structured_decision(
                    model=LLMModel.LUNA,
                    instructions="system prompt",
                    input_text="{}",
                    schema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                )

    asyncio.run(scenario())
    assert calls == 1


def test_typed_transport_timeouts_remain_timeout_errors_for_cycle_audit() -> None:
    assert isinstance(KrakenTimeoutError("timeout"), TimeoutError)
    assert isinstance(LLMTimeoutError("timeout"), TimeoutError)


def test_retry_logs_do_not_expose_provider_payload_or_secret(
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls = 0
    provider_secret = "provider-body-secret"

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                503,
                json={"error": {"message": provider_secret, "token": API_KEY}},
            )
        return httpx.Response(200, json=_completed_response())

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OpenAIResponsesClient(
                api_key=SecretStr(API_KEY),
                http_client=http_client,
                retry_policy=NO_DELAY_TWO_ATTEMPTS,
                sleep=_no_sleep,
            )
            await client.generate_structured_decision(
                model=LLMModel.LUNA,
                instructions="system prompt",
                input_text="{}",
                schema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            )

    caplog.set_level("WARNING", logger="ai_spot_trader.retry")
    asyncio.run(scenario())

    assert "network_retry operation=openai_responses" in caplog.text
    assert "http_status=503" in caplog.text
    assert provider_secret not in caplog.text
    assert API_KEY not in caplog.text
