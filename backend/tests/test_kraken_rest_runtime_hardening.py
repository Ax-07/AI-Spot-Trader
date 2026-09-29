from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx
import pytest

from ai_spot_trader.integrations.kraken.errors import (
    KrakenAPIError,
    KrakenHTTPError,
    KrakenNetworkError,
    KrakenRateLimitError,
    KrakenServerError,
)
from ai_spot_trader.integrations.kraken.rest import KrakenPublicRestClient

SINCE = datetime(2026, 9, 29, 8, 0, tzinfo=UTC)


def test_provider_api_error_is_distinct_from_structural_payload_error_and_sanitized() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"error": ["EGeneral:sensitive provider detail"], "result": {}},
                request=request,
            )

        async with httpx.AsyncClient(
            base_url="https://api.kraken.test",
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = KrakenPublicRestClient("https://api.kraken.test", client=http_client)
            with pytest.raises(KrakenAPIError) as exc_info:
                await client.fetch_ohlcv_history(
                    "BTC/USD",
                    interval_minutes=5,
                    since=SINCE,
                )
        assert "sensitive provider detail" not in str(exc_info.value)

    asyncio.run(scenario())


def test_explicit_provider_rate_limit_is_classified_without_leaking_payload() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"error": ["EAPI:Rate limit exceeded secret-context"], "result": {}},
                request=request,
            )

        async with httpx.AsyncClient(
            base_url="https://api.kraken.test",
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = KrakenPublicRestClient("https://api.kraken.test", client=http_client)
            with pytest.raises(KrakenRateLimitError) as exc_info:
                await client.fetch_pair_registry()
        assert "secret-context" not in str(exc_info.value)

    asyncio.run(scenario())


def test_http_statuses_keep_rate_limit_server_and_permanent_errors_distinct() -> None:
    async def classify(status_code: int):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code, text="provider body must stay private", request=request)

        async with httpx.AsyncClient(
            base_url="https://api.kraken.test",
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = KrakenPublicRestClient("https://api.kraken.test", client=http_client)
            with pytest.raises(Exception) as exc_info:
                await client.fetch_pair_registry()
            return exc_info.value

    rate = asyncio.run(classify(429))
    server = asyncio.run(classify(503))
    permanent = asyncio.run(classify(403))

    assert isinstance(rate, KrakenRateLimitError)
    assert isinstance(server, KrakenServerError)
    assert isinstance(permanent, KrakenHTTPError)
    assert "provider body" not in str(rate)
    assert "provider body" not in str(server)
    assert "provider body" not in str(permanent)


def test_network_failure_is_distinct_from_provider_payload_errors() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("private transport detail", request=request)

        async with httpx.AsyncClient(
            base_url="https://api.kraken.test",
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = KrakenPublicRestClient("https://api.kraken.test", client=http_client)
            with pytest.raises(KrakenNetworkError) as exc_info:
                await client.fetch_pair_registry()
        assert "private transport detail" not in str(exc_info.value)

    asyncio.run(scenario())
