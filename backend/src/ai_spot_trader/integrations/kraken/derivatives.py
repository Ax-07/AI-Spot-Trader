import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

import httpx

from ai_spot_trader.core.clock import Clock, SystemClock
from ai_spot_trader.domain.derivative_margin import (
    DerivativeMarginTier,
    TieredDerivativeInstrument,
)
from ai_spot_trader.domain.enums import DerivativeContractKind, MarketType
from ai_spot_trader.domain.models import (
    DerivativeInstrument,
    DerivativeMarketContext,
    MarketObservation,
    MarketState,
)
from ai_spot_trader.domain.symbols import parse_canonical_symbol
from ai_spot_trader.integrations.kraken.errors import (
    KrakenConnectionError,
    KrakenPayloadError,
    StaleMarketDataError,
    UnknownKrakenSymbolError,
)
from ai_spot_trader.market import DEFAULT_MARKET_HORIZONS, MarketStateBuilder

KRAKEN_DERIVATIVES_FUNDING_INTERVAL_SECONDS = Decimal(3600)
KRAKEN_DERIVATIVES_HISTORY_RESOLUTION = "1m"
_DERIVATIVES_HISTORY_INTERVAL = timedelta(minutes=1)
_HISTORY_PADDING_INTERVALS = 2
_ASSET_ALIASES = {"XBT": "BTC", "XDG": "DOGE"}
_QUOTE_CANDIDATES = ("USDC", "USDT", "USD", "EUR", "GBP", "BTC", "ETH")
_MARGIN_LEVEL_KEYS = frozenset(
    {"contracts", "numNonContractUnits", "initialMargin", "maintenanceMargin"}
)


@dataclass(frozen=True, slots=True)
class _ParsedMarginCurve:
    source: str
    tiers: tuple[DerivativeMarginTier, ...]


class DerivativeMarketSink(Protocol):
    """Optional PAPER portfolio hook for mark-to-market/funding before AgentInput."""

    def mark_derivative_market(self, market_state: MarketState) -> None: ...


class KrakenDerivativesRestSource(Protocol):
    async def fetch_instruments(self) -> tuple[DerivativeInstrument, ...]: ...

    async def fetch_ticker(
        self,
        instrument: DerivativeInstrument,
    ) -> tuple[datetime, Decimal, Decimal | None, Decimal | None]: ...

    async def fetch_mark_history(
        self,
        instrument: DerivativeInstrument,
        *,
        since: datetime,
        until: datetime,
    ) -> tuple[MarketObservation, ...]: ...

    async def aclose(self) -> None: ...


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
        self._charts_base_url = str(
            httpx.URL(base_url).copy_with(path="/api/charts/v1", query=None, fragment=None)
        ).rstrip("/")

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

    async def fetch_mark_history(
        self,
        instrument: DerivativeInstrument,
        *,
        since: datetime,
        until: datetime,
    ) -> tuple[MarketObservation, ...]:
        if since.tzinfo is None or since.utcoffset() is None:
            raise ValueError("Kraken Derivatives chart since must be timezone-aware")
        if until.tzinfo is None or until.utcoffset() is None:
            raise ValueError("Kraken Derivatives chart until must be timezone-aware")
        if since > until:
            raise ValueError("Kraken Derivatives chart since cannot be newer than until")

        payload = await self._get_json(
            (
                f"{self._charts_base_url}/mark/"
                f"{instrument.venue_symbol}/{KRAKEN_DERIVATIVES_HISTORY_RESOLUTION}"
            ),
            "Kraken Derivatives mark candles",
            params={"from": int(since.timestamp()), "to": int(until.timestamp())},
        )
        return parse_kraken_derivatives_mark_candles(payload, instrument=instrument)

    async def _get_json(
        self,
        path: str,
        label: str,
        *,
        params: Mapping[str, str | int] | None = None,
    ) -> object:
        try:
            response = await self._client.get(path, params=params)
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
        rest_client: KrakenDerivativesRestSource,
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
        self._builders: dict[str, MarketStateBuilder] = {}
        self._latest_current_observations: dict[str, MarketObservation] = {}

    async def snapshot(self, symbol: str) -> MarketState:
        canonical = _canonical_symbol(symbol)
        instrument = await self._instrument(canonical)
        observed_at, mark_price, index_price, funding_rate = await self._rest_client.fetch_ticker(
            instrument
        )
        current_observation = MarketObservation(
            observed_at=observed_at,
            symbol=canonical,
            last_price=mark_price,
        )
        self._validate_current_sequence(current_observation)

        builder = self._builders.get(canonical)
        if builder is None:
            builder = MarketStateBuilder(
                horizons=DEFAULT_MARKET_HORIZONS,
                stale_after=self._stale_after,
                clock=self._clock,
            )
            self._builders[canonical] = builder

        history = await self._rest_client.fetch_mark_history(
            instrument,
            since=observed_at
            - max(DEFAULT_MARKET_HORIZONS)
            - (_DERIVATIVES_HISTORY_INTERVAL * _HISTORY_PADDING_INTERVALS),
            until=observed_at,
        )
        as_of = self._clock.now()
        if observed_at > as_of:
            raise KrakenPayloadError("Kraken Derivatives ticker is newer than the local clock")
        if self._stale_after is not None and as_of - observed_at > self._stale_after:
            raise StaleMarketDataError(
                f"Kraken Derivatives market data is stale for {canonical}"
            )

        self._append_history(
            builder,
            symbol=canonical,
            history=history,
            before=observed_at,
        )
        retained = builder.retained_observations
        statistics_as_of = retained[-1].observed_at if retained else as_of
        base_state = builder.build(
            as_of=as_of,
            current_observation=current_observation,
            statistics_as_of=statistics_as_of,
        )
        state = MarketState(
            market_state_id=base_state.market_state_id,
            as_of=base_state.as_of,
            symbol=base_state.symbol,
            last_price=base_state.last_price,
            context=base_state.context,
            market_type=instrument.market_type,
            derivative=DerivativeMarketContext(
                observed_at=observed_at,
                instrument=instrument,
                mark_price=mark_price,
                index_price=index_price,
                funding_rate=funding_rate,
            ),
        )
        self._latest_current_observations[canonical] = current_observation
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

    def _append_history(
        self,
        builder: MarketStateBuilder,
        *,
        symbol: str,
        history: tuple[MarketObservation, ...],
        before: datetime,
    ) -> None:
        for observation in history:
            if observation.symbol != symbol:
                raise KrakenPayloadError("Kraken Derivatives mark candle symbol mismatch")
            if observation.observed_at >= before:
                continue
            latest = builder.retained_observations[-1] if builder.retained_observations else None
            if latest is not None and observation.observed_at <= latest.observed_at:
                continue
            builder.add_observation(observation)

    def _validate_current_sequence(self, observation: MarketObservation) -> None:
        previous = self._latest_current_observations.get(observation.symbol)
        if previous is None:
            return
        if observation.observed_at < previous.observed_at:
            raise KrakenPayloadError("Kraken Derivatives ticker timestamp moved backwards")
        if (
            observation.observed_at == previous.observed_at
            and observation.last_price != previous.last_price
        ):
            raise KrakenPayloadError(
                "Kraken Derivatives ticker conflicts with previous current observation"
            )


def parse_kraken_derivatives_mark_candles(
    payload: object,
    *,
    instrument: DerivativeInstrument,
) -> tuple[MarketObservation, ...]:
    """Normalize public one-minute mark candles into causal close observations."""

    root = _mapping(payload, "Kraken Derivatives mark candles payload")
    rows = root.get("candles")
    if not isinstance(rows, list):
        raise KrakenPayloadError("Kraken Derivatives mark candles must contain an array")

    observations: list[MarketObservation] = []
    previous_started_at: datetime | None = None
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise KrakenPayloadError("Kraken Derivatives mark candles contain an invalid entry")
        started_at = _epoch_milliseconds(raw.get("time"), "mark candle time")
        if previous_started_at is not None and started_at <= previous_started_at:
            raise KrakenPayloadError(
                "Kraken Derivatives mark candles are not strictly chronological"
            )
        previous_started_at = started_at
        observations.append(
            MarketObservation(
                observed_at=started_at + _DERIVATIVES_HISTORY_INTERVAL,
                symbol=instrument.symbol,
                last_price=_positive_decimal(raw.get("close"), "mark candle close"),
            )
        )
    return tuple(observations)


def parse_kraken_derivatives_instruments(payload: object) -> tuple[DerivativeInstrument, ...]:
    """Normalize public /instruments data and retain one explicit tier curve when safe."""

    root = _mapping(payload, "Kraken Derivatives instruments payload")
    result = root.get("result")
    if result is not None and result != "success":
        raise KrakenPayloadError("Kraken Derivatives instruments returned an API error")
    rows = root.get("instruments")
    if not isinstance(rows, list):
        raise KrakenPayloadError("Kraken Derivatives instruments must contain an array")

    parsed: list[DerivativeInstrument] = []
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise KrakenPayloadError("Kraken Derivatives instruments contain an invalid entry")
        tradeable = raw.get("tradeable")
        if not isinstance(tradeable, bool):
            raise KrakenPayloadError("derivative instrument tradeable flag is invalid")
        if not tradeable:
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
        if max_position is not None and max_position < min_order_quantity:
            raise KrakenPayloadError(
                "maxPositionSize cannot be smaller than the minimum order quantity"
            )
        margin_curve, initial_margin, maintenance_margin, schedule_source = _margin_metadata(raw)
        max_leverage = Decimal(1) / initial_margin
        expires_at = None
        if market_type is MarketType.FUTURE:
            expires_at = _datetime(raw.get("lastTradingTime"), "lastTradingTime")

        instrument_kwargs: dict[str, Any] = {
            "symbol": canonical,
            "venue_symbol": venue_symbol,
            "market_type": market_type,
            "contract_kind": contract_kind,
            "underlying_asset": base_asset,
            "quote_asset": quote_asset,
            "contract_size": contract_size,
            "tick_size": tick_size,
            "min_order_quantity": min_order_quantity,
            "max_position_quantity": max_position,
            "initial_margin_rate": initial_margin,
            "maintenance_margin_rate": maintenance_margin,
            "max_leverage": max_leverage,
            "funding_interval_seconds": (
                KRAKEN_DERIVATIVES_FUNDING_INTERVAL_SECONDS
                if market_type is MarketType.PERPETUAL
                else None
            ),
            "expires_at": expires_at,
        }
        if margin_curve is None:
            parsed.append(DerivativeInstrument(**instrument_kwargs))
        else:
            assert schedule_source is not None
            parsed.append(
                TieredDerivativeInstrument(
                    **instrument_kwargs,
                    margin_tiers=margin_curve,
                    margin_schedule_source=schedule_source,
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

    suspended = _optional_boolean_alias(raw, ("suspended",), "ticker suspended")
    post_only = _optional_boolean_alias(raw, ("postOnly", "post_only"), "ticker postOnly")
    if suspended is True:
        raise KrakenPayloadError("Kraken Derivatives ticker is suspended")
    if post_only is True:
        raise KrakenPayloadError("Kraken Derivatives ticker is post-only")

    raw_mark_price = raw.get("markPrice") if "markPrice" in raw else raw.get("mark_price")
    mark_price = _positive_decimal(raw_mark_price, "markPrice")
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


def _margin_metadata(
    raw: Mapping[str, Any],
) -> tuple[
    tuple[DerivativeMarginTier, ...] | None,
    Decimal,
    Decimal,
    str | None,
]:
    """Validate public schedules and select one explicit PAPER curve without merging regimes."""

    curves: list[_ParsedMarginCurve] = []
    direct: dict[str, _ParsedMarginCurve] = {}
    for key in ("marginLevels", "retailMarginLevels"):
        value = raw.get(key)
        if value is None:
            continue
        if not isinstance(value, list):
            raise KrakenPayloadError(f"{key} must be an array")
        curve = _parse_margin_curve(value, source=key)
        if curve is not None:
            curves.append(curve)
            direct[key] = curve

    named = raw.get("marginSchedules")
    named_curves: list[_ParsedMarginCurve] = []
    if named is not None:
        if not isinstance(named, Mapping):
            raise KrakenPayloadError("marginSchedules must be an object")
        named_curves = list(_margin_schedule_curves(named))
        curves.extend(named_curves)

    if not curves:
        raise KrakenPayloadError("derivative instrument has no public margin levels")

    # PAPER v1 is explicitly modeled as the public retail schedule when Kraken exposes it.
    # This is conservative relative to generic/professional schedules and does not infer a
    # private account entitlement. We never merge it with another schedule.
    selected = direct.get("retailMarginLevels")
    unique_named: dict[
        tuple[tuple[Decimal, str, Decimal, Decimal], ...], _ParsedMarginCurve
    ] = {}
    for curve in named_curves:
        signature = tuple(
            (
                tier.threshold,
                tier.threshold_basis,
                tier.initial_margin_rate,
                tier.maintenance_margin_rate,
            )
            for tier in curve.tiers
        )
        unique_named.setdefault(signature, curve)

    if selected is None:
        generic = direct.get("marginLevels")
        if not named_curves:
            selected = generic
        elif generic is None and len(unique_named) == 1:
            selected = next(iter(unique_named.values()))
        elif generic is not None and len(unique_named) == 1:
            only_named = next(iter(unique_named.values()))
            generic_signature = tuple(
                (
                    tier.threshold,
                    tier.threshold_basis,
                    tier.initial_margin_rate,
                    tier.maintenance_margin_rate,
                )
                for tier in generic.tiers
            )
            named_signature = tuple(
                (
                    tier.threshold,
                    tier.threshold_basis,
                    tier.initial_margin_rate,
                    tier.maintenance_margin_rate,
                )
                for tier in only_named.tiers
            )
            if generic_signature == named_signature:
                selected = generic

    if selected is not None:
        first = selected.tiers[0]
        return (
            selected.tiers,
            first.initial_margin_rate,
            first.maintenance_margin_rate,
            selected.source,
        )

    # Ambiguous named schedules are kept fail-closed. Preserve the old conservative scalar
    # behavior rather than pretending mutually exclusive account/regulatory curves are tiers.
    all_tiers = tuple(tier for curve in curves for tier in curve.tiers)
    return (
        None,
        max(tier.initial_margin_rate for tier in all_tiers),
        max(tier.maintenance_margin_rate for tier in all_tiers),
        None,
    )


def _parse_margin_curve(
    rows: list[object] | tuple[Mapping[str, Any], ...],
    *,
    source: str,
) -> _ParsedMarginCurve | None:
    if not rows:
        return None
    tiers: list[DerivativeMarginTier] = []
    for raw_item in rows:
        if not isinstance(raw_item, Mapping):
            raise KrakenPayloadError(f"{source} contains an invalid margin level")
        has_contracts = "contracts" in raw_item
        has_non_contracts = "numNonContractUnits" in raw_item
        if has_contracts == has_non_contracts:
            raise KrakenPayloadError(
                f"{source} margin level must contain exactly one size threshold"
            )
        threshold_key = "contracts" if has_contracts else "numNonContractUnits"
        threshold = _decimal(raw_item.get(threshold_key), threshold_key)
        if threshold < 0:
            raise KrakenPayloadError(f"{threshold_key} cannot be negative")
        initial = _positive_decimal(raw_item.get("initialMargin"), "initialMargin")
        maintenance = _positive_decimal(
            raw_item.get("maintenanceMargin"),
            "maintenanceMargin",
        )
        if initial > Decimal(1):
            raise KrakenPayloadError("initialMargin cannot exceed 1")
        if maintenance > initial:
            raise KrakenPayloadError("maintenanceMargin cannot exceed initialMargin")
        tiers.append(
            DerivativeMarginTier(
                threshold=threshold,
                threshold_basis=(
                    "CONTRACTS" if threshold_key == "contracts" else "POSITION_NOTIONAL"
                ),
                initial_margin_rate=initial,
                maintenance_margin_rate=maintenance,
            )
        )

    bases = {tier.threshold_basis for tier in tiers}
    if len(bases) != 1:
        raise KrakenPayloadError(f"{source} mixes incompatible margin threshold units")
    tiers.sort(key=lambda tier: tier.threshold)
    thresholds = tuple(tier.threshold for tier in tiers)
    if len(set(thresholds)) != len(thresholds):
        raise KrakenPayloadError(f"{source} contains duplicate margin thresholds")
    if thresholds[0] != 0:
        raise KrakenPayloadError(f"{source} margin levels must start at zero")
    initials = tuple(tier.initial_margin_rate for tier in tiers)
    maintenance_rates = tuple(tier.maintenance_margin_rate for tier in tiers)
    if initials != tuple(sorted(initials)):
        raise KrakenPayloadError(f"{source} initialMargin cannot decrease by size")
    if maintenance_rates != tuple(sorted(maintenance_rates)):
        raise KrakenPayloadError(f"{source} maintenanceMargin cannot decrease by size")
    return _ParsedMarginCurve(source=source, tiers=tuple(tiers))


def _margin_schedule_curves(
    value: Mapping[str, Any],
    *,
    path: str = "marginSchedules",
) -> tuple[_ParsedMarginCurve, ...]:
    curves: list[_ParsedMarginCurve] = []
    for schedule_name, item in value.items():
        if not isinstance(schedule_name, str) or not schedule_name.strip():
            raise KrakenPayloadError("marginSchedules contains an invalid schedule name")
        source = f"{path}.{schedule_name.strip()}"
        if isinstance(item, list):
            curve = _parse_margin_curve(item, source=source)
            if curve is not None:
                curves.append(curve)
            continue
        if isinstance(item, Mapping):
            if _MARGIN_LEVEL_KEYS.intersection(item):
                curve = _parse_margin_curve((item,), source=source)
                if curve is not None:
                    curves.append(curve)
                continue
            curves.extend(_margin_schedule_curves(item, path=source))
            continue
        raise KrakenPayloadError("marginSchedules contains an invalid margin level")
    return tuple(curves)


def _minimum_order_quantity(value: object) -> Decimal:
    if value is None:
        raise KrakenPayloadError("contractValueTradePrecision is missing")
    precision = _decimal(value, "contractValueTradePrecision")
    if precision != precision.to_integral_value() or precision < -18 or precision > 18:
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


def _optional_boolean_alias(
    raw: Mapping[str, Any],
    keys: tuple[str, ...],
    label: str,
) -> bool | None:
    values: list[bool] = []
    for key in keys:
        if key not in raw:
            continue
        value = raw.get(key)
        if not isinstance(value, bool):
            raise KrakenPayloadError(f"{label} flag is invalid")
        values.append(value)
    if not values:
        return None
    if len(set(values)) != 1:
        raise KrakenPayloadError(f"{label} aliases conflict")
    return values[0]


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


def _epoch_milliseconds(value: object, label: str) -> datetime:
    number = _decimal(value, label)
    if number != number.to_integral_value():
        raise KrakenPayloadError(f"{label} must be an integer epoch millisecond value")
    milliseconds = int(number)
    seconds, remainder = divmod(milliseconds, 1000)
    try:
        return datetime.fromtimestamp(seconds, tz=UTC) + timedelta(milliseconds=remainder)
    except (OverflowError, OSError, ValueError) as exc:
        raise KrakenPayloadError(f"{label} is invalid") from exc
