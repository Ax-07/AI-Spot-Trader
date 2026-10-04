from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

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


@dataclass(frozen=True, slots=True)
class KrakenFundingAnalyticsPoint:
    """One Kraken funding bucket with absolute and relative funding kept separate."""

    observed_at: datetime
    rate: Decimal
    relative_rate: Decimal
    rate_open: Decimal
    rate_high: Decimal
    rate_low: Decimal
    rate_close: Decimal
    relative_rate_open: Decimal
    relative_rate_high: Decimal
    relative_rate_low: Decimal
    relative_rate_close: Decimal


@dataclass(frozen=True, slots=True)
class KrakenLiquidationVolumeAnalyticsPoint:
    """Aggregate Kraken liquidation-volume point without invented long/short semantics."""

    observed_at: datetime
    value: Decimal
    bucket_kind: Literal["SCALAR", "OHLC"]
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None


class KrakenDerivativesAnalyticsClient(KrakenDerivativesPublicClient):
    """Canonical public Futures client extended with Kraken Market Analytics."""

    async def fetch_open_interest_history(
        self,
        instrument: DerivativeInstrument,
        *,
        since: datetime,
        until: datetime,
        interval_seconds: int,
    ) -> tuple[KrakenMarketAnalyticsPoint, ...]:
        payload = await self._fetch_market_analytics(
            instrument,
            analytics_type="open-interest",
            label="Kraken Futures Open Interest analytics",
            since=since,
            until=until,
            interval_seconds=interval_seconds,
        )
        return parse_kraken_open_interest_history(payload)

    async def fetch_funding_history(
        self,
        instrument: DerivativeInstrument,
        *,
        since: datetime,
        until: datetime,
        interval_seconds: int,
    ) -> tuple[KrakenFundingAnalyticsPoint, ...]:
        payload = await self._fetch_market_analytics(
            instrument,
            analytics_type="funding",
            label="Kraken Futures Funding analytics",
            since=since,
            until=until,
            interval_seconds=interval_seconds,
        )
        return parse_kraken_funding_history(payload)

    async def fetch_liquidation_volume_history(
        self,
        instrument: DerivativeInstrument,
        *,
        since: datetime,
        until: datetime,
        interval_seconds: int,
    ) -> tuple[KrakenLiquidationVolumeAnalyticsPoint, ...]:
        payload = await self._fetch_market_analytics(
            instrument,
            analytics_type="liquidation-volume",
            label="Kraken Futures Liquidation Volume analytics",
            since=since,
            until=until,
            interval_seconds=interval_seconds,
        )
        return parse_kraken_liquidation_volume_history(payload)

    async def _fetch_market_analytics(
        self,
        instrument: DerivativeInstrument,
        *,
        analytics_type: str,
        label: str,
        since: datetime,
        until: datetime,
        interval_seconds: int,
    ) -> object:
        _validate_history_request(since, until, interval_seconds)
        return await self._get_json(
            f"{self._charts_base_url}/analytics/{instrument.venue_symbol}/{analytics_type}",
            label,
            params={
                "since": int(since.timestamp()),
                "interval": interval_seconds,
                "to": int(until.timestamp()),
            },
        )


def parse_kraken_open_interest_history(
    payload: object,
) -> tuple[KrakenMarketAnalyticsPoint, ...]:
    """Parse Kraken Open Interest OHLC buckets and use the finalized bucket close."""

    timestamps, values = _analytics_arrays(payload, analytics_name="Open Interest")
    parsed: list[KrakenMarketAnalyticsPoint] = []
    previous: datetime | None = None
    for raw_timestamp, raw_value in zip(timestamps, values, strict=True):
        observed_at = _ordered_timestamp(raw_timestamp, previous)
        previous = observed_at
        open_value, high_value, low_value, close_value = _ohlc(
            raw_value,
            label="open interest",
            non_negative=True,
        )
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


def parse_kraken_funding_history(
    payload: object,
) -> tuple[KrakenFundingAnalyticsPoint, ...]:
    """Parse the dedicated Kraken funding schema without conflating its two rates.

    Kraken documents ``data.rate`` and ``data.relativeRate`` as separate OHLC arrays.  Both are
    signed. ``rate`` is retained as the absolute/raw funding-rate series and ``relativeRate`` as
    the relative funding-rate series; this parser never maps either field to ticker prediction or
    realized account funding.
    """

    root, result = _analytics_result(payload)
    timestamps = result.get("timestamp")
    data = result.get("data")
    if not isinstance(timestamps, list):
        raise KrakenPayloadError("Kraken Market Analytics timestamp must be an array")
    if not isinstance(data, Mapping):
        raise KrakenPayloadError("Kraken funding analytics data must be an object")
    if set(data.keys()) != {"rate", "relativeRate"}:
        raise KrakenPayloadError(
            "Kraken funding analytics data must contain only rate and relativeRate"
        )
    rates = data.get("rate")
    relative_rates = data.get("relativeRate")
    if not isinstance(rates, list) or not isinstance(relative_rates, list):
        raise KrakenPayloadError("Kraken funding rate series must be arrays")
    if len(timestamps) != len(rates) or len(timestamps) != len(relative_rates):
        raise KrakenPayloadError("Kraken funding timestamp/rate lengths differ")
    _require_complete_page(result)

    parsed: list[KrakenFundingAnalyticsPoint] = []
    previous: datetime | None = None
    for raw_timestamp, raw_rate, raw_relative in zip(
        timestamps,
        rates,
        relative_rates,
        strict=True,
    ):
        observed_at = _ordered_timestamp(
            raw_timestamp,
            previous,
            unit="milliseconds",
        )
        previous = observed_at
        rate_open, rate_high, rate_low, rate_close = _ohlc(
            raw_rate,
            label="funding rate",
            non_negative=False,
        )
        relative_open, relative_high, relative_low, relative_close = _ohlc(
            raw_relative,
            label="relative funding rate",
            non_negative=False,
        )
        parsed.append(
            KrakenFundingAnalyticsPoint(
                observed_at=observed_at,
                rate=rate_close,
                relative_rate=relative_close,
                rate_open=rate_open,
                rate_high=rate_high,
                rate_low=rate_low,
                rate_close=rate_close,
                relative_rate_open=relative_open,
                relative_rate_high=relative_high,
                relative_rate_low=relative_low,
                relative_rate_close=relative_close,
            )
        )
    return tuple(parsed)


def parse_kraken_liquidation_volume_history(
    payload: object,
) -> tuple[KrakenLiquidationVolumeAnalyticsPoint, ...]:
    """Parse aggregate liquidation volume without inventing liquidation direction.

    Kraken's public Analytics schema permits a scalar or generic OHLC bucket for array-valued
    analytics.  Kraken Pro documents Liquidation Volume as the *total* value force-closed in an
    interval, not a long/short split.  Scalars are therefore retained directly.  If Kraken emits
    the documented generic OHLC variant, the fourth (close) component is the representative value
    just as for the generic Analytics OHLC convention; no component is assigned a directional
    meaning.
    """

    timestamps, values = _analytics_arrays(payload, analytics_name="Liquidation Volume")
    parsed: list[KrakenLiquidationVolumeAnalyticsPoint] = []
    previous: datetime | None = None
    for raw_timestamp, raw_value in zip(timestamps, values, strict=True):
        observed_at = _ordered_timestamp(raw_timestamp, previous)
        previous = observed_at
        if isinstance(raw_value, (list, tuple)):
            open_value, high_value, low_value, close_value = _ohlc(
                raw_value,
                label="liquidation volume",
                non_negative=True,
            )
            parsed.append(
                KrakenLiquidationVolumeAnalyticsPoint(
                    observed_at=observed_at,
                    value=close_value,
                    bucket_kind="OHLC",
                    open=open_value,
                    high=high_value,
                    low=low_value,
                    close=close_value,
                )
            )
            continue
        value = _decimal(raw_value, "liquidation volume")
        if value < 0:
            raise KrakenPayloadError("liquidation volume must be non-negative")
        parsed.append(
            KrakenLiquidationVolumeAnalyticsPoint(
                observed_at=observed_at,
                value=value,
                bucket_kind="SCALAR",
            )
        )
    return tuple(parsed)


def _analytics_arrays(
    payload: object,
    *,
    analytics_name: str,
) -> tuple[list[object], list[object]]:
    _, result = _analytics_result(payload)
    timestamps = result.get("timestamp")
    values = result.get("data")
    if not isinstance(timestamps, list):
        raise KrakenPayloadError("Kraken Market Analytics timestamp must be an array")
    if not isinstance(values, list):
        raise KrakenPayloadError(f"Kraken {analytics_name} analytics data must be an array")
    if len(timestamps) != len(values):
        raise KrakenPayloadError("Kraken Market Analytics timestamp/data lengths differ")
    _require_complete_page(result)
    return timestamps, values


def _analytics_result(payload: object) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
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
    return root, result


def _require_complete_page(result: Mapping[str, Any]) -> None:
    more = result.get("more")
    if not isinstance(more, bool):
        raise KrakenPayloadError("Kraken Market Analytics more must be a boolean")
    if more:
        # Rotation cost is intentionally bounded to one request per series and market.  A partial
        # page is never silently accepted because it would make historical baselines inconsistent.
        raise KrakenPayloadError("Kraken Market Analytics response is truncated (more=true)")


def _ohlc(
    value: object,
    *,
    label: str,
    non_negative: bool,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise KrakenPayloadError(f"Kraken {label} bucket must be OHLC [open, high, low, close]")
    open_value, high_value, low_value, close_value = (
        _decimal(item, f"{label} {component}")
        for item, component in zip(value, ("open", "high", "low", "close"), strict=True)
    )
    values = (open_value, high_value, low_value, close_value)
    if non_negative and any(item < 0 for item in values):
        raise KrakenPayloadError(f"{label} OHLC values must be non-negative")
    if low_value > high_value:
        raise KrakenPayloadError(f"{label} OHLC low cannot exceed high")
    if not (low_value <= open_value <= high_value):
        raise KrakenPayloadError(f"{label} OHLC open must be within low/high")
    if not (low_value <= close_value <= high_value):
        raise KrakenPayloadError(f"{label} OHLC close must be within low/high")
    return open_value, high_value, low_value, close_value


def _validate_history_request(
    since: datetime,
    until: datetime,
    interval_seconds: int,
) -> None:
    if since.tzinfo is None or since.utcoffset() is None:
        raise ValueError("Kraken Market Analytics since must be timezone-aware")
    if until.tzinfo is None or until.utcoffset() is None:
        raise ValueError("Kraken Market Analytics until must be timezone-aware")
    if since > until:
        raise ValueError("Kraken Market Analytics since cannot be newer than until")
    if interval_seconds not in KRAKEN_ANALYTICS_INTERVALS_SECONDS:
        raise ValueError("unsupported Kraken Market Analytics interval")


def _ordered_timestamp(
    value: object,
    previous: datetime | None,
    *,
    unit: Literal["seconds", "milliseconds"] = "seconds",
) -> datetime:
    observed_at = _epoch_timestamp(value, "analytics timestamp", unit=unit)
    if previous is not None and observed_at <= previous:
        raise KrakenPayloadError("Kraken Market Analytics timestamps are not strictly chronological")
    return observed_at


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


def _epoch_timestamp(
    value: object,
    label: str,
    *,
    unit: Literal["seconds", "milliseconds"],
) -> datetime:
    number = _decimal(value, label)
    if number != number.to_integral_value():
        raise KrakenPayloadError(f"{label} must be an integer epoch {unit} value")
    raw_value = int(number)
    try:
        if unit == "milliseconds":
            seconds, milliseconds = divmod(raw_value, 1000)
            return datetime.fromtimestamp(seconds, tz=UTC) + timedelta(milliseconds=milliseconds)
        return datetime.fromtimestamp(raw_value, tz=UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise KrakenPayloadError(f"{label} is invalid") from exc
