import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest

from ai_spot_trader.agent.planner import OpenAIMultiMarketDecisionProvider
from ai_spot_trader.broker.paper import PaperBroker
from ai_spot_trader.broker.pricing import PaperExecutionCostModel
from ai_spot_trader.chat.prompt import (
    OPERATOR_CHAT_PROMPT_VERSION,
    OPERATOR_CHAT_SYSTEM_PROMPT,
)
from ai_spot_trader.domain.enums import (
    DerivativeContractKind,
    ExecutionMode,
    LLMModel,
    MarketType,
    PositionSide,
    RiskDecision,
    RiskReason,
    TradingAction,
)
from ai_spot_trader.domain.models import (
    AssetBalance,
    DerivativeInstrument,
    DerivativeMarketContext,
    MarketState,
    PortfolioState,
)
from ai_spot_trader.domain.planning import CycleDecisionPlanInput
from ai_spot_trader.portfolio.ledger import PaperPortfolioLedger
from ai_spot_trader.risk.engine import RiskEngine
from ai_spot_trader.risk.policy import RiskPolicy

NOW = datetime(2026, 10, 5, 10, 0, tzinfo=UTC)


class FixedClock:
    def now(self) -> datetime:
        return NOW


class StaticPlanClient:
    def __init__(self, output: str) -> None:
        self.output = output
        self.calls: list[dict[str, Any]] = []

    async def generate_structured_decision(
        self,
        *,
        model: LLMModel,
        instructions: str,
        input_text: str,
        schema: dict[str, Any],
    ) -> str:
        self.calls.append(
            {
                "model": model,
                "instructions": instructions,
                "input_text": input_text,
                "schema": schema,
            }
        )
        return self.output


def perpetual_market() -> MarketState:
    instrument = DerivativeInstrument(
        symbol="BTC/USD",
        venue_symbol="PF_XBTUSD",
        market_type=MarketType.PERPETUAL,
        contract_kind=DerivativeContractKind.LINEAR,
        underlying_asset="BTC",
        quote_asset="USD",
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
        symbol="BTC/USD",
        last_price=Decimal("100"),
        market_type=MarketType.PERPETUAL,
        derivative=DerivativeMarketContext(
            observed_at=NOW,
            instrument=instrument,
            mark_price=Decimal("100"),
            index_price=Decimal("100"),
            funding_rate=Decimal("0.001"),
        ),
    )


def ledger() -> PaperPortfolioLedger:
    return PaperPortfolioLedger(
        initial_state=PortfolioState(
            portfolio_state_id=uuid4(),
            as_of=NOW,
            settlement_asset="USD",
            balances=(AssetBalance(asset="USD", available=Decimal("1000")),),
        ),
        clock=FixedClock(),
        settlement_asset="USD",
    )


def cost_model() -> PaperExecutionCostModel:
    return PaperExecutionCostModel(
        fee_rate=Decimal("0.001"),
        spread_bps=Decimal("2"),
        slippage_bps=Decimal("3"),
    )


def risk_engine() -> RiskEngine:
    return RiskEngine(
        policy=RiskPolicy(
            allowed_pairs=frozenset({"BTC/USD"}),
            allow_quantity_reduction=True,
            derivative_leverage=Decimal("2"),
            max_derivative_leverage=Decimal("3"),
            max_derivative_position_notional=Decimal("500"),
            max_total_derivative_exposure=Decimal("800"),
            derivative_liquidation_buffer_ratio=Decimal("1.10"),
        ),
        cost_model=cost_model(),
        clock=FixedClock(),
    )


def agent_decision(
    *,
    action: TradingAction,
    quantity: Decimal | None,
    portfolio_state: PortfolioState,
    market_state: MarketState,
):
    client = StaticPlanClient(
        json.dumps(
            {
                "decisions": [
                    {
                        "action": action.value,
                        "symbol": market_state.symbol,
                        "market_type": market_state.market_type.value,
                        "proposed_quantity": (
                            None if quantity is None else float(quantity)
                        ),
                        "rationale": "Batch 49.1 integration fixture",
                    }
                ],
                "rationale": "Batch 49.1 integration fixture",
            }
        )
    )
    agent = OpenAIMultiMarketDecisionProvider(
        client=client,
        model=LLMModel.LUNA,
        clock=FixedClock(),
    )
    plan = asyncio.run(
        agent.generate_decision_plan(
            CycleDecisionPlanInput(
                cycle_id=uuid4(),
                created_at=NOW,
                portfolio_state=portfolio_state,
                market_states=(market_state,),
                aggressiveness=5,
                max_decisions_per_cycle=1,
            )
        )
    )
    assert len(client.calls) == 1
    return plan.decisions[0]


@pytest.mark.parametrize(
    ("open_action", "close_action", "expected_side"),
    [
        (TradingAction.BUY, TradingAction.SELL, PositionSide.LONG),
        (TradingAction.SELL, TradingAction.BUY, PositionSide.SHORT),
    ],
)
def test_agent_perpetual_decision_reaches_risk_broker_and_ledger(
    open_action: TradingAction,
    close_action: TradingAction,
    expected_side: PositionSide,
) -> None:
    market = perpetual_market()
    portfolio = ledger()
    risk = risk_engine()
    broker = PaperBroker(ledger=portfolio, cost_model=cost_model(), clock=FixedClock())

    opening = agent_decision(
        action=open_action,
        quantity=Decimal("1"),
        portfolio_state=portfolio.snapshot(),
        market_state=market,
    )
    assert opening.market_type is MarketType.PERPETUAL

    open_result = risk.evaluate(
        decision=opening,
        market_state=market,
        portfolio_state=portfolio.snapshot(),
    )
    assert open_result.assessment.status is RiskDecision.ALLOW
    assert open_result.execution_intent is not None
    assert open_result.execution_intent.mode is ExecutionMode.PAPER
    assert open_result.execution_intent.market_type is MarketType.PERPETUAL
    assert open_result.execution_intent.reduce_only is False

    open_fill = asyncio.run(
        broker.execute(open_result.execution_intent, market)
    )[0]
    assert open_fill.market_type is MarketType.PERPETUAL
    opened = portfolio.snapshot().derivative_positions
    assert len(opened) == 1
    assert opened[0].side is expected_side
    assert opened[0].quantity == Decimal("1")
    assert opened[0].leverage == Decimal("2")
    assert opened[0].liquidation_price is not None

    closing = agent_decision(
        action=close_action,
        quantity=Decimal("1"),
        portfolio_state=portfolio.snapshot(),
        market_state=market,
    )
    close_result = risk.evaluate(
        decision=closing,
        market_state=market,
        portfolio_state=portfolio.snapshot(),
    )
    assert close_result.assessment.status is RiskDecision.ALLOW
    assert close_result.execution_intent is not None
    assert close_result.execution_intent.market_type is MarketType.PERPETUAL
    assert close_result.execution_intent.reduce_only is True

    close_fill = asyncio.run(
        broker.execute(close_result.execution_intent, market)
    )[0]
    assert close_fill.reduce_only is True
    assert portfolio.snapshot().derivative_positions == ()


def test_perpetual_opposite_order_cannot_reverse_position_in_one_intent() -> None:
    market = perpetual_market()
    portfolio = ledger()
    risk = risk_engine()
    broker = PaperBroker(ledger=portfolio, cost_model=cost_model(), clock=FixedClock())

    opening = agent_decision(
        action=TradingAction.BUY,
        quantity=Decimal("1"),
        portfolio_state=portfolio.snapshot(),
        market_state=market,
    )
    open_result = risk.evaluate(
        decision=opening,
        market_state=market,
        portfolio_state=portfolio.snapshot(),
    )
    assert open_result.execution_intent is not None
    asyncio.run(broker.execute(open_result.execution_intent, market))

    oversized_sell = agent_decision(
        action=TradingAction.SELL,
        quantity=Decimal("2"),
        portfolio_state=portfolio.snapshot(),
        market_state=market,
    )
    close_only = risk.evaluate(
        decision=oversized_sell,
        market_state=market,
        portfolio_state=portfolio.snapshot(),
    )

    assert close_only.assessment.status is RiskDecision.MODIFY
    assert close_only.assessment.authorized_quantity == Decimal("1")
    assert close_only.assessment.reasons == (RiskReason.DERIVATIVE_REDUCE_ONLY_LIMIT,)
    assert close_only.execution_intent is not None
    assert close_only.execution_intent.reduce_only is True
    assert close_only.execution_intent.quantity == Decimal("1")

    asyncio.run(broker.execute(close_only.execution_intent, market))
    assert portfolio.snapshot().derivative_positions == ()


def test_agent_perpetual_hold_creates_no_execution_intent() -> None:
    market = perpetual_market()
    portfolio = ledger()
    hold = agent_decision(
        action=TradingAction.HOLD,
        quantity=None,
        portfolio_state=portfolio.snapshot(),
        market_state=market,
    )

    result = risk_engine().evaluate(
        decision=hold,
        market_state=market,
        portfolio_state=portfolio.snapshot(),
    )

    assert hold.market_type is MarketType.PERPETUAL
    assert result.assessment.status is RiskDecision.ALLOW
    assert result.assessment.reasons == (RiskReason.HOLD_NO_EXECUTION,)
    assert result.execution_intent is None


def test_operator_chat_contract_matches_perpetual_paper_runtime() -> None:
    assert OPERATOR_CHAT_PROMPT_VERSION == "operator-chat-v2"
    assert "Trading is SPOT only" not in OPERATOR_CHAT_SYSTEM_PROMPT
    assert "PAPER only" in OPERATOR_CHAT_SYSTEM_PROMPT
    assert "SPOT" in OPERATOR_CHAT_SYSTEM_PROMPT
    assert "linear PERPETUAL" in OPERATOR_CHAT_SYSTEM_PROMPT
    assert "LONG/SHORT" in OPERATOR_CHAT_SYSTEM_PROMPT
    assert "Dated FUTURE" in OPERATOR_CHAT_SYSTEM_PROMPT
    assert "LIVE execution" in OPERATOR_CHAT_SYSTEM_PROMPT
    assert "deterministic Risk Engine" in OPERATOR_CHAT_SYSTEM_PROMPT
