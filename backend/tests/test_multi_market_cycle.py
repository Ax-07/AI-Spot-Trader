import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from ai_spot_trader.broker.paper import PaperBroker
from ai_spot_trader.broker.pricing import PaperExecutionCostModel
from ai_spot_trader.domain.enums import (
    DerivativeContractKind,
    MarketType,
    RiskDecision,
    RiskReason,
    TradingAction,
)
from ai_spot_trader.domain.models import (
    AssetBalance,
    AssetPosition,
    DecisionCandidate,
    DerivativeInstrument,
    DerivativeMarketContext,
    ExecutableMarket,
    ExecutionIntent,
    MarketState,
    PortfolioState,
    RiskAssessment,
)
from ai_spot_trader.domain.planning import CycleDecisionPlan, CycleDecisionPlanInput
from ai_spot_trader.persistence.audit import AuditedTradingCycleRunner
from ai_spot_trader.portfolio.ledger import PaperPortfolioLedger
from ai_spot_trader.risk.engine import RiskResult
from ai_spot_trader.risk.policy import RiskPolicy
from ai_spot_trader.risk.sequential import SequentialCycleRiskEngine
from ai_spot_trader.trading.engine import TradingCycleStage, TradingCycleStatus, TradingCycleTimeouts
from ai_spot_trader.trading.multi_market import MultiMarketTradingCycleRunner

NOW = datetime(2026, 9, 27, 0, 0, tzinfo=UTC)
ZERO_COSTS = PaperExecutionCostModel(
    fee_rate=Decimal("0"),
    spread_bps=Decimal("0"),
    slippage_bps=Decimal("0"),
)


class FixedClock:
    def now(self) -> datetime:
        return NOW


class StaticMarkets:
    def __init__(self, states: tuple[MarketState, ...]) -> None:
        self.states = {(state.symbol, state.market_type): state for state in states}
        self.calls: list[tuple[str, MarketType]] = []

    async def snapshot(self, symbol: str, market_type: MarketType) -> MarketState:
        self.calls.append((symbol, market_type))
        return self.states[(symbol, market_type)]


class ScriptedPlanAgent:
    def __init__(self, script: tuple[tuple[str, TradingAction, Decimal | None], ...]) -> None:
        self.script = script
        self.calls: list[CycleDecisionPlanInput] = []
        self.last_tool_traces = ()

    async def generate_decision_plan(self, plan_input: CycleDecisionPlanInput) -> CycleDecisionPlan:
        self.calls.append(plan_input)
        states = {state.symbol: state for state in plan_input.market_states}
        decisions = tuple(
            DecisionCandidate(
                decision_id=uuid4(),
                cycle_id=plan_input.cycle_id,
                created_at=plan_input.created_at,
                action=action,
                symbol=symbol,
                market_type=states[symbol].market_type,
                proposed_quantity=quantity,
                rationale=f"scripted {action.value}",
            )
            for symbol, action, quantity in self.script
        )
        return CycleDecisionPlan(
            cycle_id=plan_input.cycle_id,
            created_at=plan_input.created_at,
            decisions=decisions,
            rationale="ordered test plan",
        )


class FailOnSecondBroker:
    def __init__(self, delegate: PaperBroker) -> None:
        self.delegate = delegate
        self.calls = 0

    async def execute(self, intent, market_state):
        self.calls += 1
        if self.calls == 2:
            raise RuntimeError("second broker execution failed")
        return await self.delegate.execute(intent, market_state)


class InMemoryWriter:
    def __init__(self) -> None:
        self.results = []

    async def ensure_available(self) -> None:
        return None

    async def record(self, result) -> bool:
        self.results.append(result)
        return True


def market(symbol: str, price: str = "100") -> MarketState:
    return MarketState(
        market_state_id=uuid4(),
        as_of=NOW,
        symbol=symbol,
        last_price=Decimal(price),
        market_type=MarketType.SPOT,
    )




def perpetual_market(symbol: str, price: str = "100") -> MarketState:
    base, quote = symbol.split("/")
    instrument = DerivativeInstrument(
        symbol=symbol,
        venue_symbol=f"PF_{base}{quote}",
        market_type=MarketType.PERPETUAL,
        contract_kind=DerivativeContractKind.LINEAR,
        underlying_asset=base,
        quote_asset=quote,
        contract_size=Decimal("1"),
        tick_size=Decimal("1"),
        min_order_quantity=Decimal("0.01"),
        max_position_quantity=Decimal("100"),
        initial_margin_rate=Decimal("0.10"),
        maintenance_margin_rate=Decimal("0.05"),
        max_leverage=Decimal("10"),
        funding_interval_seconds=Decimal("3600"),
    )
    return MarketState(
        market_state_id=uuid4(),
        as_of=NOW,
        symbol=symbol,
        last_price=Decimal(price),
        market_type=MarketType.PERPETUAL,
        derivative=DerivativeMarketContext(
            observed_at=NOW,
            instrument=instrument,
            mark_price=Decimal(price),
            index_price=Decimal(price),
            funding_rate=Decimal("0"),
        ),
    )

def portfolio(*, cash: str, positions: tuple[tuple[str, str], ...] = ()) -> PortfolioState:
    return PortfolioState(
        portfolio_state_id=uuid4(),
        as_of=NOW,
        settlement_asset="USD",
        balances=(AssetBalance(asset="USD", available=Decimal(cash)),),
        positions=tuple(
            AssetPosition(asset=asset, quantity=Decimal(quantity), available=Decimal(quantity))
            for asset, quantity in positions
        ),
    )


def build_runner(
    *,
    state: PortfolioState,
    states: tuple[MarketState, ...],
    script: tuple[tuple[str, TradingAction, Decimal | None], ...],
    broker_override=None,
    risk_policy: RiskPolicy | None = None,
    risk_override=None,
    max_decisions_per_cycle: int = 6,
):
    clock = FixedClock()
    ledger = PaperPortfolioLedger(initial_state=state, clock=clock, settlement_asset="USD")
    source = StaticMarkets(states)
    agent = ScriptedPlanAgent(script)
    risk = risk_override or SequentialCycleRiskEngine(
        policy=risk_policy or RiskPolicy(allow_quantity_reduction=True),
        cost_model=ZERO_COSTS,
        clock=clock,
    )
    paper = PaperBroker(ledger=ledger, cost_model=ZERO_COSTS, clock=clock)
    broker = paper if broker_override is None else broker_override(paper)
    executable = tuple(
        sorted(
            (ExecutableMarket(symbol=item.symbol, market_type=item.market_type) for item in states),
            key=lambda item: (item.market_type.value, item.symbol),
        )
    )
    runner = MultiMarketTradingCycleRunner(
        portfolio=ledger,
        agent=agent,
        risk_engine=risk,
        broker=broker,
        aggressiveness=5,
        max_decisions_per_cycle=max_decisions_per_cycle,
        timeouts=TradingCycleTimeouts(1, 1, 1),
        executable_market_data=source,
        executable_markets=executable,
        clock=clock,
    )
    return runner, ledger, agent, broker


def balance(state: PortfolioState, asset: str) -> Decimal:
    return next(item.available for item in state.balances if item.asset == asset)


def held(state: PortfolioState, asset: str) -> Decimal:
    return next((item.quantity for item in state.positions if item.asset == asset), Decimal("0"))


def test_two_buys_use_sequential_cash_and_second_is_modified() -> None:
    states = (market("BTC/USD"), market("ETH/USD"))
    runner, ledger, agent, _broker = build_runner(
        state=portfolio(cash="150"),
        states=states,
        script=(
            ("BTC/USD", TradingAction.BUY, Decimal("1")),
            ("ETH/USD", TradingAction.BUY, Decimal("1")),
        ),
    )

    result = asyncio.run(runner.run_cycle())

    assert result.status is TradingCycleStatus.COMPLETED
    assert len(agent.calls) == 1
    assert len(result.decision_results) == 2
    first, second = result.decision_results
    assert first.risk_assessment is not None and first.risk_assessment.status is RiskDecision.ALLOW
    assert second.risk_assessment is not None and second.risk_assessment.status is RiskDecision.MODIFY
    assert second.risk_assessment.authorized_quantity == Decimal("0.5")
    assert balance(second.portfolio_state_before, "USD") == Decimal("50")
    final = ledger.snapshot(as_of=NOW)
    assert balance(final, "USD") == Decimal("0")
    assert held(final, "BTC") == Decimal("1")
    assert held(final, "ETH") == Decimal("0.5")


def test_sell_then_buy_reuses_cash_from_previous_execution() -> None:
    states = (market("BTC/USD"), market("ETH/USD"))
    runner, ledger, _agent, _broker = build_runner(
        state=portfolio(cash="0", positions=(("BTC", "1"),)),
        states=states,
        script=(
            ("BTC/USD", TradingAction.SELL, Decimal("1")),
            ("ETH/USD", TradingAction.BUY, Decimal("0.8")),
        ),
    )

    result = asyncio.run(runner.run_cycle())

    assert result.status is TradingCycleStatus.COMPLETED
    assert len(result.decision_results) == 2
    second = result.decision_results[1]
    assert balance(second.portfolio_state_before, "USD") == Decimal("100")
    assert second.risk_assessment is not None and second.risk_assessment.status is RiskDecision.ALLOW
    final = ledger.snapshot(as_of=NOW)
    assert balance(final, "USD") == Decimal("20")
    assert held(final, "BTC") == Decimal("0")
    assert held(final, "ETH") == Decimal("0.8")


def test_hold_and_risk_reject_do_not_block_following_decisions() -> None:
    states = (market("BTC/USD"), market("ETH/USD"), market("SOL/USD", "50"))
    runner, ledger, _agent, _broker = build_runner(
        state=portfolio(cash="100"),
        states=states,
        script=(
            ("BTC/USD", TradingAction.HOLD, None),
            ("ETH/USD", TradingAction.SELL, Decimal("1")),
            ("SOL/USD", TradingAction.BUY, Decimal("1")),
        ),
    )

    result = asyncio.run(runner.run_cycle())

    assert result.status is TradingCycleStatus.COMPLETED
    assert [item.decision.action for item in result.decision_results] == [
        TradingAction.HOLD,
        TradingAction.SELL,
        TradingAction.BUY,
    ]
    assert result.decision_results[0].execution_intent is None
    assert result.decision_results[1].risk_assessment is not None
    assert result.decision_results[1].risk_assessment.status is RiskDecision.REJECT
    assert result.decision_results[2].fills
    final = ledger.snapshot(as_of=NOW)
    assert held(final, "SOL") == Decimal("1")
    assert balance(final, "USD") == Decimal("50")


def test_late_broker_failure_is_rolled_back_by_audited_runner() -> None:
    states = (market("BTC/USD"), market("ETH/USD"))
    delegate, ledger, _agent, broker = build_runner(
        state=portfolio(cash="250"),
        states=states,
        script=(
            ("BTC/USD", TradingAction.BUY, Decimal("1")),
            ("ETH/USD", TradingAction.BUY, Decimal("1")),
        ),
        broker_override=FailOnSecondBroker,
    )
    writer = InMemoryWriter()
    runner = AuditedTradingCycleRunner(delegate=delegate, audit_writer=writer, portfolio=ledger)

    result = asyncio.run(runner.run_cycle())

    assert result.status is TradingCycleStatus.FAILED
    assert result.failure is not None and result.failure.stage is TradingCycleStage.BROKER
    assert len(result.decision_results) == 2
    assert result.decision_results[0].fills
    assert isinstance(broker, FailOnSecondBroker) and broker.calls == 2
    restored = ledger.snapshot(as_of=NOW)
    assert balance(restored, "USD") == Decimal("250")
    assert held(restored, "BTC") == Decimal("0")
    assert held(restored, "ETH") == Decimal("0")
    assert writer.results == [result]


def test_perpetual_total_exposure_is_recalculated_after_each_fill() -> None:
    states = (perpetual_market("BTC/USD"), perpetual_market("ETH/USD"))
    runner, ledger, _agent, _broker = build_runner(
        state=portfolio(cash="1000"),
        states=states,
        script=(
            ("BTC/USD", TradingAction.BUY, Decimal("1")),
            ("ETH/USD", TradingAction.BUY, Decimal("1")),
        ),
        risk_policy=RiskPolicy(
            allowed_pairs=frozenset({"BTC/USD", "ETH/USD"}),
            allow_quantity_reduction=True,
            derivative_leverage=Decimal("1"),
            max_derivative_leverage=Decimal("2"),
            max_derivative_position_notional=Decimal("1000"),
            max_total_derivative_exposure=Decimal("150"),
            derivative_liquidation_buffer_ratio=Decimal("1.10"),
        ),
    )

    result = asyncio.run(runner.run_cycle())

    assert result.status is TradingCycleStatus.COMPLETED
    first, second = result.decision_results
    assert first.fills
    assert second.risk_assessment is not None
    assert second.risk_assessment.status is RiskDecision.REJECT
    assert RiskReason.DERIVATIVE_TOTAL_EXPOSURE_EXCEEDED in second.risk_assessment.reasons
    final = ledger.snapshot(as_of=NOW)
    assert len(final.derivative_positions) == 1
    assert final.derivative_positions[0].symbol == "BTC/USD"


def test_plan_outside_causal_universe_fails_closed_before_risk() -> None:
    class OutsideUniverseAgent:
        last_tool_traces = ()

        async def generate_decision_plan(self, plan_input: CycleDecisionPlanInput) -> CycleDecisionPlan:
            decision = DecisionCandidate(
                decision_id=uuid4(),
                cycle_id=plan_input.cycle_id,
                created_at=plan_input.created_at,
                action=TradingAction.HOLD,
                symbol="DOGE/USD",
                market_type=MarketType.SPOT,
                rationale="invalid outside causal universe",
            )
            return CycleDecisionPlan(
                cycle_id=plan_input.cycle_id,
                created_at=plan_input.created_at,
                decisions=(decision,),
            )

    state = portfolio(cash="100")
    market_state = market("BTC/USD")
    clock = FixedClock()
    ledger = PaperPortfolioLedger(initial_state=state, clock=clock, settlement_asset="USD")
    runner = MultiMarketTradingCycleRunner(
        portfolio=ledger,
        agent=OutsideUniverseAgent(),
        risk_engine=SequentialCycleRiskEngine(
            policy=RiskPolicy(allow_quantity_reduction=True),
            cost_model=ZERO_COSTS,
            clock=clock,
        ),
        broker=PaperBroker(ledger=ledger, cost_model=ZERO_COSTS, clock=clock),
        aggressiveness=5,
        max_decisions_per_cycle=6,
        timeouts=TradingCycleTimeouts(1, 1, 1),
        executable_market_data=StaticMarkets((market_state,)),
        executable_markets=(ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),),
        clock=clock,
    )

    result = asyncio.run(runner.run_cycle())

    assert result.status is TradingCycleStatus.FAILED
    assert result.failure is not None and result.failure.stage is TradingCycleStage.AGENT
    assert result.decision_results == ()
    assert balance(ledger.snapshot(as_of=NOW), "USD") == Decimal("100")


def test_configured_plan_limit_is_enforced_even_below_hard_limit() -> None:
    states = (market("BTC/USD"), market("ETH/USD"))
    runner, ledger, _agent, _broker = build_runner(
        state=portfolio(cash="300"),
        states=states,
        script=(
            ("BTC/USD", TradingAction.BUY, Decimal("1")),
            ("ETH/USD", TradingAction.BUY, Decimal("1")),
        ),
        max_decisions_per_cycle=1,
    )

    result = asyncio.run(runner.run_cycle())

    assert result.status is TradingCycleStatus.FAILED
    assert result.failure is not None and result.failure.stage is TradingCycleStage.AGENT
    assert result.decision_results == ()
    assert balance(ledger.snapshot(as_of=NOW), "USD") == Decimal("300")


def test_risk_correlation_mismatch_fails_closed() -> None:
    class WrongCycleRisk:
        def evaluate(self, *, decision, market_state, portfolio_state, management_mode=False):
            wrong_cycle = uuid4()
            assessment = RiskAssessment(
                risk_assessment_id=uuid4(),
                cycle_id=wrong_cycle,
                decision_id=decision.decision_id,
                assessed_at=NOW,
                status=RiskDecision.ALLOW,
                requested_quantity=decision.proposed_quantity,
                authorized_quantity=decision.proposed_quantity,
            )
            intent = ExecutionIntent(
                execution_id=uuid4(),
                cycle_id=wrong_cycle,
                decision_id=decision.decision_id,
                risk_assessment_id=assessment.risk_assessment_id,
                created_at=NOW,
                action=decision.action,
                symbol=decision.symbol,
                quantity=decision.proposed_quantity,
                market_type=decision.market_type,
            )
            return RiskResult(assessment=assessment, execution_intent=intent)

    states = (market("BTC/USD"),)
    runner, ledger, _agent, _broker = build_runner(
        state=portfolio(cash="200"),
        states=states,
        script=(("BTC/USD", TradingAction.BUY, Decimal("1")),),
        risk_override=WrongCycleRisk(),
    )

    result = asyncio.run(runner.run_cycle())

    assert result.status is TradingCycleStatus.FAILED
    assert result.failure is not None and result.failure.stage is TradingCycleStage.RISK
    assert result.decision_results == ()
    assert balance(ledger.snapshot(as_of=NOW), "USD") == Decimal("200")


def test_buy_then_sell_on_different_markets_in_same_cycle() -> None:
    states = (market("BTC/USD"), market("ETH/USD", "50"))
    runner, ledger, _agent, _broker = build_runner(
        state=portfolio(cash="100", positions=(("ETH", "1"),)),
        states=states,
        script=(
            ("BTC/USD", TradingAction.BUY, Decimal("0.5")),
            ("ETH/USD", TradingAction.SELL, Decimal("1")),
        ),
    )

    result = asyncio.run(runner.run_cycle())

    assert result.status is TradingCycleStatus.COMPLETED
    assert [item.decision.action for item in result.decision_results] == [
        TradingAction.BUY,
        TradingAction.SELL,
    ]
    assert all(item.fills for item in result.decision_results)
    final = ledger.snapshot(as_of=NOW)
    assert balance(final, "USD") == Decimal("100")
    assert held(final, "BTC") == Decimal("0.5")
    assert held(final, "ETH") == Decimal("0")


def test_audit_failure_restores_all_multi_market_fills() -> None:
    class FailingWriter:
        async def ensure_available(self) -> None:
            return None

        async def record(self, result) -> bool:
            raise RuntimeError("audit persistence unavailable")

    states = (market("BTC/USD"), market("ETH/USD"))
    delegate, ledger, _agent, _broker = build_runner(
        state=portfolio(cash="250"),
        states=states,
        script=(
            ("BTC/USD", TradingAction.BUY, Decimal("1")),
            ("ETH/USD", TradingAction.BUY, Decimal("1")),
        ),
    )
    runner = AuditedTradingCycleRunner(
        delegate=delegate,
        audit_writer=FailingWriter(),
        portfolio=ledger,
    )

    try:
        asyncio.run(runner.run_cycle())
    except RuntimeError as exc:
        assert str(exc) == "audit persistence unavailable"
    else:
        raise AssertionError("audit failure must propagate")

    restored = ledger.snapshot(as_of=NOW)
    assert balance(restored, "USD") == Decimal("250")
    assert held(restored, "BTC") == Decimal("0")
    assert held(restored, "ETH") == Decimal("0")
