from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Protocol, cast

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.domain.radar_context import (
    AggressorDifferentialStrategicFact,
    CvdStrategicFact,
    FundingStrategicFact,
    LiquidationVolumeStrategicFact,
    OpenInterestStrategicFact,
    PerpetualAnalyticsStrategicFact,
    RadarActivityFact,
    RadarActivityHorizonFact,
    RadarAnalyticsRankingComponentFact,
    RadarAnalyticsRankingFact,
    RadarAnalyticsStrategicContext,
    RadarFactStatus,
    RadarMarketStrategicContext,
    RadarMicrostructureFact,
    RadarStructureFact,
    RadarStructureTimeframeFact,
)


class RadarContextSnapshotInvalidError(ValueError):
    pass


class RadarContextShortlistItem(Protocol):
    @property
    def market(self) -> ExecutableMarket: ...


class RadarContextOverview(Protocol):
    observed_at: datetime
    shortlist: tuple[RadarContextShortlistItem, ...]


def build_radar_analytics_strategic_context(
    overview: RadarContextOverview,
    *,
    markets: tuple[ExecutableMarket, ...],
) -> RadarAnalyticsStrategicContext:
    """Project the exact accepted Radar snapshot into a bounded cycle-frozen Agent context."""

    observed_at = _aware_utc(overview.observed_at, "Radar overview observed_at")
    requested = tuple(sorted(set(markets), key=lambda item: (item.market_type.value, item.symbol)))
    if not requested:
        raise RadarContextSnapshotInvalidError("Radar Agent context requires accepted markets")
    if any(item.market_type is MarketType.FUTURE for item in requested):
        raise RadarContextSnapshotInvalidError("dated FUTURE cannot enter Radar Agent context")

    by_market: dict[ExecutableMarket, object] = {}
    for item in overview.shortlist:
        market = item.market
        if market not in by_market:
            by_market[market] = item

    projected: list[RadarMarketStrategicContext] = []
    for market in requested:
        item = by_market.get(market)
        if item is None:
            raise RadarContextSnapshotInvalidError(
                "accepted market is absent from the frozen Radar shortlist"
            )
        projected.append(_market_context(item, market=market, observed_at=observed_at))

    try:
        return RadarAnalyticsStrategicContext(
            observed_at=observed_at,
            markets=tuple(projected),
        )
    except ValueError as exc:
        raise RadarContextSnapshotInvalidError(str(exc)) from exc


def _market_context(
    item: object,
    *,
    market: ExecutableMarket,
    observed_at: datetime,
) -> RadarMarketStrategicContext:
    activity = getattr(item, "market_activity", None)
    microstructure = getattr(item, "microstructure", None)
    structure = getattr(item, "market_structure", None)
    analytics = getattr(item, "perpetual_analytics", None)
    ranking = getattr(item, "analytics_ranking", None)

    activity_horizons = tuple(
        RadarActivityHorizonFact(
            timeframe=_required_value(horizon.timeframe, "activity horizon timeframe"),
            trend_direction=_value(getattr(horizon, "trend_direction", None)),
            volume_ratio=getattr(horizon, "volume_ratio", None),
            volume_anomaly_score=getattr(horizon, "volume_anomaly_score", None),
            price_return=getattr(horizon, "price_return", None),
            range_anomaly_score=getattr(horizon, "range_anomaly_score", None),
            volatility_anomaly_score=getattr(horizon, "volatility_anomaly_score", None),
            complete=bool(getattr(horizon, "complete", False)),
        )
        for horizon in tuple(getattr(activity, "horizons", ()))[:4]
    )
    activity_fact = RadarActivityFact(
        status=_fact_status(getattr(activity, "status", None)),
        observed_at=_optional_utc(getattr(activity, "observed_at", None), observed_at),
        freshness_seconds=getattr(activity, "freshness_seconds", None),
        data_quality=_value(getattr(activity, "data_quality", None)),
        activity_state=_value(getattr(activity, "activity_state", None)),
        trend_direction=_value(getattr(activity, "trend_direction", None)),
        liquidity_regime=_value(getattr(activity, "liquidity_regime", None)),
        liquidity_reference_usd=getattr(activity, "liquidity_reference_usd", None),
        interest_level=_value(getattr(item, "interest_level", None)),
        characteristics=tuple(
            _required_value(value, "Radar characteristic")
            for value in tuple(getattr(item, "combined_characteristics", ()))[:12]
        ),
        horizons=activity_horizons,
        volume_24h_usd=getattr(item, "volume_24h_usd", None),
    )

    microstructure_fact = RadarMicrostructureFact(
        status=_fact_status(getattr(microstructure, "status", None)),
        observed_at=_optional_utc(getattr(microstructure, "observed_at", None), observed_at),
        freshness_seconds=getattr(microstructure, "freshness_seconds", None),
        data_quality=_value(getattr(microstructure, "data_quality", None)),
        spread_bps=getattr(microstructure, "spread_bps", None),
        total_depth_quote=getattr(microstructure, "total_depth_quote", None),
        book_imbalance=getattr(microstructure, "book_imbalance", None),
    )

    structure_fact = _structure_fact(structure, observed_at=observed_at)
    analytics_fact = _analytics_fact(
        analytics,
        ranking=ranking,
        market_type=market.market_type,
        observed_at=observed_at,
    )
    return RadarMarketStrategicContext(
        symbol=market.symbol,
        market_type=market.market_type,
        activity=activity_fact,
        microstructure=microstructure_fact,
        structure=structure_fact,
        perpetual_analytics=analytics_fact,
    )


def _structure_fact(value: object | None, *, observed_at: datetime) -> RadarStructureFact:
    if value is None:
        return RadarStructureFact(status="UNAVAILABLE")
    frames = tuple(getattr(value, "timeframes", ()))[:4]
    facts = tuple(
        RadarStructureTimeframeFact(
            timeframe=_required_value(frame.timeframe, "structure timeframe"),
            state=_required_value(frame.state, "structure state"),
            event=_value(getattr(frame, "event", None)),
            latest_final_close=_optional_utc(
                getattr(frame, "latest_final_close", None), observed_at
            ),
        )
        for frame in frames
    )
    has_error = any(getattr(frame, "error_type", None) is not None for frame in frames)
    has_known = any(item.state != "UNKNOWN" for item in facts)
    status: RadarFactStatus
    if has_error and not has_known:
        status = "TECHNICAL_ERROR"
    elif has_error or len(facts) < 4 or not has_known:
        status = "PARTIAL"
    else:
        status = "AVAILABLE"
    return RadarStructureFact(
        status=status,
        observed_at=_optional_utc(getattr(value, "observed_at", None), observed_at),
        global_state=_value(getattr(value, "global_state", None)),
        timeframes=facts,
    )


def _analytics_fact(
    analytics: object | None,
    *,
    ranking: object | None,
    market_type: MarketType,
    observed_at: datetime,
) -> PerpetualAnalyticsStrategicFact:
    if market_type is MarketType.SPOT:
        return _not_applicable_analytics()
    if analytics is None:
        return _unavailable_analytics()

    overall_status = _fact_status(getattr(analytics, "status", None))
    analytics_at = _optional_utc(getattr(analytics, "observed_at", None), observed_at)
    funding = getattr(analytics, "funding", None)
    liquidations = getattr(analytics, "liquidation_volume", None)
    cvd = getattr(analytics, "cvd", None)
    aggressor = getattr(analytics, "aggressor_differential", None)

    return PerpetualAnalyticsStrategicFact(
        status=overall_status,
        observed_at=analytics_at,
        ranking=_ranking_fact(ranking),
        open_interest=OpenInterestStrategicFact(
            status=_fact_status(getattr(analytics, "open_interest_status", None)),
            observed_at=_optional_utc(
                getattr(analytics, "current_open_interest_observed_at", None), observed_at
            ),
            freshness_seconds=getattr(analytics, "freshness_seconds", None),
            current=getattr(analytics, "current_open_interest", None),
            change_ratio=getattr(analytics, "open_interest_change_ratio", None),
            anomaly_score=getattr(analytics, "open_interest_anomaly_score", None),
        ),
        funding=FundingStrategicFact(
            status=_fact_status(getattr(funding, "status", None)),
            observed_at=_optional_utc(getattr(funding, "current_observed_at", None), observed_at),
            freshness_seconds=getattr(funding, "freshness_seconds", None),
            current_relative_rate=getattr(funding, "current_relative_rate", None),
            relative_rate_change=getattr(funding, "relative_rate_change", None),
            anomaly_score=getattr(funding, "relative_rate_anomaly_score", None),
        ),
        liquidation_volume=LiquidationVolumeStrategicFact(
            status=_fact_status(getattr(liquidations, "status", None)),
            observed_at=_optional_utc(
                getattr(liquidations, "current_observed_at", None), observed_at
            ),
            freshness_seconds=getattr(liquidations, "freshness_seconds", None),
            current_volume=getattr(liquidations, "current_volume", None),
            change_ratio=getattr(liquidations, "volume_change_ratio", None),
            anomaly_score=getattr(liquidations, "volume_anomaly_score", None),
        ),
        cvd=CvdStrategicFact(
            status=_fact_status(getattr(cvd, "status", None)),
            observed_at=_optional_utc(getattr(cvd, "current_observed_at", None), observed_at),
            freshness_seconds=getattr(cvd, "freshness_seconds", None),
            current_change=getattr(cvd, "current_cvd_change", None),
            anomaly_score=getattr(cvd, "cvd_change_anomaly_score", None),
        ),
        aggressor_differential=AggressorDifferentialStrategicFact(
            status=_fact_status(getattr(aggressor, "status", None)),
            observed_at=_optional_utc(
                getattr(aggressor, "current_observed_at", None), observed_at
            ),
            freshness_seconds=getattr(aggressor, "freshness_seconds", None),
            current_value=getattr(aggressor, "current_value", None),
            value_change=getattr(aggressor, "value_change", None),
            anomaly_score=getattr(aggressor, "anomaly_score", None),
        ),
        characteristics=tuple(
            _required_value(value, "Analytics characteristic")
            for value in tuple(getattr(analytics, "characteristics", ()))[:8]
        ),
    )


def _ranking_fact(value: object | None) -> RadarAnalyticsRankingFact | None:
    if value is None:
        return None
    components = tuple(getattr(value, "components", ()))[:4]
    facts = tuple(
        RadarAnalyticsRankingComponentFact(
            name=cast(
                Literal["OPEN_INTEREST", "FUNDING", "LIQUIDATION_VOLUME", "ORDER_FLOW"],
                _required_value(component.name, "Analytics ranking component"),
            ),
            contribution=component.contribution,
            evidence=tuple(
                _required_value(item, "Analytics ranking evidence")
                for item in tuple(component.evidence)[:2]
            ),
        )
        for component in components
    )
    return RadarAnalyticsRankingFact(
        score=value.score,
        max_score=value.max_score,
        components=facts,
        order_flow_deduplicated=value.order_flow_deduplicated,
        order_flow_conflict=value.order_flow_conflict,
    )


def _not_applicable_analytics() -> PerpetualAnalyticsStrategicFact:
    return PerpetualAnalyticsStrategicFact(
        status="NOT_APPLICABLE",
        open_interest=OpenInterestStrategicFact(status="NOT_APPLICABLE"),
        funding=FundingStrategicFact(status="NOT_APPLICABLE"),
        liquidation_volume=LiquidationVolumeStrategicFact(status="NOT_APPLICABLE"),
        cvd=CvdStrategicFact(status="NOT_APPLICABLE"),
        aggressor_differential=AggressorDifferentialStrategicFact(status="NOT_APPLICABLE"),
    )


def _unavailable_analytics() -> PerpetualAnalyticsStrategicFact:
    return PerpetualAnalyticsStrategicFact(
        status="UNAVAILABLE",
        open_interest=OpenInterestStrategicFact(status="UNAVAILABLE"),
        funding=FundingStrategicFact(status="UNAVAILABLE"),
        liquidation_volume=LiquidationVolumeStrategicFact(status="UNAVAILABLE"),
        cvd=CvdStrategicFact(status="UNAVAILABLE"),
        aggressor_differential=AggressorDifferentialStrategicFact(status="UNAVAILABLE"),
    )


def _fact_status(value: object | None) -> RadarFactStatus:
    raw = _value(value)
    if raw is None:
        return "UNAVAILABLE"
    if raw == "ERROR":
        return "TECHNICAL_ERROR"
    allowed: set[str] = {
        "AVAILABLE",
        "PARTIAL",
        "STALE",
        "INSUFFICIENT_HISTORY",
        "TECHNICAL_ERROR",
        "NOT_APPLICABLE",
    }
    return cast(RadarFactStatus, raw if raw in allowed else "UNAVAILABLE")


def _value(value: object | None) -> str | None:
    if value is None:
        return None
    raw = getattr(value, "value", value)
    return str(raw)


def _required_value(value: object | None, label: str) -> str:
    result = _value(value)
    if result is None or not result.strip():
        raise RadarContextSnapshotInvalidError(f"{label} is required")
    return result


def _aware_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise RadarContextSnapshotInvalidError(f"{label} must be timezone-aware")
    return value.astimezone(UTC)


def _optional_utc(value: object | None, boundary: datetime) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise RadarContextSnapshotInvalidError("Radar fact timestamp must be datetime")
    normalized = _aware_utc(value, "Radar fact timestamp")
    if normalized > boundary:
        raise RadarContextSnapshotInvalidError("Radar fact cannot postdate Radar snapshot")
    return normalized


__all__ = [
    "RadarContextOverview",
    "RadarContextShortlistItem",
    "RadarContextSnapshotInvalidError",
    "build_radar_analytics_strategic_context",
]
