from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from ai_spot_trader.integrations.kraken.errors import KrakenPayloadError
from ai_spot_trader.integrations.kraken.rest import KrakenPublicRestClient, _parse_ohlcv_payload

NOW = datetime(2026, 9, 28, 10, 30, tzinfo=UTC)
START = NOW - timedelta(minutes=10)


def _rows() -> list[list[object]]:
    return [
        [int(START.timestamp()), "99", "101", "98", "100", "100", "12.5", 10],
        [
            int((START + timedelta(minutes=5)).timestamp()),
            "100",
            "102",
            "99",
            "101",
            "101",
            "8.25",
            11,
        ],
    ]


def test_runtime_legacy_ohlc_result_key_is_accepted_for_single_requested_pair() -> None:
    payload = {"error": [], "result": {"XXBTZUSD": _rows(), "last": int(NOW.timestamp())}}

    candles = _parse_ohlcv_payload(
        payload,
        interval_minutes=5,
        expected_symbol="BTC/USD",
        received_at=NOW,
    )

    assert len(candles) == 2
    assert candles[0].close_price == Decimal("100")
    assert candles[0].volume == Decimal("12.5")
    assert candles[0].is_final is True
    assert candles[1].is_final is False


def test_wrong_display_ohlc_result_key_still_fails_closed() -> None:
    payload = {"error": [], "result": {"ETH/USD": _rows(), "last": int(NOW.timestamp())}}

    with pytest.raises(KrakenPayloadError, match="did not match"):
        _parse_ohlcv_payload(
            payload,
            interval_minutes=5,
            expected_symbol="BTC/USD",
            received_at=NOW,
        )


def test_spot_request_keeps_asset_version_1_while_accepting_legacy_result_key() -> None:
    async def scenario() -> None:
        seen_params: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal seen_params
            assert request.url.path == "/0/public/OHLC"
            seen_params = dict(request.url.params)
            return httpx.Response(
                200,
                json={
                    "error": [],
                    "result": {"XXBTZUSD": _rows(), "last": int(NOW.timestamp())},
                },
                request=request,
            )

        async with httpx.AsyncClient(
            base_url="https://api.kraken.test",
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = KrakenPublicRestClient("https://api.kraken.test", client=http_client)
            candles = await client.fetch_ohlcv_history(
                "BTC/USD",
                interval_minutes=5,
                since=START - timedelta(minutes=5),
            )

        assert candles
        assert seen_params["pair"] == "BTC/USD"
        assert seen_params["assetVersion"] == "1"

    asyncio.run(scenario())
