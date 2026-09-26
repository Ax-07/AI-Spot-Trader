import ast
import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from ai_spot_trader.agent.position_management import build_position_management_context
from ai_spot_trader.agent.provider import OpenAIDecisionProvider
from ai_spot_trader.agent.prompt import PROTECTED_AGENT_CONTRACT
from ai_spot_trader.agent.strategy_client import StrategyInstructionsClient
from ai_spot_trader.broker.pricing import PaperExecutionCostModel
from ai_spot_trader.domain.enums import (
    LLMModel,
    MarketType,
    RiskDecision,
    RiskReason,
    TradingAction,
    TradingStyle,
)
from ai_spot_trader.domain.experiments import aggressiveness_context, trading_style_context
from ai_spot_trader.domain.models import (
    AssetBalance,
    AssetPosition,
    DecisionCandidate,
    ExecutionCostContext,
    ExecutableMarket,
    MarketSelectionInput,
    MarketState,
    PortfolioState,
)
from ai_spot_trader.risk.capacity import CapacityEvaluator, open_position_markets
from ai_spot_trader.risk.engine import RiskEngine
from ai_spot_trader.risk.policy import RiskPolicy

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
BTC = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT)
ETH = ExecutableMarket(symbol="ETH/USD", market_type=MarketType.SPOT)


class FixedClock:
    def now(self) -> datetime:
        return NOW


class CapturingClient:
    def __init__(self) -> None:
        self.instructions: str | None = None
        self.input_payload: dict[str, object] | None = None

    async def generate_structured_decision(
        self,
        *,
        model: LLMModel,
        instructions: str,
        input_text: str,
        schema: dict[str, Any],
    ) -> str:
        del model, schema
        self.instructions = instructions
        self.input_payload = json.loads(input_text)
        return json.dumps(
            {
                "symbol": "BTC/USD",
                "market_type": "SPOT",
                "rationale": "La position ouverte reste l'opportunité stratégique choisie.",
            }
        )


def costs() -> ExecutionCostContext:
    return ExecutionCostContext(
        fee_rate=Decimal("0.001"),
        spread_bps=Decimal("2"),
        slippage_bps=Decimal("3"),
    )


def profitable_portfolio(*, available: str = "10", cash: str = "500") -> PortfolioState:
    quantity = Decimal("10")
    mark = Decimal("120")
    remaining_cost_basis = Decimal("1001")
    market_value = mark * quantity
    unrealized = market_value - remaining_cost_basis
    cash_value = Decimal(cash)
    return PortfolioState(
        portfolio_state_id=uuid4(),
        as_of=NOW,
        settlement_asset="USD",
        balances=(AssetBalance(asset="USD", available=cash_value),),
        positions=(
            AssetPosition(
                asset="BTC",
                quantity=quantity,
                available=Decimal(available),
                average_entry_price=remaining_cost_basis / quantity,
                remaining_cost_basis=remaining_cost_basis,
                accounting_complete=True,
                mark_price=mark,
                mark_observed_at=NOW,
                mark_source="LAST_PRICE",
                market_value=market_value,
                unrealized_pnl=unrealized,
                valuation_complete=True,
            ),
        ),
        cash_available=cash_value,
        spot_remaining_cost_basis_total=remaining_cost_basis,
        spot_market_value_total=market_value,
        spot_realized_pnl_total=Decimal(0),
        spot_unrealized_pnl_total=unrealized,
        equity=cash_value + market_value,
        exposure_value=market_value,
        exposure_fraction=market_value / (cash_value + market_value),
        valuation_complete=True,
    )


def test_normal_capacity_keeps_open_position_as_management_opportunity() -> None:
    portfolio = profitable_portfolio()
    assessment = CapacityEvaluator(policy=RiskPolicy()).evaluate(
        portfolio_state=portfolio,
        executable_markets=(BTC, ETH),
    )

    assert assessment.mode == "NORMAL"
    assert assessment.spot_opening_capacity == "POSSIBLE"
    assert assessment.management_markets == (BTC,)
    assert assessment.new_opening_research_skipped is False


def test_open_position_market_mapping_is_shared_and_independent_of_watchlist() -> None:
    assert open_position_markets(profitable_portfolio()) == (BTC,)


def test_agent_position_management_facade_keeps_forbidden_dependencies_out() -> None:
    source = (
        Path(__file__).parents[1]
        / "src"
        / "ai_spot_trader"
        / "agent"
        / "position_management.py"
    )
    tree = ast.parse(source.read_text(encoding="utf-8"))
    forbidden = ("ai_spot_trader.risk", "ai_spot_trader.broker")
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.append(node.module)
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
    assert not any(name.startswith(forbidden) for name in imported)


def test_legacy_campaign_prompt_does_not_gain_position_management_context() -> None:
    client = StrategyInstructionsClient(
        object(),
        strategy_prompt="Arbitre rationnellement le capital expose.",
    )
    selection_input = MarketSelectionInput(
        cycle_id=uuid4(),
        created_at=NOW,
        portfolio_state=profitable_portfolio(),
        executable_markets=(BTC,),
        aggressiveness=5,
        aggressiveness_context=aggressiveness_context(5),
    )

    instructions = client.effective_instructions(selection_input.model_dump_json())

    assert "position-management-v1" not in instructions


def test_exit_context_uses_canonical_paper_costs_without_double_counting_entry_costs() -> None:
    context = build_position_management_context(
        portfolio_state=profitable_portfolio(),
        executable_markets=(BTC, ETH),
        execution_cost_context=costs(),
    )

    assert context["management_markets"] == [
        {"symbol": "BTC/USD", "market_type": "SPOT"}
    ]
    position = context["spot_positions"][0]
    estimate = position["available_exit_estimate"]
    assert position["remaining_cost_basis"] == "1001"
    assert position["gross_unrealized_pnl"] == "199"
    assert estimate["estimated_exit_spread_cost"] == "0.240"
    assert estimate["estimated_exit_slippage_cost"] == "0.360"
    assert estimate["estimated_exit_fee"] == "1.199400"
    assert estimate["estimated_net_exit_proceeds"] == "1198.200600"
    assert estimate["estimated_released_cost_basis"] == "1001"
    assert estimate["estimated_net_pnl_if_available_sold_now"] == "197.200600"
    assert estimate["estimated_net_pnl_if_closed_now"] == "197.200600"
    assert "should_sell" not in json.dumps(context)


def test_partial_exit_context_exposes_available_quantity_without_forcing_full_close() -> None:
    context = build_position_management_context(
        portfolio_state=profitable_portfolio(available="4"),
        executable_markets=(BTC,),
        execution_cost_context=costs(),
    )
    position = context["spot_positions"][0]

    assert position["quantity"] == "10"
    assert position["available_quantity"] == "4"
    assert position["can_reduce_now"] is True
    assert position["can_fully_close_now"] is False
    assert position["available_exit_estimate"]["estimated_released_cost_basis"] == "400.4"
    assert position["available_exit_estimate"]["estimated_net_pnl_if_closed_now"] is None


def test_same_agent_can_select_open_position_in_normal_mode_with_cash_available() -> None:
    async def scenario() -> None:
        delegate = CapturingClient()
        strategic_client = StrategyInstructionsClient(
            delegate,
            strategy_prompt="Arbitre rationnellement le capital expose.",
        )
        provider = OpenAIDecisionProvider(
            client=strategic_client,
            clock=FixedClock(),
        )
        selection_input = MarketSelectionInput(
            cycle_id=uuid4(),
            created_at=NOW,
            portfolio_state=profitable_portfolio(),
            executable_markets=(BTC, ETH),
            aggressiveness=5,
            aggressiveness_context=aggressiveness_context(5),
            trading_style_context=trading_style_context(TradingStyle.SCALP),
            execution_cost_context=costs(),
        )

        selection = await provider.select_market(selection_input)

        assert selection.symbol == "BTC/USD"
        assert selection.market_type is MarketType.SPOT
        assert delegate.instructions is not None
        assert "position-management-v1" in delegate.instructions
        assert "estimated_net_pnl_if_available_sold_now" in delegate.instructions
        assert "SCALP" in delegate.instructions
        assert "signal automatique de vente" in delegate.instructions

    asyncio.run(scenario())


def test_protected_contract_requires_management_without_deterministic_profit_rule() -> None:
    assert "Une position déjà ouverte reste une opportunité stratégique" in PROTECTED_AGENT_CONTRACT
    assert "Une position bénéficiaire n'impose pas `SELL`" in PROTECTED_AGENT_CONTRACT
    assert "timer" in PROTECTED_AGENT_CONTRACT


def test_spot_max_order_notional_remains_a_per_order_cap_for_reducing_sell() -> None:
    portfolio = PortfolioState(
        portfolio_state_id=uuid4(),
        as_of=NOW,
        balances=(AssetBalance(asset="USD", available=Decimal("0")),),
        positions=(
            AssetPosition(
                asset="BTC",
                quantity=Decimal("2.5"),
                available=Decimal("2.5"),
            ),
        ),
    )
    decision = DecisionCandidate(
        decision_id=uuid4(),
        cycle_id=uuid4(),
        created_at=NOW,
        action=TradingAction.SELL,
        symbol="BTC/USD",
        proposed_quantity=Decimal("2.5"),
    )
    market = MarketState(
        market_state_id=uuid4(),
        as_of=NOW,
        symbol="BTC/USD",
        last_price=Decimal("100"),
    )
    engine = RiskEngine(
        policy=RiskPolicy(
            max_order_notional=Decimal("100"),
            allow_quantity_reduction=True,
        ),
        cost_model=PaperExecutionCostModel(
            fee_rate=Decimal(0),
            spread_bps=Decimal(0),
            slippage_bps=Decimal(0),
        ),
        clock=FixedClock(),
    )

    result = engine.evaluate(
        decision=decision,
        market_state=market,
        portfolio_state=portfolio,
    )

    assert result.assessment.status is RiskDecision.MODIFY
    assert result.assessment.authorized_quantity == Decimal("1")
    assert result.assessment.reasons == (RiskReason.MAX_ORDER_NOTIONAL_LIMIT,)
    assert result.execution_intent is not None
    assert result.execution_intent.action is TradingAction.SELL
    assert result.execution_intent.quantity == Decimal("1")
