from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from ai_spot_trader.analytics.paper import PaperAnalyticsReport, PaperAnalyticsSummary
from ai_spot_trader.domain.enums import MarketType, PositionSide, TradingAction
from ai_spot_trader.domain.models import (
    AssetBalance,
    AssetPosition,
    DerivativePosition,
    Fill,
    PortfolioState,
)
from ai_spot_trader.economic_history import project_economic_history
from ai_spot_trader.persistence.query import (
    CycleAuditDetail,
    CycleAuditSummary,
    DecisionExecutionAuditItem,
    FillAuditItem,
)
from ai_spot_trader.persistence.runs import PaperRunView

START = datetime(2026, 9, 28, 8, 0, tzinfo=UTC)
RUN_ID = UUID(int=100)


def _portfolio(
    *,
    cash: str,
    spot_quantity: str | None = None,
    short_quantity: str | None = None,
    short_unrealized: str = "0",
    offset_minutes: int = 0,
) -> PortfolioState:
    positions = ()
    if spot_quantity is not None:
        positions = (
            AssetPosition(
                asset="BTC",
                quantity=Decimal(spot_quantity),
                available=Decimal(spot_quantity),
            ),
        )
    derivative_positions = ()
    if short_quantity is not None:
        quantity = Decimal(short_quantity)
        mark = Decimal("100")
        notional = mark * quantity
        derivative_positions = (
            DerivativePosition(
                symbol="ETH/USD",
                side=PositionSide.SHORT,
                quantity=quantity,
                average_entry_price=Decimal("100"),
                mark_price=mark,
                contract_size=Decimal("1"),
                notional=notional,
                realized_pnl=Decimal("0"),
                unrealized_pnl=Decimal(short_unrealized),
                leverage=Decimal("2"),
                margin_used=notional / Decimal("2"),
                initial_margin_rate=Decimal("0.5"),
                maintenance_margin_rate=Decimal("0.05"),
                maintenance_margin=notional * Decimal("0.05"),
            ),
        )
    return PortfolioState(
        portfolio_state_id=UUID(int=1_000 + offset_minutes),
        as_of=START + timedelta(minutes=offset_minutes),
        settlement_asset="USD",
        balances=(AssetBalance(asset="USD", available=Decimal(cash)),),
        positions=positions,
        derivative_positions=derivative_positions,
    )


def _fill(
    *,
    number: int,
    symbol: str,
    market_type: MarketType,
    action: TradingAction,
    reference_price: str,
    price: str,
    fee: str,
    spread: str,
    slippage: str,
    realized: str = "0",
    funding: str = "0",
    offset_minutes: int,
) -> FillAuditItem:
    fill = Fill(
        fill_id=UUID(int=10_000 + number),
        execution_id=UUID(int=20_000 + number),
        market_state_id=UUID(int=30_000 + number),
        filled_at=START + timedelta(minutes=offset_minutes),
        pricing_as_of=START + timedelta(minutes=offset_minutes),
        action=action,
        symbol=symbol,
        quantity=Decimal("1"),
        reference_price=Decimal(reference_price),
        price=Decimal(price),
        notional=Decimal(price),
        fee=Decimal(fee),
        spread_cost=Decimal(spread),
        slippage_cost=Decimal(slippage),
        market_type=market_type,
        realized_pnl=Decimal(realized),
        funding_payment=Decimal(funding),
    )
    return FillAuditItem(
        fill_id=fill.fill_id,
        execution_id=fill.execution_id,
        market_state_id=fill.market_state_id,
        filled_at=fill.filled_at,
        payload=fill.model_dump(mode="json"),
    )


def _cycle(
    *,
    number: int,
    decision_index: int,
    before: PortfolioState,
    after: PortfolioState,
    fills: tuple[FillAuditItem, ...],
) -> CycleAuditDetail:
    return CycleAuditDetail(
        cycle_id=UUID(int=number),
        status="COMPLETED",
        recorded_at=START + timedelta(minutes=number),
        failure=None,
        market_state_id=None,
        portfolio_state_before_id=before.portfolio_state_id,
        portfolio_state_after_id=after.portfolio_state_id,
        market_as_of=None,
        portfolio_before_as_of=before.as_of,
        portfolio_after_as_of=after.as_of,
        agent_input=None,
        decision=None,
        risk_assessment=None,
        execution_intent=None,
        fills=(),
        portfolio_state_after=after.model_dump(mode="json"),
        paper_run_id=RUN_ID,
        decision_results=(
            DecisionExecutionAuditItem(
                decision_index=decision_index,
                agent_input={"portfolio_state": before.model_dump(mode="json")},
                decision={"action": "BUY"},
                risk_assessment=None,
                execution_intent=None,
                fills=fills,
                portfolio_state_after=after.model_dump(mode="json"),
            ),
        ),
    )


def _summary(
    *,
    number: int,
    decisions: int,
    buys: int = 0,
    holds: int = 0,
    rejects: int = 0,
    fills: int = 0,
) -> CycleAuditSummary:
    return CycleAuditSummary(
        cycle_id=UUID(int=number),
        paper_run_id=RUN_ID,
        status="COMPLETED",
        recorded_at=START + timedelta(minutes=number),
        decision_action=None,
        symbol=None,
        market_type=None,
        risk_status=None,
        execution_id=None,
        decision_count=decisions,
        buy_count=buys,
        sell_count=0,
        hold_count=holds,
        risk_allow_count=max(decisions - rejects, 0),
        risk_modify_count=0,
        risk_reject_count=rejects,
        execution_count=1 if fills else 0,
        fill_count=fills,
        failure=None,
    )


def _analytics() -> PaperAnalyticsReport:
    return PaperAnalyticsReport(
        calculation_version="paper-analytics-v3",
        timezone="UTC",
        source_digest="a" * 64,
        summary=PaperAnalyticsSummary(
            initial_equity=Decimal("1000"),
            ending_equity=Decimal("1005"),
            gross_pnl=Decimal("8.25"),
            net_pnl=Decimal("5"),
            fees=Decimal("1.2"),
            spread_cost=Decimal("1"),
            slippage_cost=Decimal("1"),
            max_drawdown_value=Decimal("2"),
            max_drawdown_fraction=Decimal("0.002"),
            current_drawdown_value=Decimal("0"),
            current_drawdown_fraction=Decimal("0"),
            current_exposure_value=Decimal("100"),
            current_exposure_fraction=Decimal("0.1"),
            trade_count=2,
            buy_trade_count=2,
            sell_trade_count=0,
            hold_count=1,
            reject_count=1,
            modify_count=0,
            completed_cycle_count=3,
            failed_cycle_count=0,
            valued_cycle_count=3,
            first_at=START + timedelta(minutes=1),
            last_at=START + timedelta(minutes=120),
            funding_pnl=Decimal("-0.05"),
        ),
        points=(),
        daily=(),
    )


def test_economic_history_projects_costs_turnover_and_perpetual_effects() -> None:
    spot_before = _portfolio(cash="1000", offset_minutes=1)
    spot_after = _portfolio(cash="898", spot_quantity="1", offset_minutes=2)
    short_before = _portfolio(cash="900", short_quantity="2", offset_minutes=60)
    short_after = _portfolio(
        cash="903",
        short_quantity="1",
        short_unrealized="4",
        offset_minutes=61,
    )

    spot_fill = _fill(
        number=1,
        symbol="BTC/USD",
        market_type=MarketType.SPOT,
        action=TradingAction.BUY,
        reference_price="100",
        price="101",
        fee="1",
        spread="0.5",
        slippage="0.5",
        offset_minutes=2,
    )
    perpetual_fill = _fill(
        number=2,
        symbol="ETH/USD",
        market_type=MarketType.PERPETUAL,
        action=TradingAction.BUY,
        reference_price="100",
        price="101",
        fee="0.2",
        spread="0.5",
        slippage="0.5",
        realized="3",
        funding="-0.05",
        offset_minutes=61,
    )

    cycles = (
        _cycle(
            number=1,
            decision_index=0,
            before=spot_before,
            after=spot_after,
            fills=(spot_fill,),
        ),
        _cycle(
            number=2,
            decision_index=1,
            before=short_before,
            after=short_after,
            fills=(perpetual_fill,),
        ),
        _cycle(
            number=3,
            decision_index=0,
            before=short_after,
            after=short_after,
            fills=(),
        ),
    )
    summaries = (
        _summary(number=1, decisions=1, buys=1, fills=1),
        _summary(number=2, decisions=1, buys=1, fills=1),
        _summary(number=3, decisions=1, holds=1, rejects=1),
    )
    lineage = (
        PaperRunView(
            paper_run_id=RUN_ID,
            started_at=START,
            ended_at=START + timedelta(hours=2),
            market_type=None,
            symbol=None,
        ),
    )

    report = project_economic_history(
        paper_run_id=RUN_ID,
        analytics=_analytics(),
        cycles=cycles,
        cycle_summaries=summaries,
        lineage=lineage,
    )

    assert [item.economic_effect for item in report.operations] == [
        "OPEN_SPOT",
        "REDUCE_SHORT",
    ]
    assert report.operations[1].position_before == Decimal("-2")
    assert report.operations[1].position_after == Decimal("-1")
    assert report.operations[1].action == "BUY"

    summary = report.summary
    assert summary.realized_pnl == Decimal("3")
    assert summary.unrealized_pnl == Decimal("4")
    assert summary.execution_costs == Decimal("3.2")
    assert summary.total_costs == Decimal("3.25")
    assert summary.total_notional == Decimal("202")
    assert summary.turnover_fraction == Decimal("0.202")
    assert summary.fill_count == 2
    assert summary.fills_per_hour == Decimal("1")
    assert summary.market_switch_count == 1
    assert summary.decision_count == 3
    assert summary.buy_decision_count == 2
    assert summary.hold_count == 1
    assert summary.reject_count == 1
    assert summary.open_count == 1
    assert summary.reduce_count == 1
    assert summary.short_effect_count == 1
