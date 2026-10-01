from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from ai_spot_trader.integrations.kraken.errors import (
    KrakenHTTPError,
    KrakenPayloadError,
    KrakenRateLimitError,
    KrakenServerError,
)
from ai_spot_trader.integrations.kraken.rest import KrakenPublicRestClient, _parse_ohlcv_payload
from ai_spot_trader.integrations.kraken.symbols import parse_asset_pairs_payload

NOW = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)


def _asset_pairs_payload() -> dict[str, object]:
    return {
        "error": [],
        "result": {
            "XXBTZUSD": {
                "altname": "XBTUSD",
                "wsname": "XBT/USD",
                "base": "XXBT",
                "quote": "ZUSD",
                "status": "online",
            }
        },
    }


def _ohlc_rows() -> list[list[object]]:
    start = NOW - timedelta(minutes=15)
    return [
        [int(start.timestamp()), "99", "101", "98", "100", "100", "1", 10],
        [int((start + timedelta(minutes=5)).timestamp()), "100", "102", "99", "101", "101", "2", 11],
        [int((start + timedelta(minutes=10)).timestamp()), "101", "103", "100", "102", "102", "3", 12],
    ]


def test_asset_pairs_accepts_documented_internal_key_and_keeps_canonical_aliases() -> None:
    registry = parse_asset_pairs_payload(_asset_pairs_payload())
    assert registry.normalize("BTC/USD") == "BTC/USD"
    assert registry.normalize("XBT/USD") == "BTC/USD"
    assert registry.normalize("XBTUSD") == "BTC/USD"
    assert registry.normalize("XXBTZUSD") == "BTC/USD"


def test_asset_pairs_invalid_entry_and_symbol_have_bounded_stages() -> None:
    with pytest.raises(KrakenPayloadError) as entry_info:
        parse_asset_pairs_payload({"error": [], "result": {1: {}}})
    assert entry_info.value.stage == "ASSET_PAIRS_ENTRY"

    with pytest.raises(KrakenPayloadError) as symbol_info:
        parse_asset_pairs_payload({
            "error": [],
            "result": {"XXBTZUSD": {"altname": "XBTUSD", "wsname": "XBT/USD", "base": "XETH", "quote": "ZUSD", "status": "online"}},
        })
    assert symbol_info.value.stage == "ASSET_PAIRS_SYMBOL"


@pytest.mark.parametrize("pair_key", ["BTC/USD", "XBT/USD", "XXBTZUSD"])
def test_ohlcv_accepts_display_alias_and_legacy_internal_pair_keys(pair_key: str) -> None:
    candles = _parse_ohlcv_payload(
        {"error": [], "result": {pair_key: _ohlc_rows(), "last": 1}},
        interval_minutes=5,
        expected_symbol="BTC/USD",
        received_at=NOW,
    )
    assert len(candles) == 3
    assert candles[0].close_price == 100


def test_ohlcv_rejects_wrong_display_symbol_with_pair_key_stage() -> None:
    with pytest.raises(KrakenPayloadError) as exc_info:
        _parse_ohlcv_payload(
            {"error": [], "result": {"ETH/USD": _ohlc_rows(), "last": 1}},
            interval_minutes=5,
            expected_symbol="BTC/USD",
            received_at=NOW,
        )
    assert exc_info.value.stage == "OHLC_PAIR_KEY"


@pytest.mark.parametrize(
    ("row_mutator", "expected_stage"),
    [
        (lambda rows: rows.__setitem__(0, [1, 2]), "OHLC_ROW"),
        (lambda rows: rows[0].__setitem__(0, "not-a-timestamp"), "OHLC_TIMESTAMP"),
        (lambda rows: rows[0].__setitem__(4, "not-a-number"), "OHLC_NUMERIC"),
    ],
)
def test_ohlcv_row_timestamp_numeric_failures_have_deterministic_stages(row_mutator, expected_stage: str) -> None:
    rows = _ohlc_rows()
    row_mutator(rows)
    with pytest.raises(KrakenPayloadError) as exc_info:
        _parse_ohlcv_payload(
            {"error": [], "result": {"XXBTZUSD": rows, "last": 1}},
            interval_minutes=5,
            expected_symbol="BTC/USD",
            received_at=NOW,
        )
    assert exc_info.value.stage == expected_stage


def test_normal_spot_registry_then_ohlcv_flow_succeeds_with_internal_keys() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/AssetPairs"):
                return httpx.Response(200, json=_asset_pairs_payload(), request=request)
            if request.url.path.endswith("/OHLC"):
                return httpx.Response(200, json={"error": [], "result": {"XXBTZUSD": _ohlc_rows(), "last": 1}}, request=request)
            raise AssertionError(request.url.path)

        async with httpx.AsyncClient(base_url="https://api.kraken.test", transport=httpx.MockTransport(handler)) as http_client:
            client = KrakenPublicRestClient("https://api.kraken.test", client=http_client)
            registry = await client.fetch_pair_registry()
            symbol = registry.normalize("BTC/USD")
            candles = await client.fetch_ohlcv_history(symbol, interval_minutes=5, since=NOW - timedelta(hours=1))
        assert symbol == "BTC/USD"
        assert len(candles) == 3
    asyncio.run(scenario())


def test_kraken_http_429_5xx_and_permanent_http_classification_is_unchanged() -> None:
    async def classify(status_code: int) -> Exception:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code, text="private body", request=request)
        async with httpx.AsyncClient(base_url="https://api.kraken.test", transport=httpx.MockTransport(handler)) as http_client:
            client = KrakenPublicRestClient("https://api.kraken.test", client=http_client)
            with pytest.raises(Exception) as exc_info:
                await client.fetch_pair_registry()
            return exc_info.value
    assert isinstance(asyncio.run(classify(429)), KrakenRateLimitError)
    assert isinstance(asyncio.run(classify(503)), KrakenServerError)
    assert isinstance(asyncio.run(classify(403)), KrakenHTTPError)
