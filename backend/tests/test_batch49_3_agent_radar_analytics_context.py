from __future__ import annotations

import asyncio
import inspect
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from pydantic import ValidationError

from ai_spot_trader.agent.planner import _plan_input_text
from ai_spot_trader.agent.radar_context import FrozenRadarContextDecisionProvider
from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import AssetBalance, ExecutableMarket, MarketState, PortfolioState
from ai_spot_trader.domain.planning import CycleDecisionPlan, CycleDecisionPlanInput
from ai_spot_trader.domain.radar_context import RadarAnalyticsStrategicContext
from ai_spot_trader.market.radar_agent_context import (
    RadarContextSnapshotInvalidError,
    build_radar_analytics_strategic_context,
)
from ai_spot_trader.trading.discovery_runner import (
    DynamicMarketTradingCycleRunner,
    RadarContextSnapshotMismatchError,
)

NOW = datetime(2026, 10, 5, 10, 30, tzinfo=UTC)
BTC_SPOT = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT)
BTC_PERP = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.PERPETUAL)
ETH_SPOT = ExecutableMarket(symbol="ETH/USD", market_type=MarketType.SPOT)
ETH_PERP = ExecutableMarket(symbol="ETH/USD", market_type=MarketType.PERPETUAL)


def _enum(value: str) -> SimpleNamespace:
    return SimpleNamespace(value=value)


def _activity(*, status: str = "AVAILABLE", observed_at: datetime = NOW) -> SimpleNamespace:
    horizons = tuple(
        SimpleNamespace(
            timeframe=_enum(timeframe),
            trend_direction=_enum("UP"),
            volume_ratio=Decimal("1.8"),
            volume_anomaly_score=Decimal("2.6"),
            price_return=Decimal("0.012"),
            range_anomaly_score=Decimal("1.7"),
            volatility_anomaly_score=Decimal("2.1"),
            complete=True,
        )
        for timeframe in ("5m", "15m", "1h", "4h", "1d")
    )
    return SimpleNamespace(
        status=_enum(status),
        observed_at=observed_at,
        freshness_seconds=Decimal("12"),
        data_quality=_enum("COMPLETE"),
        activity_state=_enum("ACCELERATING"),
        trend_direction=_enum("UP"),
        liquidity_regime=_enum("HIGH"),
        liquidity_reference_usd=Decimal("250000"),
        horizons=horizons,
    )


def _microstructure(*, status: str = "AVAILABLE") -> SimpleNamespace:
    return SimpleNamespace(
        status=_enum(status),
        observed_at=NOW,
        freshness_seconds=Decimal("2"),
        data_quality=_enum("COMPLETE" if status == "AVAILABLE" else status),
        spread_bps=Decimal("1.7") if status == "AVAILABLE" else None,
        total_depth_quote=Decimal("420000") if status == "AVAILABLE" else None,
        book_imbalance=Decimal("0.12") if status == "AVAILABLE" else None,
    )


def _structure(*, future: bool = False) -> SimpleNamespace:
    at = NOW + timedelta(seconds=1) if future else NOW
    frames = tuple(
        SimpleNamespace(
            timeframe=_enum(timeframe),
            state=_enum("BULLISH"),
            event=_enum("BOS_UP") if timeframe == "1h" else None,
            latest_final_close=NOW - timedelta(minutes=5),
            error_type=None,
        )
        for timeframe in ("5m", "15m", "1h", "4h")
    )
    return SimpleNamespace(observed_at=at, global_state=_enum("BULLISH"), timeframes=frames)


def _series(status: str = "AVAILABLE", **values: object) -> SimpleNamespace:
    return SimpleNamespace(
        status=_enum(status),
        current_observed_at=NOW - timedelta(minutes=5),
        freshness_seconds=Decimal("300"),
        **values,
    )


def _analytics(*, stale_funding: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        status=_enum("PARTIAL" if stale_funding else "AVAILABLE"),
        observed_at=NOW,
        open_interest_status=_enum("AVAILABLE"),
        current_open_interest_observed_at=NOW - timedelta(minutes=5),
        freshness_seconds=Decimal("300"),
        current_open_interest=Decimal("1000000"),
        open_interest_change_ratio=Decimal("1.12"),
        open_interest_anomaly_score=Decimal("3.1"),
        funding=_series(
            "STALE" if stale_funding else "AVAILABLE",
            current_relative_rate=Decimal("0.00025"),
            relative_rate_change=Decimal("0.00005"),
            relative_rate_anomaly_score=Decimal("2.8"),
        ),
        liquidation_volume=_series(
            current_volume=Decimal("250000"),
            volume_change_ratio=Decimal("2.4"),
            volume_anomaly_score=Decimal("3.6"),
        ),
        cvd=_series(
            current_cvd_change=Decimal("1200"),
            cvd_change_anomaly_score=Decimal("2.9"),
        ),
        aggressor_differential=_series(
            current_value=Decimal("800"),
            value_change=Decimal("300"),
            anomaly_score=Decimal("2.7"),
        ),
        characteristics=(
            _enum("OPEN_INTEREST_EXPANSION"),
            _enum("FUNDING_POSITIVE_EXTREME"),
            _enum("LIQUIDATION_VOLUME_SPIKE"),
            _enum("CVD_POSITIVE_IMPULSE"),
            _enum("AGGRESSOR_BUY_DOMINANCE"),
        ),
        error_type="must-not-be-serialized",
    )


def _ranking(*, score: int = 4) -> SimpleNamespace:
    contributions = {
        "OPEN_INTEREST": 1 if score >= 1 else 0,
        "FUNDING": 1 if score >= 2 else 0,
        "LIQUIDATION_VOLUME": 1 if score >= 3 else 0,
        "ORDER_FLOW": 1 if score >= 4 else 0,
    }
    return SimpleNamespace(
        score=score,
        max_score=4,
        components=tuple(
            SimpleNamespace(
                name=_enum(name),
                contribution=value,
                evidence=(
                    (_enum("CVD_POSITIVE_IMPULSE"), _enum("AGGRESSOR_BUY_DOMINANCE"))
                    if name == "ORDER_FLOW" and value
                    else ((_enum(f"{name}_ATTENTION"),) if value else ())
                ),
            )
            for name, value in contributions.items()
        ),
        order_flow_deduplicated=score == 4,
        order_flow_conflict=False,
        applied_to_ranking=True,
        rank_before_analytics=3,
        rank_after_analytics=1,
        rank_change=2,
    )


def _item(
    market: ExecutableMarket,
    *,
    analytics: object | None = None,
    ranking: object | None = None,
    activity_status: str = "AVAILABLE",
    future_structure: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        market=market,
        market_activity=_activity(status=activity_status),
        microstructure=(
            _microstructure()
            if market.market_type is MarketType.SPOT
            else _microstructure(status="NOT_APPLICABLE")
        ),
        market_structure=_structure(future=future_structure),
        combined_characteristics=("VOLUME_ANOMALY", "TRENDING"),
        interest_level=_enum("HIGH"),
        volume_24h_usd=Decimal("12000000"),
        perpetual_analytics=analytics,
        analytics_ranking=ranking,
        internal_debug="must-not-be-serialized",
    )


def _overview(*items: object, observed_at: datetime = NOW) -> SimpleNamespace:
    return SimpleNamespace(observed_at=observed_at, shortlist=tuple(items))


def _portfolio() -> PortfolioState:
    return PortfolioState(
        portfolio_state_id=uuid4(),
        as_of=NOW,
        settlement_asset="USD",
        balances=(AssetBalance(asset="USD", available=Decimal("1000")),),
        cash_available=Decimal("1000"),
        spot_remaining_cost_basis_total=Decimal(0),
        spot_market_value_total=Decimal(0),
        spot_realized_pnl_total=Decimal(0),
        spot_unrealized_pnl_total=Decimal(0),
        equity=Decimal("1000"),
        exposure_value=Decimal(0),
        exposure_fraction=Decimal(0),
        valuation_complete=True,
    )


def _spot_state(symbol: str) -> MarketState:
    return MarketState(
        market_state_id=uuid4(),
        as_of=NOW,
        symbol=symbol,
        last_price=Decimal("100"),
        market_type=MarketType.SPOT,
    )


def test_spot_context_is_visible_but_futures_analytics_are_explicitly_not_applicable() -> None:
    context = build_radar_analytics_strategic_context(
        _overview(_item(BTC_SPOT, analytics=_analytics(), ranking=_ranking())),
        markets=(BTC_SPOT,),
    )

    market = context.markets[0]
    assert market.symbol == "BTC/USD"
    assert market.market_type is MarketType.SPOT
    assert market.activity.trend_direction == "UP"
    assert market.activity.volume_24h_usd == Decimal("12000000")
    assert len(market.activity.horizons) == 4
    assert market.activity.horizons[0].timeframe == "5m"
    assert market.microstructure.spread_bps == Decimal("1.7")
    assert market.perpetual_analytics.status == "NOT_APPLICABLE"
    assert market.perpetual_analytics.ranking is None
    assert market.perpetual_analytics.open_interest.status == "NOT_APPLICABLE"


def test_perpetual_context_preserves_47_5_score_and_order_flow_deduplication() -> None:
    context = build_radar_analytics_strategic_context(
        _overview(_item(BTC_PERP, analytics=_analytics(), ranking=_ranking(score=4))),
        markets=(BTC_PERP,),
    )

    analytics = context.markets[0].perpetual_analytics
    assert analytics.ranking is not None
    assert analytics.ranking.score == analytics.ranking.max_score == 4
    assert [item.name for item in analytics.ranking.components] == [
        "OPEN_INTEREST",
        "FUNDING",
        "LIQUIDATION_VOLUME",
        "ORDER_FLOW",
    ]
    assert analytics.ranking.components[-1].contribution == 1
    assert len(analytics.ranking.components[-1].evidence) == 2
    assert analytics.ranking.order_flow_deduplicated is True
    assert analytics.open_interest.current == Decimal("1000000")
    assert analytics.funding.current_relative_rate == Decimal("0.00025")
    assert analytics.liquidation_volume.current_volume == Decimal("250000")
    assert analytics.cvd.current_change == Decimal("1200")
    assert analytics.aggressor_differential.current_value == Decimal("800")


def test_all_scope_keeps_spot_and_perpetual_same_symbol_distinct_and_sorted() -> None:
    context = build_radar_analytics_strategic_context(
        _overview(
            _item(BTC_SPOT),
            _item(BTC_PERP, analytics=_analytics(), ranking=_ranking()),
        ),
        markets=(BTC_SPOT, BTC_PERP),
    )
    assert {(item.symbol, item.market_type) for item in context.markets} == {
        ("BTC/USD", MarketType.SPOT),
        ("BTC/USD", MarketType.PERPETUAL),
    }
    assert tuple((item.market_type.value, item.symbol) for item in context.markets) == tuple(
        sorted((item.market_type.value, item.symbol) for item in context.markets)
    )


def test_market_outside_frozen_shortlist_cannot_enter_agent_context() -> None:
    with pytest.raises(RadarContextSnapshotInvalidError, match="absent"):
        build_radar_analytics_strategic_context(
            _overview(_item(BTC_SPOT)),
            markets=(ETH_SPOT,),
        )


def test_nested_future_fact_is_rejected_before_agent() -> None:
    with pytest.raises(RadarContextSnapshotInvalidError, match="postdate"):
        build_radar_analytics_strategic_context(
            _overview(_item(BTC_SPOT, future_structure=True)),
            markets=(BTC_SPOT,),
        )


def test_stale_and_missing_analytics_remain_explicit_without_artificial_values() -> None:
    stale = build_radar_analytics_strategic_context(
        _overview(_item(BTC_PERP, analytics=_analytics(stale_funding=True), ranking=_ranking(score=3))),
        markets=(BTC_PERP,),
    ).markets[0].perpetual_analytics
    missing = build_radar_analytics_strategic_context(
        _overview(_item(ETH_PERP)),
        markets=(ETH_PERP,),
    ).markets[0].perpetual_analytics

    assert stale.funding.status == "STALE"
    assert missing.status == "UNAVAILABLE"
    assert missing.open_interest.status == "UNAVAILABLE"
    assert missing.open_interest.current is None
    assert missing.funding.current_relative_rate is None


def test_serialized_context_is_bounded_and_excludes_internal_diagnostics_or_actions() -> None:
    context = build_radar_analytics_strategic_context(
        _overview(_item(BTC_PERP, analytics=_analytics(), ranking=_ranking())),
        markets=(BTC_PERP,),
    )
    serialized = context.model_dump_json()
    assert "error_type" not in serialized
    assert "internal_debug" not in serialized
    assert "rank_before_analytics" not in serialized
    assert "rank_after_analytics" not in serialized
    assert "rank_change" not in serialized
    assert "applied_to_ranking" not in serialized
    assert '"action"' not in serialized
    assert '"leverage"' not in serialized
    assert '"reduce_only"' not in serialized
    assert len(context.markets) <= 20
    assert all(len(item.structure.timeframes) <= 4 for item in context.markets)


def test_plan_input_rejects_radar_context_newer_than_decision_boundary() -> None:
    context = build_radar_analytics_strategic_context(
        _overview(_item(BTC_SPOT)),
        markets=(BTC_SPOT,),
    )
    future_context = RadarAnalyticsStrategicContext(
        observed_at=NOW + timedelta(seconds=1),
        markets=context.markets,
    )
    with pytest.raises(ValidationError, match="cannot postdate"):
        CycleDecisionPlanInput(
            cycle_id=uuid4(),
            created_at=NOW,
            portfolio_state=_portfolio(),
            market_states=(_spot_state("BTC/USD"),),
            aggressiveness=5,
            radar_analytics_context=future_context,
        )


def test_plan_input_rejects_context_market_outside_actual_plan_states() -> None:
    context = build_radar_analytics_strategic_context(
        _overview(_item(ETH_SPOT)),
        markets=(ETH_SPOT,),
    )
    with pytest.raises(ValidationError, match="inside market_states"):
        CycleDecisionPlanInput(
            cycle_id=uuid4(),
            created_at=NOW,
            portfolio_state=_portfolio(),
            market_states=(_spot_state("BTC/USD"),),
            aggressiveness=5,
            radar_analytics_context=context,
        )


def test_frozen_context_decorator_uses_same_agent_once_and_filters_to_plan_universe() -> None:
    context = build_radar_analytics_strategic_context(
        _overview(_item(BTC_SPOT), _item(ETH_SPOT)),
        markets=(BTC_SPOT, ETH_SPOT),
    )

    class Delegate:
        def __init__(self) -> None:
            self.calls = 0
            self.captured: CycleDecisionPlanInput | None = None

        async def generate_decision_plan(
            self,
            plan_input: CycleDecisionPlanInput,
        ) -> CycleDecisionPlan:
            self.calls += 1
            self.captured = plan_input
            return cast(CycleDecisionPlan, "same-call-result")

    delegate = Delegate()
    provider = FrozenRadarContextDecisionProvider(delegate, context)
    plan_input = CycleDecisionPlanInput(
        cycle_id=uuid4(),
        created_at=NOW,
        portfolio_state=_portfolio(),
        market_states=(_spot_state("BTC/USD"),),
        aggressiveness=5,
    )

    result = asyncio.run(provider.generate_decision_plan(plan_input))

    assert result == "same-call-result"
    assert delegate.calls == 1
    assert delegate.captured is not None
    assert delegate.captured.radar_analytics_context is not None
    assert tuple(item.symbol for item in delegate.captured.radar_analytics_context.markets) == (
        "BTC/USD",
    )


def test_agent_serialization_is_deterministic_and_labels_ranking_as_descriptive() -> None:
    context = build_radar_analytics_strategic_context(
        _overview(_item(BTC_SPOT)),
        markets=(BTC_SPOT,),
    )
    plan_input = CycleDecisionPlanInput(
        cycle_id=uuid4(),
        created_at=NOW,
        portfolio_state=_portfolio(),
        market_states=(_spot_state("BTC/USD"),),
        aggressiveness=5,
        radar_analytics_context=context,
    )

    first = _plan_input_text(plan_input)
    second = _plan_input_text(plan_input)
    assert first == second
    assert "indice d'attention descriptif 0..4" in first
    assert "jamais comme une action automatique" in first
    assert "TECHNICAL_ERROR" in first


def test_dated_future_remains_non_executable_before_radar_context() -> None:
    with pytest.raises(ValueError, match="FUTURE"):
        ExecutableMarket(symbol="BTC/USD", market_type=MarketType.FUTURE)


def test_frozen_context_is_immutable_for_the_cycle() -> None:
    context = build_radar_analytics_strategic_context(
        _overview(_item(BTC_SPOT)),
        markets=(BTC_SPOT,),
    )
    with pytest.raises(ValidationError, match="frozen"):
        context.observed_at = NOW - timedelta(seconds=1)  # type: ignore[misc]


def test_runner_rejects_radar_snapshot_changed_after_discovery() -> None:
    runner = object.__new__(DynamicMarketTradingCycleRunner)
    runner._radar_context_reader = SimpleNamespace(  # type: ignore[attr-defined]
        latest=_overview(_item(BTC_SPOT), observed_at=NOW + timedelta(seconds=1))
    )
    discovery_result = SimpleNamespace(
        audit=SimpleNamespace(radar_observed_at=NOW),
        watchlist=(BTC_SPOT,),
    )

    with pytest.raises(RadarContextSnapshotMismatchError, match="changed"):
        runner._freeze_radar_context(discovery_result)  # type: ignore[arg-type]


def test_runner_freezes_context_from_same_snapshot_and_only_discovery_watchlist() -> None:
    runner = object.__new__(DynamicMarketTradingCycleRunner)
    runner._radar_context_reader = SimpleNamespace(  # type: ignore[attr-defined]
        latest=_overview(_item(BTC_SPOT), _item(ETH_SPOT), observed_at=NOW)
    )
    discovery_result = SimpleNamespace(
        audit=SimpleNamespace(radar_observed_at=NOW),
        watchlist=(BTC_SPOT,),
    )

    context = runner._freeze_radar_context(discovery_result)  # type: ignore[arg-type]

    assert context is not None
    assert tuple(item.symbol for item in context.markets) == ("BTC/USD",)


def test_projection_layer_has_no_agent_action_risk_broker_or_execution_dependency() -> None:
    import ai_spot_trader.market.radar_agent_context as module

    source = inspect.getsource(module)
    assert "ai_spot_trader.risk" not in source
    assert "ai_spot_trader.broker" not in source
    assert "ExecutionIntent" not in source
    assert "TradingAction" not in source
    assert "reduce_only" not in source
    assert "leverage" not in source
