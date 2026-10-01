from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from ai_spot_trader.integrations.kraken.errors import KrakenPayloadError
from ai_spot_trader.integrations.kraken.rest import (
    KrakenPublicRestClient,
    _raise_for_api_errors,
    _raise_transport_error,
)
from ai_spot_trader.integrations.kraken.symbols import kraken_pair_key_matches
from ai_spot_trader.market.microstructure import (
    OrderBookLevel,
    OrderBookSnapshot,
    RecentTrade,
    RecentTradesSnapshot,
    TradeSide,
)


class KrakenSpotMicrostructureProvider(KrakenPublicRestClient):
    """Bounded unauthenticated Kraken SPOT L2/recent-trades reader."""

    async def fetch_order_book(self, symbol: str, *, limit: int) -> OrderBookSnapshot:
        if isinstance(limit, bool) or not 1 <= limit <= 500:
            raise ValueError("Kraken order-book limit must be within 1..500")
        try:
            response = await self._client.get(
                "/0/public/Depth",
                params={"pair": symbol, "assetVersion": 1, "count": limit},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            _raise_transport_error(exc, operation="Depth")
        payload = _json_payload(response, operation="Depth")
        _raise_for_api_errors(payload, operation="Depth")
        return _parse_order_book_payload(
            payload,
            expected_symbol=symbol,
            received_at=datetime.now(UTC),
            limit=limit,
        )

    async def fetch_recent_trades(self, symbol: str, *, limit: int) -> RecentTradesSnapshot:
        if isinstance(limit, bool) or not 1 <= limit <= 1000:
            raise ValueError("Kraken recent-trades limit must be within 1..1000")
        try:
            response = await self._client.get(
                "/0/public/Trades",
                params={"pair": symbol, "assetVersion": 1, "count": limit},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            _raise_transport_error(exc, operation="Trades")
        payload = _json_payload(response, operation="Trades")
        _raise_for_api_errors(payload, operation="Trades")
        return _parse_recent_trades_payload(
            payload,
            expected_symbol=symbol,
            received_at=datetime.now(UTC),
            limit=limit,
        )


def _json_payload(response: httpx.Response, *, operation: str) -> object:
    try:
        return json.loads(response.text)
    except json.JSONDecodeError as exc:
        raise KrakenPayloadError(f"Kraken {operation} returned invalid JSON") from exc


def _parse_order_book_payload(
    payload: object,
    *,
    expected_symbol: str,
    received_at: datetime,
    limit: int,
) -> OrderBookSnapshot:
    result = _result_mapping(payload, operation="Depth")
    _raw_symbol, book = _single_pair_result(result, expected_symbol=expected_symbol)
    if not isinstance(book, Mapping):
        raise KrakenPayloadError("Kraken Depth pair payload must be an object")
    bids = _parse_book_side(book.get("bids"), label="bids", limit=limit)
    asks = _parse_book_side(book.get("asks"), label="asks", limit=limit)
    return OrderBookSnapshot(
        observed_at=_utc(received_at),
        bids=bids,
        asks=asks,
    )


def _parse_recent_trades_payload(
    payload: object,
    *,
    expected_symbol: str,
    received_at: datetime,
    limit: int,
) -> RecentTradesSnapshot:
    result = _result_mapping(payload, operation="Trades")
    series = [(key, value) for key, value in result.items() if key != "last"]
    if len(series) != 1:
        raise KrakenPayloadError("Kraken Trades must contain exactly one pair series")
    raw_symbol, rows = series[0]
    if not isinstance(raw_symbol, str) or not kraken_pair_key_matches(raw_symbol, expected_symbol):
        raise KrakenPayloadError("Kraken Trades pair did not match requested market")
    if not isinstance(rows, list):
        raise KrakenPayloadError("Kraken Trades pair series must be an array")
    if len(rows) > limit:
        raise KrakenPayloadError("Kraken Trades exceeded the requested bounded count")

    trades = tuple(_parse_trade_row(row) for row in rows)
    trades = tuple(
        sorted(
            trades,
            key=lambda item: (item.occurred_at, item.trade_id if item.trade_id is not None else -1),
        )
    )
    return RecentTradesSnapshot(observed_at=_utc(received_at), trades=trades)


def _result_mapping(payload: object, *, operation: str) -> Mapping[Any, Any]:
    if not isinstance(payload, Mapping):
        raise KrakenPayloadError(f"Kraken {operation} payload must be an object")
    errors = payload.get("error")
    if not isinstance(errors, list):
        raise KrakenPayloadError(f"Kraken {operation} payload has invalid error field")
    if errors:
        raise KrakenPayloadError(f"Kraken {operation} returned an API error")
    result = payload.get("result")
    if not isinstance(result, Mapping):
        raise KrakenPayloadError(f"Kraken {operation} payload has no result object")
    return result


def _single_pair_result(
    result: Mapping[Any, Any], *, expected_symbol: str
) -> tuple[str, object]:
    if len(result) != 1:
        raise KrakenPayloadError("Kraken Depth must contain exactly one pair result")
    raw_symbol, value = next(iter(result.items()))
    if not isinstance(raw_symbol, str) or not kraken_pair_key_matches(raw_symbol, expected_symbol):
        raise KrakenPayloadError("Kraken Depth pair did not match requested market")
    return raw_symbol, value


def _parse_book_side(value: object, *, label: str, limit: int) -> tuple[OrderBookLevel, ...]:
    if not isinstance(value, list):
        raise KrakenPayloadError(f"Kraken Depth {label} must be an array")
    if len(value) > limit:
        raise KrakenPayloadError(f"Kraken Depth {label} exceeded requested bounded count")
    levels: list[OrderBookLevel] = []
    for raw in value:
        if not isinstance(raw, list) or len(raw) < 2:
            raise KrakenPayloadError(f"Kraken Depth {label} contains invalid level")
        price = _positive_decimal(raw[0], label=f"{label} price")
        volume = _non_negative_decimal(raw[1], label=f"{label} volume")
        timestamp = _optional_timestamp(raw[2]) if len(raw) >= 3 else None
        levels.append(
            OrderBookLevel(price=price, volume_base=volume, level_timestamp=timestamp)
        )
    return tuple(levels)


def _parse_trade_row(value: object) -> RecentTrade:
    if not isinstance(value, list) or len(value) < 4:
        raise KrakenPayloadError("Kraken Trades contains invalid trade row")
    price = _positive_decimal(value[0], label="trade price")
    volume = _positive_decimal(value[1], label="trade volume")
    occurred_at = _timestamp(value[2], label="trade timestamp")
    side = _trade_side(value[3])
    trade_id = None
    if len(value) >= 7 and value[6] is not None:
        if isinstance(value[6], bool) or not isinstance(value[6], int) or value[6] < 0:
            raise KrakenPayloadError("Kraken Trades trade id is invalid")
        trade_id = value[6]
    return RecentTrade(
        price=price,
        volume_base=volume,
        occurred_at=occurred_at,
        side=side,
        trade_id=trade_id,
    )


def _trade_side(value: object) -> TradeSide | None:
    # Kraken exposes a provider side marker. Unknown/new values remain explicitly unknown.
    if value == "b":
        return TradeSide.BUY
    if value == "s":
        return TradeSide.SELL
    return None


def _optional_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    return _timestamp(value, label="order-book timestamp")


def _timestamp(value: object, *, label: str) -> datetime:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise KrakenPayloadError(f"Kraken {label} is invalid")
    try:
        return datetime.fromtimestamp(float(value), tz=UTC)
    except (OverflowError, OSError, ValueError, TypeError) as exc:
        raise KrakenPayloadError(f"Kraken {label} is invalid") from exc


def _positive_decimal(value: object, *, label: str) -> Decimal:
    number = _decimal(value, label=label)
    if number <= 0:
        raise KrakenPayloadError(f"Kraken {label} must be positive")
    return number


def _non_negative_decimal(value: object, *, label: str) -> Decimal:
    number = _decimal(value, label=label)
    if number < 0:
        raise KrakenPayloadError(f"Kraken {label} must be non-negative")
    return number


def _decimal(value: object, *, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise KrakenPayloadError(f"Kraken {label} is invalid")
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise KrakenPayloadError(f"Kraken {label} is invalid") from exc
    if not number.is_finite():
        raise KrakenPayloadError(f"Kraken {label} must be finite")
    return number


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)
