from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Iterable
from datetime import UTC, datetime
from enum import StrEnum
from pydantic import Field, model_validator

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.attention import (
    ActivityDataQualityCounts,
    ActivityErrorCounts,
    ActivityHorizonSnapshot,
    ActivityMarketTypeStatusCounts,
    ActivityPayloadStageCounts,
    ActivityStateCounts,
    ActivityStatusCounts,
    AttentionModel,
    LiquidityRegimeCounts,
    MarketActivitySnapshot,
    MarketCharacteristic,
    MarketAttentionPolicy,
    MarketCatalogue,
    MarketTypeCounts,
    RadarStatus,
    SubthresholdActivitySnapshot,
    _MATERIAL_RETURN,
    _interest_level_and_reasons,
)
from ai_spot_trader.market.attention_microstructure import (
    MarketAttentionOverviewV3,
    MarketAttentionSnapshotV3,
    MicrostructureMarketAttentionRadar,
    MicrostructureQualityCounts,
    MicrostructureStatusCounts,
)
from ai_spot_trader.market.candles import CandleStreamService
from ai_spot_trader.market.microstructure import (
    MarketMicrostructureSnapshot,
    MicrostructurePolicy,
    MicrostructureProvider,
)


class MarketScope(StrEnum):
    SPOT = "SPOT"
    PERPETUAL = "PERPETUAL"
    ALL = "ALL"


class TrendDirection(StrEnum):
    UP = "UP"
    DOWN = "DOWN"
    NEUTRAL = "NEUTRAL"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


class ActivityHorizonSnapshotV4(ActivityHorizonSnapshot):
    trend_direction: TrendDirection = TrendDirection.UNKNOWN


class MarketActivitySnapshotV4(MarketActivitySnapshot):
    horizons: tuple[ActivityHorizonSnapshotV4, ...]
    trend_direction: TrendDirection = TrendDirection.UNKNOWN


class MarketAttentionSnapshotV4(MarketAttentionSnapshotV3):
    market_activity: MarketActivitySnapshotV4


class MarketAttentionOverviewV4(AttentionModel):
    protocol_version: str = "market-attention-radar-v4"
    observed_at: datetime
    status: RadarStatus
    informative_only: bool = True
    market_scope: MarketScope = MarketScope.ALL
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
    shortlist: tuple[MarketAttentionSnapshotV4, ...] = ()
    error_type: str | None = None

    @model_validator(mode="after")
    def validate_overview(self) -> "MarketAttentionOverviewV4":
        if self.protocol_version != "market-attention-radar-v4":
            raise ValueError("unsupported market attention protocol")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("market attention observed_at must be timezone-aware")
        if not self.informative_only:
            raise ValueError("Market Attention Radar v4 must remain informative_only")
        return self

    @classmethod
    def from_v3(
        cls,
        value: MarketAttentionOverviewV3,
        *,
        market_scope: MarketScope = MarketScope.ALL,
        catalogue_market_count: int | None = None,
    ) -> "MarketAttentionOverviewV4":
        shortlist = tuple(_snapshot_v4(item) for item in value.shortlist)
        return cls(
            observed_at=value.observed_at,
            status=value.status,
            informative_only=True,
            market_scope=market_scope,
            catalogue_market_count=(
                value.catalogue_market_count
                if catalogue_market_count is None
                else catalogue_market_count
            ),
            cached_activity_market_count=value.cached_activity_market_count,
            scanned_market_count=value.scanned_market_count,
            scanned_market_type_counts=value.scanned_market_type_counts,
            fresh_market_type_counts=value.fresh_market_type_counts,
            candidate_market_count=len(shortlist),
            activity_status_counts=value.activity_status_counts,
            activity_state_counts=value.activity_state_counts,
            activity_data_quality_counts=value.activity_data_quality_counts,
            activity_error_counts=value.activity_error_counts,
            activity_payload_stage_counts=value.activity_payload_stage_counts,
            activity_market_type_status_counts=value.activity_market_type_status_counts,
            liquidity_regime_counts=value.liquidity_regime_counts,
            microstructure_scanned_market_count=value.microstructure_scanned_market_count,
            microstructure_cached_market_count=value.microstructure_cached_market_count,
            microstructure_status_counts=value.microstructure_status_counts,
            microstructure_quality_counts=value.microstructure_quality_counts,
            microstructure_error_counts=value.microstructure_error_counts,
            subthreshold_activity=value.subthreshold_activity,
            shortlist=shortlist,
            error_type=value.error_type,
        )


def horizon_trend_direction(horizon: ActivityHorizonSnapshot) -> TrendDirection:
    if not horizon.complete or horizon.price_return is None or not horizon.price_return.is_finite():
        return TrendDirection.UNKNOWN
    threshold = _MATERIAL_RETURN.get(horizon.timeframe)
    if threshold is None:
        return TrendDirection.UNKNOWN
    if horizon.price_return >= threshold:
        return TrendDirection.UP
    if horizon.price_return <= -threshold:
        return TrendDirection.DOWN
    return TrendDirection.NEUTRAL


def summarize_trend_direction(
    horizons: Iterable[ActivityHorizonSnapshot],
) -> TrendDirection:
    directions = tuple(horizon_trend_direction(item) for item in horizons)
    known_count = sum(item is not TrendDirection.UNKNOWN for item in directions)
    if known_count < 2:
        return TrendDirection.UNKNOWN

    up_count = sum(item is TrendDirection.UP for item in directions)
    down_count = sum(item is TrendDirection.DOWN for item in directions)
    if up_count and down_count:
        return TrendDirection.MIXED
    if up_count >= 2:
        return TrendDirection.UP
    if down_count >= 2:
        return TrendDirection.DOWN
    if up_count == 0 and down_count == 0:
        return TrendDirection.NEUTRAL
    return TrendDirection.UNKNOWN


def _scope_accepts(scope: MarketScope, market_type: MarketType) -> bool:
    if scope is MarketScope.ALL:
        return market_type in (MarketType.SPOT, MarketType.PERPETUAL)
    if scope is MarketScope.SPOT:
        return market_type is MarketType.SPOT
    return market_type is MarketType.PERPETUAL


def _normalize_trending(snapshot: MarketActivitySnapshot) -> MarketActivitySnapshot:
    direction = summarize_trend_direction(snapshot.horizons)
    found = set(snapshot.characteristics)
    found.discard(MarketCharacteristic.TRENDING)
    if direction in (TrendDirection.UP, TrendDirection.DOWN):
        found.add(MarketCharacteristic.TRENDING)
    characteristics = tuple(item for item in MarketCharacteristic if item in found)
    level, reasons = _interest_level_and_reasons(snapshot, characteristics)
    return snapshot.model_copy(
        update={
            "characteristics": characteristics,
            "interest_level": level,
            "interest_reasons": reasons,
        }
    )


def _horizon_v4(value: ActivityHorizonSnapshot) -> ActivityHorizonSnapshotV4:
    return ActivityHorizonSnapshotV4(
        **value.model_dump(),
        trend_direction=horizon_trend_direction(value),
    )


def _activity_v4(value: MarketActivitySnapshot) -> MarketActivitySnapshotV4:
    horizons = tuple(_horizon_v4(item) for item in value.horizons)
    payload = value.model_dump(exclude={"horizons"})
    return MarketActivitySnapshotV4(
        **payload,
        horizons=horizons,
        trend_direction=summarize_trend_direction(value.horizons),
    )


def _snapshot_v4(value: MarketAttentionSnapshotV3) -> MarketAttentionSnapshotV4:
    return MarketAttentionSnapshotV4(
        market_activity=_activity_v4(value.market_activity),
        microstructure=value.microstructure,
        combined_characteristics=value.combined_characteristics,
        interest_level=value.interest_level,
        interest_reasons=value.interest_reasons,
    )


class ScopedTrendMarketAttentionRadar(MicrostructureMarketAttentionRadar):
    """Radar v3 enriched with a runtime market scope and deterministic trend directions."""

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
            microstructure_provider=microstructure_provider,
            policy=policy,
            microstructure_policy=microstructure_policy,
        )
        self._market_scope = MarketScope.ALL
        self._scope_refresh_lock = asyncio.Lock()
        self._v4_latest: MarketAttentionOverviewV4 | None = None
        self._v4_history: deque[MarketAttentionOverviewV4] = deque(
            maxlen=self._policy.history_limit
        )

    @property
    def market_scope(self) -> MarketScope:
        return self._market_scope

    @property
    def latest(self) -> MarketAttentionOverviewV4:  # type: ignore[override]
        if self._v4_latest is not None:
            return self._v4_latest
        return MarketAttentionOverviewV4.from_v3(
            super().latest,
            market_scope=self._market_scope,
            catalogue_market_count=self._scope_catalogue_count(),
        )

    def history(  # type: ignore[override]
        self, *, limit: int = 24
    ) -> tuple[MarketAttentionOverviewV4, ...]:
        if isinstance(limit, bool) or limit <= 0 or limit > self._policy.history_limit:
            raise ValueError("invalid market attention history limit")
        return tuple(self._v4_history)[-limit:]

    async def set_market_scope(
        self,
        market_scope: MarketScope,
        *,
        observed_at: datetime | None = None,
    ) -> MarketAttentionOverviewV4:
        if not isinstance(market_scope, MarketScope):
            market_scope = MarketScope(market_scope)
        if self._closed:
            raise RuntimeError("market attention radar is closed")

        async with self._scope_refresh_lock:
            self._market_scope = market_scope
            now = (observed_at or datetime.now(UTC)).astimezone(UTC)
            self._v4_latest = MarketAttentionOverviewV4(
                observed_at=now,
                status=RadarStatus.PARTIAL,
                informative_only=True,
                market_scope=market_scope,
                catalogue_market_count=self._scope_catalogue_count(),
            )
            return await self._refresh_v4_once(observed_at=observed_at)

    async def refresh_once(  # type: ignore[override]
        self,
        *,
        observed_at: datetime | None = None,
    ) -> MarketAttentionOverviewV4:
        async with self._scope_refresh_lock:
            return await self._refresh_v4_once(observed_at=observed_at)

    async def _refresh_v4_once(
        self,
        *,
        observed_at: datetime | None = None,
    ) -> MarketAttentionOverviewV4:
        scope = self._market_scope
        base = await super().refresh_once(observed_at=observed_at)
        overview = MarketAttentionOverviewV4.from_v3(
            base,
            market_scope=scope,
            catalogue_market_count=self._scope_catalogue_count(),
        )
        self._v4_latest = overview
        self._v4_history.append(overview)
        return overview

    async def _catalogue_if_due(self, now: datetime) -> tuple[ExecutableMarket, ...]:
        full_catalogue = await super()._catalogue_if_due(now)
        return tuple(
            market
            for market in full_catalogue
            if _scope_accepts(self._market_scope, market.market_type)
        )

    def _fresh_activities(self, now: datetime) -> tuple[MarketActivitySnapshot, ...]:
        return tuple(
            item
            for item in super()._fresh_activities(now)
            if _scope_accepts(self._market_scope, item.market.market_type)
        )

    def _classify_liquidity(
        self,
        activities: tuple[MarketActivitySnapshot, ...],
    ) -> tuple[MarketActivitySnapshot, ...]:
        return tuple(_normalize_trending(item) for item in super()._classify_liquidity(activities))

    def _next_micro_batch(
        self,
        markets: tuple[ExecutableMarket, ...],
    ) -> tuple[ExecutableMarket, ...]:
        if self._market_scope is MarketScope.PERPETUAL:
            return ()
        return super()._next_micro_batch(markets)

    def _fresh_microstructure(
        self,
        now: datetime,
    ) -> dict[ExecutableMarket, MarketMicrostructureSnapshot]:
        if self._market_scope is MarketScope.PERPETUAL:
            return {}
        return super()._fresh_microstructure(now)

    def _scope_catalogue_count(self) -> int:
        return sum(
            _scope_accepts(self._market_scope, market.market_type)
            for market in self._catalogue
        )
