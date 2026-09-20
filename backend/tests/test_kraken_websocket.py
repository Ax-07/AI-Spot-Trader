import asyncio
import json
from datetime import UTC
from decimal import Decimal

import pytest

from ai_spot_trader.integrations.kraken.errors import KrakenConnectionError, KrakenPayloadError
from ai_spot_trader.integrations.kraken.websocket import (
    KrakenTickerWebSocketClient,
    WebSocketConnection,
    parse_websocket_message,
)

TICKER_MESSAGE = json.dumps(
    {
        "channel": "ticker",
        "type": "snapshot",
        "data": [
            {
                "symbol": "BTC/EUR",
                "last": "50000.10",
                "timestamp": "2026-09-20T11:30:00.123456Z",
            }
        ],
    }
)


class FakeWebSocket:
    def __init__(self, messages: list[str | bytes | BaseException]) -> None:
        self.messages = messages
        self.sent: list[str] = []
        self.closed = False

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def recv(self) -> str | bytes:
        message = self.messages.pop(0)
        if isinstance(message, BaseException):
            raise message
        return message

    async def close(self) -> None:
        self.closed = True


def test_ticker_parser_accepts_string_number_and_normalizes_timestamp() -> None:
    (ticker,) = parse_websocket_message(TICKER_MESSAGE)

    assert ticker.symbol == "BTC/EUR"
    assert ticker.last_price == Decimal("50000.10")
    assert ticker.timestamp.tzinfo is UTC


def test_heartbeat_and_irrelevant_messages_are_ignored() -> None:
    assert parse_websocket_message('{"channel":"heartbeat"}') == ()
    assert parse_websocket_message('{"channel":"status","type":"update","data":[]}') == ()
    assert (
        parse_websocket_message(
            '{"method":"subscribe","result":{"channel":"ticker","symbol":"BTC/EUR"},"success":true}'
        )
        == ()
    )


@pytest.mark.parametrize("last_price", ["0", "-1", "not-a-number"])
def test_non_positive_or_invalid_last_price_is_rejected(last_price: str) -> None:
    payload = json.dumps(
        {
            "channel": "ticker",
            "type": "snapshot",
            "data": [
                {
                    "symbol": "BTC/EUR",
                    "last": last_price,
                    "timestamp": "2026-09-20T11:30:00Z",
                }
            ],
        }
    )
    with pytest.raises(KrakenPayloadError):
        parse_websocket_message(payload)


def test_malformed_websocket_message_is_rejected() -> None:
    with pytest.raises(KrakenPayloadError, match="invalid JSON"):
        parse_websocket_message("not-json")


def test_failed_subscription_ack_is_rejected() -> None:
    with pytest.raises(KrakenPayloadError, match="rejected"):
        parse_websocket_message('{"method":"subscribe","success":false,"error":"bad symbol"}')


def test_first_ticker_subscribes_without_auth_and_closes_cleanly() -> None:
    websocket = FakeWebSocket(
        [
            (
                '{"method":"subscribe","result":{"channel":"ticker",'
                '"symbol":"BTC/EUR"},"success":true}'
            ),
            '{"channel":"heartbeat"}',
            TICKER_MESSAGE,
        ]
    )

    async def connector(url: str) -> WebSocketConnection:
        assert url == "wss://ws.kraken.test/v2"
        return websocket

    client = KrakenTickerWebSocketClient(
        "wss://ws.kraken.test/v2",
        connector=connector,
        reconnect_delay_seconds=0,
    )
    ticker = asyncio.run(client.first_ticker("BTC/EUR"))

    assert ticker.last_price == Decimal("50000.10")
    assert websocket.closed
    assert len(websocket.sent) == 1
    subscribe = json.loads(websocket.sent[0])
    assert subscribe == {
        "method": "subscribe",
        "params": {"channel": "ticker", "symbol": ["BTC/EUR"], "snapshot": True},
    }
    assert "token" not in websocket.sent[0].lower()
    assert "api" not in websocket.sent[0].lower()


def test_websocket_reconnects_once_then_returns_ticker() -> None:
    first = FakeWebSocket([ConnectionError("disconnect")])
    second = FakeWebSocket([TICKER_MESSAGE])
    sockets = [first, second]
    sleeps: list[float] = []

    async def connector(url: str) -> WebSocketConnection:
        return sockets.pop(0)

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    client = KrakenTickerWebSocketClient(
        "wss://ws.kraken.test/v2",
        max_reconnect_attempts=1,
        reconnect_delay_seconds=0.25,
        connector=connector,
        sleep=fake_sleep,
    )
    ticker = asyncio.run(client.first_ticker("BTC/EUR"))

    assert ticker.symbol == "BTC/EUR"
    assert first.closed and second.closed
    assert sleeps == [0.25]


def test_websocket_retry_is_bounded() -> None:
    sockets = [
        FakeWebSocket([ConnectionError("first")]),
        FakeWebSocket([ConnectionError("second")]),
    ]

    async def connector(url: str) -> WebSocketConnection:
        return sockets.pop(0)

    client = KrakenTickerWebSocketClient(
        "wss://ws.kraken.test/v2",
        max_reconnect_attempts=1,
        reconnect_delay_seconds=0,
        connector=connector,
    )

    with pytest.raises(KrakenConnectionError, match="bounded retries"):
        asyncio.run(client.first_ticker("BTC/EUR"))
