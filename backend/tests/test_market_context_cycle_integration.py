import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from ai_spot_trader.broker.pricing import PaperExecutionCostModel
from ai_spot_trader.domain.enums import TradingAction
from ai_spot_trader.domain.models import (
    AgentInput,
    AssetBalance,
    DecisionCandidate,
    ExecutionIntent,
    Fill,
    MarketContext,
    MarketState,
    MarketWindowStats,
    PortfolioState,
)
from ai_spot_trader.portfolio.ledger import PaperPortfolioLedger
from ai_spot_trader.risk.engine import RiskEngine
from ai_spot_trader.risk.policy import RiskPolicy
from ai_spot_trader.trading import TradingCycleRunner, TradingCycleStatus, TradingCycleTimeouts

NOW = datetime(2026, 9, 21, 9, 0, tzinfo=UTC)
LAST_OBSERVED = NOW - timedelta(seconds=2)


class FixedClock:
    def now(self) -> datetime:
        return NOW


class ContextMarketData:
    def __init__(self, state: MarketState) -> None:
        self.state = state
        self.calls = 0

    async def snapshot(self, symbol: str) -> MarketState:
        self.calls += 1
        assert symbol == self.state.symbol
        return self.state


class CapturingHoldAgent:
    def __init__(self) -> None:
        self.inputs: list[AgentInput] = []

    async def generate_decision(self, agent_input: AgentInput) -> DecisionCandidate:
        self.inputs.append(agent_input)
        return DecisionCandidate(
            decision_id=uuid4(),
            cycle_id=agent_input.cycle_id,
            created_at=agent_input.created_at,
            action=TradingAction.HOLD,
            symbol=agent_input.market_state.symbol,
            rationale="context propagation test",
        )


class NeverBroker:
    async def execute(
        self,
        intent: ExecutionIntent,
        market_state: MarketState,
    ) -> tuple[Fill, ...]:
        raise AssertionError("HOLD must not reach broker")


def test_multi_horizon_market_context_reaches_canonical_agent_input_unchanged() -> None:
    context = MarketContext(
        last_observed_at=LAST_OBSERVED,
        data_age_seconds=Decimal("2"),
        windows=(
            MarketWindowStats(
                horizon_seconds=Decimal("300"),
                window_start=NOW - timedelta(minutes=5),
                observation_count=0,
                is_complete=False,
            ),
            MarketWindowStats(
                horizon_seconds=Decimal("1800"),
                window_start=NOW - timedelta(minutes=30),
                observation_count=0,
                is_complete=False,
            ),
        ),
    )
    market_state = MarketState(
        market_state_id=uuid4(),
        as_of=NOW,
        symbol="BTC/EUR",
        last_price=Decimal("50000"),
        context=context,
    )
    market = ContextMarketData(market_state)
    agent = CapturingHoldAgent()
    portfolio = PaperPortfolioLedger(
        initial_state=PortfolioState(
            portfolio_state_id=uuid4(),
            as_of=NOW,
            balances=(AssetBalance(asset="EUR", available=Decimal("1000")),),
        ),
        clock=FixedClock(),
    )
    costs = PaperExecutionCostModel(
        fee_rate=Decimal("0"),
        spread_bps=Decimal("0"),
        slippage_bps=Decimal("0"),
    )
    runner = TradingCycleRunner(
        market_data=market,
        portfolio=portfolio,
        agent=agent,
        risk_engine=RiskEngine(policy=RiskPolicy(), cost_model=costs, clock=FixedClock()),
        broker=NeverBroker(),
        symbol="BTC/EUR",
        aggressiveness=5,
        timeouts=TradingCycleTimeouts(1, 1, 1),
        clock=FixedClock(),
    )

    result = asyncio.run(runner.run_cycle())

    assert result.status is TradingCycleStatus.COMPLETED
    assert market.calls == 1
    assert len(agent.inputs) == 1
    assert result.agent_input is agent.inputs[0]
    agent_input = result.agent_input
    assert agent_input is not None
    assert agent_input.market_state is market_state
    market_context = agent_input.market_state.context
    assert market_context == context
    assert market_context is not None
    assert [window.horizon_seconds for window in market_context.windows] == [
        Decimal("300"),
        Decimal("1800"),
    ]
