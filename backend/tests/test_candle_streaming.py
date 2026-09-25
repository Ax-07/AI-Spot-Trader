import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_spot_trader.api.routes.candles import router as candles_router
from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.integrations.kraken.errors import KrakenPayloadError
from ai_spot_trader.integrations.kraken.rest import _parse_ohlcv_payload
from ai_spot_trader.integrations.kraken.websocket import (
    KrakenOhlcWebSocketClient,
    WebSocketConnection,
    parse_ohlc_websocket_message,
)
from ai_spot_trader.market.candles import (
    Candle,
    CandleCache,
    CandleCausalityError,
    CandleKey,
    CandleStreamService,
    CandleTimeframe,
)

NOW = datetime(2026, 9, 25, 10, 0, tzinfo=UTC)
KEY = CandleKey(symbol="BTC/USD", market_type=MarketType.SPOT, timeframe=CandleTimeframe.M1)


def candle(
    minute: int,
    *,
    close: str = "100",
    final: bool = True,
    market_type: MarketType = MarketType.SPOT,
    symbol: str = "BTC/USD",
    timeframe: CandleTimeframe = CandleTimeframe.M1,
) -> Candle:
    opened = NOW + timedelta(minutes=minute)
    duration = timeframe.duration
    closed = opened + duration
    value = Decimal(close)
    return Candle(
        symbol=symbol,
        market_type=market_type,
        timeframe=timeframe,
        open_time=opened,
        close_time=closed,
        open=value,
        high=value + 2,
        low=value - 2,
        close=value,
        volume=Decimal("3"),
        is_final=final,
        updated_at=closed if final else opened + timedelta(seconds=30),
    )


class StaticProvider:
    def __init__(self, history: tuple[Candle, ...], stream_items: tuple[Candle, ...] = ()) -> None:
        self.history_rows = history
        self.stream_items = stream_items
        self.fetch_count = 0
        self.stream_count = 0
        self.closed = False
        self.block = asyncio.Event()

    async def fetch_history(self, key: CandleKey, *, limit: int, before: datetime):
        self.fetch_count += 1
        return self.history_rows[-limit:]

    async def stream(self, key: CandleKey):
        self.stream_count += 1
        for item in self.stream_items:
            yield item
        await self.block.wait()

    async def aclose(self) -> None:
        self.closed = True
        self.block.set()




class ErrorProvider(StaticProvider):
    async def stream(self, key: CandleKey):
        self.stream_count += 1
        raise ConnectionError("simulated persistent disconnect")
        if False:
            yield candle(0)


class FakeWebSocket:
    def __init__(self, messages: list[str | bytes | BaseException]) -> None:
        self.messages = messages
        self.sent: list[str] = []
        self.closed = False

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def recv(self) -> str | bytes:
        item = self.messages.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    async def close(self) -> None:
        self.closed = True


class ReconnectingProvider:
    def __init__(self) -> None:
        self.fetch_count = 0
        self.stream_count = 0
        self.closed = False
        self.block = asyncio.Event()

    async def fetch_history(self, key: CandleKey, *, limit: int, before: datetime):
        self.fetch_count += 1
        if self.fetch_count < 3:
            return (candle(-3),)
        return (candle(-3), candle(-2))

    async def stream(self, key: CandleKey):
        self.stream_count += 1
        if self.stream_count == 1:
            raise ConnectionError("simulated disconnect")
        await self.block.wait()
        if False:
            yield candle(0)

    async def aclose(self) -> None:
        self.closed = True
        self.block.set()


def test_spot_rest_ohlcv_parser_keeps_trailing_candle_explicit() -> None:
    payload = {
        "error": [],
        "result": {
            "BTC/USD": [
                [
                    int((NOW - timedelta(minutes=2)).timestamp()),
                    "99", "102", "98", "100", "100", "5", 4,
                ],
                [
                    int((NOW - timedelta(minutes=1)).timestamp()),
                    "100", "103", "99", "101", "101", "7", 5,
                ],
            ],
            "last": int(NOW.timestamp()),
        },
    }
    rows = _parse_ohlcv_payload(
        payload,
        interval_minutes=1,
        expected_symbol="BTC/USD",
        received_at=NOW - timedelta(seconds=10),
    )
    assert [row.is_final for row in rows] == [True, False]
    assert rows[0].open_price == Decimal("99")
    assert rows[0].volume == Decimal("5")
    assert rows[1].close_price == Decimal("101")


def test_spot_rest_ohlcv_parser_rejects_non_chronological_rows() -> None:
    timestamp = int((NOW - timedelta(minutes=2)).timestamp())
    payload = {
        "error": [],
        "result": {
            "BTC/USD": [
                [timestamp, "99", "102", "98", "100", "100", "5", 4],
                [timestamp, "100", "103", "99", "101", "101", "7", 5],
            ]
        },
    }
    with pytest.raises(KrakenPayloadError, match="strictly chronological"):
        _parse_ohlcv_payload(
            payload,
            interval_minutes=1,
            expected_symbol="BTC/USD",
            received_at=NOW,
        )


def test_spot_websocket_ohlc_parser_normalizes_full_update() -> None:
    message = json.dumps(
        {
            "channel": "ohlc",
            "type": "update",
            "data": [
                {
                    "symbol": "BTC/USD",
                    "open": "100",
                    "high": "105",
                    "low": "99",
                    "close": "104",
                    "volume": "12.5",
                    "interval": 1,
                    "interval_begin": "2026-09-25T09:59:00Z",
                }
            ],
        }
    )
    (update,) = parse_ohlc_websocket_message(
        message,
        received_at=NOW - timedelta(seconds=5),
    )
    assert update.symbol == "BTC/USD"
    assert update.high_price == Decimal("105")
    assert update.volume == Decimal("12.5")
    assert update.is_final is False
    assert update.updated_at == NOW - timedelta(seconds=5)


def test_cache_deduplicates_and_replaces_current_candle() -> None:
    cache = CandleCache(max_depth=10)
    current = candle(-1, close="100", final=False)
    newer = current.model_copy(
        update={
            "high": Decimal("110"),
            "close": Decimal("108"),
            "updated_at": current.updated_at + timedelta(seconds=10),
        }
    )
    assert cache.upsert(current, now=NOW)
    assert not cache.upsert(current, now=NOW)
    assert cache.upsert(newer, now=NOW)
    assert cache.history(KEY) == (newer,)


def test_cache_accepts_new_candle_and_preserves_chronological_order() -> None:
    cache = CandleCache(max_depth=10)
    cache.upsert(candle(-1, final=False), now=NOW)
    cache.upsert(candle(-3), now=NOW)
    cache.upsert(candle(-2), now=NOW)
    assert [item.open_time for item in cache.history(KEY)] == [
        NOW - timedelta(minutes=3),
        NOW - timedelta(minutes=2),
        NOW - timedelta(minutes=1),
    ]


def test_cache_depth_is_bounded() -> None:
    cache = CandleCache(max_depth=2)
    for minute in (-4, -3, -2):
        cache.upsert(candle(minute), now=NOW)
    assert [item.open_time for item in cache.history(KEY)] == [
        NOW - timedelta(minutes=3),
        NOW - timedelta(minutes=2),
    ]


def test_cache_separates_symbol_market_type_and_timeframe() -> None:
    cache = CandleCache(max_depth=10)
    spot = candle(-2)
    perp = candle(-2, market_type=MarketType.PERPETUAL)
    eth = candle(-2, symbol="ETH/USD")
    h1 = candle(-120, timeframe=CandleTimeframe.H1)
    for item in (spot, perp, eth, h1):
        cache.upsert(item, now=NOW)
    assert len(cache.history(spot.key)) == 1
    assert len(cache.history(perp.key)) == 1
    assert len(cache.history(eth.key)) == 1
    assert len(cache.history(h1.key)) == 1


def test_cache_rejects_future_open_time_no_lookahead() -> None:
    cache = CandleCache(max_depth=10)
    with pytest.raises(CandleCausalityError, match="future"):
        cache.upsert(candle(1, final=False), now=NOW)


def test_initial_history_can_be_incomplete_without_invention() -> None:
    async def scenario() -> None:
        provider = StaticProvider((candle(-4), candle(-2)))
        service = CandleStreamService(provider, reconnect_delay_seconds=0)
        rows = await service.history(KEY, limit=1000)
        assert [item.open_time for item in rows] == [
            NOW - timedelta(minutes=4),
            NOW - timedelta(minutes=2),
        ]
        assert provider.fetch_count == 1
        await service.aclose()

    asyncio.run(scenario())


def test_reconnect_backfill_publishes_missing_real_candle_without_duplication() -> None:
    async def scenario() -> None:
        provider = ReconnectingProvider()
        service = CandleStreamService(provider, reconnect_delay_seconds=0)
        stream = service.subscribe(KEY, history_limit=10)
        received = await asyncio.wait_for(anext(stream), timeout=1)
        assert received.open_time == NOW - timedelta(minutes=2)
        assert provider.stream_count >= 1
        history = service.cache.history(KEY)
        assert [item.open_time for item in history] == [
            NOW - timedelta(minutes=3),
            NOW - timedelta(minutes=2),
        ]
        await stream.aclose()
        await service.aclose()
        assert provider.closed

    asyncio.run(scenario())


def test_multiple_consumers_share_one_backend_stream() -> None:
    async def scenario() -> None:
        update = candle(-1, close="105", final=False)
        provider = StaticProvider((candle(-2),), (update,))
        service = CandleStreamService(provider, reconnect_delay_seconds=0)
        first = service.subscribe(KEY, history_limit=10)
        second = service.subscribe(KEY, history_limit=10)
        one, two = await asyncio.gather(
            asyncio.wait_for(anext(first), timeout=1),
            asyncio.wait_for(anext(second), timeout=1),
        )
        assert one == update == two
        assert provider.stream_count == 1
        await first.aclose()
        await second.aclose()
        await service.aclose()

    asyncio.run(scenario())


def test_service_status_reports_staleness_and_cleanup() -> None:
    async def scenario() -> None:
        provider = StaticProvider((candle(-2),))
        service = CandleStreamService(
            provider,
            stale_after=timedelta(seconds=30),
            reconnect_delay_seconds=0,
        )
        await service.history(KEY, limit=10)
        status = service.status(KEY, now=NOW + timedelta(minutes=1))
        assert status.stale is True
        await service.aclose()
        assert provider.closed

    asyncio.run(scenario())


def test_history_api_returns_canonical_contract() -> None:
    provider = StaticProvider((candle(-2), candle(-1, final=False)))
    service = CandleStreamService(provider, reconnect_delay_seconds=0)
    app = FastAPI()
    app.state.candle_service = service
    app.include_router(candles_router)
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/markets/candles",
            params={
                "symbol": "BTC/USD",
                "market_type": "SPOT",
                "timeframe": "1m",
                "limit": 10,
            },
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["key"] == {
        "symbol": "BTC/USD",
        "market_type": "SPOT",
        "timeframe": "1m",
    }
    assert len(payload["candles"]) == 2
    asyncio.run(service.aclose())


def test_cockpit_websocket_gets_snapshot_then_live_update() -> None:
    live = candle(-1, close="106", final=False)
    provider = StaticProvider((candle(-2),), (live,))
    service = CandleStreamService(provider, reconnect_delay_seconds=0)
    app = FastAPI()
    app.state.candle_service = service
    app.include_router(candles_router)
    with TestClient(app) as client:
        with client.websocket_connect(
            "/api/v1/markets/candles/stream?symbol=BTC%2FUSD&market_type=SPOT&timeframe=1m&limit=10"
        ) as websocket:
            snapshot = websocket.receive_json()
            update = websocket.receive_json()
    assert snapshot["type"] == "snapshot"
    assert len(snapshot["candles"]) == 1
    assert update["type"] == "candle"
    assert update["candle"]["close"] == "106"
    asyncio.run(service.aclose())


def test_futures_chart_parser_supports_1000_target_shape_without_future_rows() -> None:
    from ai_spot_trader.integrations.kraken.candles import _parse_futures_candles

    key = CandleKey(
        symbol="BTC/USD",
        market_type=MarketType.PERPETUAL,
        timeframe=CandleTimeframe.M5,
    )
    opened = NOW - timedelta(minutes=10)
    payload = {
        "candles": [
            {
                "time": int(opened.timestamp() * 1000),
                "open": "100",
                "high": "104",
                "low": "99",
                "close": "103",
                "volume": "7.5",
            },
            {
                "time": int((opened + timedelta(minutes=5)).timestamp() * 1000),
                "open": "103",
                "high": "106",
                "low": "102",
                "close": "105",
                "volume": "8",
            },
        ]
    }
    rows = _parse_futures_candles(payload, key=key, before=NOW, limit=1000)
    assert len(rows) == 2
    assert rows[0].is_final is True
    assert rows[1].close == Decimal("105")


def test_futures_trade_parser_accepts_public_trade_feed_shape() -> None:
    from ai_spot_trader.integrations.kraken.candles import _parse_futures_trade

    trade = _parse_futures_trade(
        json.dumps(
            {
                "feed": "trade",
                "product_id": "PF_XBTUSD",
                "time": int((NOW - timedelta(seconds=2)).timestamp() * 1000),
                "price": "101.5",
                "qty": "2.25",
            }
        ),
        expected_product="PF_XBTUSD",
    )
    assert trade is not None
    traded_at, price, quantity = trade
    assert traded_at == NOW - timedelta(seconds=2)
    assert price == Decimal("101.5")
    assert quantity == Decimal("2.25")


def test_spot_ohlc_websocket_unsubscribes_and_closes_on_consumer_cleanup() -> None:
    message = json.dumps(
        {
            "channel": "ohlc",
            "type": "update",
            "data": [
                {
                    "symbol": "BTC/USD",
                    "open": "100",
                    "high": "102",
                    "low": "99",
                    "close": "101",
                    "volume": "4",
                    "interval": 1,
                    "interval_begin": "2026-09-25T09:59:00Z",
                    "timestamp": "2026-09-25T09:59:30Z",
                }
            ],
        }
    )
    socket = FakeWebSocket([message])

    async def connector(url: str) -> WebSocketConnection:
        assert url == "wss://ws.kraken.test/v2"
        return socket

    async def scenario() -> None:
        client = KrakenOhlcWebSocketClient(
            "wss://ws.kraken.test/v2",
            connector=connector,
        )
        stream = client.iter_ohlc("BTC/USD", interval_minutes=1)
        update = await anext(stream)
        assert update.close_price == Decimal("101")
        await stream.aclose()

    asyncio.run(scenario())
    assert socket.closed is True
    assert len(socket.sent) == 2
    subscribe = json.loads(socket.sent[0])
    unsubscribe = json.loads(socket.sent[1])
    assert subscribe["method"] == "subscribe"
    assert unsubscribe["method"] == "unsubscribe"
    assert subscribe["params"]["channel"] == unsubscribe["params"]["channel"] == "ohlc"
    assert subscribe["params"]["symbol"] == unsubscribe["params"]["symbol"] == ["BTC/USD"]


def test_service_status_exposes_network_error_while_reconnect_is_pending() -> None:
    async def scenario() -> None:
        provider = ErrorProvider((candle(-2),))
        service = CandleStreamService(provider, reconnect_delay_seconds=0.5)
        stream = service.subscribe(KEY, history_limit=10)
        pending = asyncio.create_task(anext(stream))
        for _ in range(50):
            status = service.status(KEY)
            if status.last_error == "ConnectionError":
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("stream error was not exposed in status")
        assert status.connected is False
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        await stream.aclose()
        await service.aclose()

    asyncio.run(scenario())
