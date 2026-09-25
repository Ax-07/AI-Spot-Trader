from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

import httpx
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import WebSocketException

from ai_spot_trader.domain.enums import DerivativeContractKind, MarketType
from ai_spot_trader.domain.models import DerivativeInstrument
from ai_spot_trader.integrations.kraken.derivatives import KrakenDerivativesPublicClient
from ai_spot_trader.integrations.kraken.errors import (
    KrakenConnectionError,
    KrakenPayloadError,
    UnknownKrakenSymbolError,
)
from ai_spot_trader.integrations.kraken.rest import (
    KRAKEN_SPOT_OHLC_MAX_ROWS,
    KrakenPublicRestClient,
)
from ai_spot_trader.integrations.kraken.websocket import KrakenOhlcWebSocketClient
from ai_spot_trader.market.candles import Candle, CandleKey, floor_time

KRAKEN_FUTURES_WS_URL = "wss://futures.kraken.com/ws/v1"
KRAKEN_FUTURES_HISTORY_TARGET_ROWS = 1000


class FuturesWebSocketConnection(Protocol):
    async def send(self, message: str) -> None: ...

    async def recv(self) -> str | bytes: ...

    async def close(self) -> None: ...


class KrakenCandleProvider:
    """Canonical Kraken candle adapter shared by the cockpit backend hub.

    SPOT reuses the existing Spot pair registry/REST transport and WebSocket v2 endpoint.
    PERPETUAL reuses the existing derivatives instrument catalogue, the public charts endpoint,
    and aggregates the documented public Futures trade feed into candles. No strategy is run here.
    """

    def __init__(
        self,
        *,
        spot_rest_url: str,
        spot_ws_url: str,
        derivatives_rest_url: str,
        timeout_seconds: float = 10.0,
        ws_receive_timeout_seconds: float = 30.0,
        futures_ws_url: str = KRAKEN_FUTURES_WS_URL,
    ) -> None:
        self._spot_rest = KrakenPublicRestClient(
            spot_rest_url,
            timeout_seconds=timeout_seconds,
        )
        self._spot_ws = KrakenOhlcWebSocketClient(
            spot_ws_url,
            receive_timeout_seconds=ws_receive_timeout_seconds,
        )
        self._derivatives = KrakenDerivativesPublicClient(
            derivatives_rest_url,
            timeout_seconds=timeout_seconds,
        )
        charts_base_url = str(
            httpx.URL(derivatives_rest_url).copy_with(
                path="/api/charts/v1/", query=None, fragment=None
            )
        )
        self._charts = httpx.AsyncClient(
            base_url=charts_base_url,
            timeout=timeout_seconds,
        )
        self._futures_ws_url = futures_ws_url
        self._ws_receive_timeout_seconds = ws_receive_timeout_seconds
        self._instrument_cache: dict[str, DerivativeInstrument] | None = None

    async def fetch_history(
        self,
        key: CandleKey,
        *,
        limit: int,
        before: datetime,
    ) -> tuple[Candle, ...]:
        if before.tzinfo is None or before.utcoffset() is None:
            raise ValueError("candle history before must be timezone-aware")
        before = before.astimezone(UTC)
        if key.market_type is MarketType.SPOT:
            return await self._spot_history(key, limit=limit, before=before)
        if key.market_type is MarketType.PERPETUAL:
            return await self._perpetual_history(key, limit=limit, before=before)
        raise ValueError("Kraken candle provider supports SPOT/PERPETUAL only")

    def stream(self, key: CandleKey) -> AsyncIterator[Candle]:
        if key.market_type is MarketType.SPOT:
            return self._stream_spot(key)
        if key.market_type is MarketType.PERPETUAL:
            return self._stream_perpetual(key)
        raise ValueError("Kraken candle provider supports SPOT/PERPETUAL only")

    async def aclose(self) -> None:
        await self._spot_rest.aclose()
        await self._derivatives.aclose()
        await self._charts.aclose()

    async def _spot_history(
        self,
        key: CandleKey,
        *,
        limit: int,
        before: datetime,
    ) -> tuple[Candle, ...]:
        registry = await self._spot_rest.fetch_pair_registry()
        symbol = registry.normalize(key.symbol)
        provider_limit = min(limit, KRAKEN_SPOT_OHLC_MAX_ROWS)
        since = before - (key.timeframe.duration * (provider_limit + 2))
        rows = await self._spot_rest.fetch_ohlcv_history(
            symbol,
            interval_minutes=key.timeframe.spot_interval_minutes,
            since=since,
        )
        candles = tuple(
            Candle(
                symbol=key.symbol,
                market_type=key.market_type,
                timeframe=key.timeframe,
                open_time=row.started_at,
                close_time=row.closed_at,
                open=row.open_price,
                high=row.high_price,
                low=row.low_price,
                close=row.close_price,
                volume=row.volume,
                is_final=row.is_final,
                updated_at=row.updated_at,
            )
            for row in rows
        )
        return candles[-provider_limit:]

    async def _perpetual_history(
        self,
        key: CandleKey,
        *,
        limit: int,
        before: datetime,
    ) -> tuple[Candle, ...]:
        instrument = await self._instrument(key.symbol)
        requested = min(limit, KRAKEN_FUTURES_HISTORY_TARGET_ROWS)
        try:
            response = await self._charts.get(
                f"mark/{instrument.venue_symbol}/{key.timeframe.futures_resolution}",
                params={"to": int(before.timestamp()), "count": requested},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise KrakenConnectionError("Kraken Futures chart candles request failed") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise KrakenPayloadError("Kraken Futures chart candles returned invalid JSON") from exc
        return _parse_futures_candles(payload, key=key, before=before, limit=requested)

    async def _instrument(self, canonical_symbol: str) -> DerivativeInstrument:
        if self._instrument_cache is None:
            instruments = await self._derivatives.fetch_instruments()
            mapping: dict[str, DerivativeInstrument] = {}
            for instrument in instruments:
                if (
                    instrument.market_type is not MarketType.PERPETUAL
                    or instrument.contract_kind is not DerivativeContractKind.LINEAR
                ):
                    continue
                current = mapping.get(instrument.symbol)
                if current is None or instrument.venue_symbol < current.venue_symbol:
                    mapping[instrument.symbol] = instrument
            self._instrument_cache = mapping
        instrument = self._instrument_cache.get(canonical_symbol)
        if instrument is None:
            raise UnknownKrakenSymbolError(
                f"no linear Kraken PERPETUAL mapped to {canonical_symbol}"
            )
        return instrument

    async def _stream_spot(self, key: CandleKey) -> AsyncIterator[Candle]:
        async for update in self._spot_ws.iter_ohlc(
            key.symbol,
            interval_minutes=key.timeframe.spot_interval_minutes,
        ):
            yield Candle(
                symbol=key.symbol,
                market_type=key.market_type,
                timeframe=key.timeframe,
                open_time=update.started_at,
                close_time=update.closed_at,
                open=update.open_price,
                high=update.high_price,
                low=update.low_price,
                close=update.close_price,
                volume=update.volume,
                is_final=update.is_final,
                updated_at=update.updated_at,
            )

    async def _stream_perpetual(self, key: CandleKey) -> AsyncIterator[Candle]:
        instrument = await self._instrument(key.symbol)
        connection: FuturesWebSocketConnection | None = None
        current: Candle | None = None
        try:
            connection = await connect(self._futures_ws_url)
            await connection.send(
                json.dumps(
                    {
                        "event": "subscribe",
                        "feed": "trade",
                        "product_ids": [instrument.venue_symbol],
                    },
                    separators=(",", ":"),
                )
            )
            while True:
                raw = await asyncio.wait_for(
                    connection.recv(), timeout=self._ws_receive_timeout_seconds
                )
                trade = _parse_futures_trade(raw, expected_product=instrument.venue_symbol)
                if trade is None:
                    continue
                traded_at, price, quantity = trade
                started_at = floor_time(traded_at, key.timeframe)
                close_time = started_at + key.timeframe.duration
                if current is None or started_at > current.open_time:
                    if current is not None:
                        yield current.model_copy(
                            update={
                                "is_final": True,
                                "updated_at": max(current.close_time, current.updated_at),
                            }
                        )
                    current = Candle(
                        symbol=key.symbol,
                        market_type=key.market_type,
                        timeframe=key.timeframe,
                        open_time=started_at,
                        close_time=close_time,
                        open=price,
                        high=price,
                        low=price,
                        close=price,
                        volume=quantity,
                        is_final=False,
                        updated_at=traded_at,
                    )
                elif started_at == current.open_time:
                    current = current.model_copy(
                        update={
                            "high": max(current.high, price),
                            "low": min(current.low, price),
                            "close": price,
                            "volume": current.volume + quantity,
                            "updated_at": traded_at,
                        }
                    )
                else:
                    continue
                yield current
        except (ConnectionError, OSError, TimeoutError, WebSocketException) as exc:
            raise KrakenConnectionError("Kraken Futures trade WebSocket failed") from exc
        finally:
            if connection is not None:
                try:
                    await connection.send(
                        json.dumps(
                            {
                                "event": "unsubscribe",
                                "feed": "trade",
                                "product_ids": [instrument.venue_symbol],
                            },
                            separators=(",", ":"),
                        )
                    )
                except Exception:
                    pass
                await connection.close()


def _parse_futures_candles(
    payload: object,
    *,
    key: CandleKey,
    before: datetime,
    limit: int,
) -> tuple[Candle, ...]:
    if not isinstance(payload, Mapping):
        raise KrakenPayloadError("Kraken Futures candles payload must be an object")
    raw_candles = payload.get("candles")
    if not isinstance(raw_candles, list):
        raise KrakenPayloadError("Kraken Futures candles payload has no candles array")

    parsed: list[Candle] = []
    previous_open: datetime | None = None
    for raw in raw_candles:
        if not isinstance(raw, Mapping):
            raise KrakenPayloadError("Kraken Futures candle must be an object")
        open_time = _epoch_datetime(raw.get("time"))
        if open_time > before:
            raise KrakenPayloadError("Kraken Futures returned a future candle")
        if previous_open is not None and open_time <= previous_open:
            raise KrakenPayloadError("Kraken Futures candles are not strictly chronological")
        previous_open = open_time
        close_time = open_time + key.timeframe.duration
        is_final = close_time <= before
        open_price = _positive_decimal(raw.get("open"), "open")
        high_price = _positive_decimal(raw.get("high"), "high")
        low_price = _positive_decimal(raw.get("low"), "low")
        close_price = _positive_decimal(raw.get("close"), "close")
        volume = _non_negative_decimal(raw.get("volume", 0), "volume")
        parsed.append(
            Candle(
                symbol=key.symbol,
                market_type=key.market_type,
                timeframe=key.timeframe,
                open_time=open_time,
                close_time=close_time,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume,
                is_final=is_final,
                updated_at=close_time if is_final else before,
            )
        )
    return tuple(parsed[-limit:])


def _parse_futures_trade(
    raw: str | bytes,
    *,
    expected_product: str,
) -> tuple[datetime, Decimal, Decimal] | None:
    try:
        payload = json.loads(raw, parse_float=Decimal)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
        raise KrakenPayloadError("Kraken Futures WebSocket returned invalid JSON") from exc
    if not isinstance(payload, Mapping):
        raise KrakenPayloadError("Kraken Futures WebSocket message must be an object")
    if payload.get("event") in ("subscribed", "unsubscribed") or payload.get("feed") == "heartbeat":
        return None
    if payload.get("event") in ("error", "subscribed_failed", "unsubscribed_failed"):
        raise KrakenPayloadError("Kraken Futures rejected the trade subscription")
    if payload.get("feed") != "trade":
        return None
    product = payload.get("product_id")
    if product != expected_product:
        raise KrakenPayloadError("Kraken Futures trade product did not match subscription")
    timestamp = payload.get("time", payload.get("timestamp"))
    return (
        _provider_datetime(timestamp),
        _positive_decimal(payload.get("price"), "trade price"),
        _non_negative_decimal(payload.get("qty", payload.get("size")), "trade quantity"),
    )


def _provider_datetime(value: Any) -> datetime:
    if isinstance(value, bool) or value is None:
        raise KrakenPayloadError("Kraken provider timestamp is invalid")
    if isinstance(value, (int, Decimal)):
        return _epoch_datetime(value)
    if isinstance(value, float):
        return _epoch_datetime(Decimal(str(value)))
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise KrakenPayloadError("Kraken provider timestamp is invalid")
        try:
            number = Decimal(stripped)
        except InvalidOperation:
            normalized = stripped[:-1] + "+00:00" if stripped.endswith("Z") else stripped
            try:
                parsed = datetime.fromisoformat(normalized)
            except ValueError as exc:
                raise KrakenPayloadError("Kraken provider timestamp is invalid") from exc
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise KrakenPayloadError("Kraken provider timestamp must be timezone-aware")
            return parsed.astimezone(UTC)
        return _epoch_datetime(number)
    raise KrakenPayloadError("Kraken provider timestamp is invalid")


def _epoch_datetime(value: Any) -> datetime:
    if isinstance(value, bool) or value is None:
        raise KrakenPayloadError("Kraken candle time is invalid")
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise KrakenPayloadError("Kraken candle time is invalid") from exc
    if not number.is_finite() or number < 0:
        raise KrakenPayloadError("Kraken candle time is invalid")
    if number > Decimal("100000000000"):
        number /= Decimal(1000)
    try:
        return datetime.fromtimestamp(float(number), tz=UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise KrakenPayloadError("Kraken candle time is invalid") from exc


def _positive_decimal(value: Any, label: str) -> Decimal:
    number = _decimal(value, label)
    if number <= 0:
        raise KrakenPayloadError(f"Kraken {label} must be positive")
    return number


def _non_negative_decimal(value: Any, label: str) -> Decimal:
    number = _decimal(value, label)
    if number < 0:
        raise KrakenPayloadError(f"Kraken {label} must be non-negative")
    return number


def _decimal(value: Any, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise KrakenPayloadError(f"Kraken {label} is invalid")
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise KrakenPayloadError(f"Kraken {label} is invalid") from exc
    if not number.is_finite():
        raise KrakenPayloadError(f"Kraken {label} must be finite")
    return number
