import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from ai_spot_trader.broker.pricing import PaperExecutionCostModel
from ai_spot_trader.control_plane import CampaignConfiguration
from ai_spot_trader.domain.enums import LLMModel, MarketType, RiskDecision, TradingAction
from ai_spot_trader.domain.models import (
    AssetBalance,
    DecisionCandidate,
    ExecutableMarket,
    MarketState,
    PortfolioState,
)
from ai_spot_trader.domain.planning import (
    DEFAULT_MAX_DECISIONS_PER_CYCLE,
    CycleDecisionPlan,
    CycleDecisionPlanInput,
)
from ai_spot_trader.risk.policy import RiskPolicy
from ai_spot_trader.risk.sequential import SequentialCycleRiskEngine

NOW = datetime(2026, 9, 27, 1, 0, tzinfo=UTC)
LEGACY_CONFIGURATION_DIGEST = "e369decaa3ac79695221f5e0f8eb7cc9a654c3e3b5a67f25dcd15db30041eb6f"


class FixedClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


def market(symbol: str = "BTC/USD", *, as_of: datetime = NOW) -> MarketState:
    return MarketState(
        market_state_id=uuid4(),
        as_of=as_of,
        symbol=symbol,
        last_price=Decimal("100"),
        market_type=MarketType.SPOT,
    )


def portfolio(*, as_of: datetime = NOW, cash: str = "1000") -> PortfolioState:
    return PortfolioState(
        portfolio_state_id=uuid4(),
        as_of=as_of,
        settlement_asset="USD",
        balances=(AssetBalance(asset="USD", available=Decimal(cash)),),
    )


def test_plan_rejects_duplicate_symbol_and_market_type() -> None:
    cycle_id = uuid4()
    decision_time = NOW + timedelta(seconds=1)
    first = DecisionCandidate(
        decision_id=uuid4(),
        cycle_id=cycle_id,
        created_at=decision_time,
        action=TradingAction.HOLD,
        symbol="BTC/USD",
        market_type=MarketType.SPOT,
        rationale="first",
    )
    second = DecisionCandidate(
        decision_id=uuid4(),
        cycle_id=cycle_id,
        created_at=decision_time,
        action=TradingAction.HOLD,
        symbol="BTC/USD",
        market_type=MarketType.SPOT,
        rationale="duplicate",
    )
    with pytest.raises(ValidationError, match="duplicate symbol"):
        CycleDecisionPlan(
            cycle_id=cycle_id,
            created_at=decision_time,
            decisions=(first, second),
        )


def test_plan_input_enforces_hard_decision_limit() -> None:
    with pytest.raises(ValidationError):
        CycleDecisionPlanInput(
            cycle_id=uuid4(),
            created_at=NOW,
            portfolio_state=portfolio(),
            market_states=(market(),),
            aggressiveness=5,
            max_decisions_per_cycle=21,
        )


def test_sequential_risk_accepts_portfolio_created_after_immutable_agent_decision() -> None:
    cycle_id = uuid4()
    decision = DecisionCandidate(
        decision_id=uuid4(),
        cycle_id=cycle_id,
        created_at=NOW,
        action=TradingAction.BUY,
        symbol="BTC/USD",
        market_type=MarketType.SPOT,
        proposed_quantity=Decimal("1"),
        rationale="planned once",
    )
    engine = SequentialCycleRiskEngine(
        policy=RiskPolicy(allow_quantity_reduction=True),
        cost_model=PaperExecutionCostModel(
            fee_rate=Decimal("0"),
            spread_bps=Decimal("0"),
            slippage_bps=Decimal("0"),
        ),
        clock=FixedClock(NOW + timedelta(seconds=2)),
    )
    result = engine.evaluate(
        decision=decision,
        market_state=market(as_of=NOW),
        portfolio_state=portfolio(as_of=NOW + timedelta(seconds=1)),
    )
    assert result.assessment.status is RiskDecision.ALLOW
    assert result.execution_intent is not None


def test_sequential_risk_still_rejects_portfolio_from_after_risk_assessment() -> None:
    cycle_id = uuid4()
    decision = DecisionCandidate(
        decision_id=uuid4(),
        cycle_id=cycle_id,
        created_at=NOW,
        action=TradingAction.BUY,
        symbol="BTC/USD",
        market_type=MarketType.SPOT,
        proposed_quantity=Decimal("1"),
        rationale="planned once",
    )
    engine = SequentialCycleRiskEngine(
        policy=RiskPolicy(allow_quantity_reduction=True),
        cost_model=PaperExecutionCostModel(
            fee_rate=Decimal("0"),
            spread_bps=Decimal("0"),
            slippage_bps=Decimal("0"),
        ),
        clock=FixedClock(NOW + timedelta(seconds=1)),
    )
    result = engine.evaluate(
        decision=decision,
        market_state=market(as_of=NOW),
        portfolio_state=portfolio(as_of=NOW + timedelta(seconds=2)),
    )
    assert result.assessment.status is RiskDecision.REJECT
    assert result.execution_intent is None


def test_legacy_campaign_digest_remains_unchanged_when_new_limit_is_absent() -> None:
    configuration = CampaignConfiguration(
        llm_model=LLMModel.LUNA,
        aggressiveness=5,
        trading_cadence_seconds=30.0,
        paper_initial_capital=Decimal("1000"),
        paper_settlement_asset="USD",
        paper_executable_markets=(
            ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),
        ),
        paper_fee_rate=Decimal("0.0026"),
        paper_spread_bps=Decimal("5"),
        paper_slippage_bps=Decimal("3"),
        risk_max_order_notional=Decimal("100"),
        risk_allowed_pairs=("BTC/USD",),
        risk_allow_quantity_reduction=True,
        cycle_market_timeout_seconds=20.0,
        cycle_agent_timeout_seconds=35.0,
        cycle_broker_timeout_seconds=5.0,
    )
    assert configuration.max_decisions_per_cycle is None
    assert configuration.effective_max_decisions_per_cycle == DEFAULT_MAX_DECISIONS_PER_CYCLE
    assert "max_decisions_per_cycle" not in configuration.canonical_payload()
    assert configuration.digest == LEGACY_CONFIGURATION_DIGEST


def test_new_campaign_persists_explicit_cycle_decision_limit() -> None:
    legacy = CampaignConfiguration(
        llm_model=LLMModel.LUNA,
        aggressiveness=5,
        trading_cadence_seconds=30.0,
        max_decisions_per_cycle=12,
        paper_initial_capital=Decimal("1000"),
        paper_settlement_asset="USD",
        paper_executable_markets=(
            ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),
        ),
        paper_fee_rate=Decimal("0.0026"),
        paper_spread_bps=Decimal("5"),
        paper_slippage_bps=Decimal("3"),
        risk_max_order_notional=Decimal("100"),
        risk_allowed_pairs=("BTC/USD",),
        risk_allow_quantity_reduction=True,
        cycle_market_timeout_seconds=20.0,
        cycle_agent_timeout_seconds=35.0,
        cycle_broker_timeout_seconds=5.0,
    )
    assert legacy.canonical_payload()["max_decisions_per_cycle"] == 12
    assert legacy.digest != LEGACY_CONFIGURATION_DIGEST
