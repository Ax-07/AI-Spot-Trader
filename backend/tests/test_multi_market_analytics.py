from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from ai_spot_trader.analytics.paper import (
    MULTI_MARKET_ANALYTICS_VERSION,
    PaperAnalyticsCycleFact,
    build_paper_analytics_report,
)
from ai_spot_trader.domain.enums import RiskDecision, RiskReason, TradingAction
from ai_spot_trader.domain.models import (
    AgentInput,
    AssetBalance,
    AssetPosition,
    DecisionCandidate,
    Fill,
    MarketState,
    PortfolioState,
    RiskAssessment,
)

BASE = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)


def _agent_input(
    *,
    cycle: int,
    symbol: str,
    price: str,
    portfolio: PortfolioState,
) -> AgentInput:
    at = BASE + timedelta(minutes=cycle)
    return AgentInput(
        cycle_id=UUID(int=cycle),
        created_at=at,
        market_state=MarketState(
            market_state_id=UUID(int=100 + cycle),
            as_of=at,
            symbol=symbol,
            last_price=Decimal(price),
        ),
        portfolio_state=portfolio.model_copy(update={"as_of": at}),
        aggressiveness=5,
    )


def test_multi_market_analytics_values_held_spot_assets_with_last_causal_mark() -> None:
    initial = PortfolioState(
        portfolio_state_id=UUID(int=200),
        as_of=BASE,
        balances=(AssetBalance(asset="USD", available=Decimal("1000")),),
    )
    first_input = _agent_input(
        cycle=1,
        symbol="BTC/USD",
        price="100",
        portfolio=initial,
    )
    first_decision = DecisionCandidate(
        decision_id=UUID(int=301),
        cycle_id=first_input.cycle_id,
        created_at=first_input.created_at,
        action=TradingAction.BUY,
        symbol="BTC/USD",
        proposed_quantity=Decimal("1"),
    )
    first_risk = RiskAssessment(
        risk_assessment_id=UUID(int=401),
        cycle_id=first_input.cycle_id,
        decision_id=first_decision.decision_id,
        assessed_at=first_input.created_at,
        status=RiskDecision.ALLOW,
        requested_quantity=Decimal("1"),
        authorized_quantity=Decimal("1"),
    )
    first_fill = Fill(
        fill_id=UUID(int=501),
        execution_id=UUID(int=601),
        market_state_id=first_input.market_state.market_state_id,
        filled_at=first_input.created_at,
        pricing_as_of=first_input.market_state.as_of,
        action=TradingAction.BUY,
        symbol="BTC/USD",
        quantity=Decimal("1"),
        reference_price=Decimal("100"),
        price=Decimal("100"),
        notional=Decimal("100"),
        fee=Decimal("0"),
        spread_cost=Decimal("0"),
        slippage_cost=Decimal("0"),
    )
    after_buy = PortfolioState(
        portfolio_state_id=UUID(int=201),
        as_of=first_input.created_at,
        balances=(AssetBalance(asset="USD", available=Decimal("900")),),
        positions=(
            AssetPosition(
                asset="BTC",
                quantity=Decimal("1"),
                available=Decimal("1"),
            ),
        ),
    )

    second_input = _agent_input(
        cycle=2,
        symbol="ETH/USD",
        price="50",
        portfolio=after_buy,
    )
    second_decision = DecisionCandidate(
        decision_id=UUID(int=302),
        cycle_id=second_input.cycle_id,
        created_at=second_input.created_at,
        action=TradingAction.HOLD,
        symbol="ETH/USD",
    )
    second_risk = RiskAssessment(
        risk_assessment_id=UUID(int=402),
        cycle_id=second_input.cycle_id,
        decision_id=second_decision.decision_id,
        assessed_at=second_input.created_at,
        status=RiskDecision.ALLOW,
        reasons=(RiskReason.HOLD_NO_EXECUTION,),
    )

    facts = (
        PaperAnalyticsCycleFact(
            cycle_id=first_input.cycle_id,
            status="COMPLETED",
            recorded_at=first_input.created_at,
            result_digest="a" * 64,
            agent_input_payload=first_input.model_dump(mode="json"),
            decision_payload=first_decision.model_dump(mode="json"),
            risk_assessment_payload=first_risk.model_dump(mode="json"),
            fill_payloads=(first_fill.model_dump(mode="json"),),
            portfolio_after_payload=after_buy.model_dump(mode="json"),
        ),
        PaperAnalyticsCycleFact(
            cycle_id=second_input.cycle_id,
            status="COMPLETED",
            recorded_at=second_input.created_at,
            result_digest="b" * 64,
            agent_input_payload=second_input.model_dump(mode="json"),
            decision_payload=second_decision.model_dump(mode="json"),
            risk_assessment_payload=second_risk.model_dump(mode="json"),
            fill_payloads=(),
            portfolio_after_payload=second_input.portfolio_state.model_dump(
                mode="json"
            ),
        ),
    )

    report = build_paper_analytics_report(facts)

    assert report.calculation_version == MULTI_MARKET_ANALYTICS_VERSION
    assert report.summary.initial_equity == Decimal("1000")
    assert report.summary.ending_equity == Decimal("1000")
    assert report.points[1].symbol == "ETH/USD"
    assert report.points[1].equity == Decimal("1000")
    assert report.points[1].exposure_value == Decimal("100")
