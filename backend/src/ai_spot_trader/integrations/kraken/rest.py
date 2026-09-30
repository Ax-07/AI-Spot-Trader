import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from ai_spot_trader.integrations.kraken.errors import (
    KrakenAPIError,
    KrakenConnectionError,
    KrakenHTTPError,
    KrakenNetworkError,
    KrakenPayloadError,
    KrakenPayloadStage,
    KrakenRateLimitError,
    KrakenServerError,
    KrakenTimeoutError,
)
from ai_spot_trader.integrations.kraken.models import KrakenOhlcCandle, KrakenOhlcvCandle
from ai_spot_trader.integrations.kraken.symbols import (
    KrakenPairRegistry,
    kraken_pair_key_matches,
    parse_asset_pairs_payload,
)

KRAKEN_OHLC_INTERVALS_MINUTES = frozenset(
    {1, 5, 15, 30, 60, 240, 1440, 10080, 21600}
)
KRAKEN_SPOT_OHLC_MAX_ROWS = 720
# Kraken documents a 720-entry OHLC limit, but a live request reproduced on
# 2026-09-29 returned 721 rows for the same bounded window. Keep the provider
# history limit at 720 while allowing exactly one runtime overflow row.
KRAKEN_SPOT_OHLC_MAX_RESPONSE_ROWS = KRAKEN_SPOT_OHLC_MAX_ROWS + 1
_LOGGER = logging.getLogger(__name__)


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
            _raise_transport_error(exc, operation="AssetPairs")

        try:
            payload = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise KrakenPayloadError(
                "Kraken AssetPairs returned invalid JSON",
                stage=KrakenPayloadStage.ASSET_PAIRS_PAYLOAD,
            ) from exc
        try:
            _raise_for_api_errors(payload, operation="AssetPairs")
            return parse_asset_pairs_payload(payload)
        except KrakenPayloadError as exc:
            _log_payload_error(operation="AssetPairs", exc=exc)
            raise

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
        payload = await self._fetch_ohlc_payload(
            symbol, interval_minutes=interval_minutes, since=since
        )
        try:
            return _parse_ohlc_payload(
                payload,
                interval_minutes=interval_minutes,
                expected_symbol=symbol,
            )
        except KrakenPayloadError as exc:
            _log_payload_error(operation="OHLC", exc=exc)
            raise

    async def fetch_ohlcv_history(
        self,
        symbol: str,
        *,
        interval_minutes: int,
        since: datetime,
    ) -> tuple[KrakenOhlcvCandle, ...]:
        """Return full OHLCV rows, keeping Kraken's trailing in-progress candle explicit."""

        if interval_minutes not in KRAKEN_OHLC_INTERVALS_MINUTES:
            raise ValueError("unsupported Kraken OHLC interval")
        if since.tzinfo is None or since.utcoffset() is None:
            raise ValueError("Kraken OHLC since must be timezone-aware")

        payload = await self._fetch_ohlc_payload(
            symbol, interval_minutes=interval_minutes, since=since
        )
        received_at = datetime.now(UTC)
        try:
            return _parse_ohlcv_payload(
                payload,
                interval_minutes=interval_minutes,
                expected_symbol=symbol,
                received_at=received_at,
            )
        except KrakenPayloadError as exc:
            _log_payload_error(operation="OHLC", exc=exc)
            raise

    async def _fetch_ohlc_payload(
        self,
        symbol: str,
        *,
        interval_minutes: int,
        since: datetime,
    ) -> object:
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
            _raise_transport_error(exc, operation="OHLC")
        try:
            payload = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise KrakenPayloadError(
                "Kraken OHLC returned invalid JSON",
                stage=KrakenPayloadStage.OHLC_RESULT,
            ) from exc
        _raise_for_api_errors(payload, operation="OHLC")
        return payload

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


def _log_payload_error(*, operation: str, exc: KrakenPayloadError) -> None:
    stage = exc.stage.value if isinstance(exc.stage, KrakenPayloadStage) else "UNCLASSIFIED"
    _LOGGER.warning("Kraken payload validation failed operation=%s stage=%s", operation, stage)


def _raise_transport_error(exc: httpx.HTTPError, *, operation: str) -> None:
    """Normalize public Kraken transport failures without surfacing response bodies or URLs."""

    if isinstance(exc, httpx.TimeoutException):
        raise KrakenTimeoutError(f"Kraken {operation} request timed out") from exc
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        if status_code == 408:
            raise KrakenTimeoutError(
                f"Kraken {operation} returned HTTP 408",
                status_code=status_code,
            ) from exc
        if status_code == 429:
            raise KrakenRateLimitError(
                f"Kraken {operation} rate limited request",
                status_code=status_code,
            ) from exc
        if status_code >= 500:
            raise KrakenServerError(
                f"Kraken {operation} returned a server error",
                status_code=status_code,
            ) from exc
        raise KrakenHTTPError(
            f"Kraken {operation} returned an HTTP error",
            status_code=status_code,
        ) from exc
    if isinstance(exc, httpx.RequestError):
        raise KrakenNetworkError(f"Kraken {operation} network request failed") from exc
    raise KrakenConnectionError(f"Kraken {operation} request failed") from exc


def _raise_for_api_errors(payload: object, *, operation: str) -> None:
    """Classify provider-declared API errors while keeping raw provider details private."""

    if not isinstance(payload, Mapping):
        return
    errors = payload.get("error")
    if not isinstance(errors, list) or not errors:
        return
    normalized = tuple(
        item.strip().lower()
        for item in errors
        if isinstance(item, str) and item.strip()
    )
    explicit_throttling = any(
        "rate limit" in item or "throttled" in item or "too many requests" in item
        for item in normalized
    )
    if explicit_throttling:
        raise KrakenRateLimitError(f"Kraken {operation} rate limited request")
    raise KrakenAPIError(f"Kraken {operation} returned an API error")


def _parse_ohlc_payload(
    payload: object,
    *,
    interval_minutes: int,
    expected_symbol: str,
) -> tuple[KrakenOhlcCandle, ...]:
    result = _ohlc_result(payload)
    raw_symbol, raw_rows = _ohlc_series(result, expected_symbol=expected_symbol)
    del raw_symbol

    interval = timedelta(minutes=interval_minutes)
    committed_rows = raw_rows[:-1]
    candles: list[KrakenOhlcCandle] = []
    previous_started_at: datetime | None = None

    for raw_row in committed_rows:
        if not isinstance(raw_row, list) or len(raw_row) < 5:
            raise KrakenPayloadError(
                "Kraken OHLC contains an invalid candle entry",
                stage=KrakenPayloadStage.OHLC_ROW,
            )

        started_at = _ohlc_timestamp(raw_row[0])
        if previous_started_at is not None and started_at <= previous_started_at:
            raise KrakenPayloadError(
                "Kraken OHLC candles are not strictly chronological",
                stage=KrakenPayloadStage.OHLC_ROW,
            )
        previous_started_at = started_at
        candles.append(
            KrakenOhlcCandle(
                started_at=started_at,
                closed_at=started_at + interval,
                close_price=_positive_decimal(raw_row[4]),
            )
        )

    return tuple(candles)


def _parse_ohlcv_payload(
    payload: object,
    *,
    interval_minutes: int,
    expected_symbol: str,
    received_at: datetime,
) -> tuple[KrakenOhlcvCandle, ...]:
    if interval_minutes not in KRAKEN_OHLC_INTERVALS_MINUTES:
        raise ValueError("unsupported Kraken OHLC interval")
    if received_at.tzinfo is None or received_at.utcoffset() is None:
        raise ValueError("Kraken OHLC received_at must be timezone-aware")
    received_at = received_at.astimezone(UTC)

    result = _ohlc_result(payload)
    _raw_symbol, raw_rows = _ohlc_series(result, expected_symbol=expected_symbol)
    if len(raw_rows) > KRAKEN_SPOT_OHLC_MAX_RESPONSE_ROWS:
        raise KrakenPayloadError(
            "Kraken OHLC returned more rows than the bounded response allowance",
            stage=KrakenPayloadStage.OHLC_SERIES,
        )

    interval = timedelta(minutes=interval_minutes)
    candles: list[KrakenOhlcvCandle] = []
    previous_started_at: datetime | None = None

    for index, raw_row in enumerate(raw_rows):
        if not isinstance(raw_row, list) or len(raw_row) < 7:
            raise KrakenPayloadError(
                "Kraken OHLC contains an invalid candle entry",
                stage=KrakenPayloadStage.OHLC_ROW,
            )

        started_at = _ohlc_timestamp(raw_row[0])
        if previous_started_at is not None and started_at <= previous_started_at:
            raise KrakenPayloadError(
                "Kraken OHLC candles are not strictly chronological",
                stage=KrakenPayloadStage.OHLC_ROW,
            )
        previous_started_at = started_at

        closed_at = started_at + interval
        is_trailing = index == len(raw_rows) - 1
        is_final = not is_trailing and closed_at <= received_at
        updated_at = closed_at if is_final else received_at
        if started_at > received_at:
            raise KrakenPayloadError(
                "Kraken OHLC contains a future candle",
                stage=KrakenPayloadStage.OHLC_ROW,
            )

        open_price = _positive_decimal(raw_row[1], label="open")
        high_price = _positive_decimal(raw_row[2], label="high")
        low_price = _positive_decimal(raw_row[3], label="low")
        close_price = _positive_decimal(raw_row[4], label="close")
        volume = _non_negative_decimal(raw_row[6], label="volume")
        if low_price > min(open_price, close_price) or high_price < max(
            open_price, close_price
        ):
            raise KrakenPayloadError(
                "Kraken OHLC price bounds are inconsistent",
                stage=KrakenPayloadStage.OHLC_ROW,
            )

        candles.append(
            KrakenOhlcvCandle(
                started_at=started_at,
                closed_at=closed_at,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                close_price=close_price,
                volume=volume,
                is_final=is_final,
                updated_at=updated_at,
            )
        )

    return tuple(candles)


def _ohlc_result(payload: object) -> Mapping[Any, Any]:
    if not isinstance(payload, Mapping):
        raise KrakenPayloadError(
            "Kraken OHLC payload must be an object",
            stage=KrakenPayloadStage.OHLC_RESULT,
        )

    errors = payload.get("error")
    if not isinstance(errors, list):
        raise KrakenPayloadError(
            "Kraken OHLC payload has an invalid error field",
            stage=KrakenPayloadStage.OHLC_RESULT,
        )
    if errors:
        raise KrakenPayloadError(
            "Kraken OHLC returned an API error",
            stage=KrakenPayloadStage.OHLC_RESULT,
        )

    result = payload.get("result")
    if not isinstance(result, Mapping):
        raise KrakenPayloadError(
            "Kraken OHLC payload has no result object",
            stage=KrakenPayloadStage.OHLC_RESULT,
        )
    return result


def _ohlc_series(
    result: Mapping[Any, Any],
    *,
    expected_symbol: str,
) -> tuple[str, list[Any]]:
    series = [(key, value) for key, value in result.items() if key != "last"]
    if len(series) != 1:
        raise KrakenPayloadError(
            "Kraken OHLC payload must contain exactly one pair series",
            stage=KrakenPayloadStage.OHLC_SERIES,
        )

    raw_symbol, raw_rows = series[0]
    if not isinstance(raw_symbol, str):
        raise KrakenPayloadError(
            "Kraken OHLC pair key is invalid",
            stage=KrakenPayloadStage.OHLC_PAIR_KEY,
        )
    if not kraken_pair_key_matches(raw_symbol, expected_symbol):
        raise KrakenPayloadError(
            "Kraken OHLC pair did not match the requested market",
            stage=KrakenPayloadStage.OHLC_PAIR_KEY,
        )
    if not isinstance(raw_rows, list):
        raise KrakenPayloadError(
            "Kraken OHLC pair series must be an array",
            stage=KrakenPayloadStage.OHLC_SERIES,
        )
    if not raw_rows:
        raise KrakenPayloadError(
            "Kraken OHLC pair series cannot be empty",
            stage=KrakenPayloadStage.OHLC_SERIES,
        )
    return raw_symbol, raw_rows


def _ohlc_timestamp(value: Any) -> datetime:
    if isinstance(value, bool) or not isinstance(value, int):
        raise KrakenPayloadError(
            "Kraken OHLC candle timestamp is invalid",
            stage=KrakenPayloadStage.OHLC_TIMESTAMP,
        )
    try:
        return datetime.fromtimestamp(value, tz=UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise KrakenPayloadError(
            "Kraken OHLC candle timestamp is invalid",
            stage=KrakenPayloadStage.OHLC_TIMESTAMP,
        ) from exc


def _positive_decimal(value: Any, *, label: str = "close") -> Decimal:
    number = _decimal(value, label=label)
    if number <= 0:
        raise KrakenPayloadError(
            f"Kraken OHLC {label} price must be positive",
            stage=KrakenPayloadStage.OHLC_NUMERIC,
        )
    return number


def _non_negative_decimal(value: Any, *, label: str) -> Decimal:
    number = _decimal(value, label=label)
    if number < 0:
        raise KrakenPayloadError(
            f"Kraken OHLC {label} must be non-negative",
            stage=KrakenPayloadStage.OHLC_NUMERIC,
        )
    return number


def _decimal(value: Any, *, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise KrakenPayloadError(
            f"Kraken OHLC {label} is invalid",
            stage=KrakenPayloadStage.OHLC_NUMERIC,
        )
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise KrakenPayloadError(
            f"Kraken OHLC {label} is invalid",
            stage=KrakenPayloadStage.OHLC_NUMERIC,
        ) from exc
    if not number.is_finite():
        raise KrakenPayloadError(
            f"Kraken OHLC {label} must be finite",
            stage=KrakenPayloadStage.OHLC_NUMERIC,
        )
    return number
