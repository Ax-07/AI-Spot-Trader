import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import httpx
import pytest
from pydantic import SecretStr

import ai_spot_trader.agent.client_factory as client_factory_module
from ai_spot_trader.agent import (
    LLMHTTPError,
    LLMNetworkError,
    LLMOutputValidationError,
    LLMProviderError,
    LLMRateLimitError,
    LLMServerError,
    LLMTimeoutError,
    OllamaStructuredDecisionClient,
    OpenAIDecisionProvider,
    OpenAIResponsesClient,
)
from ai_spot_trader.agent.client_factory import build_structured_decision_client
from ai_spot_trader.agent.llm_audit import GLOBAL_LLM_AUDIT_STORE
from ai_spot_trader.core.config import (
    PaperRunConfiguration,
    PaperRuntimeConfigurationError,
    Settings,
)
from ai_spot_trader.core.retry import RetryPolicy
from ai_spot_trader.domain.enums import LLMModel, LLMProviderKind, TradingAction
from ai_spot_trader.domain.models import (
    AgentInput,
    AssetBalance,
    AssetPosition,
    MarketState,
    PortfolioState,
)

CYCLE_ID = UUID("51000000-0000-0000-0000-000000000001")
MARKET_STATE_ID = UUID("51000000-0000-0000-0000-000000000002")
PORTFOLIO_STATE_ID = UUID("51000000-0000-0000-0000-000000000003")
MARKET_AT = datetime(2026, 10, 6, 10, 0, tzinfo=UTC)
INPUT_AT = datetime(2026, 10, 6, 10, 1, tzinfo=UTC)
DECISION_AT = datetime(2026, 10, 6, 10, 2, tzinfo=UTC)
NO_RETRY = RetryPolicy(max_attempts=1, base_delay_seconds=0, max_delay_seconds=0)
SCHEMA = {
    "type": "object",
    "properties": {"action": {"type": "string"}},
    "required": ["action"],
    "additionalProperties": False,
}


class FixedClock:
    def now(self) -> datetime:
        return DECISION_AT


def _ollama_message(content: str, *, tool_calls: object | None = None) -> dict[str, object]:
    message: dict[str, object] = {"role": "assistant", "content": content}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    return {
        "model": "qwen-test",
        "message": message,
        "done": True,
    }


def _agent_input() -> AgentInput:
    return AgentInput(
        cycle_id=CYCLE_ID,
        created_at=INPUT_AT,
        market_state=MarketState(
            market_state_id=MARKET_STATE_ID,
            as_of=MARKET_AT,
            symbol="BTC/EUR",
            last_price=Decimal("50000"),
        ),
        portfolio_state=PortfolioState(
            portfolio_state_id=PORTFOLIO_STATE_ID,
            as_of=MARKET_AT,
            balances=(AssetBalance(asset="EUR", available=Decimal("1000")),),
            positions=(
                AssetPosition(
                    asset="BTC",
                    quantity=Decimal("0.5"),
                    available=Decimal("0.5"),
                ),
            ),
        ),
        aggressiveness=5,
    )


def _paper_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "_env_file": None,
        "environment": "test",
        "llm_provider": LLMProviderKind.OLLAMA,
        "ollama_model": "qwen-local-test",
        "paper_symbol": "BTC/EUR",
        "paper_initial_capital": Decimal("1000"),
        "paper_settlement_asset": "EUR",
        "trading_cadence_seconds": 30.0,
        "aggressiveness": 5,
        "cycle_market_timeout_seconds": 5.0,
        "cycle_agent_timeout_seconds": 30.0,
        "cycle_broker_timeout_seconds": 5.0,
        "risk_max_order_notional": Decimal("100"),
        "risk_allowed_pairs": frozenset({"BTC/EUR"}),
        "risk_allow_quantity_reduction": True,
        "paper_fee_rate": Decimal("0.0026"),
        "paper_spread_bps": Decimal("5"),
        "paper_slippage_bps": Decimal("3"),
        "database_url": SecretStr(
            "postgresql+asyncpg://test-user:test-password@localhost:5432/ai_spot_trader_test"
        ),
    }
    values.update(overrides)
    return Settings(**values)


def test_ollama_structured_request_uses_native_chat_schema() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_ollama_message('{"action":"HOLD"}'))

    async def scenario() -> str:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OllamaStructuredDecisionClient(
                base_url="http://localhost:11434/",
                http_client=http_client,
                retry_policy=NO_RETRY,
            )
            return await client.generate_structured_decision(
                model="qwen-local-test",
                instructions="system instructions",
                input_text='{"cycle_id":"x"}',
                schema=SCHEMA,
            )

    assert asyncio.run(scenario()) == '{"action":"HOLD"}'
    assert captured["url"] == "http://localhost:11434/api/chat"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["model"] == "qwen-local-test"
    assert body["stream"] is False
    assert body["format"] == SCHEMA
    assert body["messages"] == [
        {"role": "system", "content": "system instructions"},
        {"role": "user", "content": '{"cycle_id":"x"}'},
    ]
    assert "Authorization" not in dict(body)


def test_ollama_tool_loop_reuses_read_only_registry() -> None:
    requests: list[dict[str, object]] = []
    responses = [
        _ollama_message(
            "",
            tool_calls=[
                {"function": {"name": "facts", "arguments": {"symbol": "BTC/EUR"}}}
            ],
        ),
        _ollama_message('{"action":"HOLD"}'),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=responses.pop(0))

    class Registry:
        openai_tools = (
            {
                "type": "function",
                "name": "facts",
                "description": "read only",
                "parameters": {
                    "type": "object",
                    "properties": {"symbol": {"type": "string"}},
                    "required": ["symbol"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        )

        async def execute(self, *, call_id: str, name: str, arguments_json: str):
            assert call_id == "ollama-tool-1"
            assert name == "facts"
            assert arguments_json == '{"symbol":"BTC/EUR"}'
            return SimpleNamespace(
                trace=SimpleNamespace(call_id=call_id),
                function_output='{"ok":true,"data":{"price":"50000"}}',
            )

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OllamaStructuredDecisionClient(
                http_client=http_client,
                retry_policy=NO_RETRY,
            )
            return await client.generate_structured_decision_with_tools(
                model="qwen-local-test",
                instructions="tools",
                input_text="{}",
                schema=SCHEMA,
                tool_registry=Registry(),  # type: ignore[arg-type]
                max_tool_calls=2,
            )

    result = asyncio.run(scenario())
    assert result.output_text == '{"action":"HOLD"}'
    assert len(result.traces) == 1
    assert requests[0]["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "facts",
                "description": "read only",
                "parameters": Registry.openai_tools[0]["parameters"],
            },
        }
    ]
    second_messages = requests[1]["messages"]
    assert isinstance(second_messages, list)
    assert any(
        isinstance(item, dict)
        and item.get("role") == "tool"
        and item.get("tool_name") == "facts"
        for item in second_messages
    )


@pytest.mark.parametrize(
    ("failure_kind", "expected"),
    [
        ("network", LLMNetworkError),
        ("timeout", LLMTimeoutError),
    ],
)
def test_ollama_network_and_timeout_errors_are_fail_closed(
    failure_kind: str,
    expected: type[Exception],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if failure_kind == "network":
            raise httpx.ConnectError("offline", request=request)
        raise httpx.ReadTimeout("slow", request=request)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OllamaStructuredDecisionClient(
                http_client=http_client,
                retry_policy=NO_RETRY,
            )
            with pytest.raises(expected):
                await client.generate_structured_decision(
                    model="qwen-local-test",
                    instructions="x",
                    input_text="{}",
                    schema=SCHEMA,
                )

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [(404, LLMHTTPError), (429, LLMRateLimitError), (500, LLMServerError)],
)
def test_ollama_http_errors_are_mapped_fail_closed(
    status_code: int,
    expected: type[Exception],
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": "provider failure"})

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OllamaStructuredDecisionClient(
                http_client=http_client,
                retry_policy=NO_RETRY,
            )
            with pytest.raises(expected):
                await client.generate_structured_decision(
                    model="missing-model",
                    instructions="x",
                    input_text="{}",
                    schema=SCHEMA,
                )

    asyncio.run(scenario())


def test_ollama_invalid_response_envelope_is_rejected() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"model": "qwen-local-test", "done": True})

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OllamaStructuredDecisionClient(
                http_client=http_client,
                retry_policy=NO_RETRY,
            )
            with pytest.raises(LLMProviderError):
                await client.generate_structured_decision(
                    model="qwen-local-test",
                    instructions="x",
                    input_text="{}",
                    schema=SCHEMA,
                )

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "raw_output",
    [
        "not-json",
        '{"action":"BUY","symbol":"BTC/EUR","proposed_quantity":0.01}',
        '{"action":"WAIT","symbol":"BTC/EUR","proposed_quantity":null,"rationale":null}',
        '{"action":"BUY","symbol":"BTC/EUR","proposed_quantity":0,"rationale":null}',
    ],
)
def test_ollama_output_still_crosses_canonical_pydantic_validation(raw_output: str) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ollama_message(raw_output))

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OllamaStructuredDecisionClient(
                http_client=http_client,
                retry_policy=NO_RETRY,
            )
            provider = OpenAIDecisionProvider(
                client=client,  # type: ignore[arg-type]
                model="qwen-local-test",  # type: ignore[arg-type]
                clock=FixedClock(),
            )
            with pytest.raises(LLMOutputValidationError):
                await provider.generate_decision(_agent_input())

    asyncio.run(scenario())


def test_ollama_valid_decision_uses_same_agent_contract() -> None:
    raw = json.dumps(
        {
            "action": "BUY",
            "symbol": "BTC/EUR",
            "proposed_quantity": 0.01,
            "rationale": "local structured decision",
        }
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ollama_message(raw))

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OllamaStructuredDecisionClient(
                http_client=http_client,
                retry_policy=NO_RETRY,
            )
            provider = OpenAIDecisionProvider(
                client=client,  # type: ignore[arg-type]
                model="qwen-local-test",  # type: ignore[arg-type]
                clock=FixedClock(),
            )
            return await provider.generate_decision(_agent_input())

    decision = asyncio.run(scenario())
    assert decision.action is TradingAction.BUY
    assert decision.proposed_quantity == Decimal("0.01")


def test_local_paper_configuration_does_not_require_openai_key() -> None:
    settings = _paper_settings(openai_api_key=None)
    run = PaperRunConfiguration.from_settings(settings)

    assert run.llm_provider is LLMProviderKind.OLLAMA
    assert run.openai_api_key is None
    assert run.ollama_model == "qwen-local-test"


def test_openai_paper_configuration_still_requires_openai_key() -> None:
    settings = _paper_settings(llm_provider=LLMProviderKind.OPENAI, openai_api_key=None)
    with pytest.raises(PaperRuntimeConfigurationError, match="openai_api_key"):
        PaperRunConfiguration.from_settings(settings)


def test_openai_factory_preserves_existing_transport_and_model() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider=LLMProviderKind.OPENAI,
        llm_model=LLMModel.SOL,
        openai_api_key=SecretStr("test-only-openai-key"),
    )

    client, model = build_structured_decision_client(
        settings,
        openai_model=settings.llm_model,
    )

    assert isinstance(client, OpenAIResponsesClient)
    assert model is LLMModel.SOL


def test_local_factory_never_constructs_openai_client(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden_openai(**_: object) -> object:
        raise AssertionError("LOCAL must never construct OpenAIResponsesClient")

    monkeypatch.setattr(client_factory_module, "OpenAIResponsesClient", forbidden_openai)
    settings = Settings(
        _env_file=None,
        llm_provider=LLMProviderKind.OLLAMA,
        ollama_model="qwen-local-test",
        openai_api_key=None,
    )

    client, model = build_structured_decision_client(
        settings,
        openai_model=LLMModel.LUNA,
    )

    assert isinstance(client, OllamaStructuredDecisionClient)
    assert model == "qwen-local-test"


def test_ollama_audit_records_provider_model_success_and_failure() -> None:
    GLOBAL_LLM_AUDIT_STORE.clear_for_tests()
    responses = [
        httpx.Response(200, json=_ollama_message('{"action":"HOLD"}')),
        httpx.Response(404, json={"error": "model missing"}),
    ]

    def handler(_: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OllamaStructuredDecisionClient(
                http_client=http_client,
                retry_policy=NO_RETRY,
            )
            await client.generate_structured_decision(
                model="qwen-local-test",
                instructions="x",
                input_text=json.dumps({"cycle_id": str(CYCLE_ID)}),
                schema=SCHEMA,
            )
            with pytest.raises(LLMHTTPError):
                await client.generate_structured_decision(
                    model="qwen-local-test",
                    instructions="x",
                    input_text=json.dumps({"cycle_id": str(CYCLE_ID)}),
                    schema=SCHEMA,
                )

    asyncio.run(scenario())
    records = tuple(reversed(GLOBAL_LLM_AUDIT_STORE.list_records(limit=10)))
    assert [item.provider for item in records] == ["OLLAMA", "OLLAMA"]
    assert [item.model for item in records] == ["qwen-local-test", "qwen-local-test"]
    assert [item.status for item in records] == ["SUCCESS", "ERROR"]
    assert records[0].latency_ms is not None and records[0].latency_ms >= 0
    assert records[1].error_type == "LLMHTTPError"


def test_openai_audit_keeps_provider_status_and_latency_after_51_1() -> None:
    GLOBAL_LLM_AUDIT_STORE.clear_for_tests()
    responses = [
        httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "ok"}],
                    }
                ],
            },
        ),
        httpx.Response(500, json={"error": {"type": "server_error"}}),
    ]

    def handler(_: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OpenAIResponsesClient(
                api_key=SecretStr("test-only-openai-key"),
                http_client=http_client,
                retry_policy=NO_RETRY,
            )
            assert await client.generate_text_response(
                model=LLMModel.LUNA,
                instructions="x",
                input_text="{}",
            ) == "ok"
            with pytest.raises(LLMServerError):
                await client.generate_text_response(
                    model=LLMModel.LUNA,
                    instructions="x",
                    input_text="{}",
                )

    asyncio.run(scenario())
    records = tuple(reversed(GLOBAL_LLM_AUDIT_STORE.list_records(limit=10)))
    assert [item.provider for item in records] == ["OPENAI", "OPENAI"]
    assert [item.status for item in records] == ["SUCCESS", "ERROR"]
    assert all(item.model == "gpt-5.6-luna" for item in records)
    assert records[0].latency_ms is not None and records[0].latency_ms >= 0
    assert records[1].error_type == "LLMServerError"
