import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from ai_spot_trader.agent.errors import AgentContractViolationError, LLMOutputValidationError
from ai_spot_trader.agent.openai_client import OpenAIResponsesClient
from ai_spot_trader.agent.planner import (
    STRATEGIC_PLAN_SCHEMA,
    OpenAIMultiMarketDecisionProvider,
)
from ai_spot_trader.agent.strategy_client import StrategyInstructionsClient
from ai_spot_trader.control_plane import CampaignConfiguration
from ai_spot_trader.domain.enums import LLMModel, MarketType, TradingAction
from ai_spot_trader.domain.experiments import (
    STRATEGIC_AGGRESSIVENESS_MAPPING_VERSION,
    aggressiveness_context,
)
from ai_spot_trader.domain.models import (
    AssetBalance,
    ExecutableMarket,
    MarketState,
    PortfolioState,
)
from ai_spot_trader.domain.planning import CycleDecisionPlanInput
from ai_spot_trader.market.discovery import MarketDiscoveryPolicy
from ai_spot_trader.trading.engine import TradingCycleStage, TradingCycleStatus, TradingCycleTimeouts
from ai_spot_trader.trading.multi_market import MultiMarketTradingCycleRunner

NOW = datetime(2026, 9, 27, 8, 0, tzinfo=UTC)


class FixedClock:
    def now(self) -> datetime:
        return NOW


class CapturingPlanClient:
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


class StaticMarkets:
    def __init__(self, states: tuple[MarketState, ...]) -> None:
        self.states = {(item.symbol, item.market_type): item for item in states}

    async def snapshot(self, symbol: str, market_type: MarketType) -> MarketState:
        return self.states[(symbol, market_type)]


class StaticPortfolio:
    def __init__(self, state: PortfolioState) -> None:
        self.state = state

    def snapshot(self, *, as_of: datetime | None = None) -> PortfolioState:
        del as_of
        return self.state


class CountingRisk:
    def __init__(self) -> None:
        self.calls = 0

    def evaluate(self, **_: object) -> object:
        self.calls += 1
        raise AssertionError("Risk must not run after an invalid LLM plan")


class UnusedBroker:
    async def execute(self, *_: object) -> tuple[()]:
        raise AssertionError("Broker must not run after an invalid LLM plan")


def market(symbol: str) -> MarketState:
    return MarketState(
        market_state_id=uuid4(),
        as_of=NOW,
        symbol=symbol,
        last_price=Decimal("100"),
        market_type=MarketType.SPOT,
    )


def portfolio() -> PortfolioState:
    return PortfolioState(
        portfolio_state_id=uuid4(),
        as_of=NOW,
        settlement_asset="USD",
        balances=(AssetBalance(asset="USD", available=Decimal("1000")),),
    )


def plan_input(*, max_decisions: int = 6, aggressiveness: int = 5) -> CycleDecisionPlanInput:
    return CycleDecisionPlanInput(
        cycle_id=uuid4(),
        created_at=NOW,
        portfolio_state=portfolio(),
        market_states=(market("BTC/USD"), market("ETH/USD")),
        aggressiveness=aggressiveness,
        aggressiveness_context=aggressiveness_context(aggressiveness),
        max_decisions_per_cycle=max_decisions,
    )


def output(decisions: list[dict[str, object]]) -> str:
    return json.dumps({"decisions": decisions, "rationale": "plan test"})


def provider(raw_output: str, *, strategy: bool = False):
    delegate = CapturingPlanClient(raw_output)
    client = (
        StrategyInstructionsClient(delegate, strategy_prompt="Priorise les signaux nets apres couts.")
        if strategy
        else delegate
    )
    return (
        OpenAIMultiMarketDecisionProvider(
            client=client,
            model=LLMModel.LUNA,
            clock=FixedClock(),
        ),
        delegate,
    )


def decision(
    action: str,
    symbol: str,
    quantity: object,
    *,
    market_type: str = "SPOT",
) -> dict[str, object]:
    return {
        "action": action,
        "symbol": symbol,
        "market_type": market_type,
        "proposed_quantity": quantity,
        "rationale": f"{action} {symbol}",
    }


def test_strict_plan_schema_encodes_action_quantity_variants() -> None:
    assert STRATEGIC_PLAN_SCHEMA["type"] == "object"
    item_schema = STRATEGIC_PLAN_SCHEMA["properties"]["decisions"]["items"]
    variants = {
        item["properties"]["action"]["enum"][0]: item
        for item in item_schema["anyOf"]
    }
    assert variants["HOLD"]["properties"]["proposed_quantity"] == {"type": "null"}
    for action in ("BUY", "SELL"):
        quantity_schema = variants[action]["properties"]["proposed_quantity"]
        assert quantity_schema == {"type": "number", "exclusiveMinimum": 0}
        assert variants[action]["additionalProperties"] is False


def test_real_openai_adapter_sends_strict_discriminated_plan_schema() -> None:
    captured: dict[str, Any] = {}
    raw_output = output([decision("HOLD", "BTC/USD", None)])

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": raw_output}],
                    }
                ],
            },
        )

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OpenAIResponsesClient(
                api_key=SecretStr("test-only-openai-secret"),
                http_client=http_client,
            )
            agent = OpenAIMultiMarketDecisionProvider(
                client=client,
                model=LLMModel.LUNA,
                clock=FixedClock(),
            )
            return await agent.generate_decision_plan(plan_input())

    result = asyncio.run(scenario())

    assert result.decisions[0].action is TradingAction.HOLD
    body = captured["body"]
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["text"]["format"]["strict"] is True
    sent_schema = body["text"]["format"]["schema"]
    assert sent_schema["type"] == "object"
    assert "anyOf" in sent_schema["properties"]["decisions"]["items"]


def test_provider_accepts_multi_market_plan_and_hold_null() -> None:
    agent, client = provider(
        output(
            [
                decision("HOLD", "BTC/USD", None),
                decision("BUY", "ETH/USD", 1.25),
            ]
        )
    )
    result = asyncio.run(agent.generate_decision_plan(plan_input()))

    assert len(client.calls) == 1
    assert [item.action for item in result.decisions] == [
        TradingAction.HOLD,
        TradingAction.BUY,
    ]
    assert result.decisions[0].proposed_quantity is None
    assert result.decisions[1].proposed_quantity == Decimal("1.25")


@pytest.mark.parametrize("action", ["BUY", "SELL"])
def test_provider_accepts_positive_buy_sell_quantity(action: str) -> None:
    agent, _ = provider(output([decision(action, "BTC/USD", 0.5)]))
    result = asyncio.run(agent.generate_decision_plan(plan_input()))
    assert result.decisions[0].proposed_quantity == Decimal("0.5")


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        (decision("WAIT", "BTC/USD", None), "invalid action"),
        (decision("HOLD", "BTC/USD", 1), "action/quantity"),
        (decision("BUY", "BTC/USD", None), "action/quantity"),
        (decision("SELL", "BTC/USD", 0), "action/quantity"),
    ],
)
def test_provider_rejects_invalid_action_quantity_outputs(
    entry: dict[str, object],
    message: str,
) -> None:
    agent, _ = provider(output([entry]))
    with pytest.raises(LLMOutputValidationError, match=message):
        asyncio.run(agent.generate_decision_plan(plan_input()))


def test_invalid_plan_is_not_silently_retried() -> None:
    agent, client = provider(output([decision("HOLD", "BTC/USD", 1)]))
    with pytest.raises(LLMOutputValidationError):
        asyncio.run(agent.generate_decision_plan(plan_input()))
    assert len(client.calls) == 1


@pytest.mark.parametrize("raw", ["", "not-json", "[]"])
def test_provider_diagnoses_empty_or_invalid_json(raw: str) -> None:
    agent, _ = provider(raw)
    with pytest.raises(LLMOutputValidationError):
        asyncio.run(agent.generate_decision_plan(plan_input()))


def test_provider_rejects_market_outside_causal_universe() -> None:
    agent, _ = provider(output([decision("HOLD", "DOGE/USD", None)]))
    with pytest.raises(AgentContractViolationError, match="outside the causal plan universe"):
        asyncio.run(agent.generate_decision_plan(plan_input()))


def test_provider_rejects_duplicate_symbol_and_market_type() -> None:
    agent, _ = provider(
        output(
            [
                decision("HOLD", "BTC/USD", None),
                decision("BUY", "BTC/USD", 1),
            ]
        )
    )
    with pytest.raises(AgentContractViolationError, match="duplicate symbol"):
        asyncio.run(agent.generate_decision_plan(plan_input()))


def test_provider_enforces_configured_max_decisions_per_cycle() -> None:
    agent, _ = provider(
        output(
            [
                decision("HOLD", "BTC/USD", None),
                decision("HOLD", "ETH/USD", None),
            ]
        )
    )
    with pytest.raises(AgentContractViolationError, match="max_decisions_per_cycle"):
        asyncio.run(agent.generate_decision_plan(plan_input(max_decisions=1)))


def test_strategy_instructions_are_explicitly_multi_market() -> None:
    agent, client = provider(
        output([decision("HOLD", "BTC/USD", None)]),
        strategy=True,
    )
    asyncio.run(agent.generate_decision_plan(plan_input()))

    instructions = client.calls[0]["instructions"]
    assert "strategic-multi-market-plan-v1" in instructions
    assert "CycleDecisionPlan" in instructions
    assert "market_states" in instructions
    assert "max_decisions_per_cycle" in instructions
    assert "Risk Engine" in instructions
    assert "SPOT uniquement" not in instructions
    assert "`SPOT` et `PERPETUAL`" in instructions
    assert "`FUTURE` date n'est pas executable" in instructions
    assert "Priorise les signaux nets apres couts." in instructions
    assert "exactement un marché" not in instructions
    assert "+4 % par jour" not in instructions
    assert "niveat=" not in instructions
    assert "niveau=5/10" in instructions
    assert "n'implique jamais d'utiliser la quantité maximale" in instructions
    assert "La qualité de la thèse prime sur la fréquence des trades" in instructions

    sent_input = json.loads(client.calls[0]["input_text"])
    assert sent_input["aggressiveness_context"]["mapping_version"] == (
        STRATEGIC_AGGRESSIVENESS_MAPPING_VERSION
    )
    assert "largest quantities" not in sent_input["aggressiveness_context"]["strategic_instruction"]
    assert "very large strategic quantities" not in sent_input["aggressiveness_context"]["strategic_instruction"]


def test_level_ten_prompt_keeps_high_initiative_without_max_quantity_bias() -> None:
    agent, client = provider(
        output([decision("HOLD", "BTC/USD", None)]),
        strategy=True,
    )
    asyncio.run(agent.generate_decision_plan(plan_input(aggressiveness=10)))

    instructions = client.calls[0]["instructions"]
    assert "niveau=10/10" in instructions
    assert "posture=maximum_experimental" in instructions
    assert "highest experimental strategic initiative" in instructions
    assert "less-perfect but still defensible thesis" in instructions
    assert "largest quantities" not in instructions
    assert "very large strategic quantities" not in instructions
    assert "never implies maximum quantity" in instructions
    assert "HOLD remains valid when no defensible trade exists" in instructions


def test_invalid_provider_plan_fails_before_risk() -> None:
    state = portfolio()
    states = (market("BTC/USD"), market("ETH/USD"))
    agent, _ = provider(output([decision("HOLD", "BTC/USD", 1)]))
    risk = CountingRisk()
    runner = MultiMarketTradingCycleRunner(
        portfolio=StaticPortfolio(state),
        agent=agent,
        risk_engine=risk,
        broker=UnusedBroker(),
        aggressiveness=5,
        max_decisions_per_cycle=6,
        timeouts=TradingCycleTimeouts(1, 1, 1),
        executable_market_data=StaticMarkets(states),
        executable_markets=(
            ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),
            ExecutableMarket(symbol="ETH/USD", market_type=MarketType.SPOT),
        ),
        clock=FixedClock(),
    )

    result = asyncio.run(runner.run_cycle())

    assert result.status is TradingCycleStatus.FAILED
    assert result.failure is not None
    assert result.failure.stage is TradingCycleStage.AGENT
    assert result.decision_plan is None
    assert result.decision_results == ()
    assert risk.calls == 0


def spot_configuration() -> CampaignConfiguration:
    return CampaignConfiguration(
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


def perpetual_configuration() -> CampaignConfiguration:
    payload = spot_configuration().model_dump()
    payload.update(
        {
            "paper_executable_markets": (
                ExecutableMarket(symbol="BTC/USD", market_type=MarketType.PERPETUAL),
            ),
            "risk_max_derivative_position_notional": Decimal("500"),
            "risk_max_total_derivative_exposure": Decimal("800"),
        }
    )
    return CampaignConfiguration.model_validate(payload)


def test_canonical_session_accepts_spot_bootstrap_market() -> None:
    config = spot_configuration()

    assert config.paper_executable_markets[0].market_type is MarketType.SPOT


def test_canonical_session_accepts_perpetual_bootstrap_market() -> None:
    config = perpetual_configuration()

    assert config.paper_executable_markets[0].market_type is MarketType.PERPETUAL


def test_canonical_session_accepts_perpetual_discovery_policy() -> None:
    payload = perpetual_configuration().model_dump()
    payload["market_discovery"] = MarketDiscoveryPolicy(
        market_types=(MarketType.PERPETUAL,),
    )

    config = CampaignConfiguration.model_validate(payload)

    assert config.market_discovery is not None
    assert config.market_discovery.market_types == (MarketType.PERPETUAL,)


def test_canonical_session_still_rejects_dated_future_market() -> None:
    payload = spot_configuration().model_dump(mode="json")
    payload["paper_executable_markets"] = (
        {"symbol": "BTC/USD", "market_type": "FUTURE"},
    )

    with pytest.raises(ValueError, match="FUTURE"):
        CampaignConfiguration.model_validate(payload)


def test_discovery_still_rejects_dated_future_market() -> None:
    with pytest.raises(ValueError, match="FUTURE"):
        MarketDiscoveryPolicy(market_types=(MarketType.FUTURE,))
