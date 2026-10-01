from __future__ import annotations

import asyncio
from collections import deque
from datetime import UTC, datetime

from pydantic import Field, model_validator

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
from ai_spot_trader.market.attention_microstructure import (
    MicrostructureQualityCounts,
    MicrostructureStatusCounts,
)
from ai_spot_trader.market.attention_scope_trend import (
    MarketActivitySnapshotV4,
    MarketAttentionOverviewV4,
    MarketAttentionSnapshotV4,
    MarketScope,
    ScopedTrendMarketAttentionRadar,
)
from ai_spot_trader.market.candles import CandleKey, CandleStreamService, CandleTimeframe
from ai_spot_trader.market.microstructure import (
    MarketMicrostructureSnapshot,
    MicrostructurePolicy,
    MicrostructureProvider,
)
from ai_spot_trader.market.structure import (
    STRUCTURE_TIMEFRAMES,
    MarketStructureAnalyzer,
    MarketStructurePolicy,
    MultiTimeframeMarketStructure,
    TimeframeMarketStructure,
    summarize_market_structures,
)


class MarketAttentionSnapshotV5(AttentionModel):
    market_activity: MarketActivitySnapshotV4
    microstructure: MarketMicrostructureSnapshot
    market_structure: MultiTimeframeMarketStructure
    combined_characteristics: tuple[str, ...] = ()
    interest_level: RadarInterestLevel = RadarInterestLevel.LOW
    interest_reasons: tuple[str, ...] = ()

    @property
    def market(self) -> ExecutableMarket:
        return self.market_activity.market


class MarketAttentionOverviewV5(AttentionModel):
    protocol_version: str = "market-attention-radar-v5"
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
    shortlist: tuple[MarketAttentionSnapshotV5, ...] = ()
    error_type: str | None = None

    @model_validator(mode="after")
    def validate_overview(self) -> "MarketAttentionOverviewV5":
        if self.protocol_version != "market-attention-radar-v5":
            raise ValueError("unsupported market attention protocol")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("market attention observed_at must be timezone-aware")
        if not self.informative_only:
            raise ValueError("Market Attention Radar v5 must remain informative_only")
        return self

    @classmethod
    def from_v4(
        cls,
        value: MarketAttentionOverviewV4,
        *,
        shortlist: tuple[MarketAttentionSnapshotV5, ...] | None = None,
        structure_policy: MarketStructurePolicy | None = None,
    ) -> "MarketAttentionOverviewV5":
        policy = structure_policy or MarketStructurePolicy()
        if shortlist is None:
            shortlist = tuple(_snapshot_with_unknown_structure(item, policy=policy) for item in value.shortlist)
        payload = value.model_dump(exclude={"protocol_version", "shortlist", "candidate_market_count"})
        return cls(
            **payload,
            candidate_market_count=len(shortlist),
            shortlist=shortlist,
        )


class StructuredMarketAttentionRadar(ScopedTrendMarketAttentionRadar):
    """Batch 42: v4 Radar plus causal native-timeframe market structure on the shortlist."""

    def __init__(
        self,
        *,
        candle_service: CandleStreamService,
        catalogue: MarketCatalogue,
        microstructure_provider: MicrostructureProvider,
        policy: MarketAttentionPolicy | None = None,
        microstructure_policy: MicrostructurePolicy | None = None,
        structure_policy: MarketStructurePolicy | None = None,
    ) -> None:
        super().__init__(
            candle_service=candle_service,
            catalogue=catalogue,
            microstructure_provider=microstructure_provider,
            policy=policy,
            microstructure_policy=microstructure_policy,
        )
        self._structure_policy = structure_policy or MarketStructurePolicy()
        self._structure_analyzer = MarketStructureAnalyzer(policy=self._structure_policy)
        self._structure_semaphore = asyncio.Semaphore(self._structure_policy.fetch_concurrency)
        self._v5_latest: MarketAttentionOverviewV5 | None = None
        self._v5_history: deque[MarketAttentionOverviewV5] = deque(
            maxlen=self._policy.history_limit
        )

    @property
    def latest(self) -> MarketAttentionOverviewV5:  # type: ignore[override]
        if self._v5_latest is not None:
            return self._v5_latest
        return MarketAttentionOverviewV5.from_v4(
            super().latest,
            structure_policy=self._structure_policy,
        )

    def history(  # type: ignore[override]
        self, *, limit: int = 24
    ) -> tuple[MarketAttentionOverviewV5, ...]:
        if isinstance(limit, bool) or limit <= 0 or limit > self._policy.history_limit:
            raise ValueError("invalid market attention history limit")
        return tuple(self._v5_history)[-limit:]

    async def _refresh_v4_once(  # type: ignore[override]
        self,
        *,
        observed_at: datetime | None = None,
    ) -> MarketAttentionOverviewV5:
        base = await super()._refresh_v4_once(observed_at=observed_at)
        enriched = await asyncio.gather(
            *(self._enrich_snapshot(item, observed_at=base.observed_at) for item in base.shortlist)
        )
        overview = MarketAttentionOverviewV5.from_v4(
            base,
            shortlist=tuple(enriched),
            structure_policy=self._structure_policy,
        )
        self._v5_latest = overview
        self._v5_history.append(overview)
        return overview

    async def _enrich_snapshot(
        self,
        value: MarketAttentionSnapshotV4,
        *,
        observed_at: datetime,
    ) -> MarketAttentionSnapshotV5:
        structure = await self._market_structure_for_market(
            value.market_activity.market,
            observed_at=observed_at,
        )
        return MarketAttentionSnapshotV5(
            market_activity=value.market_activity,
            microstructure=value.microstructure,
            market_structure=structure,
            combined_characteristics=value.combined_characteristics,
            interest_level=value.interest_level,
            interest_reasons=value.interest_reasons,
        )

    async def _market_structure_for_market(
        self,
        market: ExecutableMarket,
        *,
        observed_at: datetime,
    ) -> MultiTimeframeMarketStructure:
        async def one(timeframe: CandleTimeframe) -> TimeframeMarketStructure:
            async with self._structure_semaphore:
                try:
                    candles = await self._candles.history_as_of(
                        CandleKey(
                            symbol=market.symbol,
                            market_type=market.market_type,
                            timeframe=timeframe,
                        ),
                        as_of=observed_at,
                        limit=self._structure_policy.history_limit,
                    )
                    return self._structure_analyzer.analyze(
                        timeframe=timeframe,
                        candles=candles,
                        observed_at=observed_at,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    return self._structure_analyzer.unknown(
                        timeframe=timeframe,
                        error_type=type(exc).__name__,
                    )

        structures = await asyncio.gather(*(one(timeframe) for timeframe in STRUCTURE_TIMEFRAMES))
        return summarize_market_structures(
            observed_at=observed_at.astimezone(UTC),
            timeframes=structures,
        )


def _snapshot_with_unknown_structure(
    value: MarketAttentionSnapshotV4,
    *,
    policy: MarketStructurePolicy,
) -> MarketAttentionSnapshotV5:
    analyzer = MarketStructureAnalyzer(policy=policy)
    structure = summarize_market_structures(
        observed_at=value.market_activity.observed_at,
        timeframes=(
            analyzer.unknown(timeframe=timeframe)
            for timeframe in STRUCTURE_TIMEFRAMES
        ),
    )
    return MarketAttentionSnapshotV5(
        market_activity=value.market_activity,
        microstructure=value.microstructure,
        market_structure=structure,
        combined_characteristics=value.combined_characteristics,
        interest_level=value.interest_level,
        interest_reasons=value.interest_reasons,
    )
