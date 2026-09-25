import asyncio
import json
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import WebSocketException

from ai_spot_trader.integrations.kraken.errors import KrakenConnectionError, KrakenPayloadError
from ai_spot_trader.integrations.kraken.models import KrakenOhlcUpdate, KrakenTicker
from ai_spot_trader.integrations.kraken.rest import KRAKEN_OHLC_INTERVALS_MINUTES


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


class KrakenOhlcWebSocketClient:
    """Public WebSocket v2 OHLC reader; each generator owns one bounded connection."""

    def __init__(
        self,
        url: str,
        *,
        receive_timeout_seconds: float = 30.0,
        connector: WebSocketConnector = _default_connector,
    ) -> None:
        self._url = url
        self._receive_timeout_seconds = receive_timeout_seconds
        self._connector = connector

    async def iter_ohlc(
        self,
        symbol: str,
        *,
        interval_minutes: int,
    ) -> AsyncGenerator[KrakenOhlcUpdate, None]:
        if interval_minutes not in KRAKEN_OHLC_INTERVALS_MINUTES:
            raise ValueError("unsupported Kraken OHLC interval")
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol cannot be empty")

        connection: WebSocketConnection | None = None
        previous: KrakenOhlcUpdate | None = None
        try:
            connection = await self._connector(self._url)
            await connection.send(_ohlc_subscription_message(normalized_symbol, interval_minutes))
            while True:
                raw_message = await asyncio.wait_for(
                    connection.recv(), timeout=self._receive_timeout_seconds
                )
                received_at = datetime.now(UTC)
                for update in parse_ohlc_websocket_message(
                    raw_message,
                    received_at=received_at,
                ):
                    if update.symbol != normalized_symbol:
                        raise KrakenPayloadError(
                            "Kraken OHLC WebSocket symbol did not match subscription"
                        )
                    if update.interval_minutes != interval_minutes:
                        raise KrakenPayloadError(
                            "Kraken OHLC WebSocket interval did not match subscription"
                        )
                    if previous is not None and update.started_at > previous.started_at:
                        yield KrakenOhlcUpdate(
                            symbol=previous.symbol,
                            interval_minutes=previous.interval_minutes,
                            started_at=previous.started_at,
                            closed_at=previous.closed_at,
                            open_price=previous.open_price,
                            high_price=previous.high_price,
                            low_price=previous.low_price,
                            close_price=previous.close_price,
                            volume=previous.volume,
                            is_final=True,
                            updated_at=max(previous.closed_at, previous.updated_at),
                        )
                    previous = update
                    yield update
        except KrakenPayloadError:
            raise
        except (ConnectionError, OSError, TimeoutError, WebSocketException) as exc:
            raise KrakenConnectionError("Kraken OHLC WebSocket connection failed") from exc
        finally:
            if connection is not None:
                try:
                    await connection.send(
                        _ohlc_unsubscription_message(normalized_symbol, interval_minutes)
                    )
                except Exception:
                    pass
                await connection.close()


def parse_websocket_message(raw_message: str | bytes) -> tuple[KrakenTicker, ...]:
    """Parse relevant Kraken WebSocket v2 messages; heartbeat/system traffic is ignored."""

    payload = _json_object(raw_message)
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


def parse_ohlc_websocket_message(
    raw_message: str | bytes,
    *,
    received_at: datetime | None = None,
) -> tuple[KrakenOhlcUpdate, ...]:
    """Parse Kraken Spot WebSocket v2 OHLC frames using receipt time for causality."""

    observed_at = received_at or datetime.now(UTC)
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise KrakenPayloadError("Kraken OHLC receive time must be timezone-aware")
    observed_at = observed_at.astimezone(UTC)
    payload = _json_object(raw_message)
    channel = payload.get("channel")
    if channel in ("heartbeat", "status"):
        return ()

    method = payload.get("method")
    if method in ("subscribe", "unsubscribe"):
        if payload.get("success") is False:
            raise KrakenPayloadError("Kraken rejected the OHLC subscription request")
        return ()

    if channel != "ohlc":
        return ()
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        raise KrakenPayloadError("Kraken OHLC WebSocket message has no data entries")
    return tuple(_parse_ohlc_entry(entry, updated_at=observed_at) for entry in data)


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
        last_price=_positive_decimal(entry.get("last"), label="ticker last"),
        timestamp=_rfc3339_datetime(timestamp),
    )


def _parse_ohlc_entry(entry: object, *, updated_at: datetime) -> KrakenOhlcUpdate:
    if not isinstance(entry, Mapping):
        raise KrakenPayloadError("Kraken OHLC WebSocket entry must be an object")
    symbol = entry.get("symbol")
    interval = entry.get("interval")
    interval_begin = entry.get("interval_begin")
    if not isinstance(symbol, str) or not symbol.strip():
        raise KrakenPayloadError("Kraken OHLC WebSocket symbol is invalid")
    if isinstance(interval, bool) or not isinstance(interval, int):
        raise KrakenPayloadError("Kraken OHLC WebSocket interval is invalid")
    if interval not in KRAKEN_OHLC_INTERVALS_MINUTES:
        raise KrakenPayloadError("Kraken OHLC WebSocket interval is unsupported")
    if not isinstance(interval_begin, str):
        raise KrakenPayloadError("Kraken OHLC WebSocket interval_begin is invalid")

    started_at = _rfc3339_datetime(interval_begin)
    closed_at = started_at + timedelta(minutes=interval)
    if updated_at < started_at:
        raise KrakenPayloadError("Kraken OHLC update predates its candle")

    open_price = _positive_decimal(entry.get("open"), label="OHLC open")
    high_price = _positive_decimal(entry.get("high"), label="OHLC high")
    low_price = _positive_decimal(entry.get("low"), label="OHLC low")
    close_price = _positive_decimal(entry.get("close"), label="OHLC close")
    volume = _non_negative_decimal(entry.get("volume"), label="OHLC volume")
    if low_price > min(open_price, close_price) or high_price < max(open_price, close_price):
        raise KrakenPayloadError("Kraken OHLC WebSocket price bounds are inconsistent")

    return KrakenOhlcUpdate(
        symbol=symbol.strip().upper(),
        interval_minutes=interval,
        started_at=started_at,
        closed_at=closed_at,
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        close_price=close_price,
        volume=volume,
        is_final=False,
        updated_at=updated_at,
    )


def _json_object(raw_message: str | bytes) -> Mapping[str, Any]:
    try:
        payload = json.loads(raw_message, parse_float=Decimal)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
        raise KrakenPayloadError("Kraken WebSocket returned invalid JSON") from exc
    if not isinstance(payload, Mapping):
        raise KrakenPayloadError("Kraken WebSocket message must be an object")
    return payload


def _positive_decimal(value: Any, *, label: str) -> Decimal:
    number = _decimal(value, label=label)
    if number <= 0:
        raise KrakenPayloadError(f"Kraken {label} must be positive")
    return number


def _non_negative_decimal(value: Any, *, label: str) -> Decimal:
    number = _decimal(value, label=label)
    if number < 0:
        raise KrakenPayloadError(f"Kraken {label} must be non-negative")
    return number


def _decimal(value: Any, *, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise KrakenPayloadError(f"Kraken {label} is invalid")
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise KrakenPayloadError(f"Kraken {label} is invalid") from exc
    if not number.is_finite():
        raise KrakenPayloadError(f"Kraken {label} must be finite")
    return number


def _rfc3339_datetime(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise KrakenPayloadError("Kraken timestamp is not RFC3339") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise KrakenPayloadError("Kraken timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _subscription_message(symbols: Sequence[str]) -> str:
    payload = {
        "method": "subscribe",
        "params": {"channel": "ticker", "symbol": list(symbols), "snapshot": True},
    }
    return json.dumps(payload, separators=(",", ":"))


def _ohlc_subscription_message(symbol: str, interval_minutes: int) -> str:
    payload = {
        "method": "subscribe",
        "params": {
            "channel": "ohlc",
            "symbol": [symbol],
            "interval": interval_minutes,
            "snapshot": True,
        },
    }
    return json.dumps(payload, separators=(",", ":"))


def _ohlc_unsubscription_message(symbol: str, interval_minutes: int) -> str:
    payload = {
        "method": "unsubscribe",
        "params": {
            "channel": "ohlc",
            "symbol": [symbol],
            "interval": interval_minutes,
        },
    }
    return json.dumps(payload, separators=(",", ":"))
