from __future__ import annotations

from collections import deque
from datetime import UTC, datetime

from pydantic import Field

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.attention import MarketAttentionPolicy, MarketCatalogue, RadarStatus
from ai_spot_trader.market.attention_filters import (
    MarketAttentionSnapshotV6,
    MarketMetadataProvider,
)
from ai_spot_trader.market.attention_structure_prefilter import (
    MarketAttentionOverviewV6Structure,
    MarketStructureScanPolicy,
    StructureAwareFilteredMarketAttentionRadar,
)
from ai_spot_trader.market.candles import CandleStreamService
from ai_spot_trader.market.microstructure import MicrostructurePolicy, MicrostructureProvider
from ai_spot_trader.market.perpetual_analytics import (
    PerpetualAnalyticsCharacteristic,
    PerpetualAnalyticsCoverageDiagnostics,
    PerpetualAnalyticsPolicy,
    PerpetualAnalyticsProvider,
    PerpetualAnalyticsScanner,
    PerpetualAnalyticsSnapshot,
)
from ai_spot_trader.market.structure import MarketStructurePolicy


class MarketAttentionSnapshotV6Analytics(MarketAttentionSnapshotV6):
    """Additive Batch 47.2 candidate extension; protocol remains v6."""

    perpetual_analytics: PerpetualAnalyticsSnapshot | None = None


class MarketAttentionOverviewV6Analytics(MarketAttentionOverviewV6Structure):
    """Additive Batch 47.2 overview; OHLCV and Structure coverage stay separate."""

    shortlist: tuple[MarketAttentionSnapshotV6Analytics, ...] = ()
    perpetual_analytics_coverage: PerpetualAnalyticsCoverageDiagnostics = Field(
        default_factory=PerpetualAnalyticsCoverageDiagnostics
    )


class PerpetualAnalyticsMarketAttentionRadar(StructureAwareFilteredMarketAttentionRadar):
    """Batch 47.2 Radar: independent bounded historical OI rotation, descriptive only."""

    def __init__(
        self,
        *,
        candle_service: CandleStreamService,
        catalogue: MarketCatalogue,
        microstructure_provider: MicrostructureProvider,
        metadata_provider: MarketMetadataProvider,
        analytics_provider: PerpetualAnalyticsProvider,
        policy: MarketAttentionPolicy | None = None,
        microstructure_policy: MicrostructurePolicy | None = None,
        structure_policy: MarketStructurePolicy | None = None,
        structure_scan_policy: MarketStructureScanPolicy | None = None,
        analytics_policy: PerpetualAnalyticsPolicy | None = None,
    ) -> None:
        super().__init__(
            candle_service=candle_service,
            catalogue=catalogue,
            microstructure_provider=microstructure_provider,
            metadata_provider=metadata_provider,
            policy=policy,
            microstructure_policy=microstructure_policy,
            structure_policy=structure_policy,
            structure_scan_policy=structure_scan_policy,
        )
        self._perpetual_analytics = PerpetualAnalyticsScanner(
            analytics_provider,
            policy=analytics_policy,
            refresh_seconds=self._policy.refresh_seconds,
        )
        self._v6_analytics_latest: MarketAttentionOverviewV6Analytics | None = None
        self._v6_analytics_history: deque[MarketAttentionOverviewV6Analytics] = deque(
            maxlen=self._policy.history_limit
        )

    @property
    def latest(self) -> MarketAttentionOverviewV6Analytics:  # type: ignore[override]
        if self._v6_analytics_latest is not None:
            return self._v6_analytics_latest
        base = super().latest
        eligible = self._analytics_eligible_markets(base.observed_at)
        return self._overview_with_analytics(
            base,
            coverage=self._perpetual_analytics.coverage(
                eligible,
                as_of=base.observed_at,
            ),
        )

    def history(  # type: ignore[override]
        self,
        *,
        limit: int = 24,
    ) -> tuple[MarketAttentionOverviewV6Analytics, ...]:
        if isinstance(limit, bool) or limit <= 0 or limit > self._policy.history_limit:
            raise ValueError("invalid market attention history limit")
        return tuple(self._v6_analytics_history)[-limit:]

    async def _refresh_v4_once(  # type: ignore[override]
        self,
        *,
        observed_at: datetime | None = None,
    ) -> MarketAttentionOverviewV6Analytics:
        # The parent still owns the canonical shortlist/ranking. Our _scan_structure override
        # inserts the independent OI rotation immediately before Structure scanning, after the
        # cheap scope/cap/OHLCV/volume/activity filters have populated the eligible cache.
        base = await super()._refresh_v4_once(observed_at=observed_at)
        now = base.observed_at.astimezone(UTC)
        eligible = self._analytics_eligible_markets(now)
        overview = self._overview_with_analytics(
            base,
            coverage=self._perpetual_analytics.coverage(eligible, as_of=now),
        )
        self._v6_analytics_latest = overview
        self._v6_analytics_history.append(overview)
        return overview

    async def _scan_structure(  # type: ignore[override]
        self,
        markets: tuple[ExecutableMarket, ...],
        *,
        observed_at: datetime,
    ) -> int:
        eligible = self._analytics_eligible_markets(observed_at)
        await self._perpetual_analytics.scan(eligible, as_of=observed_at)
        return await super()._scan_structure(markets, observed_at=observed_at)

    def _analytics_eligible_markets(
        self, now: datetime
    ) -> tuple[ExecutableMarket, ...]:
        return tuple(
            item.market
            for item in self._fresh_activities(now)
            if item.status is RadarStatus.AVAILABLE
            and item.market.market_type is MarketType.PERPETUAL
        )

    def _overview_with_analytics(
        self,
        base: MarketAttentionOverviewV6Structure,
        *,
        coverage: PerpetualAnalyticsCoverageDiagnostics,
    ) -> MarketAttentionOverviewV6Analytics:
        shortlist = tuple(
            self._snapshot_with_analytics(item, observed_at=base.observed_at)
            for item in base.shortlist
        )
        payload = base.model_dump(exclude={"shortlist"})
        return MarketAttentionOverviewV6Analytics(
            **payload,
            shortlist=shortlist,
            perpetual_analytics_coverage=coverage,
        )

    def _snapshot_with_analytics(
        self,
        item: MarketAttentionSnapshotV6,
        *,
        observed_at: datetime,
    ) -> MarketAttentionSnapshotV6Analytics:
        analytics = self._perpetual_analytics.snapshot_for(
            item.market,
            as_of=observed_at,
        )
        characteristics = list(item.combined_characteristics)
        reasons = list(item.interest_reasons)
        if (
            PerpetualAnalyticsCharacteristic.OPEN_INTEREST_EXPANSION
            in analytics.characteristics
        ):
            characteristics.append("OPEN_INTEREST_EXPANSION")
            reasons.append("Open Interest historiquement élevé vs baseline propre au marché")
        if (
            PerpetualAnalyticsCharacteristic.OPEN_INTEREST_CONTRACTION
            in analytics.characteristics
        ):
            characteristics.append("OPEN_INTEREST_CONTRACTION")
            reasons.append("Open Interest historiquement faible vs baseline propre au marché")

        payload = item.model_dump()
        payload["combined_characteristics"] = tuple(dict.fromkeys(characteristics))
        payload["interest_reasons"] = tuple(dict.fromkeys(reasons))[:8]
        return MarketAttentionSnapshotV6Analytics(
            **payload,
            perpetual_analytics=analytics,
        )
