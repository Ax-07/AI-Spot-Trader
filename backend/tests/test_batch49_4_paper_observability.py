from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_spot_trader.api.economic_history_schemas import EconomicHistoryResponse
from ai_spot_trader.api.paper_observability_schemas import PaperObservabilityResponse
from ai_spot_trader.api.routes import analytics as analytics_routes
from ai_spot_trader.domain.enums import (
    MarketType,
    PositionSide,
    RiskDecision,
    RiskReason,
    TradingAction,
)
from ai_spot_trader.domain.models import (
    AssetBalance,
    AssetPosition,
    DecisionCandidate,
    DerivativePosition,
    PortfolioState,
    RiskAssessment,
)
from ai_spot_trader.economic_history import (
    EconomicHistoryReport,
    EconomicHistorySummary,
    EconomicOperation,
)
from ai_spot_trader.paper_observability import (
    PaperObservabilityDataError,
    project_paper_observability,
)
from ai_spot_trader.persistence.query import (
    CycleAuditDetail,
    DecisionExecutionAuditItem,
    FillAuditItem,
)

NOW = datetime(2026, 10, 5, 10, 0, tzinfo=UTC)
RUN_ID = UUID(int=49_400)


def _terminal_portfolio() -> PortfolioState:
    return PortfolioState(
        portfolio_state_id=UUID(int=49_401),
        as_of=NOW + timedelta(minutes=5),
        settlement_asset="USD",
        balances=(AssetBalance(asset="USD", available=Decimal("690")),),
        positions=(
            AssetPosition(
                asset="BTC",
                quantity=Decimal("1"),
                available=Decimal("1"),
                average_entry_price=Decimal("100"),
                remaining_cost_basis=Decimal("100"),
                realized_pnl=Decimal("0"),
                accounting_complete=True,
                mark_price=Decimal("110"),
                mark_observed_at=NOW + timedelta(minutes=5),
                mark_source="LAST_PRICE",
                market_value=Decimal("110"),
                unrealized_pnl=Decimal("10"),
                valuation_complete=True,
            ),
        ),
        derivative_positions=(
            DerivativePosition(
                symbol="BTC/USD",
                side=PositionSide.LONG,
                quantity=Decimal("2"),
                average_entry_price=Decimal("102.5"),
                mark_price=Decimal("100"),
                mark_observed_at=NOW + timedelta(minutes=5),
                notional=Decimal("200"),
                realized_pnl=Decimal("3"),
                unrealized_pnl=Decimal("-5"),
                leverage=Decimal("2"),
                margin_used=Decimal("100"),
                initial_margin_rate=Decimal("0.5"),
                maintenance_margin_rate=Decimal("0.05"),
                maintenance_margin=Decimal("10"),
                cumulative_funding=Decimal("-0.1"),
            ),
        ),
    )


def _history(*, spot_funding: str = "0") -> EconomicHistoryReport:
    summary = EconomicHistorySummary(
        initial_equity=Decimal("1000"),
        ending_equity=Decimal("1008"),
        gross_pnl=Decimal("11.3"),
        net_pnl=Decimal("8"),
        realized_pnl=Decimal("3"),
        unrealized_pnl=Decimal("5"),
        fees=Decimal("1.2"),
        spread_cost=Decimal("1"),
        slippage_cost=Decimal("1"),
        funding_pnl=Decimal("-0.1"),
        execution_costs=Decimal("3.2"),
        total_costs=Decimal("3.3"),
        max_drawdown_value=Decimal("7"),
        max_drawdown_fraction=Decimal("0.007"),
        current_drawdown_value=Decimal("2"),
        current_drawdown_fraction=Decimal("0.002"),
        current_exposure_value=Decimal("310"),
        current_exposure_fraction=Decimal("0.3075396825396825396825396825"),
        completed_cycle_count=3,
        failed_cycle_count=0,
        decision_count=4,
        buy_decision_count=2,
        sell_decision_count=1,
        hold_count=1,
        reject_count=1,
        modify_count=1,
        trade_count=2,
        buy_trade_count=2,
        sell_trade_count=0,
        fill_count=2,
        total_notional=Decimal("301"),
        turnover_fraction=Decimal("0.301"),
        costs_to_notional_fraction=Decimal("3.3") / Decimal("301"),
        costs_to_initial_equity_fraction=Decimal("0.0033"),
        duration_hours=Decimal("1"),
        fills_per_hour=Decimal("2"),
        market_switch_count=1,
        market_switches_per_hour=Decimal("1"),
        open_count=2,
        increase_count=0,
        reduce_count=0,
        close_count=0,
        flip_count=0,
        long_effect_count=1,
        short_effect_count=0,
        first_at=NOW,
        last_at=NOW + timedelta(hours=1),
    )
    operations = (
        EconomicOperation(
            paper_run_id=RUN_ID,
            cycle_id=UUID(int=1),
            decision_index=0,
            execution_id=UUID(int=10),
            filled_at=NOW + timedelta(minutes=1),
            symbol="BTC/USD",
            market_type="SPOT",
            action="BUY",
            economic_effect="OPEN_SPOT",
            quantity=Decimal("1"),
            reference_price=Decimal("100"),
            price=Decimal("101"),
            notional=Decimal("101"),
            fee=Decimal("1"),
            spread_cost=Decimal("0.5"),
            slippage_cost=Decimal("0.5"),
            funding_pnl=Decimal(spot_funding),
            execution_costs=Decimal("2"),
            total_costs=Decimal("2") - Decimal(spot_funding),
            realized_pnl=Decimal("0"),
            position_before=Decimal("0"),
            position_after=Decimal("1"),
            fill_count=1,
            fill_ids=(UUID(int=101),),
        ),
        EconomicOperation(
            paper_run_id=RUN_ID,
            cycle_id=UUID(int=1),
            decision_index=1,
            execution_id=UUID(int=11),
            filled_at=NOW + timedelta(minutes=2),
            symbol="BTC/USD",
            market_type="PERPETUAL",
            action="BUY",
            economic_effect="OPEN_LONG",
            quantity=Decimal("2"),
            reference_price=Decimal("100"),
            price=Decimal("100"),
            notional=Decimal("200"),
            fee=Decimal("0.2"),
            spread_cost=Decimal("0.5"),
            slippage_cost=Decimal("0.5"),
            funding_pnl=Decimal("0"),
            execution_costs=Decimal("1.2"),
            total_costs=Decimal("1.2"),
            realized_pnl=Decimal("3"),
            position_before=Decimal("0"),
            position_after=Decimal("2"),
            fill_count=1,
            fill_ids=(UUID(int=102),),
        ),
    )
    return EconomicHistoryReport(
        paper_run_id=RUN_ID,
        lineage_paper_run_ids=(RUN_ID,),
        calculation_version="paper-analytics-v3+economic-history-v1",
        timezone="UTC",
        source_digest="a" * 64,
        summary=summary,
        operations=operations,
        cycles=(),
    )


def _decision(
    *,
    number: int,
    action: TradingAction,
    symbol: str,
    market_type: MarketType,
    quantity: str | None,
) -> dict[str, object]:
    return DecisionCandidate(
        decision_id=UUID(int=1000 + number),
        cycle_id=UUID(int=number),
        created_at=NOW + timedelta(minutes=number),
        action=action,
        symbol=symbol,
        proposed_quantity=None if quantity is None else Decimal(quantity),
        market_type=market_type,
    ).model_dump(mode="json")


def _risk(
    *,
    number: int,
    status: RiskDecision,
    requested: str | None,
    authorized: str | None,
) -> dict[str, object]:
    reasons = ()
    if status is RiskDecision.MODIFY:
        reasons = (RiskReason.BUY_CASH_LIMIT,)
    elif status is RiskDecision.REJECT:
        reasons = (RiskReason.INSUFFICIENT_CASH,)
    return RiskAssessment(
        risk_assessment_id=UUID(int=2000 + number),
        cycle_id=UUID(int=number),
        decision_id=UUID(int=1000 + number),
        assessed_at=NOW + timedelta(minutes=number, seconds=1),
        status=status,
        requested_quantity=None if requested is None else Decimal(requested),
        authorized_quantity=None if authorized is None else Decimal(authorized),
        reasons=reasons,
    ).model_dump(mode="json")


def _fill_audit(number: int) -> FillAuditItem:
    return FillAuditItem(
        fill_id=UUID(int=3000 + number),
        execution_id=UUID(int=4000 + number),
        market_state_id=UUID(int=5000 + number),
        filled_at=NOW + timedelta(minutes=number),
        payload={},
    )


def _cycle(number: int, items: tuple[DecisionExecutionAuditItem, ...]) -> CycleAuditDetail:
    terminal = _terminal_portfolio().model_dump(mode="json")
    return CycleAuditDetail(
        cycle_id=UUID(int=number),
        paper_run_id=RUN_ID,
        status="COMPLETED",
        recorded_at=NOW + timedelta(minutes=number),
        failure=None,
        market_state_id=None,
        portfolio_state_before_id=None,
        portfolio_state_after_id=None,
        market_as_of=None,
        portfolio_before_as_of=None,
        portfolio_after_as_of=None,
        agent_input=None,
        decision=None,
        risk_assessment=None,
        execution_intent=None,
        fills=(),
        portfolio_state_after=terminal,
        decision_results=items,
    )


def _cycles() -> tuple[CycleAuditDetail, ...]:
    terminal = _terminal_portfolio().model_dump(mode="json")
    first = _cycle(
        1,
        (
            DecisionExecutionAuditItem(
                decision_index=0,
                agent_input=None,
                decision=_decision(
                    number=1,
                    action=TradingAction.BUY,
                    symbol="BTC/USD",
                    market_type=MarketType.SPOT,
                    quantity="1",
                ),
                risk_assessment=_risk(
                    number=1,
                    status=RiskDecision.ALLOW,
                    requested="1",
                    authorized="1",
                ),
                execution_intent={"execution_id": str(UUID(int=4001))},
                fills=(_fill_audit(1),),
                portfolio_state_after=terminal,
            ),
            DecisionExecutionAuditItem(
                decision_index=1,
                agent_input=None,
                decision=_decision(
                    number=2,
                    action=TradingAction.BUY,
                    symbol="BTC/USD",
                    market_type=MarketType.PERPETUAL,
                    quantity="2",
                ),
                risk_assessment=_risk(
                    number=2,
                    status=RiskDecision.MODIFY,
                    requested="2",
                    authorized="1",
                ),
                execution_intent={"execution_id": str(UUID(int=4002))},
                fills=(_fill_audit(2),),
                portfolio_state_after=terminal,
            ),
        ),
    )
    hold = _cycle(
        2,
        (
            DecisionExecutionAuditItem(
                decision_index=0,
                agent_input=None,
                decision=_decision(
                    number=3,
                    action=TradingAction.HOLD,
                    symbol="BTC/USD",
                    market_type=MarketType.SPOT,
                    quantity=None,
                ),
                risk_assessment=_risk(
                    number=3,
                    status=RiskDecision.ALLOW,
                    requested=None,
                    authorized=None,
                ),
                execution_intent=None,
                fills=(),
                portfolio_state_after=terminal,
            ),
        ),
    )
    reject = _cycle(
        3,
        (
            DecisionExecutionAuditItem(
                decision_index=0,
                agent_input=None,
                decision=_decision(
                    number=4,
                    action=TradingAction.SELL,
                    symbol="ETH/USD",
                    market_type=MarketType.PERPETUAL,
                    quantity="1",
                ),
                risk_assessment=_risk(
                    number=4,
                    status=RiskDecision.REJECT,
                    requested="1",
                    authorized=None,
                ),
                execution_intent=None,
                fills=(),
                portfolio_state_after=terminal,
            ),
        ),
    )
    return first, hold, reject


def test_observability_preserves_global_economics_and_splits_market_identity() -> None:
    report = project_paper_observability(history=_history(), cycles=_cycles())

    total, spot, perpetual = report.breakdowns
    assert (total.scope, spot.scope, perpetual.scope) == ("TOTAL", "SPOT", "PERPETUAL")
    assert total.gross_pnl == Decimal("11.3")
    assert total.net_pnl == Decimal("8")
    assert total.current_exposure_value == Decimal("310")
    assert spot.gross_pnl is None and spot.net_pnl is None
    assert perpetual.gross_pnl is None and perpetual.net_pnl is None
    assert _history().operations[1].funding_pnl == Decimal("0")
    assert spot.funding_pnl == Decimal("0")
    assert perpetual.funding_pnl == Decimal("-0.1")
    assert (spot.fees, spot.spread_cost, spot.slippage_cost) == (
        Decimal("1"),
        Decimal("0.5"),
        Decimal("0.5"),
    )
    assert (perpetual.fees, perpetual.spread_cost, perpetual.slippage_cost) == (
        Decimal("0.2"),
        Decimal("0.5"),
        Decimal("0.5"),
    )
    assert spot.total_costs == Decimal("2")
    assert perpetual.total_costs == Decimal("1.3")
    assert spot.current_exposure_value == Decimal("110")
    assert perpetual.current_exposure_value == Decimal("200")
    assert spot.unrealized_pnl == Decimal("10")
    assert perpetual.unrealized_pnl == Decimal("-5")

    btc_rows = [item for item in report.markets if item.symbol == "BTC/USD"]
    assert [(item.symbol, item.market_type) for item in btc_rows] == [
        ("BTC/USD", "PERPETUAL"),
        ("BTC/USD", "SPOT"),
    ]
    assert btc_rows[0].funding_pnl == Decimal("-0.1")
    assert btc_rows[1].funding_pnl == Decimal("0")


def test_observability_funnel_keeps_decisions_distinct_from_fills_and_trades() -> None:
    report = project_paper_observability(history=_history(), cycles=_cycles())
    funnel = report.funnel

    assert funnel.decision_count == 4
    assert (funnel.buy_count, funnel.sell_count, funnel.hold_count) == (2, 1, 1)
    assert (funnel.risk_allow_count, funnel.risk_modify_count, funnel.risk_reject_count) == (2, 1, 1)
    assert funnel.execution_intent_count == 2
    assert funnel.decisions_with_fill == 2
    assert funnel.decisions_without_fill == 2
    assert funnel.fill_count == 2
    assert funnel.economic_trade_count == 2

    spot = next(item for item in report.markets if item.symbol == "BTC/USD" and item.market_type == "SPOT")
    rejected = next(item for item in report.markets if item.symbol == "ETH/USD")
    assert spot.decision_count == 2
    assert spot.hold_count == 1
    assert spot.decisions_with_fill == 1
    assert rejected.risk_reject_count == 1
    assert rejected.fill_count == 0
    assert rejected.trade_count == 0


def test_observability_is_deterministic_and_refuses_spot_funding() -> None:
    forward = project_paper_observability(history=_history(), cycles=_cycles())
    reverse = project_paper_observability(history=_history(), cycles=tuple(reversed(_cycles())))
    assert forward == reverse
    assert any("SPOT.net_pnl" in item for item in forward.unavailable_metrics)

    with pytest.raises(PaperObservabilityDataError, match="SPOT"):
        project_paper_observability(history=_history(spot_funding="-0.01"), cycles=_cycles())


def test_economic_history_api_contract_exposes_observability(monkeypatch: pytest.MonkeyPatch) -> None:
    history = _history()
    observability = project_paper_observability(history=history, cycles=_cycles())
    response = EconomicHistoryResponse.model_validate(history, from_attributes=True).model_copy(
        update={
            "observability": PaperObservabilityResponse.model_validate(
                observability,
                from_attributes=True,
            )
        }
    )

    async def fake_response(request, paper_run_id):
        assert paper_run_id == RUN_ID
        return response

    monkeypatch.setattr(analytics_routes, "_economic_history_response", fake_response)
    app = FastAPI()
    app.state.runtime = SimpleNamespace(current_paper_run_id=RUN_ID)
    app.include_router(analytics_routes.router)

    with TestClient(app) as client:
        payload = client.get("/api/v1/economic-history").json()

    assert payload["observability"]["funnel"]["decision_count"] == 4
    assert [item["scope"] for item in payload["observability"]["breakdowns"]] == [
        "TOTAL",
        "SPOT",
        "PERPETUAL",
    ]
    assert payload["observability"]["breakdowns"][1]["net_pnl"] is None
    assert payload["summary"]["net_pnl"] == "8"
    assert payload["summary"]["max_drawdown_fraction"] == "0.007"
    assert payload["summary"]["current_exposure_value"] == "310"


def test_observability_keeps_missing_terminal_metrics_unavailable() -> None:
    report = project_paper_observability(history=_history(), cycles=())
    _, spot, perpetual = report.breakdowns

    assert spot.current_exposure_value is None
    assert spot.current_exposure_fraction is None
    assert spot.unrealized_pnl is None
    assert perpetual.current_exposure_value is None
    assert perpetual.current_exposure_fraction is None
    assert perpetual.unrealized_pnl is None


def test_failed_cycle_audit_does_not_turn_rollback_fill_into_economic_execution() -> None:
    terminal = _terminal_portfolio().model_dump(mode="json")
    failed = _cycle(9, (
        DecisionExecutionAuditItem(
            decision_index=0,
            agent_input=None,
            decision=_decision(
                number=9,
                action=TradingAction.BUY,
                symbol="SOL/USD",
                market_type=MarketType.SPOT,
                quantity="1",
            ),
            risk_assessment=_risk(
                number=9,
                status=RiskDecision.ALLOW,
                requested="1",
                authorized="1",
            ),
            execution_intent={"execution_id": str(UUID(int=4009))},
            fills=(_fill_audit(9),),
            portfolio_state_after=terminal,
        ),
    ))
    failed = replace(failed, status="FAILED")

    report = project_paper_observability(history=_history(), cycles=_cycles() + (failed,))
    sol = next(item for item in report.markets if item.symbol == "SOL/USD")

    assert report.funnel.decision_count == 5
    assert report.funnel.decisions_with_fill == 2
    assert sol.decision_count == 1
    assert sol.decisions_with_fill == 0
    assert sol.trade_count == 0
    assert sol.fill_count == 0
