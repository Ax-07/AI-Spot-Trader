from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from statistics import median
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.domain.symbols import parse_canonical_symbol

_BPS = Decimal("10000")
_ZERO = Decimal(0)
_ONE = Decimal(1)


class MicrostructureStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    STALE = "STALE"
    ERROR = "ERROR"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class MicrostructureDataQuality(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    STALE = "STALE"
    TECHNICAL_ERROR = "TECHNICAL_ERROR"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class TradeSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class MicrostructureCharacteristic(StrEnum):
    """Descriptive microstructure facts; none is a trading instruction."""

    TIGHT_SPREAD = "TIGHT_SPREAD"
    WIDE_SPREAD = "WIDE_SPREAD"
    DEEP_LIQUIDITY = "DEEP_LIQUIDITY"
    THIN_LIQUIDITY = "THIN_LIQUIDITY"
    ORDER_BOOK_IMBALANCE = "ORDER_BOOK_IMBALANCE"
    TRADE_ACTIVITY_SURGE = "TRADE_ACTIVITY_SURGE"
    TRADE_ACTIVITY_FADE = "TRADE_ACTIVITY_FADE"
    BUY_PRESSURE = "BUY_PRESSURE"
    SELL_PRESSURE = "SELL_PRESSURE"
    SLIPPAGE_RISK = "SLIPPAGE_RISK"


class MicrostructureModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MicrostructurePolicy(MicrostructureModel):
    """Bounded deterministic policy for Kraken SPOT microstructure snapshots."""

    book_levels: int = Field(default=100, ge=10, le=500)
    trade_count: int = Field(default=1000, ge=100, le=1000)
    market_limit_per_refresh: int = Field(default=24, ge=1, le=120)
    concurrency: int = Field(default=4, ge=1, le=16)
    cache_ttl_seconds: float = Field(default=900.0, ge=60.0, le=3600.0)
    refresh_seconds: float = Field(default=300.0, ge=30.0, le=3600.0)
    stale_after_seconds: float = Field(default=420.0, ge=30.0, le=3600.0)
    trade_current_window_seconds: int = Field(default=60, ge=15, le=300)
    trade_baseline_window_seconds: int = Field(default=300, ge=60, le=1800)
    depth_bands_bps: tuple[int, ...] = (5, 10, 25, 50)
    slippage_notionals_quote: tuple[Decimal, ...] = (
        Decimal("100"),
        Decimal("500"),
        Decimal("1000"),
        Decimal("5000"),
    )

    @model_validator(mode="after")
    def validate_policy(self) -> "MicrostructurePolicy":
        if self.trade_baseline_window_seconds <= self.trade_current_window_seconds:
            raise ValueError("trade baseline window must exceed current window")
        if not self.depth_bands_bps:
            raise ValueError("at least one depth band is required")
        if tuple(sorted(set(self.depth_bands_bps))) != self.depth_bands_bps:
            raise ValueError("depth bands must be unique and strictly increasing")
        if any(value <= 0 or value > 1000 for value in self.depth_bands_bps):
            raise ValueError("depth bands must be within 1..1000 bps")
        if not self.slippage_notionals_quote:
            raise ValueError("at least one theoretical slippage notional is required")
        if any(value <= 0 or not value.is_finite() for value in self.slippage_notionals_quote):
            raise ValueError("slippage notionals must be finite and positive")
        return self


class OrderBookLevel(MicrostructureModel):
    price: Decimal = Field(gt=0)
    volume_base: Decimal = Field(ge=0)
    level_timestamp: datetime | None = None

    @model_validator(mode="after")
    def validate_timestamp(self) -> "OrderBookLevel":
        if self.level_timestamp is not None:
            _require_aware(self.level_timestamp, "order-book level timestamp")
        return self


class OrderBookSnapshot(MicrostructureModel):
    observed_at: datetime
    bids: tuple[OrderBookLevel, ...]
    asks: tuple[OrderBookLevel, ...]
    source: Literal["KRAKEN_SPOT_REST_L2"] = "KRAKEN_SPOT_REST_L2"

    @model_validator(mode="after")
    def validate_observed_at(self) -> "OrderBookSnapshot":
        _require_aware(self.observed_at, "order-book observed_at")
        return self


class RecentTrade(MicrostructureModel):
    price: Decimal = Field(gt=0)
    volume_base: Decimal = Field(gt=0)
    occurred_at: datetime
    side: TradeSide | None = None
    trade_id: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_occurred_at(self) -> "RecentTrade":
        _require_aware(self.occurred_at, "trade occurred_at")
        return self


class RecentTradesSnapshot(MicrostructureModel):
    observed_at: datetime
    trades: tuple[RecentTrade, ...]
    source: Literal["KRAKEN_SPOT_REST_TRADES"] = "KRAKEN_SPOT_REST_TRADES"

    @model_validator(mode="after")
    def validate_observed_at(self) -> "RecentTradesSnapshot":
        _require_aware(self.observed_at, "trades observed_at")
        return self


class DepthBandSnapshot(MicrostructureModel):
    band_bps: int = Field(gt=0)
    bid_depth_base: Decimal = Field(ge=0)
    ask_depth_base: Decimal = Field(ge=0)
    bid_depth_quote: Decimal = Field(ge=0)
    ask_depth_quote: Decimal = Field(ge=0)


class SlippageEstimate(MicrostructureModel):
    side: Literal["BUY", "SELL"]
    notional_quote: Decimal = Field(gt=0)
    quote_asset: str = Field(min_length=1)
    estimated_vwap: Decimal | None = Field(default=None, gt=0)
    reference_price: Decimal | None = Field(default=None, gt=0)
    slippage_absolute: Decimal | None = Field(default=None, ge=0)
    slippage_bps: Decimal | None = Field(default=None, ge=0)
    consumed_volume_base: Decimal = Field(default=Decimal(0), ge=0)
    available_notional_quote: Decimal = Field(default=Decimal(0), ge=0)
    insufficient_depth: bool = False


class MarketMicrostructureSnapshot(MicrostructureModel):
    market: ExecutableMarket
    observed_at: datetime
    status: MicrostructureStatus
    data_quality: MicrostructureDataQuality
    freshness_seconds: Decimal | None = Field(default=None, ge=0)
    book_freshness_seconds: Decimal | None = Field(default=None, ge=0)
    trade_freshness_seconds: Decimal | None = Field(default=None, ge=0)
    quote_asset: str | None = None

    best_bid: Decimal | None = Field(default=None, gt=0)
    best_ask: Decimal | None = Field(default=None, gt=0)
    mid_price: Decimal | None = Field(default=None, gt=0)
    spread_absolute: Decimal | None = Field(default=None, ge=0)
    spread_bps: Decimal | None = Field(default=None, ge=0)
    bid_depth_base: Decimal | None = Field(default=None, ge=0)
    ask_depth_base: Decimal | None = Field(default=None, ge=0)
    bid_depth_quote: Decimal | None = Field(default=None, ge=0)
    ask_depth_quote: Decimal | None = Field(default=None, ge=0)
    total_depth_quote: Decimal | None = Field(default=None, ge=0)
    book_imbalance: Decimal | None = Field(default=None, ge=-1, le=1)
    depth_bands: tuple[DepthBandSnapshot, ...] = ()

    trade_count: int | None = Field(default=None, ge=0)
    trade_volume_base: Decimal | None = Field(default=None, ge=0)
    trade_volume_quote: Decimal | None = Field(default=None, ge=0)
    average_trade_size_base: Decimal | None = Field(default=None, ge=0)
    median_trade_size_base: Decimal | None = Field(default=None, ge=0)
    trade_rate_per_minute: Decimal | None = Field(default=None, ge=0)
    baseline_trade_rate_per_minute: Decimal | None = Field(default=None, ge=0)
    trade_activity_ratio: Decimal | None = Field(default=None, ge=0)
    trade_activity_change_per_minute: Decimal | None = None
    provider_side_coverage: Decimal | None = Field(default=None, ge=0, le=1)
    buy_volume_base: Decimal | None = Field(default=None, ge=0)
    sell_volume_base: Decimal | None = Field(default=None, ge=0)
    buy_sell_imbalance: Decimal | None = Field(default=None, ge=-1, le=1)

    slippage: tuple[SlippageEstimate, ...] = ()
    characteristics: tuple[MicrostructureCharacteristic, ...] = ()
    errors: tuple[str, ...] = ()
    error_type: str | None = None

    @model_validator(mode="after")
    def validate_snapshot(self) -> "MarketMicrostructureSnapshot":
        _require_aware(self.observed_at, "microstructure observed_at")
        if self.market.market_type is not MarketType.SPOT:
            if self.status is not MicrostructureStatus.NOT_APPLICABLE:
                raise ValueError("non-SPOT microstructure must be NOT_APPLICABLE")
            if self.data_quality is not MicrostructureDataQuality.NOT_APPLICABLE:
                raise ValueError("non-SPOT microstructure quality must be NOT_APPLICABLE")
        return self

    def slippage_for(
        self,
        side: Literal["BUY", "SELL"],
        notional_quote: Decimal,
    ) -> SlippageEstimate | None:
        return next(
            (
                item
                for item in self.slippage
                if item.side == side and item.notional_quote == notional_quote
            ),
            None,
        )


class MicrostructureProvider(Protocol):
    async def fetch_order_book(self, symbol: str, *, limit: int) -> OrderBookSnapshot: ...

    async def fetch_recent_trades(self, symbol: str, *, limit: int) -> RecentTradesSnapshot: ...

    async def aclose(self) -> None: ...


class MarketMicrostructureAnalyzer:
    """Pure deterministic calculations over one bounded L2 + recent-trades snapshot."""

    def __init__(self, *, policy: MicrostructurePolicy | None = None) -> None:
        self.policy = policy or MicrostructurePolicy()

    def analyze(
        self,
        *,
        market: ExecutableMarket,
        observed_at: datetime,
        book: OrderBookSnapshot | None,
        trades: RecentTradesSnapshot | None,
        errors: tuple[str, ...] = (),
    ) -> MarketMicrostructureSnapshot:
        observed_at = _utc(observed_at)
        if market.market_type is not MarketType.SPOT:
            return not_applicable_microstructure(market=market, observed_at=observed_at)

        _base_asset, quote_asset = parse_canonical_symbol(market.symbol)
        book_metrics = self._book_metrics(book)
        trade_metrics = self._trade_metrics(trades, observed_at=observed_at)
        analysis_errors = list(errors)
        if book is not None and book_metrics is None:
            analysis_errors.append("InvalidOrEmptyOrderBook")

        available_components = int(book_metrics is not None) + int(trade_metrics is not None)
        if available_components == 0:
            normalized_errors = tuple(dict.fromkeys(analysis_errors))
            return MarketMicrostructureSnapshot(
                market=market,
                observed_at=observed_at,
                status=(
                    MicrostructureStatus.ERROR
                    if normalized_errors
                    else MicrostructureStatus.PARTIAL
                ),
                data_quality=(
                    MicrostructureDataQuality.TECHNICAL_ERROR
                    if normalized_errors
                    else MicrostructureDataQuality.PARTIAL
                ),
                quote_asset=quote_asset,
                errors=normalized_errors,
                error_type=(
                    normalized_errors[0]
                    if normalized_errors
                    else "MicrostructureUnavailable"
                ),
            )

        book_freshness = _snapshot_freshness(book.observed_at, observed_at) if book else None
        trade_freshness = _trade_freshness(trades, observed_at=observed_at) if trades else None
        freshness_values = tuple(
            value for value in (book_freshness, trade_freshness) if value is not None
        )
        freshness = max(freshness_values, default=None)
        stale_limit = Decimal(str(self.policy.stale_after_seconds))
        stale = bool(freshness_values) and all(value > stale_limit for value in freshness_values)

        status = MicrostructureStatus.AVAILABLE
        quality = MicrostructureDataQuality.COMPLETE
        if stale:
            status = MicrostructureStatus.STALE
            quality = MicrostructureDataQuality.STALE
        elif available_components < 2 or analysis_errors:
            status = MicrostructureStatus.PARTIAL
            quality = MicrostructureDataQuality.PARTIAL

        slippage: tuple[SlippageEstimate, ...] = ()
        if book_metrics is not None:
            slippage = tuple(
                estimate
                for notional in self.policy.slippage_notionals_quote
                for estimate in (
                    _estimate_slippage(
                        side="BUY",
                        levels=book_metrics["asks"],
                        notional_quote=notional,
                        quote_asset=quote_asset,
                        reference_price=book_metrics["best_ask"],
                    ),
                    _estimate_slippage(
                        side="SELL",
                        levels=book_metrics["bids"],
                        notional_quote=notional,
                        quote_asset=quote_asset,
                        reference_price=book_metrics["best_bid"],
                    ),
                )
            )

        characteristics = _microstructure_characteristics(
            spread_bps=book_metrics["spread_bps"] if book_metrics else None,
            book_imbalance=book_metrics["book_imbalance"] if book_metrics else None,
            trade_activity_ratio=(
                trade_metrics["trade_activity_ratio"] if trade_metrics else None
            ),
            current_trade_count=(trade_metrics["current_trade_count"] if trade_metrics else 0),
            buy_sell_imbalance=(
                trade_metrics["buy_sell_imbalance"] if trade_metrics else None
            ),
            slippage=slippage,
        )

        return MarketMicrostructureSnapshot(
            market=market,
            observed_at=observed_at,
            status=status,
            data_quality=quality,
            freshness_seconds=freshness,
            book_freshness_seconds=book_freshness,
            trade_freshness_seconds=trade_freshness,
            quote_asset=quote_asset,
            best_bid=book_metrics["best_bid"] if book_metrics else None,
            best_ask=book_metrics["best_ask"] if book_metrics else None,
            mid_price=book_metrics["mid_price"] if book_metrics else None,
            spread_absolute=book_metrics["spread_absolute"] if book_metrics else None,
            spread_bps=book_metrics["spread_bps"] if book_metrics else None,
            bid_depth_base=book_metrics["bid_depth_base"] if book_metrics else None,
            ask_depth_base=book_metrics["ask_depth_base"] if book_metrics else None,
            bid_depth_quote=book_metrics["bid_depth_quote"] if book_metrics else None,
            ask_depth_quote=book_metrics["ask_depth_quote"] if book_metrics else None,
            total_depth_quote=book_metrics["total_depth_quote"] if book_metrics else None,
            book_imbalance=book_metrics["book_imbalance"] if book_metrics else None,
            depth_bands=book_metrics["depth_bands"] if book_metrics else (),
            trade_count=trade_metrics["trade_count"] if trade_metrics else None,
            trade_volume_base=trade_metrics["trade_volume_base"] if trade_metrics else None,
            trade_volume_quote=trade_metrics["trade_volume_quote"] if trade_metrics else None,
            average_trade_size_base=(
                trade_metrics["average_trade_size_base"] if trade_metrics else None
            ),
            median_trade_size_base=(
                trade_metrics["median_trade_size_base"] if trade_metrics else None
            ),
            trade_rate_per_minute=(
                trade_metrics["trade_rate_per_minute"] if trade_metrics else None
            ),
            baseline_trade_rate_per_minute=(
                trade_metrics["baseline_trade_rate_per_minute"] if trade_metrics else None
            ),
            trade_activity_ratio=(
                trade_metrics["trade_activity_ratio"] if trade_metrics else None
            ),
            trade_activity_change_per_minute=(
                trade_metrics["trade_activity_change_per_minute"] if trade_metrics else None
            ),
            provider_side_coverage=(
                trade_metrics["provider_side_coverage"] if trade_metrics else None
            ),
            buy_volume_base=trade_metrics["buy_volume_base"] if trade_metrics else None,
            sell_volume_base=trade_metrics["sell_volume_base"] if trade_metrics else None,
            buy_sell_imbalance=(
                trade_metrics["buy_sell_imbalance"] if trade_metrics else None
            ),
            slippage=slippage,
            characteristics=characteristics,
            errors=tuple(dict.fromkeys(analysis_errors)),
            error_type=analysis_errors[0] if analysis_errors else None,
        )

    def _book_metrics(self, book: OrderBookSnapshot | None) -> dict[str, object] | None:
        if book is None:
            return None
        bids = _normalize_levels(book.bids, descending=True)
        asks = _normalize_levels(book.asks, descending=False)
        if not bids or not asks:
            return None

        best_bid = bids[0].price
        best_ask = asks[0].price
        if best_bid >= best_ask:
            return None
        mid = (best_bid + best_ask) / Decimal(2)
        spread = best_ask - best_bid
        spread_bps = _safe_ratio(spread * _BPS, mid)
        bid_depth_base = sum((item.volume_base for item in bids), _ZERO)
        ask_depth_base = sum((item.volume_base for item in asks), _ZERO)
        bid_depth_quote = sum((item.price * item.volume_base for item in bids), _ZERO)
        ask_depth_quote = sum((item.price * item.volume_base for item in asks), _ZERO)
        total_depth_quote = bid_depth_quote + ask_depth_quote
        book_imbalance = (
            _safe_ratio(bid_depth_quote - ask_depth_quote, total_depth_quote)
            if total_depth_quote > 0
            else None
        )
        depth_bands = tuple(
            DepthBandSnapshot(
                band_bps=band,
                bid_depth_base=sum(
                    (
                        level.volume_base
                        for level in bids
                        if _distance_bps(mid, level.price) <= Decimal(band)
                    ),
                    _ZERO,
                ),
                ask_depth_base=sum(
                    (
                        level.volume_base
                        for level in asks
                        if _distance_bps(mid, level.price) <= Decimal(band)
                    ),
                    _ZERO,
                ),
                bid_depth_quote=sum(
                    (
                        level.price * level.volume_base
                        for level in bids
                        if _distance_bps(mid, level.price) <= Decimal(band)
                    ),
                    _ZERO,
                ),
                ask_depth_quote=sum(
                    (
                        level.price * level.volume_base
                        for level in asks
                        if _distance_bps(mid, level.price) <= Decimal(band)
                    ),
                    _ZERO,
                ),
            )
            for band in self.policy.depth_bands_bps
        )
        return {
            "bids": bids,
            "asks": asks,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid_price": mid,
            "spread_absolute": spread,
            "spread_bps": spread_bps,
            "bid_depth_base": bid_depth_base,
            "ask_depth_base": ask_depth_base,
            "bid_depth_quote": bid_depth_quote,
            "ask_depth_quote": ask_depth_quote,
            "total_depth_quote": total_depth_quote,
            "book_imbalance": book_imbalance,
            "depth_bands": depth_bands,
        }

    def _trade_metrics(
        self,
        trades: RecentTradesSnapshot | None,
        *,
        observed_at: datetime,
    ) -> dict[str, object] | None:
        if trades is None:
            return None
        causal = tuple(
            sorted(
                (
                    item
                    for item in trades.trades
                    if item.occurred_at.astimezone(UTC) <= observed_at
                ),
                key=lambda item: (item.occurred_at, item.trade_id or -1),
            )
        )
        total_volume_base = sum((item.volume_base for item in causal), _ZERO)
        total_volume_quote = sum((item.price * item.volume_base for item in causal), _ZERO)
        sizes = tuple(item.volume_base for item in causal)
        average_size = _safe_ratio(total_volume_base, Decimal(len(causal))) if causal else None
        median_size = Decimal(median(sizes)) if sizes else None

        current_window = timedelta(seconds=self.policy.trade_current_window_seconds)
        baseline_window = timedelta(seconds=self.policy.trade_baseline_window_seconds)
        current_start = observed_at - current_window
        baseline_start = observed_at - baseline_window
        current = tuple(item for item in causal if item.occurred_at.astimezone(UTC) > current_start)
        baseline = tuple(
            item
            for item in causal
            if baseline_start < item.occurred_at.astimezone(UTC) <= current_start
        )
        current_rate = (
            Decimal(len(current)) * Decimal(60)
            / Decimal(self.policy.trade_current_window_seconds)
        )
        baseline_duration = self.policy.trade_baseline_window_seconds - self.policy.trade_current_window_seconds
        baseline_rate = Decimal(len(baseline)) * Decimal(60) / Decimal(baseline_duration)
        activity_ratio = _safe_ratio(current_rate, baseline_rate) if baseline_rate > 0 else None
        activity_change = current_rate - baseline_rate

        known_sides = tuple(item for item in current if item.side is not None)
        coverage = (
            Decimal(len(known_sides)) / Decimal(len(current)) if current else None
        )
        buy_volume: Decimal | None = None
        sell_volume: Decimal | None = None
        imbalance: Decimal | None = None
        if current and len(known_sides) == len(current):
            buy_volume = sum(
                (item.volume_base for item in current if item.side is TradeSide.BUY),
                _ZERO,
            )
            sell_volume = sum(
                (item.volume_base for item in current if item.side is TradeSide.SELL),
                _ZERO,
            )
            sided_total = buy_volume + sell_volume
            if sided_total > 0:
                imbalance = _safe_ratio(buy_volume - sell_volume, sided_total)

        return {
            "trade_count": len(causal),
            "current_trade_count": len(current),
            "trade_volume_base": total_volume_base,
            "trade_volume_quote": total_volume_quote,
            "average_trade_size_base": average_size,
            "median_trade_size_base": median_size,
            "trade_rate_per_minute": current_rate,
            "baseline_trade_rate_per_minute": baseline_rate,
            "trade_activity_ratio": activity_ratio,
            "trade_activity_change_per_minute": activity_change,
            "provider_side_coverage": coverage,
            "buy_volume_base": buy_volume,
            "sell_volume_base": sell_volume,
            "buy_sell_imbalance": imbalance,
        }


def not_applicable_microstructure(
    *, market: ExecutableMarket, observed_at: datetime
) -> MarketMicrostructureSnapshot:
    return MarketMicrostructureSnapshot(
        market=market,
        observed_at=_utc(observed_at),
        status=MicrostructureStatus.NOT_APPLICABLE,
        data_quality=MicrostructureDataQuality.NOT_APPLICABLE,
    )


def missing_microstructure(
    *, market: ExecutableMarket, observed_at: datetime
) -> MarketMicrostructureSnapshot:
    if market.market_type is not MarketType.SPOT:
        return not_applicable_microstructure(market=market, observed_at=observed_at)
    _base, quote = parse_canonical_symbol(market.symbol)
    return MarketMicrostructureSnapshot(
        market=market,
        observed_at=_utc(observed_at),
        status=MicrostructureStatus.PARTIAL,
        data_quality=MicrostructureDataQuality.PARTIAL,
        quote_asset=quote,
        errors=("MicrostructureNotScannedYet",),
        error_type="MicrostructureNotScannedYet",
    )


def _normalize_levels(
    levels: tuple[OrderBookLevel, ...], *, descending: bool
) -> tuple[OrderBookLevel, ...]:
    """Sort and aggregate duplicate price levels; invalid numerics are rejected by models."""

    volume_by_price: dict[Decimal, Decimal] = {}
    timestamp_by_price: dict[Decimal, datetime | None] = {}
    for level in levels:
        if level.volume_base <= 0:
            continue
        volume_by_price[level.price] = volume_by_price.get(level.price, _ZERO) + level.volume_base
        previous = timestamp_by_price.get(level.price)
        if previous is None or (
            level.level_timestamp is not None and level.level_timestamp > previous
        ):
            timestamp_by_price[level.price] = level.level_timestamp
    return tuple(
        OrderBookLevel(
            price=price,
            volume_base=volume_by_price[price],
            level_timestamp=timestamp_by_price.get(price),
        )
        for price in sorted(volume_by_price, reverse=descending)
    )


def _estimate_slippage(
    *,
    side: Literal["BUY", "SELL"],
    levels: tuple[OrderBookLevel, ...],
    notional_quote: Decimal,
    quote_asset: str,
    reference_price: Decimal,
) -> SlippageEstimate:
    remaining = notional_quote
    consumed_quote = _ZERO
    consumed_base = _ZERO
    available_quote = sum((level.price * level.volume_base for level in levels), _ZERO)

    for level in levels:
        if remaining <= 0:
            break
        level_quote = level.price * level.volume_base
        used_quote = min(remaining, level_quote)
        if used_quote <= 0:
            continue
        consumed_quote += used_quote
        consumed_base += used_quote / level.price
        remaining -= used_quote

    insufficient = remaining > Decimal("0.00000001")
    vwap = None
    slippage_absolute = None
    slippage_bps = None
    if not insufficient and consumed_base > 0:
        vwap = consumed_quote / consumed_base
        if side == "BUY":
            slippage_absolute = max(_ZERO, vwap - reference_price)
        else:
            slippage_absolute = max(_ZERO, reference_price - vwap)
        slippage_bps = _safe_ratio(slippage_absolute * _BPS, reference_price)

    return SlippageEstimate(
        side=side,
        notional_quote=notional_quote,
        quote_asset=quote_asset,
        estimated_vwap=vwap,
        reference_price=reference_price,
        slippage_absolute=slippage_absolute,
        slippage_bps=slippage_bps,
        consumed_volume_base=consumed_base,
        available_notional_quote=available_quote,
        insufficient_depth=insufficient,
    )


def _microstructure_characteristics(
    *,
    spread_bps: Decimal | None,
    book_imbalance: Decimal | None,
    trade_activity_ratio: Decimal | None,
    current_trade_count: int,
    buy_sell_imbalance: Decimal | None,
    slippage: tuple[SlippageEstimate, ...],
) -> tuple[MicrostructureCharacteristic, ...]:
    found: set[MicrostructureCharacteristic] = set()
    if spread_bps is not None:
        if spread_bps <= Decimal("5"):
            found.add(MicrostructureCharacteristic.TIGHT_SPREAD)
        if spread_bps >= Decimal("25"):
            found.add(MicrostructureCharacteristic.WIDE_SPREAD)
    if book_imbalance is not None and abs(book_imbalance) >= Decimal("0.25"):
        found.add(MicrostructureCharacteristic.ORDER_BOOK_IMBALANCE)
    if trade_activity_ratio is not None:
        if trade_activity_ratio >= Decimal("1.75") and current_trade_count >= 5:
            found.add(MicrostructureCharacteristic.TRADE_ACTIVITY_SURGE)
        elif trade_activity_ratio <= Decimal("0.50"):
            found.add(MicrostructureCharacteristic.TRADE_ACTIVITY_FADE)
    if buy_sell_imbalance is not None:
        if buy_sell_imbalance >= Decimal("0.25"):
            found.add(MicrostructureCharacteristic.BUY_PRESSURE)
        elif buy_sell_imbalance <= Decimal("-0.25"):
            found.add(MicrostructureCharacteristic.SELL_PRESSURE)

    thousand = tuple(item for item in slippage if item.notional_quote == Decimal("1000"))
    if thousand:
        if all(
            not item.insufficient_depth
            and item.slippage_bps is not None
            and item.slippage_bps <= Decimal("10")
            for item in thousand
        ):
            found.add(MicrostructureCharacteristic.DEEP_LIQUIDITY)
        if any(
            item.insufficient_depth
            or (item.slippage_bps is not None and item.slippage_bps >= Decimal("50"))
            for item in thousand
        ):
            found.add(MicrostructureCharacteristic.THIN_LIQUIDITY)
            found.add(MicrostructureCharacteristic.SLIPPAGE_RISK)
    if any(
        item.insufficient_depth
        or (item.slippage_bps is not None and item.slippage_bps >= Decimal("50"))
        for item in slippage
        if item.notional_quote <= Decimal("1000")
    ):
        found.add(MicrostructureCharacteristic.SLIPPAGE_RISK)

    order = tuple(MicrostructureCharacteristic)
    return tuple(item for item in order if item in found)


def _snapshot_freshness(source_at: datetime, observed_at: datetime) -> Decimal:
    source_at = _utc(source_at)
    return Decimal(str(max(0.0, (observed_at - source_at).total_seconds())))


def _trade_freshness(
    trades: RecentTradesSnapshot, *, observed_at: datetime
) -> Decimal:
    causal = tuple(
        item.occurred_at.astimezone(UTC)
        for item in trades.trades
        if item.occurred_at.astimezone(UTC) <= observed_at
    )
    if not causal:
        return _snapshot_freshness(trades.observed_at, observed_at)
    latest = max(causal)
    return Decimal(str(max(0.0, (observed_at - latest).total_seconds())))


def _distance_bps(mid: Decimal, price: Decimal) -> Decimal:
    return abs(price - mid) * _BPS / mid


def _safe_ratio(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    try:
        value = numerator / denominator
    except (InvalidOperation, ZeroDivisionError):
        return None
    return value if value.is_finite() else None


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def _utc(value: datetime) -> datetime:
    _require_aware(value, "timestamp")
    return value.astimezone(UTC)
