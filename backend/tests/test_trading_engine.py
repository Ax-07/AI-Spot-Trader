import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

import ai_spot_trader.trading.engine as trading_engine_module
from ai_spot_trader.agent.errors import LLMOutputValidationError, LLMTransportError
from ai_spot_trader.broker.paper import PaperBroker
from ai_spot_trader.broker.pricing import PaperExecutionCostModel
from ai_spot_trader.core.runtime import AppRuntime
from ai_spot_trader.domain.enums import RiskDecision, RiskReason, TradingAction
from ai_spot_trader.domain.models import (
    AgentInput,
    AssetBalance,
    AssetPosition,
    DecisionCandidate,
    ExecutionIntent,
    Fill,
    MarketState,
    PortfolioState,
)
from ai_spot_trader.portfolio.ledger import PaperPortfolioLedger
from ai_spot_trader.risk.engine import RiskEngine, RiskResult
from ai_spot_trader.risk.policy import RiskPolicy
from ai_spot_trader.trading import (
    TradingCycleRunner,
    TradingCycleStage,
    TradingCycleStatus,
    TradingCycleTimeouts,
    TradingEngine,
    TradingEngineAlreadyRunningError,
)

NOW = datetime(2026, 9, 20, 15, 0, tzinfo=UTC)
MARKET_AT = NOW - timedelta(seconds=5)
CYCLE_ID = UUID("10000000-0000-0000-0000-000000000001")
DECISION_ID = UUID("20000000-0000-0000-0000-000000000002")
MARKET_ID = UUID("30000000-0000-0000-0000-000000000003")
INITIAL_PORTFOLIO_ID = UUID("40000000-0000-0000-0000-000000000004")
SNAPSHOT_ID = UUID("50000000-0000-0000-0000-000000000005")
RISK_ID = UUID("60000000-0000-0000-0000-000000000006")
EXECUTION_ID = UUID("70000000-0000-0000-0000-000000000007")
FILL_ID = UUID("80000000-0000-0000-0000-000000000008")


class FixedClock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


class FakeMarketData:
    def __init__(
        self,
        market_state: MarketState | None = None,
        *,
        error: Exception | None = None,
        block: bool = False,
    ) -> None:
        self.market_state = market_state or market()
        self.error = error
        self.block = block
        self.calls = 0

    async def snapshot(self, symbol: str) -> MarketState:
        self.calls += 1
        if self.block:
            await asyncio.Event().wait()
        if self.error is not None:
            raise self.error
        assert symbol == self.market_state.symbol
        return self.market_state


class FakeAgent:
    def __init__(
        self,
        action: TradingAction = TradingAction.HOLD,
        quantity: Decimal | None = None,
        *,
        error: Exception | None = None,
        block: bool = False,
    ) -> None:
        self.action = action
        self.quantity = quantity
        self.error = error
        self.block = block
        self.calls: list[AgentInput] = []
        self.active = 0
        self.max_active = 0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        if not block:
            self.release.set()

    async def generate_decision(self, agent_input: AgentInput) -> DecisionCandidate:
        self.calls.append(agent_input)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.entered.set()
        try:
            if self.block:
                await self.release.wait()
            if self.error is not None:
                raise self.error
            return DecisionCandidate(
                decision_id=DECISION_ID,
                cycle_id=agent_input.cycle_id,
                created_at=agent_input.created_at,
                action=self.action,
                symbol=agent_input.market_state.symbol,
                proposed_quantity=self.quantity,
                rationale="test",
            )
        finally:
            self.active -= 1


class RecordingRiskEngine(RiskEngine):
    def __init__(
        self,
        *,
        policy: RiskPolicy | None = None,
        clock: FixedClock | None = None,
    ) -> None:
        super().__init__(
            policy=policy or RiskPolicy(),
            cost_model=costs(),
            clock=clock or FixedClock(),
            risk_assessment_id_factory=lambda: RISK_ID,
            execution_id_factory=lambda: EXECUTION_ID,
        )
        self.calls: list[tuple[DecisionCandidate, MarketState, PortfolioState]] = []

    def evaluate(
        self,
        *,
        decision: DecisionCandidate,
        market_state: MarketState,
        portfolio_state: PortfolioState,
    ) -> RiskResult:
        self.calls.append((decision, market_state, portfolio_state))
        return super().evaluate(
            decision=decision,
            market_state=market_state,
            portfolio_state=portfolio_state,
        )


class RaisingRiskEngine:
    def __init__(self) -> None:
        self.calls = 0

    def evaluate(
        self,
        *,
        decision: DecisionCandidate,
        market_state: MarketState,
        portfolio_state: PortfolioState,
    ) -> RiskResult:
        self.calls += 1
        raise RuntimeError("risk failure")


class RecordingBroker:
    def __init__(
        self,
        delegate: PaperBroker | None = None,
        *,
        error: Exception | None = None,
        block: bool = False,
    ) -> None:
        self.delegate = delegate
        self.error = error
        self.block = block
        self.calls: list[tuple[ExecutionIntent, MarketState]] = []

    async def execute(
        self,
        intent: ExecutionIntent,
        market_state: MarketState,
    ) -> tuple[Fill, ...]:
        self.calls.append((intent, market_state))
        if self.block:
            await asyncio.Event().wait()
        if self.error is not None:
            raise self.error
        if self.delegate is None:
            raise AssertionError("unexpected broker call")
        return await self.delegate.execute(intent, market_state)


class AlwaysFailRunner:
    def __init__(self) -> None:
        self.calls = 0

    async def run_cycle(self) -> object:
        self.calls += 1
        raise RuntimeError("unexpected runner failure")


class FakeStoppableEngine:
    def __init__(self) -> None:
        self.stop_calls = 0

    async def stop(self) -> None:
        self.stop_calls += 1


def market(*, as_of: datetime = MARKET_AT, price: str = "100") -> MarketState:
    return MarketState(
        market_state_id=MARKET_ID,
        as_of=as_of,
        symbol="BTC/EUR",
        last_price=Decimal(price),
    )


def initial_portfolio(
    *,
    eur: str = "1000",
    btc: str | None = "2",
) -> PortfolioState:
    positions: tuple[AssetPosition, ...] = ()
    if btc is not None:
        positions = (
            AssetPosition(asset="BTC", quantity=Decimal(btc), available=Decimal(btc)),
        )
    return PortfolioState(
        portfolio_state_id=INITIAL_PORTFOLIO_ID,
        as_of=MARKET_AT,
        balances=(AssetBalance(asset="EUR", available=Decimal(eur)),),
        positions=positions,
    )


def costs() -> PaperExecutionCostModel:
    return PaperExecutionCostModel(
        fee_rate=Decimal("0"),
        spread_bps=Decimal("0"),
        slippage_bps=Decimal("0"),
    )


def ledger(
    *,
    state: PortfolioState | None = None,
    clock: FixedClock | None = None,
) -> PaperPortfolioLedger:
    return PaperPortfolioLedger(
        initial_state=state or initial_portfolio(),
        clock=clock or FixedClock(),
        portfolio_state_id_factory=lambda: SNAPSHOT_ID,
    )


def runner(
    *,
    market_data: FakeMarketData | None = None,
    portfolio: PaperPortfolioLedger | None = None,
    agent: FakeAgent | None = None,
    risk_engine: RiskEngine | None = None,
    broker: RecordingBroker | None = None,
    clock: FixedClock | None = None,
    timeouts: TradingCycleTimeouts | None = None,
) -> tuple[
    TradingCycleRunner,
    FakeMarketData,
    PaperPortfolioLedger,
    FakeAgent,
    RiskEngine,
    RecordingBroker,
]:
    shared_clock = clock or FixedClock()
    market_source = market_data or FakeMarketData()
    portfolio_ledger = portfolio or ledger(clock=shared_clock)
    fake_agent = agent or FakeAgent()
    risk = risk_engine or RecordingRiskEngine(clock=shared_clock)
    if broker is None:
        paper = PaperBroker(
            ledger=portfolio_ledger,
            cost_model=costs(),
            clock=shared_clock,
            fill_id_factory=lambda: FILL_ID,
        )
        broker = RecordingBroker(paper)
    cycle_runner = TradingCycleRunner(
        market_data=market_source,
        portfolio=portfolio_ledger,
        agent=fake_agent,
        risk_engine=risk,
        broker=broker,
        symbol="BTC/EUR",
        aggressiveness=5,
        timeouts=timeouts or TradingCycleTimeouts(1, 1, 1),
        clock=shared_clock,
        cycle_id_factory=lambda: CYCLE_ID,
    )
    return cycle_runner, market_source, portfolio_ledger, fake_agent, risk, broker


def snapshot_values(state: PortfolioState) -> tuple[Decimal, Decimal]:
    eur = next(item.available for item in state.balances if item.asset == "EUR")
    btc = next(
        (item.quantity for item in state.positions if item.asset == "BTC"),
        Decimal(0),
    )
    return eur, btc


def test_hold_runs_through_risk_and_never_calls_broker() -> None:
    cycle, _, portfolio, agent, risk, broker = runner(agent=FakeAgent(TradingAction.HOLD))

    result = asyncio.run(cycle.run_cycle())

    assert result.status is TradingCycleStatus.COMPLETED
    assert result.decision is not None and result.decision.action is TradingAction.HOLD
    assert result.risk_assessment is not None
    assert result.risk_assessment.status is RiskDecision.ALLOW
    assert result.risk_assessment.reasons == (RiskReason.HOLD_NO_EXECUTION,)
    assert len(cast(RecordingRiskEngine, risk).calls) == 1
    assert broker.calls == []
    assert result.execution_intent is None and result.fills == ()
    assert snapshot_values(portfolio.snapshot(as_of=NOW)) == (Decimal("1000"), Decimal("2"))
    assert len(agent.calls) == 1


@pytest.mark.parametrize("action", [TradingAction.BUY, TradingAction.SELL])
def test_allow_executes_broker_exactly_once(action: TradingAction) -> None:
    quantity = Decimal("1")
    state = initial_portfolio(btc="2")
    cycle, _, _, _, _, broker = runner(
        portfolio=ledger(state=state),
        agent=FakeAgent(action, quantity),
    )

    result = asyncio.run(cycle.run_cycle())

    assert result.status is TradingCycleStatus.COMPLETED
    assert len(broker.calls) == 1
    assert result.execution_intent is broker.calls[0][0]
    assert len(result.fills) == 1


def test_modify_executes_exactly_risk_authorized_quantity() -> None:
    shared_clock = FixedClock()
    risk = RecordingRiskEngine(
        policy=RiskPolicy(allow_quantity_reduction=True),
        clock=shared_clock,
    )
    cycle, _, _, _, _, broker = runner(
        clock=shared_clock,
        agent=FakeAgent(TradingAction.SELL, Decimal("3")),
        risk_engine=risk,
    )

    result = asyncio.run(cycle.run_cycle())

    assert result.risk_assessment is not None
    assert result.risk_assessment.status is RiskDecision.MODIFY
    assert result.risk_assessment.authorized_quantity == Decimal("2")
    assert result.execution_intent is not None
    assert result.execution_intent.quantity == Decimal("2")
    assert broker.calls[0][0].quantity == Decimal("2")
    assert result.fills[0].quantity == Decimal("2")


def test_reject_is_business_result_and_never_calls_broker_or_mutates_portfolio() -> None:
    cycle, _, portfolio, _, _, broker = runner(
        agent=FakeAgent(TradingAction.SELL, Decimal("3"))
    )
    before = snapshot_values(portfolio.snapshot(as_of=NOW))

    result = asyncio.run(cycle.run_cycle())

    assert result.status is TradingCycleStatus.COMPLETED
    assert result.risk_assessment is not None
    assert result.risk_assessment.status is RiskDecision.REJECT
    assert result.execution_intent is None
    assert broker.calls == []
    assert snapshot_values(portfolio.snapshot(as_of=NOW)) == before


def test_same_snapshots_and_cycle_id_are_reused_across_agent_risk_and_broker() -> None:
    cycle, market_source, _, agent, risk, broker = runner(
        agent=FakeAgent(TradingAction.BUY, Decimal("1"))
    )

    result = asyncio.run(cycle.run_cycle())

    assert market_source.calls == 1
    assert result.agent_input is agent.calls[0]
    risk_call = cast(RecordingRiskEngine, risk).calls[0]
    assert agent.calls[0].market_state is risk_call[1]
    assert agent.calls[0].portfolio_state is risk_call[2]
    assert broker.calls[0][1] is agent.calls[0].market_state
    assert result.decision is not None and result.risk_assessment is not None
    assert result.execution_intent is not None
    assert result.agent_input.cycle_id == CYCLE_ID
    assert result.decision.cycle_id == CYCLE_ID
    assert result.risk_assessment.cycle_id == CYCLE_ID
    assert result.execution_intent.cycle_id == CYCLE_ID


def test_clock_and_cycle_factory_control_input_and_chronology() -> None:
    clock = FixedClock(NOW)
    cycle, _, _, _, _, _ = runner(clock=clock)

    result = asyncio.run(cycle.run_cycle())

    assert result.cycle_id == CYCLE_ID
    assert result.agent_input is not None
    assert result.agent_input.created_at == NOW
    assert result.agent_input.market_state.as_of <= result.agent_input.created_at
    assert result.agent_input.portfolio_state.as_of <= result.agent_input.created_at


def test_market_error_stops_before_agent_risk_and_broker() -> None:
    market_source = FakeMarketData(error=RuntimeError("market unavailable"))
    agent = FakeAgent()
    risk = RecordingRiskEngine()
    broker = RecordingBroker()
    cycle, _, _, _, _, _ = runner(
        market_data=market_source,
        agent=agent,
        risk_engine=risk,
        broker=broker,
    )

    result = asyncio.run(cycle.run_cycle())

    assert result.status is TradingCycleStatus.FAILED
    assert result.failure is not None and result.failure.stage is TradingCycleStage.MARKET
    assert agent.calls == [] and risk.calls == [] and broker.calls == []


@pytest.mark.parametrize(
    "error",
    [LLMTransportError("transport"), LLMOutputValidationError("invalid output")],
)
def test_agent_errors_stop_before_risk_and_broker_without_fake_hold(error: Exception) -> None:
    agent = FakeAgent(error=error)
    risk = RecordingRiskEngine()
    broker = RecordingBroker()
    cycle, _, _, _, _, _ = runner(agent=agent, risk_engine=risk, broker=broker)

    result = asyncio.run(cycle.run_cycle())

    assert result.status is TradingCycleStatus.FAILED
    assert result.failure is not None and result.failure.stage is TradingCycleStage.AGENT
    assert result.decision is None
    assert risk.calls == [] and broker.calls == []


def test_technical_risk_error_stops_before_broker() -> None:
    bad_risk = RaisingRiskEngine()
    broker = RecordingBroker()
    cycle, _, _, _, _, _ = runner(
        agent=FakeAgent(TradingAction.BUY, Decimal("1")),
        risk_engine=cast(RiskEngine, bad_risk),
        broker=broker,
    )

    result = asyncio.run(cycle.run_cycle())

    assert result.status is TradingCycleStatus.FAILED
    assert result.failure is not None and result.failure.stage is TradingCycleStage.RISK
    assert bad_risk.calls == 1 and broker.calls == []


def test_broker_error_is_explicit_and_not_success() -> None:
    broker = RecordingBroker(error=RuntimeError("broker failure"))
    cycle, _, portfolio, _, _, _ = runner(
        agent=FakeAgent(TradingAction.BUY, Decimal("1")),
        broker=broker,
    )
    before = snapshot_values(portfolio.snapshot(as_of=NOW))

    result = asyncio.run(cycle.run_cycle())

    assert result.status is TradingCycleStatus.FAILED
    assert result.failure is not None and result.failure.stage is TradingCycleStage.BROKER
    assert result.execution_intent is not None
    assert result.fills == ()
    assert snapshot_values(portfolio.snapshot(as_of=NOW)) == before


@pytest.mark.parametrize(
    ("stage", "market_data", "agent", "broker"),
    [
        (TradingCycleStage.MARKET, FakeMarketData(block=True), FakeAgent(), RecordingBroker()),
        (TradingCycleStage.AGENT, FakeMarketData(), FakeAgent(block=True), RecordingBroker()),
        (
            TradingCycleStage.BROKER,
            FakeMarketData(),
            FakeAgent(TradingAction.BUY, Decimal("1")),
            RecordingBroker(block=True),
        ),
    ],
)
def test_external_io_timeouts_are_explicit_and_create_no_ghost_execution(
    stage: TradingCycleStage,
    market_data: FakeMarketData,
    agent: FakeAgent,
    broker: RecordingBroker,
) -> None:
    risk = RecordingRiskEngine()
    cycle, _, portfolio, _, _, _ = runner(
        market_data=market_data,
        agent=agent,
        risk_engine=risk,
        broker=broker,
        timeouts=TradingCycleTimeouts(0.01, 0.01, 0.01),
    )
    before = snapshot_values(portfolio.snapshot(as_of=NOW))

    result = asyncio.run(cycle.run_cycle())

    assert result.status is TradingCycleStatus.FAILED
    assert result.failure is not None
    assert result.failure.stage is stage
    assert result.failure.timed_out is True
    assert snapshot_values(portfolio.snapshot(as_of=NOW)) == before
    if stage is TradingCycleStage.MARKET:
        assert agent.calls == [] and risk.calls == [] and broker.calls == []
    if stage is TradingCycleStage.AGENT:
        assert risk.calls == [] and broker.calls == []


def test_future_market_snapshot_fails_before_agent() -> None:
    source = FakeMarketData(market(as_of=NOW + timedelta(microseconds=1)))
    agent = FakeAgent()
    cycle, _, _, _, risk, broker = runner(market_data=source, agent=agent)

    result = asyncio.run(cycle.run_cycle())

    assert result.status is TradingCycleStatus.FAILED
    assert result.failure is not None and result.failure.stage is TradingCycleStage.INPUT
    assert agent.calls == []
    assert cast(RecordingRiskEngine, risk).calls == [] and broker.calls == []


def test_orchestrator_preserves_risk_action_symbol_quantity_and_intent_identity() -> None:
    cycle, _, _, _, _, broker = runner(
        agent=FakeAgent(TradingAction.BUY, Decimal("1"))
    )

    result = asyncio.run(cycle.run_cycle())

    assert result.decision is not None and result.execution_intent is not None
    intent = result.execution_intent
    assert broker.calls[0][0] is intent
    assert intent.execution_id == EXECUTION_ID
    assert intent.action is result.decision.action
    assert intent.symbol == result.decision.symbol
    assert intent.quantity == result.decision.proposed_quantity


@pytest.mark.parametrize("action", [TradingAction.BUY, TradingAction.SELL])
def test_post_trade_portfolio_is_coherent(action: TradingAction) -> None:
    cycle, _, _, _, _, _ = runner(agent=FakeAgent(action, Decimal("1")))

    result = asyncio.run(cycle.run_cycle())

    assert result.portfolio_state_after is not None
    eur, btc = snapshot_values(result.portfolio_state_after)
    if action is TradingAction.BUY:
        assert (eur, btc) == (Decimal("900"), Decimal("3"))
    else:
        assert (eur, btc) == (Decimal("1100"), Decimal("1"))


def test_two_manual_cycles_cannot_overlap() -> None:
    async def scenario() -> int:
        blocking_agent = FakeAgent(block=True)
        cycle, _, _, _, _, _ = runner(agent=blocking_agent)
        first = asyncio.create_task(cycle.run_cycle())
        await blocking_agent.entered.wait()
        second = asyncio.create_task(cycle.run_cycle())
        await asyncio.sleep(0)
        assert len(blocking_agent.calls) == 1
        blocking_agent.release.set()
        await asyncio.gather(first, second)
        return blocking_agent.max_active

    assert asyncio.run(scenario()) == 1


def test_duplicate_start_is_rejected_and_stop_wakes_long_cadence() -> None:
    async def scenario() -> None:
        agent = FakeAgent()
        cycle, _, _, _, _, _ = runner(agent=agent)
        engine = TradingEngine(runner=cycle, cadence_seconds=60)
        await engine.start()
        with pytest.raises(TradingEngineAlreadyRunningError):
            await engine.start()
        while not agent.calls:
            await asyncio.sleep(0)
        await asyncio.wait_for(engine.stop(), timeout=0.2)
        assert not engine.is_running

    asyncio.run(scenario())


def test_autonomous_loop_is_sequential_without_overlap() -> None:
    async def scenario() -> int:
        agent = FakeAgent()
        cycle, _, _, _, _, _ = runner(agent=agent)
        engine = TradingEngine(runner=cycle, cadence_seconds=0.01)
        await engine.start()
        while len(agent.calls) < 3:
            await asyncio.sleep(0.005)
        await engine.stop()
        return agent.max_active

    assert asyncio.run(scenario()) == 1


def test_unexpected_cycle_error_does_not_create_tight_loop() -> None:
    async def scenario() -> int:
        failing = AlwaysFailRunner()
        engine = TradingEngine(
            runner=cast(TradingCycleRunner, failing),
            cadence_seconds=0.05,
        )
        await engine.start()
        await asyncio.sleep(0.13)
        await engine.stop()
        assert engine.last_unexpected_error_type == "RuntimeError"
        return failing.calls

    calls = asyncio.run(scenario())
    assert 2 <= calls <= 4


def test_runtime_close_stops_configured_engine() -> None:
    async def scenario() -> tuple[bool, int]:
        engine = FakeStoppableEngine()
        runtime = AppRuntime(trading_engine=engine)
        await runtime.close()
        return runtime.shutdown_requested.is_set(), engine.stop_calls

    assert asyncio.run(scenario()) == (True, 1)


@pytest.mark.parametrize(
    "timeouts",
    [
        (0, 1, 1),
        (1, 0, 1),
        (1, 1, 0),
        (-1, 1, 1),
        (float("inf"), 1, 1),
    ],
)
def test_timeouts_must_be_positive_and_explicit(timeouts: tuple[float, float, float]) -> None:
    with pytest.raises(ValueError):
        TradingCycleTimeouts(*timeouts)


def test_orchestrator_never_constructs_intent_or_references_kraken_or_live() -> None:
    source = Path(trading_engine_module.__file__).read_text(encoding="utf-8")

    assert "ExecutionIntent(" not in source
    assert "integrations.kraken" not in source
    assert "LIVE" not in source


@pytest.mark.parametrize("cadence", [0, -1, float("inf"), float("nan")])
def test_cadence_must_be_positive_and_finite(cadence: float) -> None:
    cycle, _, _, _, _, _ = runner()

    with pytest.raises(ValueError):
        TradingEngine(runner=cycle, cadence_seconds=cadence)
