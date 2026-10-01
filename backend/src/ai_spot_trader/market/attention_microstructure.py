from __future__ import annotations

import asyncio
from collections import deque
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from pydantic import Field, model_validator

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.attention import (
    ActivityDataQualityCounts,
    ActivityErrorCounts,
    ActivityMarketTypeStatusCounts,
    ActivityPayloadStageCounts,
    ActivityStateCounts,
    ActivityStatusCounts,
    AttentionModel,
    LiquidityRegime,
    LiquidityRegimeCounts,
    MarketActivitySnapshot,
    MarketActivityState,
    MarketAttentionOverview,
    MarketAttentionPolicy,
    MarketAttentionRadar,
    MarketCatalogue,
    MarketTypeCounts,
    RadarInterestLevel,
    RadarStatus,
    SubthresholdActivitySnapshot,
    _deterministic_radar_sort_key,
)
from ai_spot_trader.market.candles import CandleStreamService
from ai_spot_trader.market.microstructure import (
    MarketMicrostructureAnalyzer,
    MarketMicrostructureSnapshot,
    MicrostructureCharacteristic,
    MicrostructureDataQuality,
    MicrostructurePolicy,
    MicrostructureProvider,
    MicrostructureStatus,
    missing_microstructure,
    not_applicable_microstructure,
)


class MicrostructureStatusCounts(AttentionModel):
    AVAILABLE: int = Field(default=0, ge=0)
    PARTIAL: int = Field(default=0, ge=0)
    STALE: int = Field(default=0, ge=0)
    ERROR: int = Field(default=0, ge=0)
    NOT_APPLICABLE: int = Field(default=0, ge=0)


class MicrostructureQualityCounts(AttentionModel):
    COMPLETE: int = Field(default=0, ge=0)
    PARTIAL: int = Field(default=0, ge=0)
    STALE: int = Field(default=0, ge=0)
    TECHNICAL_ERROR: int = Field(default=0, ge=0)
    NOT_APPLICABLE: int = Field(default=0, ge=0)


class MarketAttentionSnapshotV3(AttentionModel):
    market_activity: MarketActivitySnapshot
    microstructure: MarketMicrostructureSnapshot
    combined_characteristics: tuple[str, ...] = ()
    interest_level: RadarInterestLevel = RadarInterestLevel.LOW
    interest_reasons: tuple[str, ...] = ()

    @property
    def market(self) -> ExecutableMarket:
        return self.market_activity.market


class MarketAttentionOverviewV3(AttentionModel):
    protocol_version: str = "market-attention-radar-v3"
    observed_at: datetime
    status: RadarStatus
    informative_only: bool = True
    catalogue_market_count: int = Field(default=0, ge=0)
    cached_activity_market_count: int = Field(default=0, ge=0)
    scanned_market_count: int = Field(default=0, ge=0)
    scanned_market_type_counts: MarketTypeCounts = Field(default_factory=MarketTypeCounts)
    fresh_market_type_counts: MarketTypeCounts = Field(default_factory=MarketTypeCounts)
    candidate_market_count: int = Field(default=0, ge=0)
    activity_status_counts: ActivityStatusCounts = Field(default_factory=ActivityStatusCounts)
    activity_state_counts: ActivityStateCounts = Field(default_factory=ActivityStateCounts)
    activity_data_quality_counts: ActivityDataQualityCounts = Field(
        default_factory=ActivityDataQualityCounts
    )
    activity_error_counts: ActivityErrorCounts = Field(default_factory=ActivityErrorCounts)
    activity_payload_stage_counts: ActivityPayloadStageCounts = Field(
        default_factory=ActivityPayloadStageCounts
    )
    activity_market_type_status_counts: ActivityMarketTypeStatusCounts = Field(
        default_factory=ActivityMarketTypeStatusCounts
    )
    liquidity_regime_counts: LiquidityRegimeCounts = Field(default_factory=LiquidityRegimeCounts)
    microstructure_scanned_market_count: int = Field(default=0, ge=0)
    microstructure_cached_market_count: int = Field(default=0, ge=0)
    microstructure_status_counts: MicrostructureStatusCounts = Field(
        default_factory=MicrostructureStatusCounts
    )
    microstructure_quality_counts: MicrostructureQualityCounts = Field(
        default_factory=MicrostructureQualityCounts
    )
    microstructure_error_counts: dict[str, int] = Field(default_factory=dict)
    subthreshold_activity: tuple[SubthresholdActivitySnapshot, ...] = ()
    shortlist: tuple[MarketAttentionSnapshotV3, ...] = ()
    error_type: str | None = None

    @model_validator(mode="after")
    def validate_overview(self) -> "MarketAttentionOverviewV3":
        if self.protocol_version != "market-attention-radar-v3":
            raise ValueError("unsupported market attention protocol")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("market attention observed_at must be timezone-aware")
        if not self.informative_only:
            raise ValueError("Market Attention Radar v3 must remain informative_only")
        return self

    @classmethod
    def from_base(
        cls,
        base: MarketAttentionOverview,
        *,
        shortlist: tuple[MarketAttentionSnapshotV3, ...] = (),
        microstructure_scanned_market_count: int = 0,
        microstructure_cached_market_count: int = 0,
        microstructure_status_counts: MicrostructureStatusCounts | None = None,
        microstructure_quality_counts: MicrostructureQualityCounts | None = None,
        microstructure_error_counts: dict[str, int] | None = None,
        error_type: str | None = None,
    ) -> "MarketAttentionOverviewV3":
        return cls(
            observed_at=base.observed_at,
            status=base.status,
            informative_only=True,
            catalogue_market_count=base.catalogue_market_count,
            cached_activity_market_count=base.cached_activity_market_count,
            scanned_market_count=base.scanned_market_count,
            scanned_market_type_counts=base.scanned_market_type_counts,
            fresh_market_type_counts=base.fresh_market_type_counts,
            candidate_market_count=len(shortlist),
            activity_status_counts=base.activity_status_counts,
            activity_state_counts=base.activity_state_counts,
            activity_data_quality_counts=base.activity_data_quality_counts,
            activity_error_counts=base.activity_error_counts,
            activity_payload_stage_counts=base.activity_payload_stage_counts,
            activity_market_type_status_counts=base.activity_market_type_status_counts,
            liquidity_regime_counts=base.liquidity_regime_counts,
            microstructure_scanned_market_count=microstructure_scanned_market_count,
            microstructure_cached_market_count=microstructure_cached_market_count,
            microstructure_status_counts=(
                microstructure_status_counts or MicrostructureStatusCounts()
            ),
            microstructure_quality_counts=(
                microstructure_quality_counts or MicrostructureQualityCounts()
            ),
            microstructure_error_counts=microstructure_error_counts or {},
            subthreshold_activity=base.subthreshold_activity,
            shortlist=shortlist,
            error_type=error_type or base.error_type,
        )


class MicrostructureMarketAttentionRadar(MarketAttentionRadar):
    """Batch 39 radar enriched by bounded Kraken SPOT microstructure snapshots."""

    def __init__(
        self,
        *,
        candle_service: CandleStreamService,
        catalogue: MarketCatalogue,
        microstructure_provider: MicrostructureProvider,
        policy: MarketAttentionPolicy | None = None,
        microstructure_policy: MicrostructurePolicy | None = None,
    ) -> None:
        super().__init__(
            candle_service=candle_service,
            catalogue=catalogue,
            policy=policy,
        )
        self._micro_policy = microstructure_policy or MicrostructurePolicy()
        self._micro_provider = microstructure_provider
        self._micro_analyzer = MarketMicrostructureAnalyzer(policy=self._micro_policy)
        self._micro_cache: dict[ExecutableMarket, MarketMicrostructureSnapshot] = {}
        self._micro_scan_cursor = 0
        self._micro_latest: MarketAttentionOverviewV3 | None = None
        self._micro_history: deque[MarketAttentionOverviewV3] = deque(
            maxlen=self._policy.history_limit
        )

    @property
    def latest(self) -> MarketAttentionOverviewV3:  # type: ignore[override]
        if self._micro_latest is not None:
            return self._micro_latest
        return MarketAttentionOverviewV3.from_base(super().latest)

    def history(  # type: ignore[override]
        self, *, limit: int = 24
    ) -> tuple[MarketAttentionOverviewV3, ...]:
        if isinstance(limit, bool) or limit <= 0 or limit > self._policy.history_limit:
            raise ValueError("invalid market attention history limit")
        return tuple(self._micro_history)[-limit:]

    async def refresh_once(  # type: ignore[override]
        self,
        *,
        observed_at: datetime | None = None,
    ) -> MarketAttentionOverviewV3:
        base = await super().refresh_once(observed_at=observed_at)
        now = base.observed_at.astimezone(UTC)
        micro_scanned_count = 0
        global_error: str | None = None
        try:
            current_spot = tuple(
                snapshot.market
                for snapshot in self._activity_cache.values()
                if snapshot.market.market_type is MarketType.SPOT
                and snapshot.observed_at.astimezone(UTC) == now
            )
            micro_batch = self._next_micro_batch(current_spot)
            micro_scanned_count = len(micro_batch)
            await self._scan_microstructure(micro_batch, now=now)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # final fail-soft isolation around the enrichment layer
            global_error = type(exc).__name__

        fresh_micro = self._fresh_microstructure(now)
        activities = self._classify_liquidity(self._fresh_activities(now))
        enriched = tuple(
            _enrich_snapshot(
                activity,
                fresh_micro.get(activity.market)
                or missing_microstructure(market=activity.market, observed_at=now),
            )
            if activity.market.market_type is MarketType.SPOT
            else _enrich_snapshot(
                activity,
                not_applicable_microstructure(market=activity.market, observed_at=now),
            )
            for activity in activities
        )
        shortlist = self._v3_candidates(enriched)
        all_micro = tuple(item.microstructure for item in enriched)
        overview = MarketAttentionOverviewV3.from_base(
            base,
            shortlist=shortlist,
            microstructure_scanned_market_count=micro_scanned_count,
            microstructure_cached_market_count=len(fresh_micro),
            microstructure_status_counts=_microstructure_status_counts(all_micro),
            microstructure_quality_counts=_microstructure_quality_counts(all_micro),
            microstructure_error_counts=_microstructure_error_counts(all_micro),
            error_type=global_error,
        )
        self._micro_latest = overview
        self._micro_history.append(overview)
        return overview

    async def aclose(self) -> None:
        try:
            await self._micro_provider.aclose()
        finally:
            await super().aclose()

    def _next_micro_batch(
        self,
        markets: tuple[ExecutableMarket, ...],
    ) -> tuple[ExecutableMarket, ...]:
        unique = tuple(sorted(set(markets), key=lambda item: item.symbol))
        if not unique:
            return ()
        limit = min(self._micro_policy.market_limit_per_refresh, len(unique))
        start = self._micro_scan_cursor % len(unique)
        selected = tuple(unique[(start + offset) % len(unique)] for offset in range(limit))
        self._micro_scan_cursor = (start + limit) % len(unique)
        return selected

    async def _scan_microstructure(
        self,
        markets: tuple[ExecutableMarket, ...],
        *,
        now: datetime,
    ) -> None:
        semaphore = asyncio.Semaphore(self._micro_policy.concurrency)
        refresh_after = timedelta(seconds=self._micro_policy.refresh_seconds)

        async def one(market: ExecutableMarket) -> None:
            cached = self._micro_cache.get(market)
            if cached is not None and now - cached.observed_at.astimezone(UTC) < refresh_after:
                return
            errors: list[str] = []
            book = None
            trades = None
            async with semaphore:
                try:
                    book = await self._micro_provider.fetch_order_book(
                        market.symbol,
                        limit=self._micro_policy.book_levels,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    errors.append(type(exc).__name__)

                try:
                    trades = await self._micro_provider.fetch_recent_trades(
                        market.symbol,
                        limit=self._micro_policy.trade_count,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    errors.append(type(exc).__name__)

            snapshot = self._micro_analyzer.analyze(
                market=market,
                observed_at=now,
                book=book,
                trades=trades,
                errors=tuple(errors),
            )
            self._micro_cache[market] = snapshot

        if markets:
            await asyncio.gather(*(one(market) for market in markets))

    def _fresh_microstructure(
        self,
        now: datetime,
    ) -> dict[ExecutableMarket, MarketMicrostructureSnapshot]:
        ttl = timedelta(seconds=self._micro_policy.cache_ttl_seconds)
        return {
            market: snapshot
            for market, snapshot in self._micro_cache.items()
            if now - snapshot.observed_at.astimezone(UTC) <= ttl
        }

    def _v3_candidates(
        self,
        items: tuple[MarketAttentionSnapshotV3, ...],
    ) -> tuple[MarketAttentionSnapshotV3, ...]:
        unusual_states = {
            MarketActivityState.ELEVATED,
            MarketActivityState.ACCELERATING,
            MarketActivityState.VERY_HIGH,
        }
        eligible = tuple(
            item
            for item in items
            if item.market_activity.status is RadarStatus.AVAILABLE
            and (
                item.market_activity.activity_state in unusual_states
                or _interest_rank(item.interest_level) >= _interest_rank(RadarInterestLevel.MEDIUM)
            )
        )
        if not eligible:
            return ()
        ranked = tuple(sorted(eligible, key=_v3_sort_key, reverse=True))
        by_regime: dict[LiquidityRegime, list[MarketAttentionSnapshotV3]] = {}
        for item in ranked:
            by_regime.setdefault(item.market_activity.liquidity_regime, []).append(item)

        leaders = sorted(
            (values[0] for values in by_regime.values()),
            key=_v3_sort_key,
            reverse=True,
        )
        chosen = leaders[: self._policy.candidate_limit]
        chosen_markets = {item.market for item in chosen}
        if len(chosen) < self._policy.candidate_limit:
            for item in ranked:
                if item.market in chosen_markets:
                    continue
                chosen.append(item)
                chosen_markets.add(item.market)
                if len(chosen) >= self._policy.candidate_limit:
                    break
        return tuple(sorted(chosen, key=_v3_sort_key, reverse=True))


def _enrich_snapshot(
    activity: MarketActivitySnapshot,
    micro: MarketMicrostructureSnapshot,
) -> MarketAttentionSnapshotV3:
    base_rank = _interest_rank(activity.interest_level)
    rank = base_rank
    reasons = list(activity.interest_reasons)
    active_micro = micro.status in {MicrostructureStatus.AVAILABLE, MicrostructureStatus.PARTIAL}
    characteristics = set(micro.characteristics) if active_micro else set()

    if MicrostructureCharacteristic.TRADE_ACTIVITY_SURGE in characteristics:
        rank += 1
        reasons.append("Intensité des trades en hausse")
    if MicrostructureCharacteristic.ORDER_BOOK_IMBALANCE in characteristics:
        rank += 1
        reasons.append("Déséquilibre marqué du carnet")
    if (
        MicrostructureCharacteristic.BUY_PRESSURE in characteristics
        or MicrostructureCharacteristic.SELL_PRESSURE in characteristics
    ):
        rank += 1
        reasons.append("Pression transactionnelle unilatérale observée")

    execution_cautions = {
        MicrostructureCharacteristic.WIDE_SPREAD,
        MicrostructureCharacteristic.THIN_LIQUIDITY,
        MicrostructureCharacteristic.SLIPPAGE_RISK,
    }
    if characteristics & execution_cautions:
        rank = max(0, rank - 1)
        reasons.append("Microstructure coûteuse ou peu profonde")
    elif MicrostructureCharacteristic.DEEP_LIQUIDITY in characteristics:
        reasons.append("Profondeur L2 suffisante sur les tailles testées")

    rank = min(3, rank)
    level = _level_from_rank(rank)
    combined = tuple(
        dict.fromkeys(
            [item.value for item in activity.characteristics]
            + [item.value for item in micro.characteristics]
        )
    )
    return MarketAttentionSnapshotV3(
        market_activity=activity,
        microstructure=micro,
        combined_characteristics=combined,
        interest_level=level,
        interest_reasons=tuple(dict.fromkeys(reasons))[:7],
    )


def _v3_sort_key(item: MarketAttentionSnapshotV3) -> tuple[object, ...]:
    micro_priority = sum(
        {
            MicrostructureCharacteristic.TRADE_ACTIVITY_SURGE: 4,
            MicrostructureCharacteristic.ORDER_BOOK_IMBALANCE: 3,
            MicrostructureCharacteristic.BUY_PRESSURE: 2,
            MicrostructureCharacteristic.SELL_PRESSURE: 2,
            MicrostructureCharacteristic.TIGHT_SPREAD: 1,
            MicrostructureCharacteristic.DEEP_LIQUIDITY: 1,
            MicrostructureCharacteristic.WIDE_SPREAD: -1,
            MicrostructureCharacteristic.THIN_LIQUIDITY: -2,
            MicrostructureCharacteristic.SLIPPAGE_RISK: -2,
            MicrostructureCharacteristic.TRADE_ACTIVITY_FADE: -1,
        }[characteristic]
        for characteristic in item.microstructure.characteristics
    )
    return (
        _interest_rank(item.interest_level),
        micro_priority,
        *_deterministic_radar_sort_key(item.market_activity),
    )


def _interest_rank(level: RadarInterestLevel) -> int:
    return {
        RadarInterestLevel.LOW: 0,
        RadarInterestLevel.MEDIUM: 1,
        RadarInterestLevel.HIGH: 2,
        RadarInterestLevel.VERY_HIGH: 3,
    }[level]


def _level_from_rank(rank: int) -> RadarInterestLevel:
    return (
        RadarInterestLevel.LOW,
        RadarInterestLevel.MEDIUM,
        RadarInterestLevel.HIGH,
        RadarInterestLevel.VERY_HIGH,
    )[max(0, min(3, rank))]


def _microstructure_status_counts(
    items: tuple[MarketMicrostructureSnapshot, ...],
) -> MicrostructureStatusCounts:
    return MicrostructureStatusCounts(
        AVAILABLE=sum(item.status is MicrostructureStatus.AVAILABLE for item in items),
        PARTIAL=sum(item.status is MicrostructureStatus.PARTIAL for item in items),
        STALE=sum(item.status is MicrostructureStatus.STALE for item in items),
        ERROR=sum(item.status is MicrostructureStatus.ERROR for item in items),
        NOT_APPLICABLE=sum(
            item.status is MicrostructureStatus.NOT_APPLICABLE for item in items
        ),
    )


def _microstructure_quality_counts(
    items: tuple[MarketMicrostructureSnapshot, ...],
) -> MicrostructureQualityCounts:
    return MicrostructureQualityCounts(
        COMPLETE=sum(item.data_quality is MicrostructureDataQuality.COMPLETE for item in items),
        PARTIAL=sum(item.data_quality is MicrostructureDataQuality.PARTIAL for item in items),
        STALE=sum(item.data_quality is MicrostructureDataQuality.STALE for item in items),
        TECHNICAL_ERROR=sum(
            item.data_quality is MicrostructureDataQuality.TECHNICAL_ERROR for item in items
        ),
        NOT_APPLICABLE=sum(
            item.data_quality is MicrostructureDataQuality.NOT_APPLICABLE for item in items
        ),
    )


def _microstructure_error_counts(
    items: tuple[MarketMicrostructureSnapshot, ...],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        if item.error_type is None:
            continue
        counts[item.error_type] = counts.get(item.error_type, 0) + 1
    return dict(sorted(counts.items()))
