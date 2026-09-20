import asyncio
import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from ai_spot_trader.agent import (
    STRATEGIC_DECISION_SCHEMA,
    LLMProviderError,
    LLMTransportError,
    OpenAIResponsesClient,
)
from ai_spot_trader.domain.enums import LLMModel

API_KEY = "test-only-openai-secret"
OUTPUT_TEXT = (
    '{"action":"HOLD","symbol":"BTC/EUR",'
    '"proposed_quantity":null,"rationale":null}'
)


def _completed_response(text: str = OUTPUT_TEXT) -> dict[str, Any]:
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
    }


def _run(client: OpenAIResponsesClient) -> str:
    return asyncio.run(
        client.generate_structured_decision(
            model=LLMModel.LUNA,
            instructions="system prompt",
            input_text='{"cycle_id":"test"}',
            schema=STRATEGIC_DECISION_SCHEMA,
        )
    )


def test_responses_client_uses_structured_outputs_without_network() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_completed_response())

    async def scenario() -> str:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OpenAIResponsesClient(
                api_key=SecretStr(API_KEY),
                http_client=http_client,
            )
            return await client.generate_structured_decision(
                model=LLMModel.LUNA,
                instructions="system prompt",
                input_text='{"cycle_id":"test"}',
                schema=STRATEGIC_DECISION_SCHEMA,
            )

    result = asyncio.run(scenario())

    assert result == OUTPUT_TEXT
    assert captured["url"] == "https://api.openai.com/v1/responses"
    assert captured["authorization"] == f"Bearer {API_KEY}"
    body = captured["body"]
    assert body["model"] == "gpt-5.6-luna"
    assert body["store"] is False
    assert "tools" not in body
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["text"]["format"]["strict"] is True
    assert body["text"]["format"]["schema"]["additionalProperties"] is False
    assert set(body["text"]["format"]["schema"]["required"]) == {
        "action",
        "symbol",
        "proposed_quantity",
        "rationale",
    }


def test_http_failure_does_not_expose_secret() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": API_KEY}})

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OpenAIResponsesClient(
                api_key=SecretStr(API_KEY),
                http_client=http_client,
            )
            with pytest.raises(LLMTransportError) as exc_info:
                await client.generate_structured_decision(
                    model=LLMModel.LUNA,
                    instructions="system prompt",
                    input_text="{}",
                    schema=STRATEGIC_DECISION_SCHEMA,
                )
            assert API_KEY not in str(exc_info.value)

    asyncio.run(scenario())


def test_transport_error_is_explicit_and_has_no_retry() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("offline", request=request)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OpenAIResponsesClient(
                api_key=SecretStr(API_KEY),
                http_client=http_client,
            )
            with pytest.raises(LLMTransportError):
                await client.generate_structured_decision(
                    model=LLMModel.LUNA,
                    instructions="system prompt",
                    input_text="{}",
                    schema=STRATEGIC_DECISION_SCHEMA,
                )

    asyncio.run(scenario())
    assert calls == 1


@pytest.mark.parametrize(
    "response",
    [
        {"status": "incomplete", "output": []},
        {"status": "completed"},
        {"status": "completed", "output": []},
        {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "refusal", "refusal": "cannot comply"}],
                }
            ],
        },
    ],
)
def test_incomplete_or_refused_provider_response_is_rejected(
    response: dict[str, Any],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OpenAIResponsesClient(
                api_key=SecretStr(API_KEY),
                http_client=http_client,
            )
            with pytest.raises(LLMProviderError):
                await client.generate_structured_decision(
                    model=LLMModel.LUNA,
                    instructions="system prompt",
                    input_text="{}",
                    schema=STRATEGIC_DECISION_SCHEMA,
                )

    asyncio.run(scenario())


def test_provider_response_with_multiple_output_text_parts_is_rejected() -> None:
    response = _completed_response()
    response["output"][0]["content"].append(
        {"type": "output_text", "text": OUTPUT_TEXT}
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OpenAIResponsesClient(
                api_key=SecretStr(API_KEY),
                http_client=http_client,
            )
            with pytest.raises(LLMProviderError):
                await client.generate_structured_decision(
                    model=LLMModel.LUNA,
                    instructions="system prompt",
                    input_text="{}",
                    schema=STRATEGIC_DECISION_SCHEMA,
                )

    asyncio.run(scenario())
