from __future__ import annotations

import asyncio
from collections import deque
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from math import ceil
from typing import cast

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
    LiquidityRegimeCounts,
    MarketAttentionPolicy,
    MarketCatalogue,
    MarketTypeCounts,
    RadarInterestLevel,
    RadarStatus,
    SubthresholdActivitySnapshot,
)
from ai_spot_trader.market.attention_filters import (
    FilteredStructuredMarketAttentionRadar,
    MarketAttentionCoverageDiagnostics,
    MarketAttentionFilters,
    MarketAttentionOverviewV6,
    MarketAttentionSnapshotV6,
    MarketCapCategory,
    MarketMetadataProvider,
    Volume24hStatusCounts,
    _volume_status_counts,
)
from ai_spot_trader.market.attention_microstructure import (
    MicrostructureQualityCounts,
    MicrostructureStatusCounts,
    _enrich_snapshot,
    _v3_sort_key,
)
from ai_spot_trader.market.attention_scope_trend import (
    MarketAttentionOverviewV4,
    MarketScope,
    ScopedTrendMarketAttentionRadar,
    TrendDirection,
    _snapshot_v4,
)
from ai_spot_trader.market.attention_structure import MarketAttentionSnapshotV5
from ai_spot_trader.market.candles import CandleStreamService, CandleTimeframe
from ai_spot_trader.market.microstructure import (
    MicrostructurePolicy,
    MicrostructureProvider,
    missing_microstructure,
    not_applicable_microstructure,
)
from ai_spot_trader.market.structure import (
    STRUCTURE_TIMEFRAMES,
    MarketStructurePolicy,
    MarketStructureState,
    MultiTimeframeMarketStructure,
    MultiTimeframeStructureState,
    StructureEvent,
    summarize_market_structures,
)


class StructureCoverageStatus(StrEnum):
    NO_MARKETS = "NO_MARKETS"
    COVERED = "COVERED"
    ROTATING = "ROTATING"
    TTL_EXPIRED = "TTL_EXPIRED"
    CONFIGURATION_TOO_SLOW = "CONFIGURATION_TOO_SLOW"


class MarketStructureScanPolicy(AttentionModel):
    """Radar-level cost policy, separate from swing-analysis geometry."""

    market_limit_per_refresh: int = Field(default=20, ge=1, le=100)
    cache_ttl_seconds: float = Field(default=3600.0, ge=60.0, le=86_400.0)


class MarketStructureCoverageDiagnostics(AttentionModel):
    eligible_market_count: int = Field(default=0, ge=0)
    fresh_market_count: int = Field(default=0, ge=0)
    expired_market_count: int = Field(default=0, ge=0)
    unseen_market_count: int = Field(default=0, ge=0)
    scanned_market_count: int = Field(default=0, ge=0)
    coverage_ratio: float | None = Field(default=None, ge=0, le=1)
    effective_market_limit: int = Field(default=0, ge=0)
    estimated_refreshes_per_full_rotation: int = Field(default=0, ge=0)
    estimated_full_rotation_seconds: float = Field(default=0.0, ge=0)
    cache_ttl_seconds: float = Field(default=0.0, ge=0)
    oldest_structure_age_seconds: float | None = Field(default=None, ge=0)
    rotation_within_cache_ttl: bool = True
    status: StructureCoverageStatus = StructureCoverageStatus.NO_MARKETS

    @model_validator(mode="after")
    def validate_partition(self) -> "MarketStructureCoverageDiagnostics":
        if (
            self.fresh_market_count
            + self.expired_market_count
            + self.unseen_market_count
            != self.eligible_market_count
        ):
            raise ValueError("structure coverage counts must partition eligible markets")
        return self


class StructureTimeframeFilter(AttentionModel):
    states: tuple[MarketStructureState, ...] = ()
    events: tuple[StructureEvent, ...] = ()

    @model_validator(mode="after")
    def validate_filter(self) -> "StructureTimeframeFilter":
        if MarketStructureState.UNKNOWN in self.states:
            raise ValueError("UNKNOWN cannot be selected as a structure state filter")
        if len(set(self.states)) != len(self.states):
            raise ValueError("structure states cannot contain duplicates")
        if len(set(self.events)) != len(self.events):
            raise ValueError("structure events cannot contain duplicates")
        return self

    @property
    def enabled(self) -> bool:
        return bool(self.states or self.events)


class StructureAwareMarketAttentionFilters(MarketAttentionFilters):
    trend_directions: tuple[TrendDirection, ...] = ()
    structure_global_states: tuple[MultiTimeframeStructureState, ...] = ()
    structure_5m: StructureTimeframeFilter = Field(default_factory=StructureTimeframeFilter)
    structure_15m: StructureTimeframeFilter = Field(default_factory=StructureTimeframeFilter)
    structure_1h: StructureTimeframeFilter = Field(default_factory=StructureTimeframeFilter)
    structure_4h: StructureTimeframeFilter = Field(default_factory=StructureTimeframeFilter)

    @model_validator(mode="after")
    def validate_structure_filters(self) -> "StructureAwareMarketAttentionFilters":
        if TrendDirection.UNKNOWN in self.trend_directions:
            raise ValueError("UNKNOWN cannot be selected as a trend filter")
        if len(set(self.trend_directions)) != len(self.trend_directions):
            raise ValueError("trend_directions cannot contain duplicates")
        if MultiTimeframeStructureState.UNKNOWN in self.structure_global_states:
            raise ValueError("UNKNOWN cannot be selected as a global structure filter")
        if len(set(self.structure_global_states)) != len(self.structure_global_states):
            raise ValueError("structure_global_states cannot contain duplicates")
        return self

    @property
    def trend_filter_enabled(self) -> bool:
        return bool(self.trend_directions)

    @property
    def structure_filter_enabled(self) -> bool:
        return bool(
            self.structure_global_states
            or self.structure_5m.enabled
            or self.structure_15m.enabled
            or self.structure_1h.enabled
            or self.structure_4h.enabled
        )

    @property
    def attention_filter_enabled(self) -> bool:
        return self.trend_filter_enabled or self.structure_filter_enabled

    def structure_filter(self, timeframe: CandleTimeframe) -> StructureTimeframeFilter:
        mapping = {
            CandleTimeframe.M5: self.structure_5m,
            CandleTimeframe.M15: self.structure_15m,
            CandleTimeframe.H1: self.structure_1h,
            CandleTimeframe.H4: self.structure_4h,
        }
        return mapping[timeframe]


class MarketAttentionOverviewV6Structure(MarketAttentionOverviewV6):
    """Additive Batch 45 extension; protocol stays v6 for compatibility."""

    filters: StructureAwareMarketAttentionFilters = Field(
        default_factory=StructureAwareMarketAttentionFilters
    )
    structure_coverage: MarketStructureCoverageDiagnostics = Field(
        default_factory=MarketStructureCoverageDiagnostics
    )

_TIMEFRAME_ATTENTION_RANK = {
    CandleTimeframe.M5: 1,
    CandleTimeframe.M15: 2,
    CandleTimeframe.H1: 3,
    CandleTimeframe.H4: 4,
}
_EVENT_ATTENTION_RANK = {
    StructureEvent.BOS_UP: 1,
    StructureEvent.BOS_DOWN: 1,
    StructureEvent.CHOCH_UP: 2,
    StructureEvent.CHOCH_DOWN: 2,
}


def _structure_attention_key(
    structure: MultiTimeframeMarketStructure,
) -> tuple[int, int]:
    """Rank confirmed events only; direction never changes the rank."""

    strongest = (0, 0)
    for frame in structure.timeframes:
        if frame.event is None:
            continue
        candidate = (
            _TIMEFRAME_ATTENTION_RANK.get(frame.timeframe, 0),
            _EVENT_ATTENTION_RANK[frame.event],
        )
        if candidate > strongest:
            strongest = candidate
    return strongest


def _strongest_structure_event(
    structure: MultiTimeframeMarketStructure,
) -> tuple[CandleTimeframe, StructureEvent] | None:
    values = tuple(
        (frame.timeframe, frame.event)
        for frame in structure.timeframes
        if frame.event is not None
    )
    if not values:
        return None
    return max(
        cast(tuple[tuple[CandleTimeframe, StructureEvent], ...], values),
        key=lambda item: (
            _TIMEFRAME_ATTENTION_RANK.get(item[0], 0),
            _EVENT_ATTENTION_RANK[item[1]],
        ),
    )


def _advanced_filters_accept(
    item: MarketAttentionSnapshotV6,
    filters: StructureAwareMarketAttentionFilters,
) -> bool:
    if item.market_activity.status is not RadarStatus.AVAILABLE:
        return False
    if filters.trend_directions:
        if item.market_activity.trend_direction not in filters.trend_directions:
            return False

    structure = item.market_structure
    if filters.structure_global_states:
        if structure.global_state not in filters.structure_global_states:
            return False

    for timeframe in STRUCTURE_TIMEFRAMES:
        criterion = filters.structure_filter(timeframe)
        if not criterion.enabled:
            continue
        frame = structure.timeframe(timeframe)
        if frame is None:
            return False
        if criterion.states and frame.state not in criterion.states:
            return False
        if criterion.events and (frame.event is None or frame.event not in criterion.events):
            return False
    return True


def _structured_candidate_sort_key(item: MarketAttentionSnapshotV6) -> tuple[object, ...]:
    # Preserve the canonical interest rank as the primary ordering signal. Structure is an
    # additive, directionally symmetric tiebreaker before the remaining micro/activity facts.
    canonical = _v3_sort_key(item)
    return (canonical[0], *_structure_attention_key(item.market_structure), *canonical[1:])


def _select_final_candidates(
    *,
    items: tuple[MarketAttentionSnapshotV6, ...],
    canonical_candidate_markets: frozenset[ExecutableMarket],
    filters: StructureAwareMarketAttentionFilters,
    candidate_limit: int,
) -> tuple[MarketAttentionSnapshotV6, ...]:
    if filters.attention_filter_enabled:
        pool = tuple(item for item in items if _advanced_filters_accept(item, filters))
    else:
        pool = tuple(
            item
            for item in items
            if item.market_activity.status is RadarStatus.AVAILABLE
            and (
                item.market in canonical_candidate_markets
                or _structure_attention_key(item.market_structure) != (0, 0)
            )
        )
    if not pool:
        return ()
    ranked = sorted(pool, key=_structured_candidate_sort_key, reverse=True)
    return tuple(ranked[:candidate_limit])


class StructureAwareFilteredMarketAttentionRadar(FilteredStructuredMarketAttentionRadar):
    """Batch 45 Radar: bounded structure prefilter plus runtime trend/structure filters."""

    def __init__(
        self,
        *,
        candle_service: CandleStreamService,
        catalogue: MarketCatalogue,
        microstructure_provider: MicrostructureProvider,
        metadata_provider: MarketMetadataProvider,
        policy: MarketAttentionPolicy | None = None,
        microstructure_policy: MicrostructurePolicy | None = None,
        structure_policy: MarketStructurePolicy | None = None,
        structure_scan_policy: MarketStructureScanPolicy | None = None,
    ) -> None:
        super().__init__(
            candle_service=candle_service,
            catalogue=catalogue,
            microstructure_provider=microstructure_provider,
            metadata_provider=metadata_provider,
            policy=policy,
            microstructure_policy=microstructure_policy,
            structure_policy=structure_policy,
        )
        self._filters = StructureAwareMarketAttentionFilters()  # type: ignore[assignment]
        self._structure_scan_policy = structure_scan_policy or MarketStructureScanPolicy()
        self._structure_cache: dict[ExecutableMarket, MultiTimeframeMarketStructure] = {}
        self._structure_scan_cursor = 0
        self._v6_structure_latest: MarketAttentionOverviewV6Structure | None = None
        self._v6_structure_history: deque[MarketAttentionOverviewV6Structure] = deque(
            maxlen=self._policy.history_limit
        )

    @property
    def filters(self) -> StructureAwareMarketAttentionFilters:  # type: ignore[override]
        value = super().filters
        if isinstance(value, StructureAwareMarketAttentionFilters):
            return value
        return StructureAwareMarketAttentionFilters.model_validate(value.model_dump())

    @property
    def latest(self) -> MarketAttentionOverviewV6Structure:  # type: ignore[override]
        if self._v6_structure_latest is not None:
            return self._v6_structure_latest
        base = ScopedTrendMarketAttentionRadar.latest.fget(self)
        assert base is not None
        return self._overview_from_v4(
            base,
            shortlist=(),
            structure_coverage=self._structure_coverage((), base.observed_at, scanned_count=0),
        )

    def history(  # type: ignore[override]
        self, *, limit: int = 24
    ) -> tuple[MarketAttentionOverviewV6Structure, ...]:
        if isinstance(limit, bool) or limit <= 0 or limit > self._policy.history_limit:
            raise ValueError("invalid market attention history limit")
        return tuple(self._v6_structure_history)[-limit:]

    async def set_filters(  # type: ignore[override]
        self,
        filters: StructureAwareMarketAttentionFilters,
        *,
        observed_at: datetime | None = None,
    ) -> MarketAttentionOverviewV6Structure:
        if not isinstance(filters, StructureAwareMarketAttentionFilters):
            filters = StructureAwareMarketAttentionFilters.model_validate(filters)
        if self._closed:
            raise RuntimeError("market attention radar is closed")

        # Keep the Batch 43 atomic filter-transition invariant: once filters change, `latest`
        # must never expose a shortlist produced with the previous filter set.
        async with self._scope_refresh_lock:
            self._market_scope = filters.market_scope
            self._filters = filters  # type: ignore[assignment]
            now = (observed_at or datetime.now(UTC)).astimezone(UTC)
            eligible = tuple(
                snapshot.market
                for snapshot in self._fresh_activities(now)
                if snapshot.status is RadarStatus.AVAILABLE
            )
            self._v6_structure_latest = MarketAttentionOverviewV6Structure(
                observed_at=now,
                status=RadarStatus.PARTIAL,
                informative_only=True,
                market_scope=filters.market_scope,
                filters=filters,
                catalogue_market_count=self._scope_catalogue_count(),
                market_cap_metadata_status=self._metadata_status,
                market_cap_metadata_provider=self._metadata_provider_name,
                coverage=self._coverage(now),
                structure_coverage=self._structure_coverage(
                    eligible,
                    now,
                    scanned_count=0,
                ),
            )
            return await self._refresh_v4_once(observed_at=observed_at)

    async def _refresh_v4_once(  # type: ignore[override]
        self,
        *,
        observed_at: datetime | None = None,
    ) -> MarketAttentionOverviewV6Structure:
        # Deliberately bypass the Batch 42 post-shortlist structure stage. Dynamic dispatch still
        # preserves Batch 43/44 scope, market-cap, volume, liquidity and microstructure hooks.
        base = await ScopedTrendMarketAttentionRadar._refresh_v4_once(
            self,
            observed_at=observed_at,
        )
        now = base.observed_at.astimezone(UTC)
        activities = self._classify_liquidity(self._fresh_activities(now))
        fresh_micro = self._fresh_microstructure(now)

        v4_items = tuple(
            _snapshot_v4(
                _enrich_snapshot(
                    activity,
                    fresh_micro.get(activity.market)
                    or (
                        missing_microstructure(market=activity.market, observed_at=now)
                        if activity.market.market_type is MarketType.SPOT
                        else not_applicable_microstructure(
                            market=activity.market,
                            observed_at=now,
                        )
                    ),
                )
            )
            for activity in activities
        )
        eligible_markets = tuple(
            item.market
            for item in v4_items
            if item.market_activity.status is RadarStatus.AVAILABLE
        )
        structure_batch = self._next_structure_batch(eligible_markets)
        scanned_count = await self._scan_structure(structure_batch, observed_at=now)
        fresh_structure = self._fresh_structures(now)

        all_items = tuple(
            self._snapshot_with_structure_v6(
                item,
                structure=fresh_structure.get(item.market),
                observed_at=now,
            )
            for item in v4_items
        )
        canonical_candidate_markets = frozenset(item.market for item in base.shortlist)
        shortlist = _select_final_candidates(
            items=all_items,
            canonical_candidate_markets=canonical_candidate_markets,
            filters=self.filters,
            candidate_limit=self._policy.candidate_limit,
        )
        overview = self._overview_from_v4(
            base,
            shortlist=shortlist,
            structure_coverage=self._structure_coverage(
                eligible_markets,
                now,
                scanned_count=scanned_count,
            ),
        )
        self._v6_structure_latest = overview
        self._v6_structure_history.append(overview)
        return overview

    def _next_structure_batch(
        self,
        markets: tuple[ExecutableMarket, ...],
    ) -> tuple[ExecutableMarket, ...]:
        unique = tuple(
            sorted(
                set(markets),
                key=lambda item: (item.market_type.value, item.symbol),
            )
        )
        if not unique:
            self._structure_scan_cursor = 0
            return ()
        limit = min(self._structure_scan_policy.market_limit_per_refresh, len(unique))
        start = self._structure_scan_cursor % len(unique)
        selected = tuple(unique[(start + offset) % len(unique)] for offset in range(limit))
        self._structure_scan_cursor = (start + limit) % len(unique)
        return selected

    async def _scan_structure(
        self,
        markets: tuple[ExecutableMarket, ...],
        *,
        observed_at: datetime,
    ) -> int:
        ttl = timedelta(seconds=self._structure_scan_policy.cache_ttl_seconds)

        async def one(market: ExecutableMarket) -> bool:
            cached = self._structure_cache.get(market)
            if cached is not None:
                cached_at = cached.observed_at.astimezone(UTC)
                if cached_at <= observed_at and observed_at - cached_at <= ttl:
                    return False
            structure = await self._market_structure_for_market(
                market,
                observed_at=observed_at,
            )
            self._structure_cache[market] = structure
            return True

        if not markets:
            return 0
        refreshed = await asyncio.gather(*(one(market) for market in markets))
        return sum(refreshed)

    def _fresh_structures(
        self,
        now: datetime,
    ) -> dict[ExecutableMarket, MultiTimeframeMarketStructure]:
        ttl = timedelta(seconds=self._structure_scan_policy.cache_ttl_seconds)
        return {
            market: structure
            for market, structure in self._structure_cache.items()
            if structure.observed_at.astimezone(UTC) <= now
            and now - structure.observed_at.astimezone(UTC) <= ttl
        }

    def _unknown_structure(self, observed_at: datetime) -> MultiTimeframeMarketStructure:
        return summarize_market_structures(
            observed_at=observed_at,
            timeframes=(
                self._structure_analyzer.unknown(timeframe=timeframe)
                for timeframe in STRUCTURE_TIMEFRAMES
            ),
        )

    def _snapshot_with_structure_v6(
        self,
        value,
        *,
        structure: MultiTimeframeMarketStructure | None,
        observed_at: datetime,
    ) -> MarketAttentionSnapshotV6:
        resolved = structure or self._unknown_structure(observed_at)
        v5 = MarketAttentionSnapshotV5(
            market_activity=value.market_activity,
            microstructure=value.microstructure,
            market_structure=resolved,
            combined_characteristics=value.combined_characteristics,
            interest_level=value.interest_level,
            interest_reasons=value.interest_reasons,
        )
        result = self._snapshot_v6(v5)
        event = _strongest_structure_event(resolved)
        if event is None:
            return result
        timeframe, structure_event = event
        characteristic = f"STRUCTURE_{timeframe.value}_{structure_event.value}"
        reason = f"Événement structurel confirmé {timeframe.value} · {structure_event.value}"
        return result.model_copy(
            update={
                "combined_characteristics": tuple(
                    dict.fromkeys((*result.combined_characteristics, characteristic))
                ),
                "interest_reasons": tuple(
                    dict.fromkeys((*result.interest_reasons, reason))
                )[:8],
            }
        )

    def _structure_coverage(
        self,
        eligible_markets: tuple[ExecutableMarket, ...],
        now: datetime,
        *,
        scanned_count: int,
    ) -> MarketStructureCoverageDiagnostics:
        now = now.astimezone(UTC)
        ttl_seconds = float(self._structure_scan_policy.cache_ttl_seconds)
        fresh = 0
        expired = 0
        unseen = 0
        ages: list[float] = []
        for market in eligible_markets:
            structure = self._structure_cache.get(market)
            if structure is None:
                unseen += 1
                continue
            structure_at = structure.observed_at.astimezone(UTC)
            if structure_at > now:
                unseen += 1
                continue
            age = (now - structure_at).total_seconds()
            ages.append(age)
            if age <= ttl_seconds:
                fresh += 1
            else:
                expired += 1

        eligible_count = len(eligible_markets)
        effective_limit = min(
            self._structure_scan_policy.market_limit_per_refresh,
            eligible_count,
        )
        refreshes = ceil(eligible_count / effective_limit) if effective_limit else 0
        estimated_seconds = refreshes * float(self._policy.refresh_seconds)
        within_ttl = refreshes == 0 or estimated_seconds <= ttl_seconds
        ratio = fresh / eligible_count if eligible_count else None

        if eligible_count == 0:
            status = StructureCoverageStatus.NO_MARKETS
        elif not within_ttl:
            status = StructureCoverageStatus.CONFIGURATION_TOO_SLOW
        elif expired:
            status = StructureCoverageStatus.TTL_EXPIRED
        elif fresh == eligible_count:
            status = StructureCoverageStatus.COVERED
        else:
            status = StructureCoverageStatus.ROTATING

        return MarketStructureCoverageDiagnostics(
            eligible_market_count=eligible_count,
            fresh_market_count=fresh,
            expired_market_count=expired,
            unseen_market_count=unseen,
            scanned_market_count=scanned_count,
            coverage_ratio=ratio,
            effective_market_limit=effective_limit,
            estimated_refreshes_per_full_rotation=refreshes,
            estimated_full_rotation_seconds=estimated_seconds,
            cache_ttl_seconds=ttl_seconds,
            oldest_structure_age_seconds=max(ages) if ages else None,
            rotation_within_cache_ttl=within_ttl,
            status=status,
        )

    def _overview_from_v4(
        self,
        base: MarketAttentionOverviewV4,
        *,
        shortlist: tuple[MarketAttentionSnapshotV6, ...],
        structure_coverage: MarketStructureCoverageDiagnostics,
    ) -> MarketAttentionOverviewV6Structure:
        filters = self.filters
        payload = base.model_dump(
            exclude={"protocol_version", "shortlist", "candidate_market_count", "market_scope"}
        )
        return MarketAttentionOverviewV6Structure(
            **payload,
            market_scope=filters.market_scope,
            filters=filters,
            candidate_market_count=len(shortlist),
            shortlist=shortlist,
            market_cap_metadata_status=self._metadata_status,
            market_cap_metadata_provider=self._metadata_provider_name,
            volume_24h_status_counts=_volume_status_counts(
                tuple(self._volume_24h_by_market.values()),
                minimum=filters.min_volume_24h_usd,
            ),
            coverage=self._coverage(base.observed_at),
            structure_coverage=structure_coverage,
        )
