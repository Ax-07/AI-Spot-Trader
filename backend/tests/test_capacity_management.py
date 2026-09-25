import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel

from ai_spot_trader.agent.provider import OpenAIDecisionProvider
from ai_spot_trader.broker.pricing import PaperExecutionCostModel
from ai_spot_trader.domain.enums import (
    DerivativeContractKind,
    MarketType,
    PositionSide,
    RiskDecision,
    RiskReason,
    TradingAction,
)
from ai_spot_trader.domain.models import (
    AgentInput,
    AssetBalance,
    AssetPosition,
    DecisionCandidate,
    DerivativeInstrument,
    DerivativeMarketContext,
    DerivativePosition,
    ExecutableMarket,
    Fill,
    MarketSelection,
    MarketSelectionInput,
    MarketState,
    PortfolioState,
    RiskAssessment,
    market_selection_digest,
)
from ai_spot_trader.persistence.repository import _selection_input_payload
from ai_spot_trader.risk.capacity import CapacityEvaluator
from ai_spot_trader.risk.engine import RiskEngine, RiskResult
from ai_spot_trader.risk.policy import RiskPolicy
from ai_spot_trader.tools.read_only import (
    ReadOnlyFunctionTool,
    ReadOnlyToolRegistry,
    ToolLoopResult,
)
from ai_spot_trader.trading.engine import (
    TradingCycleFailure,
    TradingCycleResult,
    TradingCycleRunner,
    TradingCycleStage,
    TradingCycleStatus,
    TradingCycleTimeouts,
)

NOW = datetime(2026, 9, 25, 8, 0, tzinfo=UTC)
SPOT_BTC = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT)
SPOT_ETH = ExecutableMarket(symbol="ETH/USD", market_type=MarketType.SPOT)
PERP_BTC = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.PERPETUAL)
PERP_ETH = ExecutableMarket(symbol="ETH/USD", market_type=MarketType.PERPETUAL)


class FixedClock:
    def now(self) -> datetime:
        return NOW


def policy(**overrides: object) -> RiskPolicy:
    values: dict[str, object] = {
        "max_order_notional": Decimal("1000"),
        "allowed_pairs": frozenset({"BTC/USD", "ETH/USD"}),
        "allow_quantity_reduction": True,
        "derivative_leverage": Decimal("1"),
        "max_derivative_leverage": Decimal("3"),
        "max_derivative_position_notional": Decimal("500"),
        "max_total_derivative_exposure": Decimal("1000"),
    }
    values.update(overrides)
    return RiskPolicy(**values)  # type: ignore[arg-type]


def spot_position(
    asset: str = "BTC",
    *,
    quantity: str = "1",
    price: str = "100",
) -> AssetPosition:
    q = Decimal(quantity)
    p = Decimal(price)
    value = q * p
    return AssetPosition(
        asset=asset,
        quantity=q,
        available=q,
        average_entry_price=p,
        remaining_cost_basis=value,
        accounting_complete=True,
        mark_price=p,
        mark_observed_at=NOW,
        mark_source="LAST_PRICE",
        market_value=value,
        unrealized_pnl=Decimal(0),
        valuation_complete=True,
    )


def derivative_position(
    symbol: str = "BTC/USD",
    *,
    side: PositionSide = PositionSide.LONG,
    quantity: str = "2",
    price: str = "100",
    margin: str = "200",
) -> DerivativePosition:
    q = Decimal(quantity)
    p = Decimal(price)
    notional = q * p
    return DerivativePosition(
        symbol=symbol,
        side=side,
        quantity=q,
        average_entry_price=p,
        mark_price=p,
        mark_observed_at=NOW,
        notional=notional,
        unrealized_pnl=Decimal(0),
        leverage=Decimal("1"),
        margin_used=Decimal(margin),
        initial_margin_rate=Decimal("0.10"),
        maintenance_margin_rate=Decimal("0.05"),
        maintenance_margin=notional * Decimal("0.05"),
        cumulative_funding=Decimal(0),
    )


def complete_portfolio(
    *,
    cash: str,
    spots: tuple[AssetPosition, ...] = (),
    derivatives: tuple[DerivativePosition, ...] = (),
) -> PortfolioState:
    cash_value = Decimal(cash)
    spot_value = sum((position.market_value or Decimal(0) for position in spots), Decimal(0))
    spot_cost = sum(
        (position.remaining_cost_basis or Decimal(0) for position in spots),
        Decimal(0),
    )
    derivative_equity = sum(
        (
            position.margin_used
            + position.unrealized_pnl
            + position.cumulative_funding
            for position in derivatives
        ),
        Decimal(0),
    )
    derivative_exposure = sum((position.notional for position in derivatives), Decimal(0))
    equity = cash_value + spot_value + derivative_equity
    exposure = spot_value + derivative_exposure
    return PortfolioState(
        portfolio_state_id=uuid4(),
        as_of=NOW,
        settlement_asset="USD",
        balances=(AssetBalance(asset="USD", available=cash_value),),
        positions=spots,
        derivative_positions=derivatives,
        cash_available=cash_value,
        spot_remaining_cost_basis_total=spot_cost,
        spot_market_value_total=spot_value,
        spot_realized_pnl_total=Decimal(0),
        spot_unrealized_pnl_total=Decimal(0),
        equity=equity,
        exposure_value=exposure,
        exposure_fraction=(exposure / equity if equity > 0 else None),
        valuation_complete=True,
    )


def derivative_market(symbol: str = "BTC/USD", *, price: str = "100") -> MarketState:
    base, quote = symbol.split("/")
    p = Decimal(price)
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
        last_price=p,
        market_type=MarketType.PERPETUAL,
        derivative=DerivativeMarketContext(
            observed_at=NOW,
            instrument=instrument,
            mark_price=p,
        ),
    )


def spot_market(symbol: str = "BTC/USD", *, price: str = "100") -> MarketState:
    return MarketState(
        market_state_id=uuid4(),
        as_of=NOW,
        symbol=symbol,
        last_price=Decimal(price),
    )


def decision(
    action: TradingAction,
    *,
    market_type: MarketType,
    quantity: str | None = None,
    symbol: str = "BTC/USD",
) -> DecisionCandidate:
    return DecisionCandidate(
        decision_id=uuid4(),
        cycle_id=uuid4(),
        created_at=NOW,
        action=action,
        symbol=symbol,
        proposed_quantity=None if quantity is None else Decimal(quantity),
        market_type=market_type,
    )


def risk_engine(p: RiskPolicy | None = None) -> RiskEngine:
    return RiskEngine(
        policy=p or policy(),
        cost_model=PaperExecutionCostModel(
            fee_rate=Decimal("0"),
            spread_bps=Decimal("0"),
            slippage_bps=Decimal("0"),
        ),
        clock=FixedClock(),
    )


def test_capacity_available_stays_normal() -> None:
    assessment = CapacityEvaluator(policy=policy()).evaluate(
        portfolio_state=complete_portfolio(cash="1000"),
        executable_markets=(SPOT_BTC,),
    )
    assert assessment.mode == "NORMAL"
    assert assessment.reason == "OPENING_CAPACITY_AVAILABLE"
    assert assessment.spot_opening_capacity == "POSSIBLE"
    assert assessment.management_markets == ()


def test_derivative_total_exposure_saturation_enters_management() -> None:
    position = derivative_position(quantity="3", margin="300")
    assessment = CapacityEvaluator(
        policy=policy(max_total_derivative_exposure=Decimal("300"))
    ).evaluate(
        portfolio_state=complete_portfolio(cash="100", derivatives=(position,)),
        executable_markets=(PERP_BTC,),
    )
    assert assessment.mode == "MANAGEMENT"
    assert assessment.reason == "DERIVATIVE_TOTAL_EXPOSURE_SATURATED"
    assert assessment.perpetual_opening_capacity == "UNAVAILABLE"
    assert assessment.management_markets == (PERP_BTC,)


def test_derivative_position_cap_can_saturate_single_market() -> None:
    position = derivative_position(quantity="5", margin="500")
    assessment = CapacityEvaluator(
        policy=policy(
            max_derivative_position_notional=Decimal("500"),
            max_total_derivative_exposure=Decimal("1000"),
        )
    ).evaluate(
        portfolio_state=complete_portfolio(cash="100", derivatives=(position,)),
        executable_markets=(PERP_BTC,),
    )
    assert assessment.mode == "MANAGEMENT"
    assert assessment.reason == "DERIVATIVE_POSITION_CAPACITY_SATURATED"


def test_zero_settlement_cash_enters_management_but_keeps_open_spot_market() -> None:
    position = spot_position()
    assessment = CapacityEvaluator(policy=policy()).evaluate(
        portfolio_state=complete_portfolio(cash="0", spots=(position,)),
        executable_markets=(SPOT_BTC, SPOT_ETH),
    )
    assert assessment.mode == "MANAGEMENT"
    assert assessment.reason == "NO_SETTLEMENT_CASH"
    assert assessment.management_markets == (SPOT_BTC,)


def test_incomplete_valuation_is_safe_management_without_invented_capacity() -> None:
    state = PortfolioState(
        portfolio_state_id=uuid4(),
        as_of=NOW,
        settlement_asset="USD",
        balances=(AssetBalance(asset="USD", available=Decimal("1000")),),
        positions=(AssetPosition(asset="BTC", quantity=Decimal("1"), available=Decimal("1")),),
        cash_available=Decimal("1000"),
        valuation_complete=False,
    )
    assessment = CapacityEvaluator(policy=policy()).evaluate(
        portfolio_state=state,
        executable_markets=(SPOT_BTC,),
    )
    assert assessment.mode == "MANAGEMENT"
    assert assessment.reason == "VALUATION_INCOMPLETE"
    assert assessment.spot_opening_capacity == "UNKNOWN"
    assert assessment.management_markets == (SPOT_BTC,)


def test_incomplete_empty_portfolio_fails_closed_with_no_management_market() -> None:
    state = PortfolioState(
        portfolio_state_id=uuid4(),
        as_of=NOW,
        settlement_asset="USD",
        balances=(AssetBalance(asset="USD", available=Decimal("1000")),),
        cash_available=Decimal("1000"),
        valuation_complete=False,
    )
    assessment = CapacityEvaluator(policy=policy()).evaluate(
        portfolio_state=state,
        executable_markets=(SPOT_BTC,),
    )
    assert assessment.mode == "MANAGEMENT"
    assert assessment.management_markets == ()


def test_mixed_portfolio_management_contains_spot_and_perpetual_positions() -> None:
    spot = spot_position()
    perp = derivative_position()
    assessment = CapacityEvaluator(policy=policy()).evaluate(
        portfolio_state=complete_portfolio(cash="0", spots=(spot,), derivatives=(perp,)),
        executable_markets=(PERP_BTC, SPOT_BTC, SPOT_ETH),
    )
    assert assessment.mode == "MANAGEMENT"
    assert assessment.management_markets == (PERP_BTC, SPOT_BTC)


def test_mixed_portfolio_remains_normal_when_spot_capacity_exists() -> None:
    perp = derivative_position(quantity="3", margin="300")
    assessment = CapacityEvaluator(
        policy=policy(max_total_derivative_exposure=Decimal("300"))
    ).evaluate(
        portfolio_state=complete_portfolio(cash="100", derivatives=(perp,)),
        executable_markets=(PERP_BTC, SPOT_BTC),
    )
    assert assessment.mode == "NORMAL"
    assert assessment.spot_opening_capacity == "POSSIBLE"
    assert assessment.perpetual_opening_capacity == "UNAVAILABLE"


def test_capacity_returns_to_normal_after_cash_is_released() -> None:
    evaluator = CapacityEvaluator(policy=policy())
    saturated = evaluator.evaluate(
        portfolio_state=complete_portfolio(cash="0", spots=(spot_position(),)),
        executable_markets=(SPOT_BTC,),
    )
    released = evaluator.evaluate(
        portfolio_state=complete_portfolio(cash="100", spots=(spot_position(),)),
        executable_markets=(SPOT_BTC,),
    )
    assert saturated.mode == "MANAGEMENT"
    assert released.mode == "NORMAL"


def test_capacity_payload_audits_mode_reason_and_search_skip_without_token_estimate() -> None:
    assessment = CapacityEvaluator(policy=policy()).evaluate(
        portfolio_state=complete_portfolio(cash="0", spots=(spot_position(),)),
        executable_markets=(SPOT_BTC,),
    )
    payload = assessment.to_payload()
    assert payload["mode"] == "MANAGEMENT"
    assert payload["reason"] == "NO_SETTLEMENT_CASH"
    assert payload["new_opening_research_skipped"] is True
    assert "tokens" not in payload


def test_audit_payload_records_effective_management_universe_and_reason() -> None:
    portfolio = complete_portfolio(cash="0", spots=(spot_position(),))
    assessment = CapacityEvaluator(policy=policy()).evaluate(
        portfolio_state=portfolio,
        executable_markets=(SPOT_BTC, SPOT_ETH),
    )
    cycle_id = uuid4()
    selection_input = MarketSelectionInput(
        cycle_id=cycle_id,
        created_at=NOW,
        portfolio_state=portfolio,
        executable_markets=(SPOT_BTC, SPOT_ETH),
        aggressiveness=5,
    )
    result = TradingCycleResult(
        cycle_id=cycle_id,
        status=TradingCycleStatus.FAILED,
        failure=TradingCycleFailure(
            stage=TradingCycleStage.MARKET_SELECTION,
            error_type="TestFailure",
        ),
        capacity_assessment=assessment,
        market_selection_input=selection_input,
    )

    payload = _selection_input_payload(result)

    assert payload is not None
    assert payload["executable_markets"] == [
        {"symbol": "BTC/USD", "market_type": "SPOT"}
    ]
    assert payload["capacity_context"]["mode"] == "MANAGEMENT"
    assert payload["capacity_context"]["reason"] == "NO_SETTLEMENT_CASH"


class _ToolArgs(BaseModel):
    pass


async def _tool_handler(_: BaseModel) -> dict[str, str]:
    return {"unexpected": "call"}


class CapturingClient:
    def __init__(self) -> None:
        self.plain_inputs: list[dict[str, object]] = []
        self.tool_calls = 0

    async def generate_structured_decision(self, **kwargs: object) -> str:
        raw = kwargs["input_text"]
        assert isinstance(raw, str)
        payload = json.loads(raw)
        self.plain_inputs.append(payload)
        market = payload["executable_markets"][0]
        return json.dumps(
            {
                "symbol": market["symbol"],
                "market_type": market["market_type"],
                "rationale": "gestion",
            }
        )

    async def generate_structured_decision_with_tools(self, **_: object) -> ToolLoopResult:
        self.tool_calls += 1
        return ToolLoopResult(output_text="{}", traces=())


def test_management_market_selection_disables_research_tools_and_hides_new_markets() -> None:
    client = CapturingClient()
    registry = ReadOnlyToolRegistry(
        (
            ReadOnlyFunctionTool(
                name="dummy",
                description="dummy",
                parameters={"type": "object", "properties": {}, "additionalProperties": False},
                arguments_model=_ToolArgs,
                handler=_tool_handler,
            ),
        ),
        timeout_seconds=1,
        max_result_bytes=128,
        clock=FixedClock(),
    )
    provider = OpenAIDecisionProvider(
        client=client,
        clock=FixedClock(),
        tool_registry=registry,
        max_tool_calls=3,
    )
    selection_input = MarketSelectionInput(
        cycle_id=uuid4(),
        created_at=NOW,
        portfolio_state=complete_portfolio(cash="0", spots=(spot_position(),)),
        executable_markets=(SPOT_BTC, SPOT_ETH),
        aggressiveness=5,
    )

    result = asyncio.run(
        provider.select_management_market(
            selection_input,
            capacity_reason="NO_SETTLEMENT_CASH",
            management_markets=(SPOT_BTC,),
        )
    )

    assert result.symbol == "BTC/USD"
    assert client.tool_calls == 0
    assert len(client.plain_inputs) == 1
    sent = client.plain_inputs[0]
    assert sent["executable_markets"] == [
        {"symbol": "BTC/USD", "market_type": "SPOT"}
    ]
    assert sent["capacity_context"]["mode"] == "MANAGEMENT"
    assert sent["capacity_context"]["new_opening_research_skipped"] is True


def test_spot_hold_and_reductions_remain_possible_in_management() -> None:
    engine = risk_engine()
    portfolio = PortfolioState(
        portfolio_state_id=uuid4(),
        as_of=NOW,
        balances=(AssetBalance(asset="USD", available=Decimal("0")),),
        positions=(AssetPosition(asset="BTC", quantity=Decimal("1"), available=Decimal("1")),),
    )
    hold = engine.evaluate(
        decision=decision(TradingAction.HOLD, market_type=MarketType.SPOT),
        market_state=spot_market(),
        portfolio_state=portfolio,
        management_mode=True,
    )
    partial = engine.evaluate(
        decision=decision(TradingAction.SELL, market_type=MarketType.SPOT, quantity="0.5"),
        market_state=spot_market(),
        portfolio_state=portfolio,
        management_mode=True,
    )
    close = engine.evaluate(
        decision=decision(TradingAction.SELL, market_type=MarketType.SPOT, quantity="1"),
        market_state=spot_market(),
        portfolio_state=portfolio,
        management_mode=True,
    )
    assert hold.assessment.status is RiskDecision.ALLOW
    assert partial.execution_intent is not None
    assert partial.execution_intent.quantity == Decimal("0.5")
    assert close.execution_intent is not None
    assert close.execution_intent.quantity == Decimal("1")


def test_spot_buy_cannot_increase_exposure_in_management() -> None:
    result = risk_engine().evaluate(
        decision=decision(TradingAction.BUY, market_type=MarketType.SPOT, quantity="0.1"),
        market_state=spot_market(),
        portfolio_state=complete_portfolio(cash="100", spots=(spot_position(),)),
        management_mode=True,
    )
    assert result.assessment.status is RiskDecision.REJECT
    assert result.assessment.reasons == (RiskReason.MANAGEMENT_EXPOSURE_INCREASE,)
    assert result.execution_intent is None


def test_perpetual_partial_reduction_and_close_remain_reduce_only_in_management() -> None:
    position = derivative_position(side=PositionSide.LONG, quantity="2", margin="200")
    portfolio = PortfolioState(
        portfolio_state_id=uuid4(),
        as_of=NOW,
        balances=(AssetBalance(asset="USD", available=Decimal("0")),),
        derivative_positions=(position,),
    )
    partial = risk_engine().evaluate(
        decision=decision(TradingAction.SELL, market_type=MarketType.PERPETUAL, quantity="1"),
        market_state=derivative_market(),
        portfolio_state=portfolio,
        management_mode=True,
    )
    close = risk_engine().evaluate(
        decision=decision(TradingAction.SELL, market_type=MarketType.PERPETUAL, quantity="2"),
        market_state=derivative_market(),
        portfolio_state=portfolio,
        management_mode=True,
    )
    assert partial.execution_intent is not None and partial.execution_intent.reduce_only is True
    assert close.execution_intent is not None and close.execution_intent.reduce_only is True


def test_perpetual_same_side_increase_is_rejected_in_management() -> None:
    position = derivative_position(side=PositionSide.LONG)
    result = risk_engine().evaluate(
        decision=decision(TradingAction.BUY, market_type=MarketType.PERPETUAL, quantity="1"),
        market_state=derivative_market(),
        portfolio_state=PortfolioState(
            portfolio_state_id=uuid4(),
            as_of=NOW,
            balances=(AssetBalance(asset="USD", available=Decimal("1000")),),
            derivative_positions=(position,),
        ),
        management_mode=True,
    )
    assert result.assessment.reasons == (RiskReason.MANAGEMENT_EXPOSURE_INCREASE,)
    assert result.execution_intent is None


class ManagementLedger:
    def __init__(self) -> None:
        self.state = complete_portfolio(cash="0", spots=(spot_position(),))

    def snapshot(self, *, as_of: datetime | None = None) -> PortfolioState:
        return self.state if as_of is None else self.state.model_copy(update={"as_of": as_of})


class ExecutionSource:
    async def snapshot(self, symbol: str, market_type: MarketType) -> MarketState:
        assert (symbol, market_type) == ("BTC/USD", MarketType.SPOT)
        return spot_market()


class ManagementAgent:
    def __init__(self) -> None:
        self.normal_selection_calls = 0
        self.management_selection_calls = 0
        self.management_decision_calls = 0
        self.last_tool_traces = ()

    async def select_market(self, _: MarketSelectionInput) -> MarketSelection:
        self.normal_selection_calls += 1
        raise AssertionError("NORMAL market discovery must not run in MANAGEMENT")

    async def select_management_market(
        self,
        value: MarketSelectionInput,
        *,
        capacity_reason: str,
        management_markets: tuple[ExecutableMarket, ...],
    ) -> MarketSelection:
        self.management_selection_calls += 1
        assert capacity_reason == "NO_SETTLEMENT_CASH"
        assert value.portfolio_state.positions[0].asset == "BTC"
        assert management_markets == (SPOT_BTC,)
        selection_id = UUID(int=101)
        return MarketSelection(
            selection_id=selection_id,
            cycle_id=value.cycle_id,
            selected_at=NOW,
            symbol="BTC/USD",
            market_type=MarketType.SPOT,
            tool_traces=(),
            selection_digest=market_selection_digest(
                selection_id=selection_id,
                cycle_id=value.cycle_id,
                selected_at=NOW,
                symbol="BTC/USD",
                market_type=MarketType.SPOT,
                tool_traces=(),
            ),
        )

    async def generate_decision(self, _: AgentInput) -> DecisionCandidate:
        raise AssertionError("normal final decision surface must not run in MANAGEMENT")

    async def generate_management_decision(
        self,
        value: AgentInput,
        *,
        capacity_reason: str,
    ) -> DecisionCandidate:
        self.management_decision_calls += 1
        assert capacity_reason == "NO_SETTLEMENT_CASH"
        return DecisionCandidate(
            decision_id=UUID(int=102),
            cycle_id=value.cycle_id,
            created_at=NOW,
            action=TradingAction.HOLD,
            symbol=value.market_state.symbol,
            proposed_quantity=None,
            market_type=value.market_state.market_type,
            tool_traces=(),
        )


class RecordingRisk:
    def __init__(self) -> None:
        self.management_modes: list[bool] = []

    def evaluate(
        self,
        *,
        decision: DecisionCandidate,
        market_state: MarketState,
        portfolio_state: PortfolioState,
        management_mode: bool = False,
    ) -> RiskResult:
        del market_state, portfolio_state
        self.management_modes.append(management_mode)
        return RiskResult(
            assessment=RiskAssessment(
                risk_assessment_id=UUID(int=103),
                cycle_id=decision.cycle_id,
                decision_id=decision.decision_id,
                assessed_at=NOW,
                status=RiskDecision.ALLOW,
                reasons=(RiskReason.HOLD_NO_EXECUTION,),
            ),
            execution_intent=None,
        )


class NeverBroker:
    async def execute(self, *_: object) -> tuple[Fill, ...]:
        raise AssertionError("HOLD must never reach Broker")


def test_runner_management_keeps_same_agent_on_open_position_and_audits_mode() -> None:
    agent = ManagementAgent()
    risk = RecordingRisk()
    runner = TradingCycleRunner(
        executable_market_data=ExecutionSource(),
        executable_markets=(SPOT_BTC, SPOT_ETH),
        capacity_evaluator=CapacityEvaluator(policy=policy()),
        portfolio=ManagementLedger(),
        agent=agent,
        risk_engine=risk,
        broker=NeverBroker(),
        aggressiveness=5,
        timeouts=TradingCycleTimeouts(1, 1, 1),
        clock=FixedClock(),
        cycle_id_factory=lambda: UUID(int=100),
    )

    result = asyncio.run(runner.run_cycle())

    assert result.status is TradingCycleStatus.COMPLETED
    assert result.capacity_assessment is not None
    assert result.capacity_assessment.mode == "MANAGEMENT"
    assert result.capacity_assessment.reason == "NO_SETTLEMENT_CASH"
    assert result.agent_tool_traces == ()
    assert agent.normal_selection_calls == 0
    assert agent.management_selection_calls == 1
    assert agent.management_decision_calls == 1
    assert risk.management_modes == [True]

class NormalLedger:
    def __init__(self) -> None:
        self.state = complete_portfolio(cash="1000")

    def snapshot(self, *, as_of: datetime | None = None) -> PortfolioState:
        return self.state if as_of is None else self.state.model_copy(update={"as_of": as_of})


class NormalAgent:
    def __init__(self) -> None:
        self.normal_selection_calls = 0
        self.normal_decision_calls = 0
        self.management_selection_calls = 0
        self.management_decision_calls = 0
        self.last_tool_traces = ()

    async def select_market(self, value: MarketSelectionInput) -> MarketSelection:
        self.normal_selection_calls += 1
        selection_id = UUID(int=201)
        return MarketSelection(
            selection_id=selection_id,
            cycle_id=value.cycle_id,
            selected_at=NOW,
            symbol="BTC/USD",
            market_type=MarketType.SPOT,
            tool_traces=(),
            selection_digest=market_selection_digest(
                selection_id=selection_id,
                cycle_id=value.cycle_id,
                selected_at=NOW,
                symbol="BTC/USD",
                market_type=MarketType.SPOT,
                tool_traces=(),
            ),
        )

    async def select_management_market(
        self,
        value: MarketSelectionInput,
        *,
        capacity_reason: str,
        management_markets: tuple[ExecutableMarket, ...],
    ) -> MarketSelection:
        del value, capacity_reason, management_markets
        self.management_selection_calls += 1
        raise AssertionError("MANAGEMENT selection must not run when capacity is available")

    async def generate_decision(self, value: AgentInput) -> DecisionCandidate:
        self.normal_decision_calls += 1
        return DecisionCandidate(
            decision_id=UUID(int=202),
            cycle_id=value.cycle_id,
            created_at=NOW,
            action=TradingAction.HOLD,
            symbol=value.market_state.symbol,
            proposed_quantity=None,
            market_type=value.market_state.market_type,
            tool_traces=(),
        )

    async def generate_management_decision(
        self,
        value: AgentInput,
        *,
        capacity_reason: str,
    ) -> DecisionCandidate:
        del value, capacity_reason
        self.management_decision_calls += 1
        raise AssertionError("MANAGEMENT decision must not run when capacity is available")


def test_runner_normal_mode_preserves_existing_market_selection_path() -> None:
    agent = NormalAgent()
    risk = RecordingRisk()
    runner = TradingCycleRunner(
        executable_market_data=ExecutionSource(),
        executable_markets=(SPOT_BTC, SPOT_ETH),
        capacity_evaluator=CapacityEvaluator(policy=policy()),
        portfolio=NormalLedger(),
        agent=agent,
        risk_engine=risk,
        broker=NeverBroker(),
        aggressiveness=5,
        timeouts=TradingCycleTimeouts(1, 1, 1),
        clock=FixedClock(),
        cycle_id_factory=lambda: UUID(int=200),
    )

    result = asyncio.run(runner.run_cycle())

    assert result.status is TradingCycleStatus.COMPLETED
    assert result.capacity_assessment is not None
    assert result.capacity_assessment.mode == "NORMAL"
    assert agent.normal_selection_calls == 1
    assert agent.normal_decision_calls == 1
    assert agent.management_selection_calls == 0
    assert agent.management_decision_calls == 0
    assert risk.management_modes == [False]
