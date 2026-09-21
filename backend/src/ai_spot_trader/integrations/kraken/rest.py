import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from ai_spot_trader.integrations.kraken.errors import KrakenConnectionError, KrakenPayloadError
from ai_spot_trader.integrations.kraken.models import KrakenOhlcCandle
from ai_spot_trader.integrations.kraken.symbols import (
    KrakenPairRegistry,
    parse_asset_pairs_payload,
)

KRAKEN_OHLC_INTERVALS_MINUTES = frozenset(
    {1, 5, 15, 30, 60, 240, 1440, 10080, 21600}
)


class KrakenPublicRestClient:
    """Small unauthenticated REST client for Kraken Spot discovery and price history."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds)
        self._owns_client = client is None

    async def fetch_pair_registry(self) -> KrakenPairRegistry:
        try:
            response = await self._client.get(
                "/0/public/AssetPairs",
                params={"assetVersion": 1, "aclass_base": "currency"},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise KrakenConnectionError("Kraken AssetPairs request failed") from exc

        try:
            payload = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise KrakenPayloadError("Kraken AssetPairs returned invalid JSON") from exc
        return parse_asset_pairs_payload(payload)

    async def fetch_ohlc_history(
        self,
        symbol: str,
        *,
        interval_minutes: int,
        since: datetime,
    ) -> tuple[KrakenOhlcCandle, ...]:
        """Return committed OHLC closes only; Kraken's live trailing candle is excluded."""

        if interval_minutes not in KRAKEN_OHLC_INTERVALS_MINUTES:
            raise ValueError("unsupported Kraken OHLC interval")
        if since.tzinfo is None or since.utcoffset() is None:
            raise ValueError("Kraken OHLC since must be timezone-aware")

        try:
            response = await self._client.get(
                "/0/public/OHLC",
                params={
                    "pair": symbol,
                    "assetVersion": 1,
                    "interval": interval_minutes,
                    "since": int(since.timestamp()),
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise KrakenConnectionError("Kraken OHLC request failed") from exc

        try:
            payload = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise KrakenPayloadError("Kraken OHLC returned invalid JSON") from exc
        return _parse_ohlc_payload(
            payload,
            interval_minutes=interval_minutes,
            expected_symbol=symbol,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


def _parse_ohlc_payload(
    payload: object,
    *,
    interval_minutes: int,
    expected_symbol: str,
) -> tuple[KrakenOhlcCandle, ...]:
    if not isinstance(payload, Mapping):
        raise KrakenPayloadError("Kraken OHLC payload must be an object")

    errors = payload.get("error")
    if not isinstance(errors, list):
        raise KrakenPayloadError("Kraken OHLC payload has an invalid error field")
    if errors:
        raise KrakenPayloadError("Kraken OHLC returned an API error")

    result = payload.get("result")
    if not isinstance(result, Mapping):
        raise KrakenPayloadError("Kraken OHLC payload has no result object")

    series = [(key, value) for key, value in result.items() if key != "last"]
    if len(series) != 1:
        raise KrakenPayloadError("Kraken OHLC payload must contain exactly one pair series")

    raw_symbol, raw_rows = series[0]
    normalized_expected = expected_symbol.strip().upper()
    if not isinstance(raw_symbol, str) or raw_symbol.strip().upper() != normalized_expected:
        raise KrakenPayloadError("Kraken OHLC pair did not match the requested market")
    if not isinstance(raw_rows, list):
        raise KrakenPayloadError("Kraken OHLC pair series must be an array")
    if not raw_rows:
        raise KrakenPayloadError("Kraken OHLC pair series cannot be empty")

    interval = timedelta(minutes=interval_minutes)
    committed_rows = raw_rows[:-1]
    candles: list[KrakenOhlcCandle] = []
    previous_started_at: datetime | None = None

    for raw_row in committed_rows:
        if not isinstance(raw_row, list) or len(raw_row) < 5:
            raise KrakenPayloadError("Kraken OHLC contains an invalid candle entry")

        raw_timestamp = raw_row[0]
        if isinstance(raw_timestamp, bool) or not isinstance(raw_timestamp, int):
            raise KrakenPayloadError("Kraken OHLC candle timestamp is invalid")
        try:
            started_at = datetime.fromtimestamp(raw_timestamp, tz=UTC)
        except (OverflowError, OSError, ValueError) as exc:
            raise KrakenPayloadError("Kraken OHLC candle timestamp is invalid") from exc

        if previous_started_at is not None and started_at <= previous_started_at:
            raise KrakenPayloadError("Kraken OHLC candles are not strictly chronological")
        previous_started_at = started_at

        candles.append(
            KrakenOhlcCandle(
                started_at=started_at,
                closed_at=started_at + interval,
                close_price=_positive_decimal(raw_row[4]),
            )
        )

    return tuple(candles)


def _positive_decimal(value: Any) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise KrakenPayloadError("Kraken OHLC close price is invalid")
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise KrakenPayloadError("Kraken OHLC close price is invalid") from exc
    if not number.is_finite() or number <= 0:
        raise KrakenPayloadError("Kraken OHLC close price must be positive")
    return number
