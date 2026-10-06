import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

import ai_spot_trader.agent.client_factory as client_factory_module
from ai_spot_trader.agent.client_factory import build_structured_decision_client
from ai_spot_trader.agent.errors import AgentContractViolationError
from ai_spot_trader.agent.llm_audit import GLOBAL_LLM_AUDIT_STORE
from ai_spot_trader.agent.ollama_client import OllamaStructuredDecisionClient
from ai_spot_trader.agent.openai_client import OpenAIResponsesClient
from ai_spot_trader.agent.planner import (
    STRATEGIC_PLAN_SCHEMA,
    OpenAIMultiMarketDecisionProvider,
    build_strategic_plan_schema,
)
from ai_spot_trader.core.config import Settings
from ai_spot_trader.core.retry import RetryPolicy
from ai_spot_trader.domain.enums import (
    DerivativeContractKind,
    LLMModel,
    LLMProviderKind,
    MarketType,
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

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
NO_RETRY = RetryPolicy(max_attempts=1, base_delay_seconds=0, max_delay_seconds=0)


class FixedClock:
    def now(self) -> datetime:
        return NOW + timedelta(seconds=1)


class CapturingClient:
    def __init__(self, output: str) -> None:
        self.output = output
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
        return self.output


def _market(symbol: str, market_type: MarketType) -> MarketState:
    derivative = None
    if market_type is MarketType.PERPETUAL:
        base_asset, quote_asset = symbol.split("/", maxsplit=1)
        derivative = DerivativeMarketContext(
            observed_at=NOW,
            instrument=DerivativeInstrument(
                symbol=symbol,
                venue_symbol=f"PF_{base_asset}{quote_asset}",
                market_type=MarketType.PERPETUAL,
                contract_kind=DerivativeContractKind.LINEAR,
                underlying_asset=base_asset,
                quote_asset=quote_asset,
                contract_size=Decimal("1"),
                tick_size=Decimal("0.01"),
                min_order_quantity=Decimal("0.0001"),
                max_position_quantity=Decimal("1000000"),
                initial_margin_rate=Decimal("0.10"),
                maintenance_margin_rate=Decimal("0.05"),
                max_leverage=Decimal("10"),
                funding_interval_seconds=Decimal("3600"),
            ),
            mark_price=Decimal("100"),
            index_price=Decimal("100"),
            funding_rate=Decimal("0"),
        )
    return MarketState(
        market_state_id=uuid4(),
        as_of=NOW,
        symbol=symbol,
        last_price=Decimal("100"),
        market_type=market_type,
        derivative=derivative,
    )


def _plan_input(*markets: MarketState) -> CycleDecisionPlanInput:
    ordered = tuple(sorted(markets, key=lambda item: (item.market_type.value, item.symbol)))
    return CycleDecisionPlanInput(
        cycle_id=uuid4(),
        created_at=NOW,
        portfolio_state=PortfolioState(
            portfolio_state_id=uuid4(),
            as_of=NOW,
            settlement_asset="USD",
            balances=(AssetBalance(asset="USD", available=Decimal("1000")),),
        ),
        market_states=ordered,
        aggressiveness=5,
    )


def _decision(
    action: str,
    symbol: str,
    market_type: str,
    quantity: object,
    *,
    thesis_update: object = None,
) -> dict[str, object]:
    return {
        "action": action,
        "symbol": symbol,
        "market_type": market_type,
        "proposed_quantity": quantity,
        "rationale": "batch 51.1.1 test",
        "thesis_update": thesis_update,
    }


def _plan(*decisions: dict[str, object]) -> str:
    return json.dumps({"decisions": list(decisions), "rationale": "test"})


def _variants(schema: dict[str, Any]) -> list[dict[str, Any]]:
    return schema["properties"]["decisions"]["items"]["anyOf"]


def _identity(variant: dict[str, Any]) -> tuple[str, str, str]:
    properties = variant["properties"]
    return (
        properties["action"]["enum"][0],
        properties["symbol"]["enum"][0],
        properties["market_type"]["enum"][0],
    )


def _contains_key_recursive(value: object, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key_recursive(item, key) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_key_recursive(item, key) for item in value)
    return False


def test_causal_schema_with_one_market_allows_only_that_exact_pair() -> None:
    plan_input = _plan_input(_market("ACE/USD", MarketType.PERPETUAL))

    schema = build_strategic_plan_schema(plan_input)
    identities = {_identity(item) for item in _variants(schema)}

    assert identities == {
        ("BUY", "ACE/USD", "PERPETUAL"),
        ("SELL", "ACE/USD", "PERPETUAL"),
        ("HOLD", "ACE/USD", "PERPETUAL"),
    }
    assert all("BTC/USD" not in item["properties"]["symbol"]["enum"] for item in _variants(schema))
    assert all(item["properties"]["market_type"]["enum"] == ["PERPETUAL"] for item in _variants(schema))


def test_causal_schema_preserves_exact_spot_perpetual_pairs_without_cross_product() -> None:
    plan_input = _plan_input(
        _market("ACE/USD", MarketType.PERPETUAL),
        _market("BTC/USD", MarketType.SPOT),
    )

    identities = {_identity(item) for item in _variants(build_strategic_plan_schema(plan_input))}

    for action in ("BUY", "SELL", "HOLD"):
        assert (action, "ACE/USD", "PERPETUAL") in identities
        assert (action, "BTC/USD", "SPOT") in identities
        assert (action, "ACE/USD", "SPOT") not in identities
        assert (action, "BTC/USD", "PERPETUAL") not in identities


def test_causal_schema_preserves_action_quantity_and_thesis_contracts() -> None:
    plan_input = _plan_input(_market("ACE/USD", MarketType.PERPETUAL))
    dynamic_variants = _variants(build_strategic_plan_schema(plan_input))
    static_thesis_schema = _variants(STRATEGIC_PLAN_SCHEMA)[0]["properties"]["thesis_update"]

    by_action = {item["properties"]["action"]["enum"][0]: item for item in dynamic_variants}
    assert by_action["BUY"]["properties"]["proposed_quantity"] == {
        "type": "number",
        "exclusiveMinimum": 0,
    }
    assert by_action["SELL"]["properties"]["proposed_quantity"] == {
        "type": "number",
        "exclusiveMinimum": 0,
    }
    assert by_action["HOLD"]["properties"]["proposed_quantity"] == {"type": "null"}
    assert all(
        item["properties"]["thesis_update"] == static_thesis_schema
        for item in dynamic_variants
    )
    thesis_object = static_thesis_schema["anyOf"][0]
    assert thesis_object["additionalProperties"] is False
    assert thesis_object["required"] == [
        "status",
        "horizon",
        "thesis_summary",
        "supporting_facts",
        "invalidation_conditions",
        "review_summary",
    ]


def test_provider_sends_dynamic_schema_and_keeps_post_schema_business_guard() -> None:
    plan_input = _plan_input(_market("ACE/USD", MarketType.PERPETUAL))
    client = CapturingClient(
        _plan(_decision("HOLD", "BTC/USD", "SPOT", None))
    )
    provider = OpenAIMultiMarketDecisionProvider(
        client=client,  # type: ignore[arg-type]
        model=LLMModel.LUNA,
        clock=FixedClock(),
    )

    with pytest.raises(AgentContractViolationError, match="outside the causal plan universe"):
        asyncio.run(provider.generate_decision_plan(plan_input))

    identities = {_identity(item) for item in _variants(client.calls[0]["schema"])}
    assert identities == {
        ("BUY", "ACE/USD", "PERPETUAL"),
        ("SELL", "ACE/USD", "PERPETUAL"),
        ("HOLD", "ACE/USD", "PERPETUAL"),
    }


def test_ollama_valid_authorized_market_uses_dynamic_schema_and_think_false() -> None:
    plan_input = _plan_input(_market("ACE/USD", MarketType.PERPETUAL))
    captured: dict[str, Any] = {}
    output = _plan(_decision("HOLD", "ACE/USD", "PERPETUAL", None))

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "qwen3.5:9b",
                "done": True,
                "message": {"role": "assistant", "content": output},
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
            return await provider.generate_decision_plan(plan_input)

    result = asyncio.run(scenario())

    assert result.decisions[0].action is TradingAction.HOLD
    assert result.decisions[0].symbol == "ACE/USD"
    assert result.decisions[0].market_type is MarketType.PERPETUAL
    assert captured["think"] is False
    identities = {_identity(item) for item in _variants(captured["format"])}
    assert all(symbol == "ACE/USD" and market_type == "PERPETUAL" for _, symbol, market_type in identities)


def test_ollama_thinking_is_never_persisted_in_public_audit() -> None:
    GLOBAL_LLM_AUDIT_STORE.clear_for_tests()
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "qwen3.5:9b",
                "done": True,
                "message": {
                    "role": "assistant",
                    "thinking": "private detailed reasoning that must never be audited",
                    "content": '{"action":"HOLD"}',
                },
            },
        )

    async def scenario() -> str:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OllamaStructuredDecisionClient(
                http_client=http_client,
                retry_policy=NO_RETRY,
            )
            return await client.generate_structured_decision(
                model="qwen3.5:9b",
                instructions="x",
                input_text=json.dumps({"cycle_id": str(uuid4())}),
                schema={
                    "type": "object",
                    "properties": {"action": {"type": "string"}},
                    "required": ["action"],
                    "additionalProperties": False,
                },
            )

    assert asyncio.run(scenario()) == '{"action":"HOLD"}'
    assert captured["think"] is False
    record = GLOBAL_LLM_AUDIT_STORE.list_records(limit=1)[0]
    assert record.provider == "OLLAMA"
    assert record.status == "SUCCESS"
    assert record.response_text == '{"action":"HOLD"}'
    assert not _contains_key_recursive(record.response_output, "thinking")
    assert "private detailed reasoning" not in json.dumps(record.response_output)


def test_openai_transport_receives_same_dynamic_causal_schema() -> None:
    plan_input = _plan_input(_market("BTC/USD", MarketType.SPOT))
    captured: dict[str, Any] = {}
    output = _plan(_decision("HOLD", "BTC/USD", "SPOT", None))

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": output}],
                    }
                ],
            },
        )

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OpenAIResponsesClient(
                api_key=SecretStr("test-only-openai-secret"),
                http_client=http_client,
                retry_policy=NO_RETRY,
            )
            provider = OpenAIMultiMarketDecisionProvider(
                client=client,
                model=LLMModel.LUNA,
                clock=FixedClock(),
            )
            return await provider.generate_decision_plan(plan_input)

    result = asyncio.run(scenario())

    assert result.decisions[0].symbol == "BTC/USD"
    sent_schema = captured["text"]["format"]["schema"]
    identities = {_identity(item) for item in _variants(sent_schema)}
    assert identities == {
        ("BUY", "BTC/USD", "SPOT"),
        ("SELL", "BTC/USD", "SPOT"),
        ("HOLD", "BTC/USD", "SPOT"),
    }


def test_ollama_provider_selection_never_constructs_openai_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_openai(**_: object) -> object:
        raise AssertionError("OLLAMA must never construct OpenAIResponsesClient")

    monkeypatch.setattr(client_factory_module, "OpenAIResponsesClient", forbidden_openai)
    settings = Settings(
        _env_file=None,
        llm_provider=LLMProviderKind.OLLAMA,
        ollama_model="qwen3.5:9b",
        openai_api_key=None,
    )

    client, model = build_structured_decision_client(
        settings,
        openai_model=LLMModel.LUNA,
    )

    assert isinstance(client, OllamaStructuredDecisionClient)
    assert model == "qwen3.5:9b"
