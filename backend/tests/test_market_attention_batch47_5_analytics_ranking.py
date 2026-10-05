from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market import attention_perpetual_analytics as ranking_module
from ai_spot_trader.market.attention import ActivityAnomalyMethod
from ai_spot_trader.market.attention_perpetual_analytics import (
    PerpetualAnalyticsRankingComponentName,
    _analytics_candidate_sort_key,
    _analytics_ranking_context,
    _rerank_analytics_shortlist,
)
from ai_spot_trader.market.attention_scope_trend import MarketScope
from ai_spot_trader.market.perpetual_analytics import (
    PerpetualAggressorAnalyticsSnapshot,
    PerpetualAnalyticsCharacteristic,
    PerpetualAnalyticsSnapshot,
    PerpetualAnalyticsStatus,
    PerpetualCvdAnalyticsSnapshot,
    PerpetualCvdPoint,
    PerpetualFundingAnalyticsSnapshot,
    PerpetualLiquidationVolumeAnalyticsSnapshot,
    PerpetualAnalyticsPolicy,
    analyze_cvd_history,
)

NOW = datetime(2026, 10, 5, 1, 0, tzinfo=UTC)
PERP = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.PERPETUAL)
SPOT = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT)


def _snapshot(
    *characteristics: PerpetualAnalyticsCharacteristic,
    oi_status: PerpetualAnalyticsStatus = PerpetualAnalyticsStatus.AVAILABLE,
    funding_status: PerpetualAnalyticsStatus | None = PerpetualAnalyticsStatus.AVAILABLE,
    liquidation_status: PerpetualAnalyticsStatus | None = PerpetualAnalyticsStatus.AVAILABLE,
    cvd_status: PerpetualAnalyticsStatus | None = PerpetualAnalyticsStatus.AVAILABLE,
    aggressor_status: PerpetualAnalyticsStatus | None = PerpetualAnalyticsStatus.AVAILABLE,
) -> PerpetualAnalyticsSnapshot:
    def funding():
        if funding_status is None:
            return None
        return PerpetualFundingAnalyticsSnapshot(status=funding_status, observed_at=NOW)

    def liquidations():
        if liquidation_status is None:
            return None
        return PerpetualLiquidationVolumeAnalyticsSnapshot(
            status=liquidation_status,
            observed_at=NOW,
        )

    def cvd():
        if cvd_status is None:
            return None
        return PerpetualCvdAnalyticsSnapshot(status=cvd_status, observed_at=NOW)

    def aggressor():
        if aggressor_status is None:
            return None
        return PerpetualAggressorAnalyticsSnapshot(
            status=aggressor_status,
            observed_at=NOW,
        )

    return PerpetualAnalyticsSnapshot(
        market=PERP,
        status=PerpetualAnalyticsStatus.AVAILABLE,
        observed_at=NOW,
        open_interest_status=oi_status,
        funding=funding(),
        liquidation_volume=liquidations(),
        cvd=cvd(),
        aggressor_differential=aggressor(),
        characteristics=characteristics,
    )


def _component(context, name: PerpetualAnalyticsRankingComponentName):
    return next(item for item in context.components if item.name is name)


def test_positive_and_negative_signed_anomalies_have_symmetric_attention_influence() -> None:
    positive = _analytics_ranking_context(
        _snapshot(
            PerpetualAnalyticsCharacteristic.OPEN_INTEREST_EXPANSION,
            PerpetualAnalyticsCharacteristic.FUNDING_POSITIVE_EXTREME,
            PerpetualAnalyticsCharacteristic.CVD_POSITIVE_IMPULSE,
            PerpetualAnalyticsCharacteristic.AGGRESSOR_BUY_DOMINANCE,
        ),
        applied_to_ranking=True,
    )
    negative = _analytics_ranking_context(
        _snapshot(
            PerpetualAnalyticsCharacteristic.OPEN_INTEREST_CONTRACTION,
            PerpetualAnalyticsCharacteristic.FUNDING_NEGATIVE_EXTREME,
            PerpetualAnalyticsCharacteristic.CVD_NEGATIVE_IMPULSE,
            PerpetualAnalyticsCharacteristic.AGGRESSOR_SELL_DOMINANCE,
        ),
        applied_to_ranking=True,
    )
    assert positive.score == negative.score == 3
    assert positive.order_flow_deduplicated is True
    assert negative.order_flow_deduplicated is True
    assert positive.order_flow_conflict is False
    assert negative.order_flow_conflict is False


def test_score_is_capped_by_four_independent_semantic_families() -> None:
    context = _analytics_ranking_context(
        _snapshot(
            PerpetualAnalyticsCharacteristic.OPEN_INTEREST_EXPANSION,
            PerpetualAnalyticsCharacteristic.FUNDING_POSITIVE_EXTREME,
            PerpetualAnalyticsCharacteristic.LIQUIDATION_VOLUME_SPIKE,
            PerpetualAnalyticsCharacteristic.CVD_POSITIVE_IMPULSE,
            PerpetualAnalyticsCharacteristic.AGGRESSOR_BUY_DOMINANCE,
        ),
        applied_to_ranking=True,
    )
    assert context.score == context.max_score == 4
    assert sum(component.contribution for component in context.components) == 4
    order_flow = _component(context, PerpetualAnalyticsRankingComponentName.ORDER_FLOW)
    assert order_flow.contribution == 1
    assert len(order_flow.evidence) == 2
    assert context.order_flow_deduplicated is True


def test_cvd_and_aggressor_opposite_directions_do_not_create_false_confirmation() -> None:
    context = _analytics_ranking_context(
        _snapshot(
            PerpetualAnalyticsCharacteristic.CVD_POSITIVE_IMPULSE,
            PerpetualAnalyticsCharacteristic.AGGRESSOR_SELL_DOMINANCE,
        ),
        applied_to_ranking=True,
    )
    order_flow = _component(context, PerpetualAnalyticsRankingComponentName.ORDER_FLOW)
    assert context.score == 0
    assert order_flow.contribution == 0
    assert context.order_flow_conflict is True
    assert context.order_flow_deduplicated is False


@pytest.mark.parametrize(
    "status",
    [
        PerpetualAnalyticsStatus.INSUFFICIENT_HISTORY,
        PerpetualAnalyticsStatus.STALE,
        PerpetualAnalyticsStatus.TECHNICAL_ERROR,
        PerpetualAnalyticsStatus.PARTIAL,
    ],
)
def test_non_available_series_are_neutral_not_penalties(status: PerpetualAnalyticsStatus) -> None:
    context = _analytics_ranking_context(
        _snapshot(
            PerpetualAnalyticsCharacteristic.FUNDING_POSITIVE_EXTREME,
            funding_status=status,
            oi_status=PerpetualAnalyticsStatus.INSUFFICIENT_HISTORY,
            liquidation_status=PerpetualAnalyticsStatus.STALE,
            cvd_status=PerpetualAnalyticsStatus.TECHNICAL_ERROR,
            aggressor_status=None,
        ),
        applied_to_ranking=True,
    )
    assert context.score == 0
    funding = _component(context, PerpetualAnalyticsRankingComponentName.FUNDING)
    assert funding.contribution == 0
    assert funding.series[0].status == status.value
    assert funding.series[0].used is False
    order_flow = _component(context, PerpetualAnalyticsRankingComponentName.ORDER_FLOW)
    assert order_flow.series[1].status == "UNAVAILABLE"


def test_availability_without_anomaly_never_earns_points() -> None:
    context = _analytics_ranking_context(_snapshot(), applied_to_ranking=True)
    assert context.score == 0
    assert all(component.contribution == 0 for component in context.components)
    assert all(
        diagnostic.status == PerpetualAnalyticsStatus.AVAILABLE.value
        for component in context.components
        for diagnostic in component.series
    )


def test_zero_mad_signed_series_cannot_create_ranking_score() -> None:
    policy = PerpetualAnalyticsPolicy(
        baseline_periods=6,
        history_lookback_seconds=72_000,
    )
    start = NOW - timedelta(hours=9)
    points = tuple(
        PerpetualCvdPoint(observed_at=start + timedelta(hours=index), cvd=Decimal(value))
        for index, value in enumerate(["0", "1", "2", "3", "4", "5", "6", "7", "20"])
    )
    cvd, characteristics = analyze_cvd_history(points=points, as_of=NOW, policy=policy)
    assert cvd.baseline_cvd_change_mad == Decimal("0")
    assert cvd.cvd_change_anomaly_method is ActivityAnomalyMethod.UNAVAILABLE
    assert characteristics == ()
    analytics = _snapshot()
    analytics = analytics.model_copy(
        update={"cvd": cvd, "characteristics": characteristics}
    )
    context = _analytics_ranking_context(analytics, applied_to_ranking=True)
    assert context.score == 0
    assert _component(
        context, PerpetualAnalyticsRankingComponentName.ORDER_FLOW
    ).contribution == 0


def test_legacy_payload_without_cvd_or_aggressor_remains_rankable() -> None:
    context = _analytics_ranking_context(
        _snapshot(
            PerpetualAnalyticsCharacteristic.OPEN_INTEREST_EXPANSION,
            PerpetualAnalyticsCharacteristic.LIQUIDATION_VOLUME_SPIKE,
            cvd_status=None,
            aggressor_status=None,
        ),
        applied_to_ranking=True,
    )
    assert context.score == 2
    order_flow = _component(context, PerpetualAnalyticsRankingComponentName.ORDER_FLOW)
    assert [item.status for item in order_flow.series] == ["UNAVAILABLE", "UNAVAILABLE"]
    assert order_flow.contribution == 0


def test_analytics_sort_key_is_injected_after_interest_and_structure(monkeypatch) -> None:
    canonical = (3, 4, 2, 8, 7, 6, "BTC/USD")
    monkeypatch.setattr(
        ranking_module,
        "_structured_candidate_sort_key",
        lambda _item: canonical,
    )
    item = SimpleNamespace(analytics_ranking=SimpleNamespace(score=4))
    assert _analytics_candidate_sort_key(item) == (3, 4, 2, 4, 8, 7, 6, "BTC/USD")


def test_all_scope_preserves_spot_slots_and_candidate_population(monkeypatch) -> None:
    first_perp = SimpleNamespace(market=PERP, rank_key=(1,))
    spot = SimpleNamespace(market=SPOT, rank_key=(999,))
    second_perp = SimpleNamespace(
        market=ExecutableMarket(symbol="ETH/USD", market_type=MarketType.PERPETUAL),
        rank_key=(4,),
    )
    original = (first_perp, spot, second_perp)
    monkeypatch.setattr(
        ranking_module,
        "_analytics_candidate_sort_key",
        lambda item: item.rank_key,
    )
    ranked = _rerank_analytics_shortlist(original, market_scope=MarketScope.ALL)
    assert ranked == (second_perp, spot, first_perp)
    assert ranked[1] is spot
    assert len(ranked) == len(original)
    assert {id(item) for item in ranked} == {id(item) for item in original}


def test_spot_scope_is_bit_for_bit_unchanged(monkeypatch) -> None:
    first = SimpleNamespace(market=SPOT, rank_key=(0,))
    second = SimpleNamespace(
        market=ExecutableMarket(symbol="ETH/USD", market_type=MarketType.SPOT),
        rank_key=(100,),
    )
    monkeypatch.setattr(
        ranking_module,
        "_analytics_candidate_sort_key",
        lambda item: item.rank_key,
    )
    original = (first, second)
    assert _rerank_analytics_shortlist(original, market_scope=MarketScope.SPOT) is original


def test_equal_analytics_keys_keep_deterministic_existing_order(monkeypatch) -> None:
    first = SimpleNamespace(market=PERP, rank_key=(2,))
    second = SimpleNamespace(
        market=ExecutableMarket(symbol="ETH/USD", market_type=MarketType.PERPETUAL),
        rank_key=(2,),
    )
    monkeypatch.setattr(
        ranking_module,
        "_analytics_candidate_sort_key",
        lambda item: item.rank_key,
    )
    original = (first, second)
    assert _rerank_analytics_shortlist(original, market_scope=MarketScope.PERPETUAL) == original


def test_ranking_layer_has_no_agent_risk_broker_or_order_execution_dependency() -> None:
    source = inspect.getsource(ranking_module)
    assert "ai_spot_trader.agent" not in source
    assert "ai_spot_trader.risk" not in source
    assert "ai_spot_trader.broker" not in source
    assert 'payload["interest_level"]' not in source
    assert "candidate_limit" not in inspect.getsource(ranking_module._rerank_analytics_shortlist)
