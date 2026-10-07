import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

from ai_spot_trader.agent.errors import (
    AgentContractViolationError,
    LLMNetworkError,
    LLMOutputValidationError,
)
from ai_spot_trader.agent.llm_audit import GLOBAL_LLM_AUDIT_STORE, llm_audit_context
from ai_spot_trader.agent.ollama_client import OllamaStructuredDecisionClient
from ai_spot_trader.agent.planner import OpenAIMultiMarketDecisionProvider
from ai_spot_trader.core.retry import RetryPolicy
from ai_spot_trader.domain.enums import LLMModel, MarketType, TradingAction
from ai_spot_trader.domain.experiments import aggressiveness_context
from ai_spot_trader.domain.models import (
    AssetBalance,
    ExecutableMarket,
    MarketState,
    PortfolioState,
)
from ai_spot_trader.domain.planning import CycleDecisionPlanInput
from ai_spot_trader.trading.engine import (
    TradingCycleStage,
    TradingCycleStatus,
    TradingCycleTimeouts,
)
from ai_spot_trader.trading.multi_market import MultiMarketTradingCycleRunner

NOW = datetime(2026, 10, 7, 10, 0, tzinfo=UTC)
SESSION_ID = UUID("51700000-0000-0000-0000-000000000001")
CYCLE_ID = UUID("51700000-0000-0000-0000-000000000002")
NO_RETRY = RetryPolicy(max_attempts=1, base_delay_seconds=0, max_delay_seconds=0)


class FixedClock:
    def now(self) -> datetime:
        return NOW + timedelta(seconds=1)


class NaiveClock:
    def now(self) -> datetime:
        return datetime(2026, 10, 7, 10, 0)


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
        raise AssertionError("Risk must not run after exhausted contract regeneration")


class UnusedBroker:
    async def execute(self, *_: object) -> tuple[()]:
        raise AssertionError("Broker must not run after exhausted contract regeneration")


class SequencedPlanClient:
    def __init__(self, *results: str | Exception) -> None:
        self.results = list(results)
        self.calls: list[dict[str, Any]] = []

    async def generate_structured_decision(
        self,
        *,
        model: LLMModel | str,
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
        if not self.results:
            raise AssertionError("unexpected additional LLM call")
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


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


def plan_input(*, max_decisions: int = 6) -> CycleDecisionPlanInput:
    return CycleDecisionPlanInput(
        cycle_id=CYCLE_ID,
        created_at=NOW,
        portfolio_state=portfolio(),
        market_states=(market("BTC/USD"), market("ETH/USD")),
        aggressiveness=5,
        aggressiveness_context=aggressiveness_context(5),
        max_decisions_per_cycle=max_decisions,
    )


def decision(
    action: str,
    symbol: str,
    quantity: object,
) -> dict[str, object]:
    return {
        "action": action,
        "symbol": symbol,
        "market_type": "SPOT",
        "proposed_quantity": quantity,
        "rationale": f"{action} {symbol}",
        "thesis_update": None,
    }


def output(*decisions: dict[str, object]) -> str:
    return json.dumps({"decisions": list(decisions), "rationale": "batch 51.7"})


def ollama_provider(*results: str | Exception, clock: object | None = None):
    client = SequencedPlanClient(*results)
    provider = OpenAIMultiMarketDecisionProvider(
        client=client,  # type: ignore[arg-type]
        model="qwen3.5:9b",  # type: ignore[arg-type]
        clock=clock or FixedClock(),  # type: ignore[arg-type]
    )
    return provider, client


def test_valid_first_output_keeps_single_llm_call() -> None:
    provider, client = ollama_provider(output(decision("HOLD", "BTC/USD", None)))

    result = asyncio.run(provider.generate_decision_plan(plan_input()))

    assert result.decisions[0].action is TradingAction.HOLD
    assert len(client.calls) == 1
    assert "contract_regeneration" not in json.loads(client.calls[0]["input_text"])


def test_invalid_json_then_valid_regenerates_once() -> None:
    provider, client = ollama_provider(
        "{not-json",
        output(decision("HOLD", "BTC/USD", None)),
    )

    result = asyncio.run(provider.generate_decision_plan(plan_input()))

    assert result.decisions[0].action is TradingAction.HOLD
    assert len(client.calls) == 2
    correction = json.loads(client.calls[1]["input_text"])["contract_regeneration"]
    assert correction["attempt"] == 1
    assert correction["reason"] == "INVALID_JSON"
    assert "{not-json" not in client.calls[1]["input_text"]


def test_negative_sell_then_valid_regenerates_once() -> None:
    provider, client = ollama_provider(
        output(decision("SELL", "BTC/USD", -0.15)),
        output(decision("SELL", "BTC/USD", 0.15)),
    )

    result = asyncio.run(provider.generate_decision_plan(plan_input()))

    assert result.decisions[0].proposed_quantity == Decimal("0.15")
    assert len(client.calls) == 2
    correction = json.loads(client.calls[1]["input_text"])["contract_regeneration"]
    assert correction["reason"] == "INVALID_ACTION_OR_QUANTITY"


def test_duplicate_market_then_valid_regenerates_once() -> None:
    provider, client = ollama_provider(
        output(
            decision("HOLD", "BTC/USD", None),
            decision("BUY", "BTC/USD", 0.1),
        ),
        output(decision("HOLD", "BTC/USD", None)),
    )

    result = asyncio.run(provider.generate_decision_plan(plan_input()))

    assert len(result.decisions) == 1
    assert len(client.calls) == 2
    correction = json.loads(client.calls[1]["input_text"])["contract_regeneration"]
    assert correction["reason"] == "DUPLICATE_MARKET"


def test_max_decisions_then_valid_regenerates_once() -> None:
    provider, client = ollama_provider(
        output(
            decision("HOLD", "BTC/USD", None),
            decision("HOLD", "ETH/USD", None),
        ),
        output(decision("HOLD", "BTC/USD", None)),
    )

    result = asyncio.run(provider.generate_decision_plan(plan_input(max_decisions=1)))

    assert len(result.decisions) == 1
    assert len(client.calls) == 2
    correction = json.loads(client.calls[1]["input_text"])["contract_regeneration"]
    assert correction["reason"] == "MAX_DECISIONS_PER_CYCLE"


def test_two_invalid_outputs_fail_after_exactly_two_calls() -> None:
    provider, client = ollama_provider("not-json", "still-not-json")

    with pytest.raises(LLMOutputValidationError):
        asyncio.run(provider.generate_decision_plan(plan_input()))

    assert len(client.calls) == 2


def test_two_invalid_outputs_fail_cycle_before_risk_and_broker() -> None:
    state = portfolio()
    states = (market("BTC/USD"), market("ETH/USD"))
    provider, client = ollama_provider("not-json", "still-not-json")
    risk = CountingRisk()
    runner = MultiMarketTradingCycleRunner(
        portfolio=StaticPortfolio(state),
        agent=provider,
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
    assert len(client.calls) == 2


def test_internal_clock_violation_is_not_contract_retried() -> None:
    provider, client = ollama_provider(
        output(decision("HOLD", "BTC/USD", None)),
        clock=NaiveClock(),
    )

    with pytest.raises(AgentContractViolationError, match="timezone-aware"):
        asyncio.run(provider.generate_decision_plan(plan_input()))

    assert len(client.calls) == 1


def test_network_error_is_not_contract_retried() -> None:
    provider, client = ollama_provider(LLMNetworkError("network unavailable"))

    with pytest.raises(LLMNetworkError):
        asyncio.run(provider.generate_decision_plan(plan_input()))

    assert len(client.calls) == 1


def test_openai_model_does_not_gain_contract_retry_or_extra_cost() -> None:
    client = SequencedPlanClient(
        "not-json",
        output(decision("HOLD", "BTC/USD", None)),
    )
    provider = OpenAIMultiMarketDecisionProvider(
        client=client,  # type: ignore[arg-type]
        model=LLMModel.LUNA,
        clock=FixedClock(),
    )

    with pytest.raises(LLMOutputValidationError):
        asyncio.run(provider.generate_decision_plan(plan_input()))

    assert len(client.calls) == 1


def test_regeneration_logs_are_safe_and_correlated(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider, _ = ollama_provider(
        output(decision("SELL", "BTC/USD", -0.1)),
        output(decision("HOLD", "BTC/USD", None)),
    )

    caplog.set_level(logging.INFO, logger="ai_spot_trader.agent.planner")
    with llm_audit_context(session_id=SESSION_ID, cycle_id=CYCLE_ID):
        asyncio.run(provider.generate_decision_plan(plan_input()))

    messages = "\n".join(caplog.messages)
    assert "agent_contract_regeneration_started" in messages
    assert "agent_contract_regeneration_succeeded" in messages
    assert f"session_id={SESSION_ID}" in messages
    assert f"cycle_id={CYCLE_ID}" in messages
    assert "reason=INVALID_ACTION_OR_QUANTITY" in messages
    assert "-0.1" not in messages
    assert "SELL BTC/USD" not in messages


def test_real_ollama_transport_creates_two_correlated_audit_records() -> None:
    GLOBAL_LLM_AUDIT_STORE.clear_for_tests()
    responses = [
        "not-json",
        output(decision("HOLD", "BTC/USD", None)),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "qwen3.5:9b",
                "done": True,
                "message": {"role": "assistant", "content": responses.pop(0)},
            },
        )

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OllamaStructuredDecisionClient(
                http_client=http_client,
                retry_policy=NO_RETRY,
            )
            provider = OpenAIMultiMarketDecisionProvider(
                client=client,  # type: ignore[arg-type]
                model="qwen3.5:9b",  # type: ignore[arg-type]
                clock=FixedClock(),
            )
            with llm_audit_context(session_id=SESSION_ID, cycle_id=CYCLE_ID):
                return await provider.generate_decision_plan(plan_input())

    result = asyncio.run(scenario())

    assert result.decisions[0].action is TradingAction.HOLD
    records = GLOBAL_LLM_AUDIT_STORE.list_records(
        limit=10,
        session_id=SESSION_ID,
        cycle_id=CYCLE_ID,
    )
    assert len(records) == 2
    assert all(record.provider == "OLLAMA" for record in records)
    assert all(record.category == "STRATEGIC_MULTI_MARKET_PLAN" for record in records)
    requests = [record.request for record in records]
    serialized = [json.dumps(item, ensure_ascii=False) for item in requests]
    assert any("contract_regeneration" in item for item in serialized)
    assert any("contract_regeneration" not in item for item in serialized)
