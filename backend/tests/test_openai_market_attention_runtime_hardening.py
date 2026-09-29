from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ai_spot_trader.integrations.openai_market_attention import (
    PUBLIC_ATTENTION_SCHEMA,
    PublicAttentionResearchError,
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


def test_structured_output_schema_matches_canonical_string_limits() -> None:
    props = PUBLIC_ATTENTION_SCHEMA["properties"]
    assert props["confidence_context"] == {
        "type": "string",
        "minLength": 1,
        "maxLength": 2000,
    }

    metric = props["quantitative_metrics"]["items"]["properties"]
    assert metric["name"]["minLength"] == 1
    assert metric["name"]["maxLength"] == 128
    assert metric["value"]["maxLength"] == 256
    assert metric["unit"]["anyOf"][0]["maxLength"] == 64
    assert metric["window"]["anyOf"][0]["maxLength"] == 64
    assert metric["source_url"]["anyOf"][0]["maxLength"] == 2048

    observation = props["qualitative_observations"]["items"]["properties"]
    catalyst = props["possible_catalysts"]["items"]["properties"]
    source = props["sources"]["items"]["properties"]
    assert observation["text"]["maxLength"] == 2000
    assert catalyst["description"]["maxLength"] == 2000
    assert source["title"]["maxLength"] == 1000
    assert source["url"]["maxLength"] == 2048


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


def test_canonical_validation_failure_is_wrapped_as_research_error() -> None:
    payload = _payload()
    payload["quantitative_metrics"][0]["name"] = "x" * 129  # type: ignore[index]

    with pytest.raises(PublicAttentionResearchError, match="canonical validation"):
        _snapshot_from_payload(
            payload,
            asset="QNT",
            observed_at=NOW,
            provider_sources={USED: "Used"},
            provider_citations={USED},
        )
