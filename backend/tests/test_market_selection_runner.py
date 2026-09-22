import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from ai_spot_trader.domain.enums import (
    DerivativeContractKind,
    MarketType,
    RiskDecision,
    RiskReason,
    TradingAction,
)
from ai_spot_trader.domain.models import (
    AssetBalance,
    DecisionCandidate,
    DerivativeInstrument,
    DerivativeMarketContext,
    ExecutableMarket,
    ExecutionIntent,
    Fill,
    MarketSelection,
    MarketSelectionInput,
    MarketState,
    PortfolioState,
    RiskAssessment,
    market_selection_digest,
)
from ai_spot_trader.risk.engine import RiskResult
from ai_spot_trader.trading.engine import (
    TradingCycleRunner,
    TradingCycleStage,
    TradingCycleStatus,
    TradingCycleTimeouts,
)

NOW = datetime(2026, 9, 22, 14, 0, tzinfo=UTC)
CYCLE = UUID("10000000-0000-0000-0000-000000000001")
SELECTION = UUID("20000000-0000-0000-0000-000000000002")
DECISION = UUID("30000000-0000-0000-0000-000000000003")
RISK = UUID("40000000-0000-0000-0000-000000000004")
EXECUTION = UUID("50000000-0000-0000-0000-000000000005")
FILL = UUID("60000000-0000-0000-0000-000000000006")
PORTFOLIO = UUID("70000000-0000-0000-0000-000000000007")


class FixedClock:
    def now(self) -> datetime:
        return NOW


class Ledger:
    def __init__(self) -> None:
        self.state = PortfolioState(
            portfolio_state_id=PORTFOLIO,
            as_of=NOW - timedelta(seconds=2),
            balances=(AssetBalance(asset="USD", available=Decimal("1000")),),
        )
        self.calls = 0

    def snapshot(self, *, as_of: datetime | None = None) -> PortfolioState:
        self.calls += 1
        return self.state if as_of is None else self.state.model_copy(update={"as_of": as_of})


class ExecutionMarkets:
    def __init__(
        self,
        states: dict[tuple[str, MarketType], MarketState],
        error: Exception | None = None,
    ) -> None:
        self.states = states
        self.error = error
        self.calls: list[tuple[str, MarketType]] = []

    async def snapshot(self, symbol: str, market_type: MarketType) -> MarketState:
        self.calls.append((symbol, market_type))
        if self.error is not None:
            raise self.error
        return self.states[(symbol, market_type)]


class Agent:
    def __init__(
        self,
        *,
        selected: ExecutableMarket,
        action: TradingAction = TradingAction.HOLD,
        wrong_final_symbol: str | None = None,
    ) -> None:
        self.selected = selected
        self.action = action
        self.wrong_final_symbol = wrong_final_symbol
        self.selection_inputs: list[MarketSelectionInput] = []
        self.agent_inputs = []
        self.last_tool_traces = ()

    async def select_market(self, value: MarketSelectionInput) -> MarketSelection:
        self.selection_inputs.append(value)
        return MarketSelection(
            selection_id=SELECTION,
            cycle_id=value.cycle_id,
            selected_at=NOW,
            symbol=self.selected.symbol,
            market_type=self.selected.market_type,
            selection_digest=market_selection_digest(
                selection_id=SELECTION,
                cycle_id=value.cycle_id,
                selected_at=NOW,
                symbol=self.selected.symbol,
                market_type=self.selected.market_type,
                tool_traces=(),
            ),
        )

    async def generate_decision(self, value):
        self.agent_inputs.append(value)
        return DecisionCandidate(
            decision_id=DECISION,
            cycle_id=value.cycle_id,
            created_at=NOW,
            action=self.action,
            symbol=self.wrong_final_symbol or value.market_state.symbol,
            proposed_quantity=None if self.action is TradingAction.HOLD else Decimal("1"),
            rationale="test",
            market_type=value.market_state.market_type,
            tool_traces=value.market_selection.tool_traces if value.market_selection else (),
        )


class Risk:
    def __init__(self) -> None:
        self.calls = []

    def evaluate(self, *, decision, market_state, portfolio_state) -> RiskResult:
        self.calls.append((decision, market_state, portfolio_state))
        if decision.action is TradingAction.HOLD:
            assessment = RiskAssessment(
                risk_assessment_id=RISK,
                cycle_id=decision.cycle_id,
                decision_id=decision.decision_id,
                assessed_at=NOW,
                status=RiskDecision.ALLOW,
                reasons=(RiskReason.HOLD_NO_EXECUTION,),
            )
            return RiskResult(assessment=assessment, execution_intent=None)
        assessment = RiskAssessment(
            risk_assessment_id=RISK,
            cycle_id=decision.cycle_id,
            decision_id=decision.decision_id,
            assessed_at=NOW,
            status=RiskDecision.ALLOW,
            requested_quantity=Decimal("1"),
            authorized_quantity=Decimal("1"),
        )
        intent = ExecutionIntent(
            execution_id=EXECUTION,
            cycle_id=decision.cycle_id,
            decision_id=decision.decision_id,
            risk_assessment_id=RISK,
            created_at=NOW,
            action=decision.action,
            symbol=decision.symbol,
            quantity=Decimal("1"),
            market_type=decision.market_type,
            leverage=Decimal("1") if decision.market_type is MarketType.PERPETUAL else None,
        )
        return RiskResult(assessment=assessment, execution_intent=intent)


class Broker:
    def __init__(self) -> None:
        self.calls = []

    async def execute(self, intent: ExecutionIntent, market_state: MarketState) -> tuple[Fill, ...]:
        self.calls.append((intent, market_state))
        return (
            Fill(
                fill_id=FILL,
                execution_id=intent.execution_id,
                market_state_id=market_state.market_state_id,
                filled_at=NOW,
                pricing_as_of=market_state.as_of,
                action=intent.action,
                symbol=intent.symbol,
                quantity=intent.quantity,
                reference_price=market_state.last_price,
                price=market_state.last_price,
                notional=market_state.last_price * intent.quantity,
                fee=Decimal("0"),
                spread_cost=Decimal("0"),
                slippage_cost=Decimal("0"),
                market_type=intent.market_type,
            ),
        )


def spot(symbol: str, price: str, ident: int) -> MarketState:
    return MarketState(
        market_state_id=UUID(int=ident),
        as_of=NOW - timedelta(seconds=1),
        symbol=symbol,
        last_price=Decimal(price),
    )


def perp(symbol: str, price: str, ident: int) -> MarketState:
    base, quote = symbol.split("/")
    instrument = DerivativeInstrument(
        symbol=symbol,
        venue_symbol=f"PF_{base}{quote}",
        market_type=MarketType.PERPETUAL,
        contract_kind=DerivativeContractKind.LINEAR,
        underlying_asset=base,
        quote_asset=quote,
        contract_size=Decimal("1"),
        tick_size=Decimal("0.1"),
        min_order_quantity=Decimal("0.001"),
        initial_margin_rate=Decimal("0.1"),
        maintenance_margin_rate=Decimal("0.05"),
        max_leverage=Decimal("10"),
        funding_interval_seconds=Decimal("3600"),
    )
    return MarketState(
        market_state_id=UUID(int=ident),
        as_of=NOW - timedelta(seconds=1),
        symbol=symbol,
        last_price=Decimal(price),
        market_type=MarketType.PERPETUAL,
        derivative=DerivativeMarketContext(
            observed_at=NOW - timedelta(seconds=1),
            instrument=instrument,
            mark_price=Decimal(price),
        ),
    )


def make_runner(
    selected: ExecutableMarket,
    state: MarketState,
    *,
    action: TradingAction = TradingAction.HOLD,
    market_error: Exception | None = None,
    wrong_final_symbol: str | None = None,
):
    universe = (
        ExecutableMarket(symbol="ETH/USD", market_type=MarketType.PERPETUAL),
        ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),
        ExecutableMarket(symbol="ETH/USD", market_type=MarketType.SPOT),
    )
    agent = Agent(selected=selected, action=action, wrong_final_symbol=wrong_final_symbol)
    markets = ExecutionMarkets({(selected.symbol, selected.market_type): state}, error=market_error)
    risk, broker, ledger = Risk(), Broker(), Ledger()
    runner = TradingCycleRunner(
        executable_market_data=markets,
        executable_markets=universe,
        portfolio=ledger,
        agent=agent,
        risk_engine=risk,
        broker=broker,
        aggressiveness=5,
        timeouts=TradingCycleTimeouts(1, 1, 1),
        clock=FixedClock(),
        cycle_id_factory=lambda: CYCLE,
    )
    return runner, markets, agent, risk, broker, ledger


def test_agent_can_switch_from_bootstrap_like_btc_context_to_eth_spot_and_hold() -> None:
    selected = ExecutableMarket(symbol="ETH/USD", market_type=MarketType.SPOT)
    runner, markets, agent, risk, broker, ledger = make_runner(
        selected,
        spot("ETH/USD", "2000", 10),
    )
    result = asyncio.run(runner.run_cycle())
    assert result.status is TradingCycleStatus.COMPLETED
    assert result.market_selection is not None and result.market_selection.symbol == "ETH/USD"
    assert result.agent_input is not None and result.agent_input.market_state.symbol == "ETH/USD"
    assert risk.calls[0][1] is result.agent_input.market_state
    assert broker.calls == []
    assert ledger.calls >= 2
    assert markets.calls == [("ETH/USD", MarketType.SPOT)]


def test_perpetual_selection_uses_exact_snapshot_for_risk_broker_fill() -> None:
    selected = ExecutableMarket(symbol="ETH/USD", market_type=MarketType.PERPETUAL)
    state = perp("ETH/USD", "2000", 11)
    runner, _, _, risk, broker, _ = make_runner(selected, state, action=TradingAction.BUY)
    result = asyncio.run(runner.run_cycle())
    assert result.status is TradingCycleStatus.COMPLETED
    assert risk.calls[0][1] is state
    assert broker.calls[0][1] is state
    assert result.fills[0].market_state_id == state.market_state_id
    assert result.decision is not None and result.decision.market_type is MarketType.PERPETUAL


def test_snapshot_failure_after_selection_is_technical_failure_with_selection_preserved() -> None:
    selected = ExecutableMarket(symbol="ETH/USD", market_type=MarketType.SPOT)
    runner, _, _, risk, broker, _ = make_runner(
        selected,
        spot("ETH/USD", "2000", 12),
        market_error=RuntimeError("network"),
    )
    result = asyncio.run(runner.run_cycle())
    assert result.status is TradingCycleStatus.FAILED
    assert result.failure is not None and result.failure.stage is TradingCycleStage.MARKET
    assert result.market_selection is not None and result.market_selection.symbol == "ETH/USD"
    assert result.agent_input is None and result.decision is None
    assert risk.calls == [] and broker.calls == []


def test_final_decision_cannot_switch_symbol_after_executable_snapshot() -> None:
    selected = ExecutableMarket(symbol="ETH/USD", market_type=MarketType.SPOT)
    runner, _, _, risk, broker, _ = make_runner(
        selected,
        spot("ETH/USD", "2000", 13),
        wrong_final_symbol="BTC/USD",
    )
    result = asyncio.run(runner.run_cycle())
    assert result.status is TradingCycleStatus.FAILED
    assert result.failure is not None and result.failure.stage is TradingCycleStage.AGENT
    assert risk.calls == [] and broker.calls == []


def test_selection_outside_runner_universe_fails_before_market_and_risk() -> None:
    selected = ExecutableMarket(symbol="SOL/USD", market_type=MarketType.SPOT)
    runner, markets, _, risk, broker, _ = make_runner(
        selected,
        spot("SOL/USD", "150", 14),
    )
    result = asyncio.run(runner.run_cycle())
    assert result.status is TradingCycleStatus.FAILED
    assert result.failure is not None
    assert result.failure.stage is TradingCycleStage.MARKET_SELECTION
    assert markets.calls == []
    assert risk.calls == [] and broker.calls == []


def test_selected_source_mismatch_fails_before_final_agent_and_risk() -> None:
    selected = ExecutableMarket(symbol="ETH/USD", market_type=MarketType.SPOT)
    wrong_state = spot("BTC/USD", "60000", 15)
    runner, markets, agent, risk, broker, _ = make_runner(selected, wrong_state)
    result = asyncio.run(runner.run_cycle())
    assert result.status is TradingCycleStatus.FAILED
    assert result.failure is not None and result.failure.stage is TradingCycleStage.MARKET
    assert markets.calls == [("ETH/USD", MarketType.SPOT)]
    assert agent.agent_inputs == []
    assert risk.calls == [] and broker.calls == []


def test_spot_selection_keeps_complete_portfolio_identical_across_selection_and_decision() -> None:
    selected = ExecutableMarket(symbol="ETH/USD", market_type=MarketType.SPOT)
    runner, _, agent, _, _, _ = make_runner(selected, spot("ETH/USD", "2000", 16))
    result = asyncio.run(runner.run_cycle())
    assert result.status is TradingCycleStatus.COMPLETED
    assert agent.selection_inputs[0].portfolio_state == agent.agent_inputs[0].portfolio_state
    assert agent.agent_inputs[0].portfolio_state.balances == (
        AssetBalance(asset="USD", available=Decimal("1000")),
    )


def test_final_decision_market_type_mismatch_fails_before_risk() -> None:
    class WrongMarketTypeAgent(Agent):
        async def generate_decision(self, value):
            self.agent_inputs.append(value)
            return DecisionCandidate(
                decision_id=DECISION,
                cycle_id=value.cycle_id,
                created_at=NOW,
                action=TradingAction.HOLD,
                symbol=value.market_state.symbol,
                rationale="test",
                market_type=MarketType.PERPETUAL,
                tool_traces=value.market_selection.tool_traces,
            )

    selected = ExecutableMarket(symbol="ETH/USD", market_type=MarketType.SPOT)
    universe = (
        ExecutableMarket(symbol="ETH/USD", market_type=MarketType.PERPETUAL),
        ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),
        selected,
    )
    agent = WrongMarketTypeAgent(selected=selected)
    markets = ExecutionMarkets({("ETH/USD", MarketType.SPOT): spot("ETH/USD", "2000", 17)})
    risk, broker, ledger = Risk(), Broker(), Ledger()
    runner = TradingCycleRunner(
        executable_market_data=markets,
        executable_markets=universe,
        portfolio=ledger,
        agent=agent,
        risk_engine=risk,
        broker=broker,
        aggressiveness=5,
        timeouts=TradingCycleTimeouts(1, 1, 1),
        clock=FixedClock(),
        cycle_id_factory=lambda: CYCLE,
    )
    result = asyncio.run(runner.run_cycle())
    assert result.status is TradingCycleStatus.FAILED
    assert result.failure is not None and result.failure.stage is TradingCycleStage.AGENT
    assert risk.calls == [] and broker.calls == []


def test_partial_selection_research_traces_survive_selection_failure() -> None:
    from ai_spot_trader.domain.models import AgentToolTrace, canonical_json_digest

    trace_result = {"ok": True, "markets": []}
    trace = AgentToolTrace(
        call_id="call-1",
        tool_name="list_markets",
        arguments={},
        started_at=NOW - timedelta(seconds=2),
        completed_at=NOW - timedelta(seconds=1),
        status="SUCCESS",
        result=trace_result,
        result_digest=canonical_json_digest(trace_result),
    )

    class PartialFailAgent:
        last_tool_traces = (trace,)

        async def select_market(self, value):
            raise RuntimeError("selection failed")

        async def generate_decision(self, value):
            raise AssertionError("final decision must not run")

    universe = (ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),)
    markets = ExecutionMarkets({("BTC/USD", MarketType.SPOT): spot("BTC/USD", "60000", 18)})
    risk, broker, ledger = Risk(), Broker(), Ledger()
    runner = TradingCycleRunner(
        executable_market_data=markets,
        executable_markets=universe,
        portfolio=ledger,
        agent=PartialFailAgent(),
        risk_engine=risk,
        broker=broker,
        aggressiveness=5,
        timeouts=TradingCycleTimeouts(1, 1, 1),
        clock=FixedClock(),
        cycle_id_factory=lambda: CYCLE,
    )
    result = asyncio.run(runner.run_cycle())
    assert result.status is TradingCycleStatus.FAILED
    assert result.failure is not None
    assert result.failure.stage is TradingCycleStage.MARKET_SELECTION
    assert result.market_selection_input is not None
    assert result.market_selection is None
    assert result.agent_tool_traces == (trace,)
    assert markets.calls == [] and risk.calls == [] and broker.calls == []


def test_market_selection_cannot_postdate_final_agent_input() -> None:
    class FutureSelectionAgent(Agent):
        async def select_market(self, value: MarketSelectionInput) -> MarketSelection:
            selected_at = NOW + timedelta(seconds=5)
            return MarketSelection(
                selection_id=SELECTION,
                cycle_id=value.cycle_id,
                selected_at=selected_at,
                symbol=self.selected.symbol,
                market_type=self.selected.market_type,
                selection_digest=market_selection_digest(
                    selection_id=SELECTION,
                    cycle_id=value.cycle_id,
                    selected_at=selected_at,
                    symbol=self.selected.symbol,
                    market_type=self.selected.market_type,
                    tool_traces=(),
                ),
            )

    selected = ExecutableMarket(symbol="ETH/USD", market_type=MarketType.SPOT)
    universe = (
        ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),
        selected,
    )
    agent = FutureSelectionAgent(selected=selected)
    markets = ExecutionMarkets({("ETH/USD", MarketType.SPOT): spot("ETH/USD", "2000", 19)})
    risk, broker, ledger = Risk(), Broker(), Ledger()
    runner = TradingCycleRunner(
        executable_market_data=markets,
        executable_markets=universe,
        portfolio=ledger,
        agent=agent,
        risk_engine=risk,
        broker=broker,
        aggressiveness=5,
        timeouts=TradingCycleTimeouts(1, 1, 1),
        clock=FixedClock(),
        cycle_id_factory=lambda: CYCLE,
    )
    result = asyncio.run(runner.run_cycle())
    assert result.status is TradingCycleStatus.FAILED
    assert result.failure is not None and result.failure.stage is TradingCycleStage.INPUT
    assert risk.calls == [] and broker.calls == []


def test_legacy_single_market_runner_remains_compatible() -> None:
    class LegacyMarket:
        async def snapshot(self, symbol: str) -> MarketState:
            assert symbol == "BTC/USD"
            return spot("BTC/USD", "60000", 20)

    class LegacyAgent:
        last_tool_traces = ()

        async def generate_decision(self, value):
            return DecisionCandidate(
                decision_id=DECISION,
                cycle_id=value.cycle_id,
                created_at=NOW,
                action=TradingAction.HOLD,
                symbol=value.market_state.symbol,
                market_type=value.market_state.market_type,
                rationale="compatibilité",
            )

    risk, broker, ledger = Risk(), Broker(), Ledger()
    runner = TradingCycleRunner(
        market_data=LegacyMarket(),
        symbol="BTC/USD",
        portfolio=ledger,
        agent=LegacyAgent(),
        risk_engine=risk,
        broker=broker,
        aggressiveness=5,
        timeouts=TradingCycleTimeouts(1, 1, 1),
        clock=FixedClock(),
        cycle_id_factory=lambda: CYCLE,
    )
    result = asyncio.run(runner.run_cycle())
    assert result.status is TradingCycleStatus.COMPLETED
    assert result.market_selection is None
    assert result.decision is not None and result.decision.symbol == "BTC/USD"
    assert result.risk_assessment is not None
    assert broker.calls == []


def test_same_selection_runner_can_switch_spot_to_perpetual_and_back() -> None:
    universe = (
        ExecutableMarket(symbol="ETH/USD", market_type=MarketType.PERPETUAL),
        ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),
    )
    agent = Agent(selected=universe[1], action=TradingAction.HOLD)
    markets = ExecutionMarkets(
        {
            ("BTC/USD", MarketType.SPOT): spot("BTC/USD", "60000", 21),
            ("ETH/USD", MarketType.PERPETUAL): perp("ETH/USD", "2000", 22),
        }
    )
    risk, broker, ledger = Risk(), Broker(), Ledger()
    runner = TradingCycleRunner(
        executable_market_data=markets,
        executable_markets=universe,
        portfolio=ledger,
        agent=agent,
        risk_engine=risk,
        broker=broker,
        aggressiveness=5,
        timeouts=TradingCycleTimeouts(1, 1, 1),
        clock=FixedClock(),
        cycle_id_factory=lambda: CYCLE,
    )

    first = asyncio.run(runner.run_cycle())
    agent.selected = universe[0]
    second = asyncio.run(runner.run_cycle())
    agent.selected = universe[1]
    third = asyncio.run(runner.run_cycle())

    assert first.status is TradingCycleStatus.COMPLETED
    assert second.status is TradingCycleStatus.COMPLETED
    assert third.status is TradingCycleStatus.COMPLETED
    assert first.market_selection is not None
    assert second.market_selection is not None
    assert third.market_selection is not None
    assert first.market_selection.market_type is MarketType.SPOT
    assert second.market_selection.market_type is MarketType.PERPETUAL
    assert third.market_selection.market_type is MarketType.SPOT
    assert markets.calls == [
        ("BTC/USD", MarketType.SPOT),
        ("ETH/USD", MarketType.PERPETUAL),
        ("BTC/USD", MarketType.SPOT),
    ]
    assert broker.calls == []


def test_cross_symbol_research_traces_flow_selection_to_final_decision() -> None:
    from ai_spot_trader.domain.models import AgentToolTrace, canonical_json_digest

    btc_result = {
        "ok": True,
        "snapshot": {"symbol": "BTC/USD", "market_type": "SPOT", "last_price": "60000"},
    }
    eth_result = {
        "ok": True,
        "snapshot": {"symbol": "ETH/USD", "market_type": "SPOT", "last_price": "2000"},
    }
    traces = (
        AgentToolTrace(
            call_id="btc-research",
            tool_name="get_market_snapshot",
            arguments={"symbol": "BTC/USD", "market_type": "SPOT"},
            started_at=NOW - timedelta(seconds=4),
            completed_at=NOW - timedelta(seconds=3),
            status="SUCCESS",
            result=btc_result,
            result_digest=canonical_json_digest(btc_result),
        ),
        AgentToolTrace(
            call_id="eth-research",
            tool_name="get_market_snapshot",
            arguments={"symbol": "ETH/USD", "market_type": "SPOT"},
            started_at=NOW - timedelta(seconds=2),
            completed_at=NOW - timedelta(seconds=1),
            status="SUCCESS",
            result=eth_result,
            result_digest=canonical_json_digest(eth_result),
        ),
    )

    class ResearchAgent(Agent):
        last_tool_traces = traces

        async def select_market(self, value: MarketSelectionInput) -> MarketSelection:
            self.selection_inputs.append(value)
            return MarketSelection(
                selection_id=SELECTION,
                cycle_id=value.cycle_id,
                selected_at=NOW,
                symbol="ETH/USD",
                market_type=MarketType.SPOT,
                rationale="ETH retenu après comparaison BTC/ETH",
                tool_traces=traces,
                selection_digest=market_selection_digest(
                    selection_id=SELECTION,
                    cycle_id=value.cycle_id,
                    selected_at=NOW,
                    symbol="ETH/USD",
                    market_type=MarketType.SPOT,
                    tool_traces=traces,
                    rationale="ETH retenu après comparaison BTC/ETH",
                ),
            )

    universe = (
        ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),
        ExecutableMarket(symbol="ETH/USD", market_type=MarketType.SPOT),
    )
    agent = ResearchAgent(selected=universe[1], action=TradingAction.HOLD)
    markets = ExecutionMarkets({("ETH/USD", MarketType.SPOT): spot("ETH/USD", "2000", 23)})
    risk, broker, ledger = Risk(), Broker(), Ledger()
    runner = TradingCycleRunner(
        executable_market_data=markets,
        executable_markets=universe,
        portfolio=ledger,
        agent=agent,
        risk_engine=risk,
        broker=broker,
        aggressiveness=5,
        timeouts=TradingCycleTimeouts(1, 1, 1),
        clock=FixedClock(),
        cycle_id_factory=lambda: CYCLE,
    )

    result = asyncio.run(runner.run_cycle())
    assert result.status is TradingCycleStatus.COMPLETED
    assert result.market_selection is not None
    assert result.market_selection.symbol == "ETH/USD"
    assert result.market_selection.tool_traces == traces
    assert result.agent_input is not None
    assert result.agent_input.market_selection is result.market_selection
    assert result.decision is not None
    assert result.decision.tool_traces == traces
    assert result.agent_tool_traces == traces
    assert broker.calls == []
