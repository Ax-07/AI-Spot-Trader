from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from ai_spot_trader.integrations.kraken.errors import KrakenPayloadError
from ai_spot_trader.integrations.kraken.microstructure import (
    KrakenSpotMicrostructureProvider,
    _parse_order_book_payload,
    _parse_recent_trades_payload,
)
from ai_spot_trader.market.microstructure import TradeSide

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def test_order_book_parser_accepts_unordered_levels_and_preserves_bounds() -> None:
    payload = {
        "error": [],
        "result": {
            "BTC/USD": {
                "bids": [["99", "1", 1_700_000_000], ["100", "2", 1_700_000_001]],
                "asks": [["102", "1", 1_700_000_002], ["101", "3", 1_700_000_003]],
            }
        },
    }
    snapshot = _parse_order_book_payload(
        payload,
        expected_symbol="BTC/USD",
        received_at=NOW,
        limit=100,
    )
    assert len(snapshot.bids) == 2
    assert snapshot.bids[0].price == Decimal("99")
    assert snapshot.asks[1].price == Decimal("101")


def test_order_book_parser_rejects_negative_volume() -> None:
    payload = {
        "error": [],
        "result": {"BTC/USD": {"bids": [["100", "-1", 1]], "asks": [["101", "1", 1]]}},
    }
    with pytest.raises(KrakenPayloadError):
        _parse_order_book_payload(
            payload,
            expected_symbol="BTC/USD",
            received_at=NOW,
            limit=100,
        )


def test_order_book_parser_rejects_more_levels_than_requested() -> None:
    payload = {
        "error": [],
        "result": {
            "BTC/USD": {
                "bids": [["100", "1", 1], ["99", "1", 1]],
                "asks": [["101", "1", 1]],
            }
        },
    }
    with pytest.raises(KrakenPayloadError):
        _parse_order_book_payload(
            payload,
            expected_symbol="BTC/USD",
            received_at=NOW,
            limit=1,
        )


def test_recent_trades_parser_maps_only_known_provider_side_markers() -> None:
    payload = {
        "error": [],
        "result": {
            "BTC/USD": [
                ["100", "1", 1_700_000_000.1, "b", "m", "", 1],
                ["101", "2", 1_700_000_001.1, "s", "l", "", 2],
                ["102", "3", 1_700_000_002.1, "?", "m", "", 3],
            ],
            "last": "1700000003000000000",
        },
    }
    snapshot = _parse_recent_trades_payload(
        payload,
        expected_symbol="BTC/USD",
        received_at=NOW,
        limit=1000,
    )
    assert [item.side for item in snapshot.trades] == [TradeSide.BUY, TradeSide.SELL, None]
    assert [item.trade_id for item in snapshot.trades] == [1, 2, 3]


def test_recent_trades_parser_rejects_wrong_pair() -> None:
    payload = {"error": [], "result": {"ETH/USD": [], "last": "1"}}
    with pytest.raises(KrakenPayloadError):
        _parse_recent_trades_payload(
            payload,
            expected_symbol="BTC/USD",
            received_at=NOW,
            limit=1000,
        )


def test_provider_uses_public_depth_and_trades_endpoints_with_bounded_counts() -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, request.url.query.decode()))
        if request.url.path.endswith("/Depth"):
            payload = {
                "error": [],
                "result": {"BTC/USD": {"bids": [["100", "1", 1]], "asks": [["101", "1", 1]]}},
            }
        else:
            payload = {
                "error": [],
                "result": {"BTC/USD": [["100", "1", 1_700_000_000.0, "b", "m", "", 1]], "last": "1"},
            }
        return httpx.Response(200, text=json.dumps(payload), request=request)

    async def scenario() -> tuple[object, object]:
        client = httpx.AsyncClient(base_url="https://kraken.test", transport=httpx.MockTransport(handler))
        provider = KrakenSpotMicrostructureProvider("https://kraken.test", client=client)
        try:
            book = await provider.fetch_order_book("BTC/USD", limit=50)
            trades = await provider.fetch_recent_trades("BTC/USD", limit=200)
            return book, trades
        finally:
            await client.aclose()

    book, trades = asyncio.run(scenario())
    assert book.bids[0].price == Decimal("100")
    assert trades.trades[0].side is TradeSide.BUY
    assert any(path.endswith("/Depth") and "count=50" in query for path, query in seen)
    assert any(path.endswith("/Trades") and "count=200" in query for path, query in seen)
    assert all("assetVersion=1" in query for _path, query in seen)
