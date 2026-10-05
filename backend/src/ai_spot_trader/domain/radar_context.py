from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, model_validator

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import DomainModel, NonEmptyText, UtcDateTime
from ai_spot_trader.domain.symbols import parse_canonical_symbol

RadarFactStatus = Literal[
    "AVAILABLE",
    "PARTIAL",
    "STALE",
    "INSUFFICIENT_HISTORY",
    "TECHNICAL_ERROR",
    "NOT_APPLICABLE",
    "UNAVAILABLE",
]


class RadarContextModel(DomainModel):
    """Immutable strict base for one cycle-frozen Radar/Analytics strategic context."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class RadarActivityHorizonFact(RadarContextModel):
    timeframe: NonEmptyText
    trend_direction: NonEmptyText | None = None
    volume_ratio: Decimal | None = None
    volume_anomaly_score: Decimal | None = None
    price_return: Decimal | None = None
    range_anomaly_score: Decimal | None = None
    volatility_anomaly_score: Decimal | None = None
    complete: bool


class RadarActivityFact(RadarContextModel):
    status: RadarFactStatus
    observed_at: UtcDateTime | None = None
    freshness_seconds: Annotated[Decimal, Field(ge=0)] | None = None
    data_quality: NonEmptyText | None = None
    activity_state: NonEmptyText | None = None
    trend_direction: NonEmptyText | None = None
    liquidity_regime: NonEmptyText | None = None
    liquidity_reference_usd: Annotated[Decimal, Field(ge=0)] | None = None
    interest_level: NonEmptyText | None = None
    characteristics: Annotated[tuple[NonEmptyText, ...], Field(max_length=12)] = ()
    horizons: Annotated[tuple[RadarActivityHorizonFact, ...], Field(max_length=4)] = ()
    volume_24h_usd: Annotated[Decimal, Field(ge=0)] | None = None


class RadarMicrostructureFact(RadarContextModel):
    status: RadarFactStatus
    observed_at: UtcDateTime | None = None
    freshness_seconds: Annotated[Decimal, Field(ge=0)] | None = None
    data_quality: NonEmptyText | None = None
    spread_bps: Annotated[Decimal, Field(ge=0)] | None = None
    total_depth_quote: Annotated[Decimal, Field(ge=0)] | None = None
    book_imbalance: Annotated[Decimal, Field(ge=-1, le=1)] | None = None


class RadarStructureTimeframeFact(RadarContextModel):
    timeframe: NonEmptyText
    state: NonEmptyText
    event: NonEmptyText | None = None
    latest_final_close: UtcDateTime | None = None


class RadarStructureFact(RadarContextModel):
    status: RadarFactStatus
    observed_at: UtcDateTime | None = None
    global_state: NonEmptyText | None = None
    timeframes: Annotated[tuple[RadarStructureTimeframeFact, ...], Field(max_length=4)] = ()


class RadarAnalyticsRankingComponentFact(RadarContextModel):
    name: Literal["OPEN_INTEREST", "FUNDING", "LIQUIDATION_VOLUME", "ORDER_FLOW"]
    contribution: Annotated[int, Field(ge=0, le=1)]
    evidence: Annotated[tuple[NonEmptyText, ...], Field(max_length=2)] = ()


class RadarAnalyticsRankingFact(RadarContextModel):
    score: Annotated[int, Field(ge=0, le=4)]
    max_score: Literal[4] = 4
    components: Annotated[
        tuple[RadarAnalyticsRankingComponentFact, ...], Field(max_length=4)
    ] = ()
    order_flow_deduplicated: bool = False
    order_flow_conflict: bool = False

    @model_validator(mode="after")
    def validate_components(self) -> "RadarAnalyticsRankingFact":
        names = tuple(item.name for item in self.components)
        if len(set(names)) != len(names):
            raise ValueError("Analytics ranking components must be unique")
        if sum(item.contribution for item in self.components) != self.score:
            raise ValueError("Analytics ranking score must equal component contributions")
        return self


class OpenInterestStrategicFact(RadarContextModel):
    status: RadarFactStatus
    observed_at: UtcDateTime | None = None
    freshness_seconds: Annotated[Decimal, Field(ge=0)] | None = None
    current: Annotated[Decimal, Field(ge=0)] | None = None
    change_ratio: Decimal | None = None
    anomaly_score: Decimal | None = None


class FundingStrategicFact(RadarContextModel):
    status: RadarFactStatus
    observed_at: UtcDateTime | None = None
    freshness_seconds: Annotated[Decimal, Field(ge=0)] | None = None
    current_relative_rate: Decimal | None = None
    relative_rate_change: Decimal | None = None
    anomaly_score: Decimal | None = None


class LiquidationVolumeStrategicFact(RadarContextModel):
    status: RadarFactStatus
    observed_at: UtcDateTime | None = None
    freshness_seconds: Annotated[Decimal, Field(ge=0)] | None = None
    current_volume: Annotated[Decimal, Field(ge=0)] | None = None
    change_ratio: Decimal | None = None
    anomaly_score: Decimal | None = None


class CvdStrategicFact(RadarContextModel):
    status: RadarFactStatus
    observed_at: UtcDateTime | None = None
    freshness_seconds: Annotated[Decimal, Field(ge=0)] | None = None
    current_change: Decimal | None = None
    anomaly_score: Decimal | None = None


class AggressorDifferentialStrategicFact(RadarContextModel):
    status: RadarFactStatus
    observed_at: UtcDateTime | None = None
    freshness_seconds: Annotated[Decimal, Field(ge=0)] | None = None
    current_value: Decimal | None = None
    value_change: Decimal | None = None
    anomaly_score: Decimal | None = None


class PerpetualAnalyticsStrategicFact(RadarContextModel):
    status: RadarFactStatus
    observed_at: UtcDateTime | None = None
    ranking: RadarAnalyticsRankingFact | None = None
    open_interest: OpenInterestStrategicFact
    funding: FundingStrategicFact
    liquidation_volume: LiquidationVolumeStrategicFact
    cvd: CvdStrategicFact
    aggressor_differential: AggressorDifferentialStrategicFact
    characteristics: Annotated[tuple[NonEmptyText, ...], Field(max_length=8)] = ()


class RadarMarketStrategicContext(RadarContextModel):
    symbol: NonEmptyText
    market_type: MarketType
    activity: RadarActivityFact
    microstructure: RadarMicrostructureFact
    structure: RadarStructureFact
    perpetual_analytics: PerpetualAnalyticsStrategicFact

    @model_validator(mode="after")
    def validate_market(self) -> "RadarMarketStrategicContext":
        parse_canonical_symbol(self.symbol)
        if self.market_type is MarketType.FUTURE:
            raise ValueError("dated FUTURE cannot appear in Agent Radar context")
        analytics = self.perpetual_analytics
        if self.market_type is MarketType.SPOT:
            facts = (
                analytics.open_interest,
                analytics.funding,
                analytics.liquidation_volume,
                analytics.cvd,
                analytics.aggressor_differential,
            )
            if analytics.status != "NOT_APPLICABLE" or any(
                item.status != "NOT_APPLICABLE" for item in facts
            ):
                raise ValueError("SPOT Futures Analytics must be NOT_APPLICABLE")
            if analytics.ranking is not None:
                raise ValueError("SPOT cannot expose a Futures Analytics ranking")
        return self


class RadarAnalyticsStrategicContext(RadarContextModel):
    """Bounded descriptive facts frozen from the exact Radar snapshot used for discovery."""

    context_version: Literal["radar-analytics-strategic-v1"] = "radar-analytics-strategic-v1"
    observed_at: UtcDateTime
    markets: Annotated[tuple[RadarMarketStrategicContext, ...], Field(min_length=1, max_length=20)]

    @model_validator(mode="after")
    def validate_context(self) -> "RadarAnalyticsStrategicContext":
        ordered = tuple(
            sorted(self.markets, key=lambda item: (item.market_type.value, item.symbol))
        )
        if ordered != self.markets:
            raise ValueError("Radar strategic context markets must use deterministic sorted order")
        keys = tuple((item.symbol, item.market_type) for item in self.markets)
        if len(set(keys)) != len(keys):
            raise ValueError("Radar strategic context markets must be unique")
        for market in self.markets:
            self._validate_market_causality(market)
        return self

    def _validate_market_causality(self, market: RadarMarketStrategicContext) -> None:
        timestamps = [
            market.activity.observed_at,
            market.microstructure.observed_at,
            market.structure.observed_at,
            market.perpetual_analytics.observed_at,
            *(item.latest_final_close for item in market.structure.timeframes),
            market.perpetual_analytics.open_interest.observed_at,
            market.perpetual_analytics.funding.observed_at,
            market.perpetual_analytics.liquidation_volume.observed_at,
            market.perpetual_analytics.cvd.observed_at,
            market.perpetual_analytics.aggressor_differential.observed_at,
        ]
        if any(value is not None and value > self.observed_at for value in timestamps):
            raise ValueError("Radar strategic context contains post-snapshot data")


def restrict_radar_analytics_context(
    context: RadarAnalyticsStrategicContext | None,
    *,
    markets: tuple[tuple[str, MarketType], ...],
) -> RadarAnalyticsStrategicContext | None:
    if context is None:
        return None
    allowed = set(markets)
    selected = tuple(
        item for item in context.markets if (item.symbol, item.market_type) in allowed
    )
    if not selected:
        return None
    return RadarAnalyticsStrategicContext(
        observed_at=context.observed_at,
        markets=selected,
    )


__all__ = [
    "AggressorDifferentialStrategicFact",
    "CvdStrategicFact",
    "FundingStrategicFact",
    "LiquidationVolumeStrategicFact",
    "OpenInterestStrategicFact",
    "PerpetualAnalyticsStrategicFact",
    "RadarActivityFact",
    "RadarActivityHorizonFact",
    "RadarAnalyticsRankingComponentFact",
    "RadarAnalyticsRankingFact",
    "RadarAnalyticsStrategicContext",
    "RadarFactStatus",
    "RadarMarketStrategicContext",
    "RadarMicrostructureFact",
    "RadarStructureFact",
    "RadarStructureTimeframeFact",
    "restrict_radar_analytics_context",
]
