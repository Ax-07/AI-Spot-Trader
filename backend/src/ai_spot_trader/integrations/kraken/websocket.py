import asyncio
import json
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import WebSocketException

from ai_spot_trader.integrations.kraken.errors import KrakenConnectionError, KrakenPayloadError
from ai_spot_trader.integrations.kraken.models import KrakenTicker


class WebSocketConnection(Protocol):
    async def send(self, message: str) -> None: ...

    async def recv(self) -> str | bytes: ...

    async def close(self) -> None: ...


WebSocketConnector = Callable[[str], Awaitable[WebSocketConnection]]
Sleep = Callable[[float], Awaitable[None]]


async def _default_connector(url: str) -> ClientConnection:
    return await connect(url)


class KrakenTickerWebSocketClient:
    """Public WebSocket v2 ticker reader with bounded reconnect and clean close."""

    def __init__(
        self,
        url: str,
        *,
        max_reconnect_attempts: int = 2,
        reconnect_delay_seconds: float = 1.0,
        receive_timeout_seconds: float = 15.0,
        connector: WebSocketConnector = _default_connector,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._url = url
        self._max_reconnect_attempts = max_reconnect_attempts
        self._reconnect_delay_seconds = reconnect_delay_seconds
        self._receive_timeout_seconds = receive_timeout_seconds
        self._connector = connector
        self._sleep = sleep

    async def first_ticker(self, symbol: str) -> KrakenTicker:
        stream = self.iter_tickers((symbol,))
        try:
            return await anext(stream)
        finally:
            await stream.aclose()

    async def iter_tickers(self, symbols: Sequence[str]) -> AsyncGenerator[KrakenTicker, None]:
        if not symbols:
            raise ValueError("at least one symbol is required")

        reconnects = 0
        while True:
            connection: WebSocketConnection | None = None
            try:
                connection = await self._connector(self._url)
                await connection.send(_subscription_message(symbols))
                while True:
                    raw_message = await asyncio.wait_for(
                        connection.recv(), timeout=self._receive_timeout_seconds
                    )
                    for ticker in parse_websocket_message(raw_message):
                        yield ticker
            except KrakenPayloadError:
                raise
            except (ConnectionError, OSError, TimeoutError, WebSocketException) as exc:
                if reconnects >= self._max_reconnect_attempts:
                    raise KrakenConnectionError(
                        "Kraken WebSocket connection failed after bounded retries"
                    ) from exc
                reconnects += 1
                if self._reconnect_delay_seconds:
                    await self._sleep(self._reconnect_delay_seconds)
            finally:
                if connection is not None:
                    await connection.close()


def parse_websocket_message(raw_message: str | bytes) -> tuple[KrakenTicker, ...]:
    """Parse relevant Kraken WebSocket v2 messages; heartbeat/system traffic is ignored."""

    try:
        payload = json.loads(raw_message, parse_float=Decimal)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
        raise KrakenPayloadError("Kraken WebSocket returned invalid JSON") from exc

    if not isinstance(payload, Mapping):
        raise KrakenPayloadError("Kraken WebSocket message must be an object")

    channel = payload.get("channel")
    if channel == "heartbeat":
        return ()

    method = payload.get("method")
    if method == "subscribe":
        if payload.get("success") is False:
            raise KrakenPayloadError("Kraken rejected the ticker subscription")
        return ()

    if channel != "ticker":
        return ()

    data = payload.get("data")
    if not isinstance(data, list) or not data:
        raise KrakenPayloadError("Kraken ticker message has no data entries")

    return tuple(_parse_ticker_entry(entry) for entry in data)


def _parse_ticker_entry(entry: object) -> KrakenTicker:
    if not isinstance(entry, Mapping):
        raise KrakenPayloadError("Kraken ticker entry must be an object")

    symbol = entry.get("symbol")
    timestamp = entry.get("timestamp")
    if not isinstance(symbol, str) or not symbol.strip():
        raise KrakenPayloadError("Kraken ticker has an invalid symbol")
    if not isinstance(timestamp, str):
        raise KrakenPayloadError("Kraken ticker has an invalid timestamp")

    return KrakenTicker(
        symbol=symbol.strip().upper(),
        last_price=_positive_decimal(entry.get("last")),
        timestamp=_rfc3339_datetime(timestamp),
    )


def _positive_decimal(value: Any) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise KrakenPayloadError("Kraken ticker last price is invalid")
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise KrakenPayloadError("Kraken ticker last price is invalid") from exc
    if not number.is_finite() or number <= 0:
        raise KrakenPayloadError("Kraken ticker last price must be positive")
    return number


def _rfc3339_datetime(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise KrakenPayloadError("Kraken ticker timestamp is not RFC3339") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise KrakenPayloadError("Kraken ticker timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _subscription_message(symbols: Sequence[str]) -> str:
    # Kraken Spot WebSocket v2 ticker: subscribe + params.channel/symbol/snapshot.
    payload = {
        "method": "subscribe",
        "params": {"channel": "ticker", "symbol": list(symbols), "snapshot": True},
    }
    return json.dumps(payload, separators=(",", ":"))
