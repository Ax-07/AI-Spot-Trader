from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import httpx
import pytest
from pydantic import SecretStr

from ai_spot_trader.domain.enums import LLMModel
from ai_spot_trader.integrations.openai_market_attention import (
    PUBLIC_ATTENTION_SCHEMA,
    OpenAIWebAttentionResearcher,
    PublicAttentionContractError,
    PublicAttentionIncompleteError,
    PublicAttentionRateLimitError,
    PublicAttentionResearchError,
    PublicAttentionServerError,
    PublicAttentionTransportError,
    PublicAttentionValidationError,
    _snapshot_from_payload,
)
from ai_spot_trader.market.attention import RadarStatus

NOW = datetime(2026, 9, 29, 8, 0, tzinfo=UTC)
USED = "https://example.org/used"
UNUSED = "https://example.org/unused"
INVENTED = "https://invented.invalid/not-provider-backed"


def _payload(*, source_url: str | None = USED) -> dict[str, object]:
    return {
        "attention_direction": "RISING",
        "confidence_context": "Recent public attention is rising with bounded source coverage.",
        "quantitative_metrics": [
            {
                "name": "mentions",
                "value": "430",
                "unit": "mentions",
                "window": "24h rolling",
                "source_url": source_url,
                "published_at": None,
            }
        ],
        "qualitative_observations": [
            {"text": "Discussion activity increased.", "source_url": source_url}
        ],
        "possible_catalysts": [
            {"description": "Official project announcement.", "source_url": source_url}
        ],
        "sources": [
            {"title": "Used source", "url": USED, "published_at": None},
            {"title": "Unused source", "url": UNUSED, "published_at": None},
        ],
    }


def _schema_keywords(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            found.add(key)
            found.update(_schema_keywords(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_schema_keywords(child))
    return found


def test_structured_output_schema_uses_supported_wire_subset() -> None:
    keywords = _schema_keywords(PUBLIC_ATTENTION_SCHEMA)
    assert "minLength" not in keywords
    assert "maxLength" not in keywords
    assert PUBLIC_ATTENTION_SCHEMA["additionalProperties"] is False
    assert PUBLIC_ATTENTION_SCHEMA["properties"]["confidence_context"] == {
        "type": "string"
    }


def test_payload_at_canonical_maximum_lengths_is_accepted() -> None:
    payload = _payload()
    payload["confidence_context"] = "c" * 2000
    metric = payload["quantitative_metrics"][0]  # type: ignore[index]
    metric["name"] = "n" * 128  # type: ignore[index]
    metric["value"] = "v" * 256  # type: ignore[index]
    metric["unit"] = "u" * 64  # type: ignore[index]
    metric["window"] = "w" * 64  # type: ignore[index]
    payload["qualitative_observations"][0]["text"] = "o" * 2000  # type: ignore[index]
    payload["possible_catalysts"][0]["description"] = "d" * 2000  # type: ignore[index]
    payload["sources"][0]["title"] = "t" * 1000  # type: ignore[index]

    snapshot = _snapshot_from_payload(
        payload,
        asset="QNT",
        observed_at=NOW,
        provider_sources={USED: "Provider title"},
        provider_citations={USED},
    )

    assert snapshot.research_status is RadarStatus.AVAILABLE
    assert len(snapshot.confidence_context) == 2000
    assert len(snapshot.quantitative_metrics[0].name) == 128
    assert len(snapshot.sources[0].title) == 1000


def test_exposed_sources_prioritize_structured_references_and_provider_citations() -> None:
    snapshot = _snapshot_from_payload(
        _payload(),
        asset="QNT",
        observed_at=NOW,
        provider_sources={USED: "Used", UNUSED: "Unused"},
        provider_citations=set(),
    )
    assert [source.url for source in snapshot.sources] == [USED]

    cited = _snapshot_from_payload(
        _payload(source_url=None),
        asset="QNT",
        observed_at=NOW,
        provider_sources={USED: "Used", UNUSED: "Unused"},
        provider_citations={UNUSED},
    )
    assert [source.url for source in cited.sources] == [UNUSED]


def test_structured_url_absent_from_provider_metadata_is_never_canonical() -> None:
    payload = _payload(source_url=INVENTED)
    payload["sources"] = [
        {"title": "Invented", "url": INVENTED, "published_at": None}
    ]
    snapshot = _snapshot_from_payload(
        payload,
        asset="QNT",
        observed_at=NOW,
        provider_sources={USED: "Provider-backed fallback"},
        provider_citations=set(),
    )

    assert snapshot.quantitative_metrics[0].source_url is None
    assert INVENTED not in {source.url for source in snapshot.sources}
    assert [source.url for source in snapshot.sources] == [USED]


def test_absence_of_provider_source_stays_partial_without_false_available() -> None:
    snapshot = _snapshot_from_payload(
        _payload(),
        asset="QNT",
        observed_at=NOW,
        provider_sources={},
        provider_citations=set(),
    )
    assert snapshot.research_status is RadarStatus.PARTIAL
    assert snapshot.sources == ()
    assert snapshot.quantitative_metrics[0].source_url is None
    assert len(snapshot.confidence_context) <= 2000


def test_canonical_validation_failure_is_wrapped_as_validation_error() -> None:
    payload = _payload()
    payload["quantitative_metrics"][0]["name"] = "x" * 129  # type: ignore[index]

    with pytest.raises(PublicAttentionValidationError, match="canonical validation"):
        _snapshot_from_payload(
            payload,
            asset="QNT",
            observed_at=NOW,
            provider_sources={USED: "Used"},
            provider_citations={USED},
        )


def test_request_keeps_web_search_store_include_and_strict_schema() -> None:
    async def scenario() -> None:
        captured: dict[str, object] = {}
        structured = _payload()

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "output": [
                        {
                            "type": "web_search_call",
                            "action": {
                                "type": "search",
                                "sources": [{"url": USED, "title": "Used"}],
                            },
                        },
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps(structured),
                                    "annotations": [
                                        {"type": "url_citation", "url": USED, "title": "Used"}
                                    ],
                                }
                            ],
                        },
                    ],
                },
                request=request,
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            researcher = OpenAIWebAttentionResearcher(
                api_key=SecretStr("test-key"),
                model=LLMModel.LUNA,
                http_client=http_client,
            )
            snapshot = await researcher.research(
                asset="QNT",
                symbols=("QNT/USD",),
                observed_at=NOW,
            )

        assert captured["store"] is False
        assert captured["tools"] == [{"type": "web_search"}]
        assert captured["include"] == ["web_search_call.action.sources"]
        assert captured["text"]["format"]["strict"] is True  # type: ignore[index]
        assert captured["text"]["format"]["schema"] == PUBLIC_ATTENTION_SCHEMA  # type: ignore[index]
        assert snapshot.research_status is RadarStatus.AVAILABLE

    asyncio.run(scenario())


def test_http_400_contract_429_and_5xx_are_distinct_and_sanitized() -> None:
    async def classify(status_code: int) -> Exception:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                status_code,
                text='{"error":{"message":"secret provider detail"}}',
                request=request,
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            researcher = OpenAIWebAttentionResearcher(
                api_key=SecretStr("test-key"),
                model=LLMModel.LUNA,
                http_client=http_client,
                max_attempts=1,
            )
            try:
                await researcher.research(asset="QNT", symbols=("QNT/USD",), observed_at=NOW)
            except Exception as exc:  # noqa: BLE001 - test captures exact public type below
                return exc
        raise AssertionError("expected request to fail")

    contract = asyncio.run(classify(400))
    rate = asyncio.run(classify(429))
    server = asyncio.run(classify(503))

    assert isinstance(contract, PublicAttentionContractError)
    assert isinstance(rate, PublicAttentionRateLimitError)
    assert isinstance(server, PublicAttentionServerError)
    for exc in (contract, rate, server):
        assert isinstance(exc, PublicAttentionResearchError)
        assert "secret provider detail" not in str(exc)


def test_transport_and_incomplete_response_are_distinct() -> None:
    async def transport_scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("private transport detail", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            researcher = OpenAIWebAttentionResearcher(
                api_key=SecretStr("test-key"),
                model=LLMModel.LUNA,
                http_client=http_client,
                max_attempts=1,
            )
            with pytest.raises(PublicAttentionTransportError) as exc_info:
                await researcher.research(asset="QNT", symbols=("QNT/USD",), observed_at=NOW)
            assert "private transport detail" not in str(exc_info.value)

    async def incomplete_scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"status": "incomplete", "output": []},
                request=request,
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            researcher = OpenAIWebAttentionResearcher(
                api_key=SecretStr("test-key"),
                model=LLMModel.LUNA,
                http_client=http_client,
            )
            with pytest.raises(PublicAttentionIncompleteError):
                await researcher.research(asset="QNT", symbols=("QNT/USD",), observed_at=NOW)

    asyncio.run(transport_scenario())
    asyncio.run(incomplete_scenario())
