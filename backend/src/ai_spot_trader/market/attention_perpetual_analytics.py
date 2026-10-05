from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import Field

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.attention import (
    AttentionModel,
    MarketAttentionPolicy,
    MarketCatalogue,
    RadarStatus,
)
from ai_spot_trader.market.attention_filters import (
    MarketAttentionSnapshotV6,
    MarketMetadataProvider,
)
from ai_spot_trader.market.attention_scope_trend import MarketScope
from ai_spot_trader.market.attention_structure_prefilter import (
    MarketAttentionOverviewV6Structure,
    MarketStructureScanPolicy,
    StructureAwareFilteredMarketAttentionRadar,
    _structured_candidate_sort_key,
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
    PerpetualAnalyticsStatus,
)
from ai_spot_trader.market.structure import MarketStructurePolicy


class PerpetualAnalyticsRankingComponentName(StrEnum):
    OPEN_INTEREST = "OPEN_INTEREST"
    FUNDING = "FUNDING"
    LIQUIDATION_VOLUME = "LIQUIDATION_VOLUME"
    ORDER_FLOW = "ORDER_FLOW"


class PerpetualAnalyticsRankingSeriesDiagnostic(AttentionModel):
    """Explain whether one source series was usable by the bounded ranking policy."""

    series: str
    status: str
    used: bool = False


class PerpetualAnalyticsRankingComponent(AttentionModel):
    """One independent semantic family; availability alone never earns a point."""

    name: PerpetualAnalyticsRankingComponentName
    contribution: int = Field(default=0, ge=0, le=1)
    evidence: tuple[PerpetualAnalyticsCharacteristic, ...] = ()
    series: tuple[PerpetualAnalyticsRankingSeriesDiagnostic, ...] = ()


class PerpetualAnalyticsRankingContext(AttentionModel):
    """Bounded attention-only score used after candidate admission and Structure ranking."""

    score: int = Field(default=0, ge=0, le=4)
    max_score: int = Field(default=4, ge=4, le=4)
    components: tuple[PerpetualAnalyticsRankingComponent, ...] = ()
    order_flow_deduplicated: bool = False
    order_flow_conflict: bool = False
    applied_to_ranking: bool = False
    rank_before_analytics: int | None = Field(default=None, ge=1)
    rank_after_analytics: int | None = Field(default=None, ge=1)
    rank_change: int | None = None
    ranking_policy: str = "INTEREST_STRUCTURE_ANALYTICS_V1"


class MarketAttentionSnapshotV6Analytics(MarketAttentionSnapshotV6):
    """Additive Futures Analytics candidate extension; protocol remains v6."""

    perpetual_analytics: PerpetualAnalyticsSnapshot | None = None
    analytics_ranking: PerpetualAnalyticsRankingContext | None = None


class MarketAttentionOverviewV6Analytics(MarketAttentionOverviewV6Structure):
    """Additive overview; OHLCV, Structure and Futures Analytics coverage stay separate."""

    shortlist: tuple[MarketAttentionSnapshotV6Analytics, ...] = ()
    perpetual_analytics_coverage: PerpetualAnalyticsCoverageDiagnostics = Field(
        default_factory=PerpetualAnalyticsCoverageDiagnostics
    )


_OI_EVIDENCE = frozenset(
    {
        PerpetualAnalyticsCharacteristic.OPEN_INTEREST_EXPANSION,
        PerpetualAnalyticsCharacteristic.OPEN_INTEREST_CONTRACTION,
    }
)
_FUNDING_EVIDENCE = frozenset(
    {
        PerpetualAnalyticsCharacteristic.FUNDING_POSITIVE_EXTREME,
        PerpetualAnalyticsCharacteristic.FUNDING_NEGATIVE_EXTREME,
    }
)
_LIQUIDATION_EVIDENCE = frozenset(
    {PerpetualAnalyticsCharacteristic.LIQUIDATION_VOLUME_SPIKE}
)
_CVD_EVIDENCE = frozenset(
    {
        PerpetualAnalyticsCharacteristic.CVD_POSITIVE_IMPULSE,
        PerpetualAnalyticsCharacteristic.CVD_NEGATIVE_IMPULSE,
    }
)
_AGGRESSOR_EVIDENCE = frozenset(
    {
        PerpetualAnalyticsCharacteristic.AGGRESSOR_BUY_DOMINANCE,
        PerpetualAnalyticsCharacteristic.AGGRESSOR_SELL_DOMINANCE,
    }
)


def _series_status(value) -> str:
    if value is None:
        return "UNAVAILABLE"
    status = getattr(value, "status", value)
    return status.value if isinstance(status, PerpetualAnalyticsStatus) else str(status)


def _active_evidence(
    analytics: PerpetualAnalyticsSnapshot,
    allowed: frozenset[PerpetualAnalyticsCharacteristic],
    *,
    status: PerpetualAnalyticsStatus | None,
) -> tuple[PerpetualAnalyticsCharacteristic, ...]:
    if status is not PerpetualAnalyticsStatus.AVAILABLE:
        return ()
    return tuple(item for item in analytics.characteristics if item in allowed)


def _direction(
    evidence: tuple[PerpetualAnalyticsCharacteristic, ...],
) -> int:
    positive = {
        PerpetualAnalyticsCharacteristic.CVD_POSITIVE_IMPULSE,
        PerpetualAnalyticsCharacteristic.AGGRESSOR_BUY_DOMINANCE,
    }
    negative = {
        PerpetualAnalyticsCharacteristic.CVD_NEGATIVE_IMPULSE,
        PerpetualAnalyticsCharacteristic.AGGRESSOR_SELL_DOMINANCE,
    }
    has_positive = any(item in positive for item in evidence)
    has_negative = any(item in negative for item in evidence)
    if has_positive == has_negative:
        return 0
    return 1 if has_positive else -1


def _analytics_ranking_context(
    analytics: PerpetualAnalyticsSnapshot,
    *,
    applied_to_ranking: bool,
) -> PerpetualAnalyticsRankingContext:
    """Build four bounded semantic components without using raw score magnitude.

    Signed positive/negative anomalies are symmetric attention evidence. Missing, stale,
    insufficient or technical series contribute zero without subtracting points. CVD and
    Aggressor Differential are one order-flow family and can therefore contribute at most one.
    """

    oi_status = analytics.open_interest_status
    funding_status = analytics.funding.status if analytics.funding is not None else None
    liquidation_status = (
        analytics.liquidation_volume.status
        if analytics.liquidation_volume is not None
        else None
    )
    cvd_status = analytics.cvd.status if analytics.cvd is not None else None
    aggressor_status = (
        analytics.aggressor_differential.status
        if analytics.aggressor_differential is not None
        else None
    )

    oi_evidence = _active_evidence(analytics, _OI_EVIDENCE, status=oi_status)
    funding_evidence = _active_evidence(
        analytics,
        _FUNDING_EVIDENCE,
        status=funding_status,
    )
    liquidation_evidence = _active_evidence(
        analytics,
        _LIQUIDATION_EVIDENCE,
        status=liquidation_status,
    )
    cvd_evidence = _active_evidence(analytics, _CVD_EVIDENCE, status=cvd_status)
    aggressor_evidence = _active_evidence(
        analytics,
        _AGGRESSOR_EVIDENCE,
        status=aggressor_status,
    )

    cvd_direction = _direction(cvd_evidence)
    aggressor_direction = _direction(aggressor_evidence)
    order_flow_deduplicated = (
        cvd_direction != 0
        and aggressor_direction != 0
        and cvd_direction == aggressor_direction
    )
    order_flow_conflict = (
        cvd_direction != 0
        and aggressor_direction != 0
        and cvd_direction != aggressor_direction
    )
    order_flow_contribution = int(
        not order_flow_conflict and (cvd_direction != 0 or aggressor_direction != 0)
    )

    components = (
        PerpetualAnalyticsRankingComponent(
            name=PerpetualAnalyticsRankingComponentName.OPEN_INTEREST,
            contribution=int(bool(oi_evidence)),
            evidence=oi_evidence,
            series=(
                PerpetualAnalyticsRankingSeriesDiagnostic(
                    series="open-interest",
                    status=_series_status(oi_status),
                    used=bool(oi_evidence),
                ),
            ),
        ),
        PerpetualAnalyticsRankingComponent(
            name=PerpetualAnalyticsRankingComponentName.FUNDING,
            contribution=int(bool(funding_evidence)),
            evidence=funding_evidence,
            series=(
                PerpetualAnalyticsRankingSeriesDiagnostic(
                    series="funding",
                    status=_series_status(analytics.funding),
                    used=bool(funding_evidence),
                ),
            ),
        ),
        PerpetualAnalyticsRankingComponent(
            name=PerpetualAnalyticsRankingComponentName.LIQUIDATION_VOLUME,
            contribution=int(bool(liquidation_evidence)),
            evidence=liquidation_evidence,
            series=(
                PerpetualAnalyticsRankingSeriesDiagnostic(
                    series="liquidation-volume",
                    status=_series_status(analytics.liquidation_volume),
                    used=bool(liquidation_evidence),
                ),
            ),
        ),
        PerpetualAnalyticsRankingComponent(
            name=PerpetualAnalyticsRankingComponentName.ORDER_FLOW,
            contribution=order_flow_contribution,
            evidence=tuple((*cvd_evidence, *aggressor_evidence)),
            series=(
                PerpetualAnalyticsRankingSeriesDiagnostic(
                    series="cvd",
                    status=_series_status(analytics.cvd),
                    used=bool(cvd_evidence),
                ),
                PerpetualAnalyticsRankingSeriesDiagnostic(
                    series="aggressor-differential",
                    status=_series_status(analytics.aggressor_differential),
                    used=bool(aggressor_evidence),
                ),
            ),
        ),
    )
    return PerpetualAnalyticsRankingContext(
        score=min(4, sum(item.contribution for item in components)),
        components=components,
        order_flow_deduplicated=order_flow_deduplicated,
        order_flow_conflict=order_flow_conflict,
        applied_to_ranking=applied_to_ranking,
    )


def _analytics_candidate_sort_key(
    item: MarketAttentionSnapshotV6Analytics,
) -> tuple[object, ...]:
    """Inject Analytics only after interest level and confirmed Structure priority."""

    canonical = _structured_candidate_sort_key(item)
    analytics_score = item.analytics_ranking.score if item.analytics_ranking else 0
    return (*canonical[:3], analytics_score, *canonical[3:])


def _rerank_analytics_shortlist(
    shortlist: tuple[MarketAttentionSnapshotV6Analytics, ...],
    *,
    market_scope: MarketScope,
) -> tuple[MarketAttentionSnapshotV6Analytics, ...]:
    """Reorder existing PERP candidates only; never add/drop a market.

    In ALL scope, SPOT positions are frozen because SPOT has no comparable Futures Analytics.
    PERPETUAL candidates may only exchange positions with other PERPETUAL candidates.
    """

    if market_scope is MarketScope.SPOT:
        return shortlist
    perpetual = tuple(
        item
        for item in shortlist
        if item.market.market_type is MarketType.PERPETUAL
    )
    if len(perpetual) < 2:
        return shortlist
    ranked_perpetual = iter(
        sorted(perpetual, key=_analytics_candidate_sort_key, reverse=True)
    )
    return tuple(
        next(ranked_perpetual)
        if item.market.market_type is MarketType.PERPETUAL
        else item
        for item in shortlist
    )


class PerpetualAnalyticsMarketAttentionRadar(StructureAwareFilteredMarketAttentionRadar):
    """Bounded Futures Analytics rotation plus attention-only PERP shortlist reranking."""

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
        # The parent owns candidate admission, candidate_limit and Structure ranking. Analytics
        # scans immediately before Structure, then only reranks PERPs already in that shortlist.
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
        enriched = tuple(
            self._snapshot_with_analytics(
                item,
                observed_at=base.observed_at,
                market_scope=base.market_scope,
            )
            for item in base.shortlist
        )
        ranked = _rerank_analytics_shortlist(
            enriched,
            market_scope=base.market_scope,
        )
        ranking_enabled = (
            base.market_scope is not MarketScope.SPOT
            and sum(
                item.market.market_type is MarketType.PERPETUAL
                for item in enriched
            ) >= 2
        )
        before_positions = {
            (item.market.market_type, item.market.symbol): index
            for index, item in enumerate(enriched, start=1)
        }
        after_positions = {
            (item.market.market_type, item.market.symbol): index
            for index, item in enumerate(ranked, start=1)
        }
        shortlist = tuple(
            item.model_copy(
                update={
                    "analytics_ranking": item.analytics_ranking.model_copy(
                        update={
                            "applied_to_ranking": ranking_enabled,
                            "rank_before_analytics": before_positions[
                                (item.market.market_type, item.market.symbol)
                            ],
                            "rank_after_analytics": after_positions[
                                (item.market.market_type, item.market.symbol)
                            ],
                            "rank_change": (
                                before_positions[(item.market.market_type, item.market.symbol)]
                                - after_positions[(item.market.market_type, item.market.symbol)]
                            ),
                        }
                    )
                }
            )
            if item.analytics_ranking is not None
            else item
            for item in ranked
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
        market_scope: MarketScope,
    ) -> MarketAttentionSnapshotV6Analytics:
        analytics = self._perpetual_analytics.snapshot_for(
            item.market,
            as_of=observed_at,
        )
        ranking = (
            _analytics_ranking_context(
                analytics,
                applied_to_ranking=False,
            )
            if item.market.market_type is MarketType.PERPETUAL
            else None
        )
        characteristics = list(item.combined_characteristics)
        reasons = list(item.interest_reasons)
        labels = {
            PerpetualAnalyticsCharacteristic.OPEN_INTEREST_EXPANSION: (
                "OPEN_INTEREST_EXPANSION",
                "Open Interest historiquement élevé vs baseline propre au marché",
            ),
            PerpetualAnalyticsCharacteristic.OPEN_INTEREST_CONTRACTION: (
                "OPEN_INTEREST_CONTRACTION",
                "Open Interest historiquement faible vs baseline propre au marché",
            ),
            PerpetualAnalyticsCharacteristic.FUNDING_POSITIVE_EXTREME: (
                "FUNDING_POSITIVE_EXTREME",
                "Funding relatif positif inhabituel vs historique propre au marché",
            ),
            PerpetualAnalyticsCharacteristic.FUNDING_NEGATIVE_EXTREME: (
                "FUNDING_NEGATIVE_EXTREME",
                "Funding relatif négatif inhabituel vs historique propre au marché",
            ),
            PerpetualAnalyticsCharacteristic.LIQUIDATION_VOLUME_SPIKE: (
                "LIQUIDATION_VOLUME_SPIKE",
                "Volume total de liquidations inhabituellement élevé vs historique propre au marché",
            ),
            PerpetualAnalyticsCharacteristic.CVD_POSITIVE_IMPULSE: (
                "CVD_POSITIVE_IMPULSE",
                "Impulsion CVD positive inhabituelle vs historique propre au marché",
            ),
            PerpetualAnalyticsCharacteristic.CVD_NEGATIVE_IMPULSE: (
                "CVD_NEGATIVE_IMPULSE",
                "Impulsion CVD négative inhabituelle vs historique propre au marché",
            ),
            PerpetualAnalyticsCharacteristic.AGGRESSOR_BUY_DOMINANCE: (
                "AGGRESSOR_BUY_DOMINANCE",
                "Pression agressive acheteuse inhabituellement forte vs historique propre au marché",
            ),
            PerpetualAnalyticsCharacteristic.AGGRESSOR_SELL_DOMINANCE: (
                "AGGRESSOR_SELL_DOMINANCE",
                "Pression agressive vendeuse inhabituellement forte vs historique propre au marché",
            ),
        }
        for characteristic in analytics.characteristics:
            mapped = labels.get(characteristic)
            if mapped is None:
                continue
            label, reason = mapped
            characteristics.append(label)
            reasons.append(reason)

        payload = item.model_dump()
        payload["combined_characteristics"] = tuple(dict.fromkeys(characteristics))
        payload["interest_reasons"] = tuple(dict.fromkeys(reasons))[:8]
        return MarketAttentionSnapshotV6Analytics(
            **payload,
            perpetual_analytics=analytics,
            analytics_ranking=ranking,
        )
