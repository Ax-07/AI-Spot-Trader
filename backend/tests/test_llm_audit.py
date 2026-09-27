import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from ai_spot_trader.agent.llm_audit import GLOBAL_LLM_AUDIT_STORE, llm_audit_context
from ai_spot_trader.agent.openai_client import OpenAIResponsesClient
from ai_spot_trader.api.routes.llm_audit import router
from ai_spot_trader.domain.enums import LLMModel


def _message(text: str) -> dict[str, object]:
    return {
        "status": "completed",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
    }


def test_structured_request_is_captured_exactly_without_transport_secrets() -> None:
    GLOBAL_LLM_AUDIT_STORE.clear_for_tests()
    cycle_id = uuid4()
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        assert request.headers["Authorization"] == "Bearer super-secret-openai-key"
        return httpx.Response(200, json=_message('{"action":"HOLD"}'))

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OpenAIResponsesClient(api_key=SecretStr("super-secret-openai-key"), http_client=http_client)
            await client.generate_structured_decision(
                model=LLMModel.LUNA,
                instructions="exact instructions",
                input_text=json.dumps({"cycle_id": str(cycle_id)}),
                schema={"type": "object", "additionalProperties": False},
            )

    asyncio.run(scenario())
    record = GLOBAL_LLM_AUDIT_STORE.list_records(limit=1)[0]
    assert record.request == seen[0]
    encoded = json.dumps(record.request)
    assert "super-secret-openai-key" not in encoded
    assert "Authorization" not in encoded
    assert record.cycle_id == cycle_id
    assert record.category == "STRATEGIC_SINGLETON"


def test_tool_loop_captures_tools_calls_outputs_and_order() -> None:
    GLOBAL_LLM_AUDIT_STORE.clear_for_tests()
    responses = [
        {
            "status": "completed",
            "output": [{"type": "function_call", "call_id": "call_1", "name": "facts", "arguments": "{}"}],
        },
        _message('{"action":"HOLD"}'),
    ]

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=responses.pop(0))

    class Registry:
        openai_tools = ({"type": "function", "name": "facts", "description": "read only", "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},)

        async def execute(self, *, call_id: str, name: str, arguments_json: str):
            assert (call_id, name, arguments_json) == ("call_1", "facts", "{}")
            return SimpleNamespace(trace=SimpleNamespace(call_id=call_id), function_output='{"ok":true}')

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OpenAIResponsesClient(api_key=SecretStr("test-key"), http_client=http_client)
            await client.generate_structured_decision_with_tools(
                model=LLMModel.LUNA,
                instructions="tools",
                input_text=json.dumps({"cycle_id": str(uuid4()), "strategic_plan_contract": {}}),
                schema={"type": "object"},
                tool_registry=Registry(),  # type: ignore[arg-type]
                max_tool_calls=2,
            )

    asyncio.run(scenario())
    records = tuple(reversed(GLOBAL_LLM_AUDIT_STORE.list_records(limit=10)))
    assert [item.sequence for item in records] == sorted(item.sequence for item in records)
    assert records[0].request["parallel_tool_calls"] is False
    assert records[0].request["tools"] == list(Registry.openai_tools)
    second_input = records[1].request["input"]
    assert isinstance(second_input, list)
    assert any(isinstance(item, dict) and item.get("type") == "function_call_output" and item.get("output") == '{"ok":true}' for item in second_input)
    assert records[0].response_output[0]["type"] == "function_call"


def test_operator_chat_call_is_captured_and_correlated_to_session() -> None:
    GLOBAL_LLM_AUDIT_STORE.clear_for_tests()
    session_id = uuid4()
    cycle_id = uuid4()

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_message("chat reply"))

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OpenAIResponsesClient(api_key=SecretStr("test-key"), http_client=http_client)
            with llm_audit_context(session_id=session_id, cycle_id=cycle_id):
                await client.generate_text_response(
                    model=LLMModel.LUNA,
                    instructions="operator chat",
                    input_text=json.dumps({"chat_history": [], "canonical_context": {"historical_cycle_id": str(cycle_id)}}),
                )

    asyncio.run(scenario())
    record = GLOBAL_LLM_AUDIT_STORE.list_records(limit=1)[0]
    assert record.category == "OPERATOR_CHAT"
    assert record.session_id == session_id
    assert record.cycle_id == cycle_id
    assert record.response_text == "chat reply"


def test_audit_failure_never_breaks_llm_response(monkeypatch) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_message("ok"))

    monkeypatch.setattr(GLOBAL_LLM_AUDIT_STORE, "append", lambda **_: (_ for _ in ()).throw(RuntimeError("audit down")))

    async def scenario() -> str:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OpenAIResponsesClient(api_key=SecretStr("test-key"), http_client=http_client)
            return await client.generate_text_response(model=LLMModel.LUNA, instructions="x", input_text="{}")

    assert asyncio.run(scenario()) == "ok"


def test_llm_audit_api_exposes_read_only_records() -> None:
    GLOBAL_LLM_AUDIT_STORE.clear_for_tests()
    GLOBAL_LLM_AUDIT_STORE.append(
        request={"model": "gpt-5.6-luna", "instructions": "x", "input": "{}", "store": False},
        response=_message("ok"),
    )
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).get("/api/v1/llm-audit")
    assert response.status_code == 200
    payload = response.json()
    assert payload["persistence"] == "PROCESS_MEMORY"
    assert payload["items"][0]["request"]["store"] is False
