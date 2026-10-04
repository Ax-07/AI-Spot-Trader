from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from ai_spot_trader.domain.models import DerivativeInstrument
from ai_spot_trader.integrations.kraken.derivatives import KrakenDerivativesPublicClient
from ai_spot_trader.integrations.kraken.errors import KrakenPayloadError

KRAKEN_ANALYTICS_INTERVALS_SECONDS = frozenset(
    {60, 300, 900, 1800, 3600, 14400, 43200, 86400, 604800}
)


@dataclass(frozen=True, slots=True)
class KrakenMarketAnalyticsPoint:
    observed_at: datetime
    value: Decimal
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


class KrakenDerivativesAnalyticsClient(KrakenDerivativesPublicClient):
    """Batch 47.2 extension of the canonical public Futures client.

    The application still owns a single Futures public-client instance. This subclass only adds
    the public Market Analytics transport/parsing surface; it does not create another HTTP client.
    """

    async def fetch_open_interest_history(
        self,
        instrument: DerivativeInstrument,
        *,
        since: datetime,
        until: datetime,
        interval_seconds: int,
    ) -> tuple[KrakenMarketAnalyticsPoint, ...]:
        if since.tzinfo is None or since.utcoffset() is None:
            raise ValueError("Kraken Market Analytics since must be timezone-aware")
        if until.tzinfo is None or until.utcoffset() is None:
            raise ValueError("Kraken Market Analytics until must be timezone-aware")
        if since > until:
            raise ValueError("Kraken Market Analytics since cannot be newer than until")
        if interval_seconds not in KRAKEN_ANALYTICS_INTERVALS_SECONDS:
            raise ValueError("unsupported Kraken Market Analytics interval")

        payload = await self._get_json(
            (
                f"{self._charts_base_url}/analytics/"
                f"{instrument.venue_symbol}/open-interest"
            ),
            "Kraken Futures Open Interest analytics",
            params={
                "since": int(since.timestamp()),
                "interval": interval_seconds,
                "to": int(until.timestamp()),
            },
        )
        return parse_kraken_open_interest_history(payload)


def parse_kraken_open_interest_history(
    payload: object,
) -> tuple[KrakenMarketAnalyticsPoint, ...]:
    """Parse Kraken open-interest OHLC buckets without inventing an OI unit.

    The public schema exposes an Ohlc variant and the live PF_XBTUSD smoke performed for
    Batch 47.2 returned four values per timestamp.  The fourth value (close) is the
    representative value forwarded to the provider-neutral historical series.
    """

    root = _mapping(payload, "Kraken Market Analytics payload")
    errors = root.get("errors")
    if errors is not None:
        if not isinstance(errors, list):
            raise KrakenPayloadError("Kraken Market Analytics errors must be an array")
        if errors:
            raise KrakenPayloadError("Kraken Market Analytics returned provider errors")

    result = root.get("result")
    if not isinstance(result, Mapping):
        raise KrakenPayloadError("Kraken Market Analytics result must be an object")

    timestamps = result.get("timestamp")
    values = result.get("data")
    more = result.get("more")
    if not isinstance(timestamps, list):
        raise KrakenPayloadError("Kraken Market Analytics timestamp must be an array")
    if not isinstance(values, list):
        raise KrakenPayloadError("Kraken Market Analytics data must be an array")
    if not isinstance(more, bool):
        raise KrakenPayloadError("Kraken Market Analytics more must be a boolean")
    if len(timestamps) != len(values):
        raise KrakenPayloadError("Kraken Market Analytics timestamp/data lengths differ")
    if more:
        # Batch 47.2 intentionally keeps one request per selected market. Silently accepting a
        # truncated page would make the robust baseline non-deterministic, so fail closed.
        raise KrakenPayloadError("Kraken Market Analytics response is truncated (more=true)")

    parsed: list[KrakenMarketAnalyticsPoint] = []
    previous: datetime | None = None
    for raw_timestamp, raw_value in zip(timestamps, values, strict=True):
        observed_at = _epoch_seconds(raw_timestamp, "analytics timestamp")
        if previous is not None and observed_at <= previous:
            raise KrakenPayloadError(
                "Kraken Market Analytics timestamps are not strictly chronological"
            )
        previous = observed_at
        open_value, high_value, low_value, close_value = _open_interest_ohlc(raw_value)
        parsed.append(
            KrakenMarketAnalyticsPoint(
                observed_at=observed_at,
                value=close_value,
                open=open_value,
                high=high_value,
                low=low_value,
                close=close_value,
            )
        )
    return tuple(parsed)


def _open_interest_ohlc(value: object) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Parse the live Kraken open-interest bucket as [open, high, low, close]."""

    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise KrakenPayloadError(
            "Kraken open-interest analytics bucket must be OHLC [open, high, low, close]"
        )
    open_value, high_value, low_value, close_value = (
        _decimal(item, f"open interest {label}")
        for item, label in zip(value, ("open", "high", "low", "close"), strict=True)
    )
    values = (open_value, high_value, low_value, close_value)
    if any(item < 0 for item in values):
        raise KrakenPayloadError("open interest OHLC values must be non-negative")
    if low_value > high_value:
        raise KrakenPayloadError("open interest OHLC low cannot exceed high")
    if not (low_value <= open_value <= high_value):
        raise KrakenPayloadError("open interest OHLC open must be within low/high")
    if not (low_value <= close_value <= high_value):
        raise KrakenPayloadError("open interest OHLC close must be within low/high")
    return open_value, high_value, low_value, close_value


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise KrakenPayloadError(f"{label} must be an object")
    return value


def _decimal(value: object, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise KrakenPayloadError(f"{label} is invalid")
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise KrakenPayloadError(f"{label} is invalid") from exc
    if not number.is_finite():
        raise KrakenPayloadError(f"{label} must be finite")
    return number


def _epoch_seconds(value: object, label: str) -> datetime:
    number = _decimal(value, label)
    if number != number.to_integral_value():
        raise KrakenPayloadError(f"{label} must be an integer epoch second value")
    try:
        return datetime.fromtimestamp(int(number), tz=UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise KrakenPayloadError(f"{label} is invalid") from exc
