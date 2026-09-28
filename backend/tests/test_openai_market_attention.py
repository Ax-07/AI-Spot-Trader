from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import httpx
import pytest
from pydantic import SecretStr

from ai_spot_trader.domain.enums import LLMModel
from ai_spot_trader.integrations.openai_market_attention import (
    OpenAIWebAttentionResearcher,
    PublicAttentionResearchError,
)
from ai_spot_trader.market.attention import PublicAttentionDirection, RadarStatus

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


def completed_response(*, include_sources: bool = True) -> dict[str, object]:
    source = "https://example.org/qnt-news"
    structured = {
        "attention_direction": "RISING",
        "confidence_context": (
            "Recent public attention is rising, but source coverage is not exhaustive."
        ),
        "quantitative_metrics": [
            {
                "name": "mentions",
                "value": "430",
                "unit": "mentions",
                "window": "24h rolling",
                "source_url": source,
                "published_at": None,
            }
        ],
        "qualitative_observations": [
            {"text": "Discussion activity increased.", "source_url": source}
        ],
        "possible_catalysts": [
            {"description": "Official project announcement.", "source_url": source}
        ],
        "sources": [{"title": "QNT update", "url": source, "published_at": None}],
    }
    output: list[dict[str, object]] = []
    if include_sources:
        output.append(
            {
                "type": "web_search_call",
                "action": {
                    "type": "search",
                    "sources": [{"url": source, "title": "QNT update"}],
                },
            }
        )
    output.append(
        {
            "type": "message",
            "content": [
                {
                    "type": "output_text",
                    "text": json.dumps(structured),
                    "annotations": (
                        [{"type": "url_citation", "url": source, "title": "QNT update"}]
                        if include_sources
                        else []
                    ),
                }
            ],
        }
    )
    return {"status": "completed", "output": output}


def test_openai_web_attention_uses_hosted_web_search_structured_output_and_sources() -> None:
    async def scenario() -> None:
        requests: list[dict[str, object]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(json.loads(request.content))
            return httpx.Response(200, json=completed_response(), request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OpenAIWebAttentionResearcher(
                api_key=SecretStr("test-key"),
                model=LLMModel.LUNA,
                http_client=http_client,
            )
            snapshot = await client.research(asset="QNT", symbols=("QNT/USD",), observed_at=NOW)

        body = requests[0]
        assert body["store"] is False
        assert body["tools"] == [{"type": "web_search"}]
        assert body["include"] == ["web_search_call.action.sources"]
        assert body["text"]["format"]["type"] == "json_schema"  # type: ignore[index]
        assert body["text"]["format"]["strict"] is True  # type: ignore[index]
        assert snapshot.research_status is RadarStatus.AVAILABLE
        assert snapshot.attention_direction is PublicAttentionDirection.RISING
        assert snapshot.quantitative_metrics[0].window == "24h rolling"
        assert snapshot.sources[0].url == "https://example.org/qnt-news"
        assert snapshot.sources[0].source_domain == "example.org"

    asyncio.run(scenario())


def test_openai_web_attention_marks_partial_without_provider_source_metadata() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=completed_response(include_sources=False),
                request=request,
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OpenAIWebAttentionResearcher(
                api_key=SecretStr("test-key"),
                model=LLMModel.LUNA,
                http_client=http_client,
            )
            snapshot = await client.research(asset="QNT", symbols=("QNT/USD",), observed_at=NOW)
        assert snapshot.research_status is RadarStatus.PARTIAL
        assert snapshot.sources == ()
        assert snapshot.quantitative_metrics[0].source_url is None

    asyncio.run(scenario())


def test_openai_web_attention_retries_bounded_transient_failure() -> None:
    async def scenario() -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(503, json={"error": {"type": "server_error"}}, request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OpenAIWebAttentionResearcher(
                api_key=SecretStr("test-key"),
                model=LLMModel.LUNA,
                http_client=http_client,
                max_attempts=2,
            )
            with pytest.raises(PublicAttentionResearchError):
                await client.research(asset="QNT", symbols=("QNT/USD",), observed_at=NOW)
        assert calls == 2

    asyncio.run(scenario())


def test_openai_web_attention_prompt_forbids_trading_recommendations() -> None:
    async def scenario() -> None:
        captured = ""

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured
            payload = json.loads(request.content)
            captured = payload["instructions"]
            return httpx.Response(200, json=completed_response(), request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OpenAIWebAttentionResearcher(
                api_key=SecretStr("test-key"),
                model=LLMModel.LUNA,
                http_client=http_client,
            )
            await client.research(asset="QNT", symbols=("QNT/USD",), observed_at=NOW)
        assert "BUY, SELL ou HOLD" in captured
        assert "aucune probabilite de hausse ou baisse" in captured
        assert "n'influence pas le trading" in captured

    asyncio.run(scenario())
