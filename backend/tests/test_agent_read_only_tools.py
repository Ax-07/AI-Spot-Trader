import asyncio
import inspect
import json
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from functools import wraps
from typing import Any
from uuid import uuid4

import httpx
import pytest
from pydantic import BaseModel, ConfigDict, JsonValue, SecretStr

import ai_spot_trader.tools.market_research as market_tools
import ai_spot_trader.tools.read_only as read_only
from ai_spot_trader.agent.errors import AgentContractViolationError
from ai_spot_trader.agent.openai_client import OpenAIResponsesClient
from ai_spot_trader.agent.provider import OpenAIDecisionProvider
from ai_spot_trader.domain.enums import ExecutionMode, LLMModel, MarketType, TradingAction
from ai_spot_trader.domain.models import (
    AgentInput,
    AgentToolTrace,
    AssetBalance,
    AssetPosition,
    DecisionCandidate,
    MarketState,
    PortfolioState,
    canonical_json_digest,
)
from ai_spot_trader.integrations.kraken.errors import (
    KrakenPayloadError,
    UnknownKrakenSymbolError,
)
from ai_spot_trader.market.research import MarketResearchMarket, MarketResearchService
from ai_spot_trader.tools.market_research import build_market_research_tool_registry
from ai_spot_trader.tools.read_only import (
    MalformedToolArgumentsError,
    ReadOnlyFunctionTool,
    ReadOnlyToolRegistry,
    ToolCallBudgetExceededError,
    ToolLoopResult,
    UnknownToolError,
)

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


def async_test[**P](
    func: Callable[P, Coroutine[Any, Any, None]],
) -> Callable[P, None]:
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> None:
        asyncio.run(func(*args, **kwargs))

    return wrapper


DECISION_HOLD = (
    '{"action":"HOLD","symbol":"BTC/USD","proposed_quantity":null,'
    '"rationale":"Attente."}'
)


class FixedClock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


class AdvancingClock:
    def __init__(self, start: datetime = NOW) -> None:
        self.value = start

    def now(self) -> datetime:
        self.value += timedelta(milliseconds=1)
        return self.value


class EmptyArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


async def _empty_handler(_: BaseModel) -> JsonValue:
    return {"fact": "ok"}


def _simple_registry(*, max_result_bytes: int = 4096) -> ReadOnlyToolRegistry:
    return ReadOnlyToolRegistry(
        (
            ReadOnlyFunctionTool(
                name="facts",
                description="Read facts only.",
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                arguments_model=EmptyArgs,
                handler=_empty_handler,
            ),
        ),
        timeout_seconds=1,
        max_result_bytes=max_result_bytes,
        clock=AdvancingClock(),
    )


def _message(text: str) -> dict[str, object]:
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
    }


def _call(
    call_id: str = "call_1",
    *,
    name: str = "facts",
    arguments: str = "{}",
) -> dict[str, object]:
    return {
        "status": "completed",
        "output": [
            {
                "type": "function_call",
                "call_id": call_id,
                "name": name,
                "arguments": arguments,
            }
        ],
    }


def _client_for(
    responses: list[dict[str, object]],
    requests: list[dict[str, object]],
) -> OpenAIResponsesClient:
    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=responses.pop(0))

    return OpenAIResponsesClient(
        api_key=SecretStr("test-key"),
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


@async_test
async def test_direct_hold_requires_zero_tool_calls_and_store_false() -> None:
    requests: list[dict[str, object]] = []
    client = _client_for([_message(DECISION_HOLD)], requests)

    result = await client.generate_structured_decision_with_tools(
        model=LLMModel.LUNA,
        instructions="x",
        input_text="{}",
        schema={"type": "object"},
        tool_registry=_simple_registry(),
        max_tool_calls=3,
    )

    assert result.traces == ()
    assert json.loads(result.output_text)["action"] == "HOLD"
    assert requests[0]["store"] is False
    assert requests[0]["parallel_tool_calls"] is False
    assert len(requests) == 1


@async_test
async def test_one_tool_call_replays_previous_output_and_function_result() -> None:
    requests: list[dict[str, object]] = []
    client = _client_for([_call(), _message(DECISION_HOLD)], requests)

    result = await client.generate_structured_decision_with_tools(
        model=LLMModel.LUNA,
        instructions="x",
        input_text="{}",
        schema={"type": "object"},
        tool_registry=_simple_registry(),
        max_tool_calls=3,
    )

    assert len(result.traces) == 1
    second_input = requests[1]["input"]
    assert isinstance(second_input, list)
    assert any(item.get("type") == "function_call" for item in second_input)
    assert any(item.get("type") == "function_call_output" for item in second_input)


@async_test
async def test_multiple_successive_tool_calls_are_supported() -> None:
    requests: list[dict[str, object]] = []
    client = _client_for(
        [_call("call_1"), _call("call_2"), _message(DECISION_HOLD)],
        requests,
    )

    result = await client.generate_structured_decision_with_tools(
        model=LLMModel.LUNA,
        instructions="x",
        input_text="{}",
        schema={"type": "object"},
        tool_registry=_simple_registry(),
        max_tool_calls=3,
    )

    assert [trace.call_id for trace in result.traces] == ["call_1", "call_2"]
    assert len(requests) == 3


@async_test
async def test_tool_call_budget_is_fail_closed() -> None:
    client = _client_for([_call("call_1"), _call("call_2")], [])
    with pytest.raises(ToolCallBudgetExceededError):
        await client.generate_structured_decision_with_tools(
            model=LLMModel.LUNA,
            instructions="x",
            input_text="{}",
            schema={"type": "object"},
            tool_registry=_simple_registry(),
            max_tool_calls=1,
        )


@async_test
async def test_unknown_tool_is_refused() -> None:
    with pytest.raises(UnknownToolError):
        await _simple_registry().execute(
            call_id="c",
            name="buy",
            arguments_json="{}",
        )


@async_test
@pytest.mark.parametrize("arguments", ["{", "[]", '{"extra":1}'])
async def test_malformed_tool_arguments_are_refused(arguments: str) -> None:
    with pytest.raises(MalformedToolArgumentsError):
        await _simple_registry().execute(
            call_id="c",
            name="facts",
            arguments_json=arguments,
        )


@async_test
async def test_runtime_tool_error_is_sanitized_and_auditable() -> None:
    async def broken(_: BaseModel) -> JsonValue:
        raise OSError("secret/provider detail must not leak")

    registry = ReadOnlyToolRegistry(
        (
            ReadOnlyFunctionTool(
                name="facts",
                description="x",
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                arguments_model=EmptyArgs,
                handler=broken,
            ),
        ),
        timeout_seconds=1,
        max_result_bytes=4096,
        clock=AdvancingClock(),
    )
    execution = await registry.execute(
        call_id="c",
        name="facts",
        arguments_json="{}",
    )

    assert execution.trace.status == "ERROR"
    assert execution.trace.error_type == "OSError"
    assert "secret" not in execution.function_output
    assert execution.trace.result_digest


@async_test
async def test_tool_timeout_is_sanitized() -> None:
    async def slow(_: BaseModel) -> JsonValue:
        await asyncio.sleep(0.05)
        return {"late": True}

    registry = ReadOnlyToolRegistry(
        (
            ReadOnlyFunctionTool(
                name="facts",
                description="x",
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                arguments_model=EmptyArgs,
                handler=slow,
            ),
        ),
        timeout_seconds=0.001,
        max_result_bytes=4096,
        clock=AdvancingClock(),
    )
    execution = await registry.execute(
        call_id="c",
        name="facts",
        arguments_json="{}",
    )
    assert execution.trace.status == "ERROR"
    assert execution.trace.error_type == "TimeoutError"


@async_test
async def test_oversized_tool_result_is_replaced_by_bounded_error() -> None:
    async def huge(_: BaseModel) -> JsonValue:
        return {"blob": "x" * 5000}

    registry = ReadOnlyToolRegistry(
        (
            ReadOnlyFunctionTool(
                name="facts",
                description="x",
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                arguments_model=EmptyArgs,
                handler=huge,
            ),
        ),
        timeout_seconds=1,
        max_result_bytes=128,
        clock=AdvancingClock(),
    )
    execution = await registry.execute(
        call_id="c",
        name="facts",
        arguments_json="{}",
    )
    assert execution.trace.status == "ERROR"
    assert execution.trace.error_type == "ToolResultTooLargeError"
    assert len(execution.function_output.encode()) <= 128


class FakeResearchBackend:
    async def list_markets(
        self,
        market_type: MarketType | None,
    ) -> tuple[MarketResearchMarket, ...]:
        items = (
            MarketResearchMarket(
                symbol="ETH/USD",
                market_type=MarketType.SPOT,
                venue_symbol="ETH/USD",
                status="online",
                underlying_asset="ETH",
                quote_asset="USD",
            ),
            MarketResearchMarket(
                symbol="BTC/USD",
                market_type=MarketType.SPOT,
                venue_symbol="BTC/USD",
                status="online",
                underlying_asset="BTC",
                quote_asset="USD",
            ),
        )
        return tuple(item for item in items if market_type in (None, item.market_type))

    async def snapshot(self, symbol: str, market_type: MarketType) -> MarketState:
        if symbol != "BTC/USD":
            raise LookupError("unknown")
        return MarketState(
            market_state_id=uuid4(),
            as_of=NOW,
            symbol=symbol,
            last_price=Decimal("60000"),
            market_type=market_type,
        )


@async_test
async def test_market_listing_is_neutral_deterministic_and_paginated() -> None:
    service = MarketResearchService(
        FakeResearchBackend(),
        max_list_limit=1,
        clock=FixedClock(),
    )
    first = await service.list_markets(market_type=None, cursor=0, limit=1)
    second = await service.list_markets(market_type=None, cursor=1, limit=1)
    assert first.markets[0].symbol == "BTC/USD"
    assert second.markets[0].symbol == "ETH/USD"
    assert first.next_cursor == 1


@async_test
async def test_market_tool_registry_contains_only_read_only_market_tools() -> None:
    service = MarketResearchService(
        FakeResearchBackend(),
        max_list_limit=10,
        clock=FixedClock(),
    )
    registry = build_market_research_tool_registry(
        service,
        timeout_seconds=1,
        max_result_bytes=4096,
        clock=AdvancingClock(),
    )
    assert registry.registered_names == {"list_markets", "get_market_snapshot"}
    assert "buy" not in registry.registered_names
    assert "sell" not in registry.registered_names


class CapturingToolClient:
    def __init__(self) -> None:
        self.input_text = ""

    async def generate_structured_decision(self, **_: object) -> str:
        raise AssertionError("tool path expected")

    async def generate_structured_decision_with_tools(
        self,
        **kwargs: object,
    ) -> ToolLoopResult:
        self.input_text = str(kwargs["input_text"])
        return ToolLoopResult(output_text=DECISION_HOLD, traces=())


@async_test
async def test_provider_keeps_full_portfolio_and_final_symbol_constraint() -> None:
    client = CapturingToolClient()
    provider = OpenAIDecisionProvider(
        client=client,
        clock=FixedClock(NOW + timedelta(seconds=1)),
        tool_registry=_simple_registry(),
        max_tool_calls=2,
    )
    portfolio = PortfolioState(
        portfolio_state_id=uuid4(),
        as_of=NOW,
        mode=ExecutionMode.PAPER,
        balances=(AssetBalance(asset="USD", available=Decimal("1000")),),
        positions=(
            AssetPosition(
                asset="ETH",
                quantity=Decimal("2"),
                available=Decimal("2"),
            ),
        ),
    )
    agent_input = AgentInput(
        cycle_id=uuid4(),
        created_at=NOW,
        market_state=MarketState(
            market_state_id=uuid4(),
            as_of=NOW,
            symbol="BTC/USD",
            last_price=Decimal("60000"),
        ),
        portfolio_state=portfolio,
        aggressiveness=5,
    )
    decision = await provider.generate_decision(agent_input)
    serialized = json.loads(client.input_text)
    assert serialized["portfolio_state"]["balances"]
    assert serialized["portfolio_state"]["positions"]
    assert decision.symbol == agent_input.market_state.symbol
    assert decision.action is TradingAction.HOLD


@async_test
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (UnknownKrakenSymbolError("missing"), "UnknownKrakenSymbolError"),
        (KrakenPayloadError("bad payload"), "KrakenPayloadError"),
        (httpx.NetworkError("network"), "NetworkError"),
        (LookupError("no data"), "LookupError"),
    ],
)
async def test_market_tool_provider_failures_are_sanitized(
    error: Exception,
    expected: str,
) -> None:
    class BrokenBackend(FakeResearchBackend):
        async def snapshot(self, symbol: str, market_type: MarketType) -> MarketState:
            raise error

    service = MarketResearchService(
        BrokenBackend(),
        max_list_limit=10,
        clock=FixedClock(),
    )
    registry = build_market_research_tool_registry(
        service,
        timeout_seconds=1,
        max_result_bytes=4096,
        clock=AdvancingClock(),
    )
    execution = await registry.execute(
        call_id="c",
        name="get_market_snapshot",
        arguments_json='{"symbol":"BTC/USD","market_type":"SPOT"}',
    )
    assert execution.trace.status == "ERROR"
    assert execution.trace.error_type == expected
    assert str(error) not in execution.function_output


@async_test
async def test_unknown_market_symbol_is_a_tool_error_not_an_execution_path() -> None:
    service = MarketResearchService(
        FakeResearchBackend(),
        max_list_limit=10,
        clock=FixedClock(),
    )
    registry = build_market_research_tool_registry(
        service,
        timeout_seconds=1,
        max_result_bytes=4096,
        clock=AdvancingClock(),
    )
    execution = await registry.execute(
        call_id="c",
        name="get_market_snapshot",
        arguments_json='{"symbol":"DOGE/USD","market_type":"SPOT"}',
    )
    assert execution.trace.status == "ERROR"
    assert execution.trace.error_type == "LookupError"



@async_test
async def test_snapshot_future_arguments_are_refused_in_batch_18_1() -> None:
    service = MarketResearchService(
        FakeResearchBackend(),
        max_list_limit=10,
        clock=FixedClock(),
    )
    registry = build_market_research_tool_registry(
        service,
        timeout_seconds=1,
        max_result_bytes=4096,
        clock=AdvancingClock(),
    )
    with pytest.raises(MalformedToolArgumentsError):
        await registry.execute(
            call_id="c",
            name="get_market_snapshot",
            arguments_json='{"symbol":"BTC/USD","market_type":"FUTURE"}',
        )


@async_test
async def test_list_limit_above_configured_bound_is_refused_as_malformed() -> None:
    service = MarketResearchService(
        FakeResearchBackend(),
        max_list_limit=2,
        clock=FixedClock(),
    )
    registry = build_market_research_tool_registry(
        service,
        timeout_seconds=1,
        max_result_bytes=4096,
        clock=AdvancingClock(),
    )
    with pytest.raises(MalformedToolArgumentsError):
        await registry.execute(
            call_id="c",
            name="list_markets",
            arguments_json='{"market_type":"ALL","cursor":0,"limit":3}',
        )

def test_trace_digest_is_deterministic_and_rejects_post_decision_data() -> None:
    result = {"ok": True, "data": {"b": 2, "a": 1}}
    reordered = {"data": {"a": 1, "b": 2}, "ok": True}
    assert canonical_json_digest(result) == canonical_json_digest(reordered)
    trace = AgentToolTrace(
        call_id="c",
        tool_name="facts",
        arguments={},
        started_at=NOW,
        completed_at=NOW + timedelta(seconds=2),
        status="SUCCESS",
        error_type=None,
        result=result,
        result_digest=canonical_json_digest(result),
    )
    with pytest.raises(ValueError, match="newer than the final decision"):
        DecisionCandidate(
            decision_id=uuid4(),
            cycle_id=uuid4(),
            created_at=NOW + timedelta(seconds=1),
            action=TradingAction.HOLD,
            symbol="BTC/USD",
            rationale="x",
            tool_traces=(trace,),
        )


def test_decision_payload_persists_normalized_tool_traces() -> None:
    result = {"ok": True, "data": {"price": "60000"}}
    trace = AgentToolTrace(
        call_id="c",
        tool_name="get_market_snapshot",
        arguments={"symbol": "BTC/USD"},
        started_at=NOW,
        completed_at=NOW,
        status="SUCCESS",
        error_type=None,
        result=result,
        result_digest=canonical_json_digest(result),
    )
    decision = DecisionCandidate(
        decision_id=uuid4(),
        cycle_id=uuid4(),
        created_at=NOW,
        action=TradingAction.HOLD,
        symbol="BTC/USD",
        rationale="x",
        tool_traces=(trace,),
    )
    payload = decision.model_dump(mode="json")
    assert payload["tool_traces"][0]["call_id"] == "c"
    assert payload["tool_traces"][0]["result"] == result


def test_read_only_tool_modules_have_no_execution_authority_imports() -> None:
    source = inspect.getsource(market_tools) + inspect.getsource(read_only)
    for forbidden in ("RiskEngine", "PaperBroker", "ExecutionIntent"):
        assert forbidden not in source


def test_tool_budget_configuration_defaults_are_non_strategic_and_bounded() -> None:
    from ai_spot_trader.core.config import Settings

    settings = Settings(_env_file=None)
    assert settings.agent_tool_max_calls == 6
    assert settings.agent_tool_timeout_seconds == 5.0
    assert settings.agent_tool_max_result_bytes == 32768
    assert settings.agent_tool_list_markets_max_limit == 50


@async_test
async def test_tool_enabled_provider_cannot_change_final_market_symbol() -> None:
    class WrongSymbolClient(CapturingToolClient):
        async def generate_structured_decision_with_tools(
            self,
            **kwargs: object,
        ) -> ToolLoopResult:
            self.input_text = str(kwargs["input_text"])
            return ToolLoopResult(
                output_text=(
                    '{"action":"HOLD","symbol":"ETH/USD",'
                    '"proposed_quantity":null,"rationale":"Attente."}'
                ),
                traces=(),
            )

    provider = OpenAIDecisionProvider(
        client=WrongSymbolClient(),
        clock=FixedClock(NOW + timedelta(seconds=1)),
        tool_registry=_simple_registry(),
        max_tool_calls=2,
    )
    agent_input = AgentInput(
        cycle_id=uuid4(),
        created_at=NOW,
        market_state=MarketState(
            market_state_id=uuid4(),
            as_of=NOW,
            symbol="BTC/USD",
            last_price=Decimal("60000"),
        ),
        portfolio_state=PortfolioState(
            portfolio_state_id=uuid4(),
            as_of=NOW,
            balances=(AssetBalance(asset="USD", available=Decimal("1000")),),
        ),
        aggressiveness=5,
    )
    with pytest.raises(AgentContractViolationError, match="symbol must equal"):
        await provider.generate_decision(agent_input)


def test_decision_payload_identity_changes_when_tool_trace_changes() -> None:
    common = dict(
        decision_id=uuid4(),
        cycle_id=uuid4(),
        created_at=NOW,
        action=TradingAction.HOLD,
        symbol="BTC/USD",
        rationale="Attente.",
    )
    without_tools = DecisionCandidate(**common)
    result = {"ok": True, "data": {"price": "60000"}}
    trace = AgentToolTrace(
        call_id="c",
        tool_name="get_market_snapshot",
        arguments={"symbol": "BTC/USD", "market_type": "SPOT"},
        started_at=NOW,
        completed_at=NOW,
        status="SUCCESS",
        error_type=None,
        result=result,
        result_digest=canonical_json_digest(result),
    )
    with_tools = DecisionCandidate(**common, tool_traces=(trace,))
    assert canonical_json_digest(without_tools.model_dump(mode="json")) != canonical_json_digest(
        with_tools.model_dump(mode="json")
    )

@async_test
async def test_client_retains_completed_trace_when_later_budget_failure_occurs() -> None:
    client = _client_for([_call("call_1"), _call("call_2")], [])

    with pytest.raises(ToolCallBudgetExceededError):
        await client.generate_structured_decision_with_tools(
            model=LLMModel.LUNA,
            instructions="x",
            input_text="{}",
            schema={"type": "object"},
            tool_registry=_simple_registry(),
            max_tool_calls=1,
        )

    assert [trace.call_id for trace in client.last_tool_traces] == ["call_1"]


@async_test
async def test_provider_retains_partial_research_when_final_decision_fails() -> None:
    client = _client_for([_call("call_1"), _call("call_2")], [])
    provider = OpenAIDecisionProvider(
        client=client,
        clock=FixedClock(NOW + timedelta(seconds=1)),
        tool_registry=_simple_registry(),
        max_tool_calls=1,
    )
    agent_input = AgentInput(
        cycle_id=uuid4(),
        created_at=NOW,
        market_state=MarketState(
            market_state_id=uuid4(),
            as_of=NOW,
            symbol="BTC/USD",
            last_price=Decimal("60000"),
        ),
        portfolio_state=PortfolioState(
            portfolio_state_id=uuid4(),
            as_of=NOW,
            balances=(AssetBalance(asset="USD", available=Decimal("1000")),),
        ),
        aggressiveness=5,
    )

    with pytest.raises(ToolCallBudgetExceededError):
        await provider.generate_decision(agent_input)

    assert [trace.call_id for trace in provider.last_tool_traces] == ["call_1"]


def _sample_trace(*, price: str = "60000") -> AgentToolTrace:
    result = {"ok": True, "data": {"price": price}}
    return AgentToolTrace(
        call_id="call_1",
        tool_name="get_market_snapshot",
        arguments={"symbol": "BTC/USD", "market_type": "SPOT"},
        started_at=NOW,
        completed_at=NOW,
        status="SUCCESS",
        error_type=None,
        result=result,
        result_digest=canonical_json_digest(result),
    )


def test_failed_cycle_can_carry_agent_tool_traces_without_decision() -> None:
    from ai_spot_trader.trading.engine import (
        TradingCycleFailure,
        TradingCycleResult,
        TradingCycleStage,
        TradingCycleStatus,
    )

    trace = _sample_trace()
    result = TradingCycleResult(
        cycle_id=uuid4(),
        status=TradingCycleStatus.FAILED,
        failure=TradingCycleFailure(
            stage=TradingCycleStage.AGENT,
            error_type="ToolCallBudgetExceededError",
        ),
        agent_tool_traces=(trace,),
    )

    assert result.decision is None
    assert result.agent_tool_traces == (trace,)


def test_cycle_digest_changes_with_agent_tool_trace() -> None:
    from ai_spot_trader.persistence.repository import _result_digest
    from ai_spot_trader.trading.engine import (
        TradingCycleFailure,
        TradingCycleResult,
        TradingCycleStage,
        TradingCycleStatus,
    )

    cycle_id = uuid4()
    base = dict(
        cycle_id=cycle_id,
        status=TradingCycleStatus.FAILED,
        failure=TradingCycleFailure(
            stage=TradingCycleStage.AGENT,
            error_type="TestError",
        ),
    )
    without_trace = TradingCycleResult(**base)
    with_trace = TradingCycleResult(**base, agent_tool_traces=(_sample_trace(),))

    assert _result_digest(without_trace, paper_run_id=None) != _result_digest(
        with_trace, paper_run_id=None
    )


def test_cycle_repository_graph_persists_trace_even_without_decision() -> None:
    from ai_spot_trader.persistence.models import CycleRecord
    from ai_spot_trader.persistence.repository import SqlAlchemyCycleAuditRepository
    from ai_spot_trader.trading.engine import (
        TradingCycleFailure,
        TradingCycleResult,
        TradingCycleStage,
        TradingCycleStatus,
    )

    trace = _sample_trace()
    result = TradingCycleResult(
        cycle_id=uuid4(),
        status=TradingCycleStatus.FAILED,
        failure=TradingCycleFailure(
            stage=TradingCycleStage.AGENT,
            error_type="LLMProviderError",
        ),
        agent_tool_traces=(trace,),
    )

    class FakeSession:
        def __init__(self) -> None:
            self.values: list[object] = []

        def add(self, value: object) -> None:
            self.values.append(value)

    session = FakeSession()
    repository = SqlAlchemyCycleAuditRepository(None)  # type: ignore[arg-type]
    repository._add_graph(  # noqa: SLF001 - focused persistence contract test
        session,  # type: ignore[arg-type]
        result=result,
        digest="0" * 64,
    )

    cycle = next(value for value in session.values if isinstance(value, CycleRecord))
    assert cycle.agent_tool_traces_payload is not None
    assert cycle.agent_tool_traces_payload[0]["call_id"] == "call_1"
    assert cycle.decision is None


def test_cycle_query_detail_exposes_persisted_tool_traces() -> None:
    from ai_spot_trader.persistence.models import CycleRecord
    from ai_spot_trader.persistence.query import _cycle_detail

    trace_payload = _sample_trace().model_dump(mode="json")
    record = CycleRecord(
        cycle_id=uuid4(),
        paper_run_id=None,
        status="FAILED",
        recorded_at=NOW,
        result_digest="0" * 64,
        failure_stage="AGENT",
        failure_error_type="LLMProviderError",
        failure_timed_out=False,
        market_state_id=None,
        portfolio_state_before_id=None,
        portfolio_state_after_id=None,
        market_as_of=None,
        portfolio_before_as_of=None,
        portfolio_after_as_of=None,
        agent_input_payload=None,
        agent_tool_traces_payload=[trace_payload],
        portfolio_after_payload=None,
    )
    record.decision = None
    record.risk_assessment = None
    record.execution_intent = None

    detail = _cycle_detail(record)
    assert detail.agent_tool_traces[0]["call_id"] == "call_1"

@async_test
async def test_trading_runner_keeps_partial_tool_traces_on_agent_failure() -> None:
    from ai_spot_trader.trading.engine import (
        TradingCycleRunner,
        TradingCycleStage,
        TradingCycleStatus,
        TradingCycleTimeouts,
    )

    trace = _sample_trace()

    class MarketData:
        async def snapshot(self, symbol: str) -> MarketState:
            assert symbol == "BTC/USD"
            return MarketState(
                market_state_id=uuid4(),
                as_of=NOW,
                symbol=symbol,
                last_price=Decimal("60000"),
            )

    class Portfolio:
        def snapshot(self, *, as_of: datetime | None = None) -> PortfolioState:
            return PortfolioState(
                portfolio_state_id=uuid4(),
                as_of=as_of or NOW,
                balances=(AssetBalance(asset="USD", available=Decimal("1000")),),
            )

    class FailingAgent:
        @property
        def last_tool_traces(self) -> tuple[AgentToolTrace, ...]:
            return (trace,)

        async def generate_decision(self, agent_input: AgentInput) -> DecisionCandidate:
            raise ToolCallBudgetExceededError("budget")

    class ForbiddenRisk:
        def evaluate(self, **_: object) -> object:
            raise AssertionError("Risk must not run after Agent failure")

    class ForbiddenBroker:
        async def execute(self, *args: object, **kwargs: object) -> object:
            raise AssertionError("Broker must not run after Agent failure")

    runner = TradingCycleRunner(
        market_data=MarketData(),  # type: ignore[arg-type]
        portfolio=Portfolio(),  # type: ignore[arg-type]
        agent=FailingAgent(),  # type: ignore[arg-type]
        risk_engine=ForbiddenRisk(),  # type: ignore[arg-type]
        broker=ForbiddenBroker(),  # type: ignore[arg-type]
        symbol="BTC/USD",
        aggressiveness=5,
        timeouts=TradingCycleTimeouts(
            market_seconds=1,
            agent_seconds=1,
            broker_seconds=1,
        ),
        clock=FixedClock(NOW + timedelta(seconds=1)),
    )

    result = await runner.run_cycle()
    assert result.status is TradingCycleStatus.FAILED
    assert result.failure is not None
    assert result.failure.stage is TradingCycleStage.AGENT
    assert result.agent_tool_traces == (trace,)
    assert result.decision is None
