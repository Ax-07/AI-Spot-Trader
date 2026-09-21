import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol
from uuid import uuid4

import httpx

from ai_spot_trader.core.clock import Clock, SystemClock
from ai_spot_trader.domain.enums import DerivativeContractKind, MarketType
from ai_spot_trader.domain.models import (
    DerivativeInstrument,
    DerivativeMarketContext,
    MarketState,
)
from ai_spot_trader.domain.symbols import parse_canonical_symbol
from ai_spot_trader.integrations.kraken.errors import (
    KrakenConnectionError,
    KrakenPayloadError,
    StaleMarketDataError,
    UnknownKrakenSymbolError,
)

KRAKEN_DERIVATIVES_FUNDING_INTERVAL_SECONDS = Decimal(3600)
_ASSET_ALIASES = {"XBT": "BTC", "XDG": "DOGE"}
_QUOTE_CANDIDATES = ("USDC", "USDT", "USD", "EUR", "GBP", "BTC", "ETH")


class DerivativeMarketSink(Protocol):
    """Optional PAPER portfolio hook for mark-to-market/funding before AgentInput."""

    def mark_derivative_market(self, market_state: MarketState) -> None: ...


class KrakenDerivativesPublicClient:
    """Unauthenticated Kraken Derivatives REST client; no private endpoint is exposed."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds)
        self._owns_client = client is None

    async def fetch_instruments(self) -> tuple[DerivativeInstrument, ...]:
        payload = await self._get_json("/instruments", "Kraken Derivatives instruments")
        return parse_kraken_derivatives_instruments(payload)

    async def fetch_ticker(
        self,
        instrument: DerivativeInstrument,
    ) -> tuple[datetime, Decimal, Decimal | None, Decimal | None]:
        payload = await self._get_json(
            f"/tickers/{instrument.venue_symbol}",
            "Kraken Derivatives ticker",
        )
        return parse_kraken_derivatives_ticker(payload, instrument=instrument)

    async def _get_json(self, path: str, label: str) -> object:
        try:
            response = await self._client.get(path)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise KrakenConnectionError(f"{label} request failed") from exc
        try:
            return json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise KrakenPayloadError(f"{label} returned invalid JSON") from exc

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


class KrakenDerivativesMarketDataSource:
    """Public Kraken Derivatives source for canonical PAPER market snapshots."""

    def __init__(
        self,
        rest_client: KrakenDerivativesPublicClient,
        *,
        clock: Clock | None = None,
        market_sink: DerivativeMarketSink | None = None,
        stale_after: timedelta | None = None,
    ) -> None:
        self._rest_client = rest_client
        self._clock = clock or SystemClock()
        self._market_sink = market_sink
        self._stale_after = stale_after
        self._instruments: dict[str, DerivativeInstrument] | None = None

    async def snapshot(self, symbol: str) -> MarketState:
        canonical = _canonical_symbol(symbol)
        instrument = await self._instrument(canonical)
        observed_at, mark_price, index_price, funding_rate = await self._rest_client.fetch_ticker(
            instrument
        )
        as_of = self._clock.now()
        if observed_at > as_of:
            raise KrakenPayloadError("Kraken Derivatives ticker is newer than the local clock")
        if self._stale_after is not None and as_of - observed_at > self._stale_after:
            raise StaleMarketDataError(
                f"Kraken Derivatives market data is stale for {canonical}"
            )
        state = MarketState(
            market_state_id=uuid4(),
            as_of=as_of,
            symbol=canonical,
            last_price=mark_price,
            market_type=instrument.market_type,
            derivative=DerivativeMarketContext(
                observed_at=observed_at,
                instrument=instrument,
                mark_price=mark_price,
                index_price=index_price,
                funding_rate=funding_rate,
            ),
        )
        if self._market_sink is not None:
            self._market_sink.mark_derivative_market(state)
        return state

    async def refresh_instruments(self) -> dict[str, DerivativeInstrument]:
        discovered = await self._rest_client.fetch_instruments()
        mapping: dict[str, DerivativeInstrument] = {}
        for instrument in discovered:
            existing = mapping.get(instrument.symbol)
            if existing is not None and existing.venue_symbol != instrument.venue_symbol:
                # Prefer a linear perpetual for the canonical pair. This is the only derivative
                # family executable in Batch 16 and avoids ambiguous canonical mappings.
                if (
                    existing.market_type is MarketType.PERPETUAL
                    and existing.contract_kind is DerivativeContractKind.LINEAR
                ):
                    continue
                if not (
                    instrument.market_type is MarketType.PERPETUAL
                    and instrument.contract_kind is DerivativeContractKind.LINEAR
                ):
                    continue
            mapping[instrument.symbol] = instrument
        self._instruments = mapping
        return mapping

    async def aclose(self) -> None:
        await self._rest_client.aclose()

    async def _instrument(self, symbol: str) -> DerivativeInstrument:
        registry = self._instruments or await self.refresh_instruments()
        instrument = registry.get(symbol)
        if instrument is None:
            raise UnknownKrakenSymbolError(
                f"no Kraken Derivatives instrument mapped to {symbol}"
            )
        return instrument


def parse_kraken_derivatives_instruments(payload: object) -> tuple[DerivativeInstrument, ...]:
    """Normalize public /instruments data without assuming a private account tier."""

    root = _mapping(payload, "Kraken Derivatives instruments payload")
    result = root.get("result")
    if result is not None and result != "success":
        raise KrakenPayloadError("Kraken Derivatives instruments returned an API error")
    rows = root.get("instruments")
    if not isinstance(rows, list):
        raise KrakenPayloadError("Kraken Derivatives instruments must contain an array")

    parsed: list[DerivativeInstrument] = []
    for raw in rows:
        if not isinstance(raw, Mapping) or raw.get("tradeable") is False:
            continue
        venue_symbol = _non_empty_text(raw.get("symbol"), "instrument symbol").upper()
        market_type, contract_kind = _contract_classification(
            venue_symbol,
            _optional_text(raw.get("type")),
        )
        canonical, base_asset, quote_asset = _instrument_pair(raw, venue_symbol)
        contract_size = _positive_decimal(raw.get("contractSize"), "contractSize")
        tick_size = _positive_decimal(raw.get("tickSize"), "tickSize")
        min_order_quantity = _minimum_order_quantity(raw.get("contractValueTradePrecision"))
        max_position = _optional_positive_decimal(raw.get("maxPositionSize"))
        initial_margin, maintenance_margin = _conservative_margin_rates(raw)
        max_leverage = Decimal(1) / initial_margin
        expires_at = None
        if market_type is MarketType.FUTURE:
            expires_at = _datetime(raw.get("lastTradingTime"), "lastTradingTime")

        parsed.append(
            DerivativeInstrument(
                symbol=canonical,
                venue_symbol=venue_symbol,
                market_type=market_type,
                contract_kind=contract_kind,
                underlying_asset=base_asset,
                quote_asset=quote_asset,
                contract_size=contract_size,
                tick_size=tick_size,
                min_order_quantity=min_order_quantity,
                max_position_quantity=max_position,
                initial_margin_rate=initial_margin,
                maintenance_margin_rate=maintenance_margin,
                max_leverage=max_leverage,
                funding_interval_seconds=(
                    KRAKEN_DERIVATIVES_FUNDING_INTERVAL_SECONDS
                    if market_type is MarketType.PERPETUAL
                    else None
                ),
                expires_at=expires_at,
            )
        )
    if not parsed:
        raise KrakenPayloadError("Kraken Derivatives returned no usable instruments")
    return tuple(parsed)


def parse_kraken_derivatives_ticker(
    payload: object,
    *,
    instrument: DerivativeInstrument,
) -> tuple[datetime, Decimal, Decimal | None, Decimal | None]:
    """Return observed_at, mark, index and normalized relative funding per interval."""

    root = _mapping(payload, "Kraken Derivatives ticker payload")
    result = root.get("result")
    if result is not None and result != "success":
        raise KrakenPayloadError("Kraken Derivatives ticker returned an API error")
    raw = root.get("ticker")
    if not isinstance(raw, Mapping):
        # Compatibility with the all-tickers shape used by test fixtures/older clients.
        tickers = root.get("tickers")
        if isinstance(tickers, list):
            raw = next(
                (
                    item
                    for item in tickers
                    if isinstance(item, Mapping)
                    and str(item.get("symbol", "")).upper() == instrument.venue_symbol
                ),
                None,
            )
    if not isinstance(raw, Mapping):
        raise KrakenPayloadError("Kraken Derivatives ticker object is missing")
    raw_symbol = _non_empty_text(raw.get("symbol"), "ticker symbol").upper()
    if raw_symbol != instrument.venue_symbol:
        raise KrakenPayloadError("Kraken Derivatives ticker symbol mismatch")

    mark_price = _positive_decimal(
        raw.get("markPrice", raw.get("mark_price", raw.get("last"))),
        "markPrice",
    )
    index_price = _optional_positive_decimal(raw.get("indexPrice", raw.get("index")))
    observed_at = _datetime(root.get("serverTime"), "serverTime")

    funding_rate: Decimal | None = None
    if instrument.market_type is MarketType.PERPETUAL:
        raw_funding = raw.get("fundingRate")
        if raw_funding is not None:
            absolute_funding = _decimal(raw_funding, "fundingRate")
            # Kraken Futures exposes the funding amount per contract. Normalize it to a
            # dimensionless rate so the provider-agnostic PAPER ledger can accrue notional*rate.
            funding_rate = absolute_funding / (mark_price * instrument.contract_size)
    return observed_at, mark_price, index_price, funding_rate


def _conservative_margin_rates(raw: Mapping[str, Any]) -> tuple[Decimal, Decimal]:
    schedules: list[Mapping[str, Any]] = []
    for key in ("marginLevels", "retailMarginLevels"):
        value = raw.get(key)
        if isinstance(value, list):
            schedules.extend(item for item in value if isinstance(item, Mapping))
    if not schedules:
        raise KrakenPayloadError("derivative instrument has no public margin levels")
    initials = [
        _positive_decimal(item.get("initialMargin"), "initialMargin") for item in schedules
    ]
    maintenance = [
        _positive_decimal(item.get("maintenanceMargin"), "maintenanceMargin")
        for item in schedules
    ]
    # Public metadata cannot tell us which account/regulatory schedule applies. Batch 16
    # therefore chooses the most conservative public rates instead of guessing the user's tier.
    return max(initials), max(maintenance)


def _minimum_order_quantity(value: object) -> Decimal:
    if value is None:
        return Decimal(1)
    precision = _decimal(value, "contractValueTradePrecision")
    if precision != precision.to_integral_value() or precision < 0 or precision > 18:
        raise KrakenPayloadError("contractValueTradePrecision is invalid")
    return Decimal(1).scaleb(-int(precision))


def _contract_classification(
    venue_symbol: str,
    raw_type: str | None,
) -> tuple[MarketType, DerivativeContractKind]:
    prefix = venue_symbol.split("_", 1)[0].upper()
    if prefix in {"PF", "PI"}:
        market_type = MarketType.PERPETUAL
    elif prefix in {"FF", "FI", "FV"}:
        market_type = MarketType.FUTURE
    else:
        market_type = (
            MarketType.PERPETUAL
            if raw_type is not None and "perpet" in raw_type.lower()
            else MarketType.FUTURE
        )
    if prefix in {"PF", "FF", "FV"}:
        kind = DerivativeContractKind.LINEAR
    elif prefix in {"PI", "FI"} or (
        raw_type is not None and "inverse" in raw_type.lower()
    ):
        kind = DerivativeContractKind.INVERSE
    else:
        kind = DerivativeContractKind.LINEAR
    return market_type, kind


def _instrument_pair(
    raw: Mapping[str, Any],
    venue_symbol: str,
) -> tuple[str, str, str]:
    raw_base = _optional_text(raw.get("base"))
    raw_quote = _optional_text(raw.get("quote"))
    if raw_base is not None and raw_quote is not None:
        base = _asset(raw_base)
        quote = _asset(raw_quote)
        canonical = f"{base}/{quote}"
        parse_canonical_symbol(canonical)
        return canonical, base, quote

    body = venue_symbol.split("_", 1)[-1]
    if "_" in body:
        body = body.split("_", 1)[0]
    for quote_code in _QUOTE_CANDIDATES:
        if body.endswith(quote_code) and len(body) > len(quote_code):
            base = _asset(body[: -len(quote_code)])
            quote = _asset(quote_code)
            canonical = f"{base}/{quote}"
            parse_canonical_symbol(canonical)
            return canonical, base, quote
    raise KrakenPayloadError(f"cannot normalize Kraken Derivatives symbol {venue_symbol}")


def _canonical_symbol(value: str) -> str:
    base, quote = parse_canonical_symbol(value)
    return f"{_asset(base)}/{_asset(quote)}"


def _asset(value: str) -> str:
    token = value.strip().upper()
    return _ASSET_ALIASES.get(token, token)


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise KrakenPayloadError(f"{label} must be an object")
    return value


def _non_empty_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KrakenPayloadError(f"{label} is invalid")
    return value.strip()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise KrakenPayloadError("Kraken Derivatives text field is invalid")
    return value.strip()


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


def _positive_decimal(value: object, label: str) -> Decimal:
    number = _decimal(value, label)
    if number <= 0:
        raise KrakenPayloadError(f"{label} must be positive")
    return number


def _optional_positive_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    return _positive_decimal(value, "positive decimal")


def _datetime(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise KrakenPayloadError(f"{label} is invalid")
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise KrakenPayloadError(f"{label} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise KrakenPayloadError(f"{label} must be timezone-aware")
    return parsed.astimezone(UTC)
