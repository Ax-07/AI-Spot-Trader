from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pydantic import SecretStr

from ai_spot_trader.domain.enums import LLMModel
from ai_spot_trader.integrations.kraken.errors import (
    KrakenHTTPError,
    KrakenPayloadError,
    KrakenRateLimitError,
    KrakenServerError,
)
from ai_spot_trader.integrations.kraken.rest import (
    KrakenPublicRestClient,
    _parse_ohlcv_payload,
)
from ai_spot_trader.integrations.kraken.symbols import parse_asset_pairs_payload
from ai_spot_trader.integrations.openai_market_attention import (
    PUBLIC_ATTENTION_SCHEMA,
    OpenAIWebAttentionResearcher,
    PublicAttentionBadRequestError,
    PublicAttentionContractError,
    PublicAttentionHTTPError,
    PublicAttentionRequestError,
    PublicAttentionResponseError,
    PublicAttentionSchemaError,
    PublicAttentionRateLimitError,
    PublicAttentionServerError,
    PublicAttentionTransportError,
    PublicAttentionValidationError,
    _snapshot_from_payload,
)
from ai_spot_trader.market.attention import RadarStatus

NOW = datetime(2026, 9, 29, 10, 0, tzinfo=UTC)
SOURCE = "https://example.org/source"
INVENTED = "https://invented.invalid/not-provider-backed"


def _asset_pairs_payload() -> dict[str, object]:
    return {
        "error": [],
        "result": {
            "XXBTZUSD": {
                "altname": "XBTUSD",
                "wsname": "XBT/USD",
                "base": "XXBT",
                "quote": "ZUSD",
                "status": "online",
            }
        },
    }


def _ohlc_rows() -> list[list[object]]:
    start = NOW - timedelta(minutes=15)
    return [
        [int(start.timestamp()), "99", "101", "98", "100", "100", "1", 10],
        [
            int((start + timedelta(minutes=5)).timestamp()),
            "100",
            "102",
            "99",
            "101",
            "101",
            "2",
            11,
        ],
        [
            int((start + timedelta(minutes=10)).timestamp()),
            "101",
            "103",
            "100",
            "102",
            "102",
            "3",
            12,
        ],
    ]


def _public_payload(*, source_url: str | None = SOURCE) -> dict[str, object]:
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
        "sources": [{"title": "Source", "url": SOURCE, "published_at": None}],
    }


def _completed_response(payload: dict[str, object] | None = None) -> dict[str, object]:
    structured = payload or _public_payload()
    return {
        "status": "completed",
        "output": [
            {
                "type": "web_search_call",
                "action": {
                    "type": "search",
                    "sources": [{"url": SOURCE, "title": "Source"}],
                },
            },
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(structured),
                        "annotations": [
                            {"type": "url_citation", "url": SOURCE, "title": "Source"}
                        ],
                    }
                ],
            },
        ],
    }


def _schema_keywords(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        found.update(value)
        for child in value.values():
            found.update(_schema_keywords(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_schema_keywords(child))
    return found


def test_asset_pairs_accepts_documented_internal_key_and_keeps_canonical_aliases() -> None:
    registry = parse_asset_pairs_payload(_asset_pairs_payload())

    assert registry.normalize("BTC/USD") == "BTC/USD"
    assert registry.normalize("XBT/USD") == "BTC/USD"
    assert registry.normalize("XBTUSD") == "BTC/USD"
    assert registry.normalize("XXBTZUSD") == "BTC/USD"
    assert registry.pairs[0].symbol == "BTC/USD"


def test_asset_pairs_display_key_remains_supported() -> None:
    registry = parse_asset_pairs_payload(
        {
            "error": [],
            "result": {
                "BTC/EUR": {
                    "altname": "XBTEUR",
                    "wsname": "XBT/EUR",
                    "status": "online",
                }
            },
        }
    )
    assert registry.normalize("BTC/EUR") == "BTC/EUR"
    assert registry.normalize("XBT/EUR") == "BTC/EUR"


def test_asset_pairs_invalid_entry_and_symbol_have_bounded_stages() -> None:
    with pytest.raises(KrakenPayloadError) as entry_info:
        parse_asset_pairs_payload({"error": [], "result": {1: {}}})
    assert entry_info.value.stage == "ASSET_PAIRS_ENTRY"

    with pytest.raises(KrakenPayloadError) as symbol_info:
        parse_asset_pairs_payload(
            {
                "error": [],
                "result": {
                    "XXBTZUSD": {
                        "altname": "XBTUSD",
                        "wsname": "XBT/USD",
                        "base": "XETH",
                        "quote": "ZUSD",
                        "status": "online",
                    }
                },
            }
        )
    assert symbol_info.value.stage == "ASSET_PAIRS_SYMBOL"


@pytest.mark.parametrize("pair_key", ["BTC/USD", "XBT/USD", "XXBTZUSD"])
def test_ohlcv_accepts_display_alias_and_legacy_internal_pair_keys(pair_key: str) -> None:
    candles = _parse_ohlcv_payload(
        {"error": [], "result": {pair_key: _ohlc_rows(), "last": 1}},
        interval_minutes=5,
        expected_symbol="BTC/USD",
        received_at=NOW,
    )
    assert len(candles) == 3
    assert candles[0].close_price == 100


def test_ohlcv_rejects_wrong_display_symbol_with_pair_key_stage() -> None:
    with pytest.raises(KrakenPayloadError) as exc_info:
        _parse_ohlcv_payload(
            {"error": [], "result": {"ETH/USD": _ohlc_rows(), "last": 1}},
            interval_minutes=5,
            expected_symbol="BTC/USD",
            received_at=NOW,
        )
    assert exc_info.value.stage == "OHLC_PAIR_KEY"


@pytest.mark.parametrize(
    ("row_mutator", "expected_stage"),
    [
        (lambda rows: rows.__setitem__(0, [1, 2]), "OHLC_ROW"),
        (lambda rows: rows[0].__setitem__(0, "not-a-timestamp"), "OHLC_TIMESTAMP"),
        (lambda rows: rows[0].__setitem__(4, "not-a-number"), "OHLC_NUMERIC"),
    ],
)
def test_ohlcv_row_timestamp_numeric_failures_have_deterministic_stages(
    row_mutator,
    expected_stage: str,
) -> None:
    rows = _ohlc_rows()
    row_mutator(rows)
    with pytest.raises(KrakenPayloadError) as exc_info:
        _parse_ohlcv_payload(
            {"error": [], "result": {"XXBTZUSD": rows, "last": 1}},
            interval_minutes=5,
            expected_symbol="BTC/USD",
            received_at=NOW,
        )
    assert exc_info.value.stage == expected_stage


def test_normal_spot_registry_then_ohlcv_flow_succeeds_with_internal_keys() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/AssetPairs"):
                return httpx.Response(200, json=_asset_pairs_payload(), request=request)
            if request.url.path.endswith("/OHLC"):
                return httpx.Response(
                    200,
                    json={"error": [], "result": {"XXBTZUSD": _ohlc_rows(), "last": 1}},
                    request=request,
                )
            raise AssertionError(request.url.path)

        async with httpx.AsyncClient(
            base_url="https://api.kraken.test",
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = KrakenPublicRestClient("https://api.kraken.test", client=http_client)
            registry = await client.fetch_pair_registry()
            symbol = registry.normalize("BTC/USD")
            candles = await client.fetch_ohlcv_history(
                symbol,
                interval_minutes=5,
                since=NOW - timedelta(hours=1),
            )
        assert symbol == "BTC/USD"
        assert len(candles) == 3

    asyncio.run(scenario())


def test_kraken_payload_log_exposes_only_operation_and_stage(caplog) -> None:
    secret = "PRIVATE-PROVIDER-VALUE"

    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "error": [],
                    "result": {
                        secret: {
                            "altname": "XBTUSD",
                            "wsname": "XBT/USD",
                            "base": "XETH",
                            "quote": "ZUSD",
                            "status": "online",
                        }
                    },
                },
                request=request,
            )

        async with httpx.AsyncClient(
            base_url="https://api.kraken.test",
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = KrakenPublicRestClient("https://api.kraken.test", client=http_client)
            with pytest.raises(KrakenPayloadError) as exc_info:
                await client.fetch_pair_registry()
        assert exc_info.value.stage == "ASSET_PAIRS_SYMBOL"

    with caplog.at_level("WARNING"):
        asyncio.run(scenario())
    text = caplog.text
    assert "operation=AssetPairs" in text
    assert "stage=ASSET_PAIRS_SYMBOL" in text
    assert secret not in text
    assert "XBT/USD" not in text


def test_kraken_http_429_5xx_and_permanent_http_classification_is_unchanged() -> None:
    async def classify(status_code: int) -> Exception:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code, text="private body", request=request)

        async with httpx.AsyncClient(
            base_url="https://api.kraken.test",
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = KrakenPublicRestClient("https://api.kraken.test", client=http_client)
            with pytest.raises(Exception) as exc_info:
                await client.fetch_pair_registry()
            return exc_info.value

    assert isinstance(asyncio.run(classify(429)), KrakenRateLimitError)
    assert isinstance(asyncio.run(classify(503)), KrakenServerError)
    assert isinstance(asyncio.run(classify(403)), KrakenHTTPError)


def test_public_attention_wire_schema_uses_supported_subset_without_length_keywords() -> None:
    keywords = _schema_keywords(PUBLIC_ATTENTION_SCHEMA)
    assert "minLength" not in keywords
    assert "maxLength" not in keywords


def test_public_attention_pydantic_limit_remains_active_with_value_free_diagnostic(caplog) -> None:
    payload = _public_payload()
    secret_value = "DO-NOT-LOG-" + ("x" * 200)
    payload["quantitative_metrics"][0]["name"] = secret_value  # type: ignore[index]

    with caplog.at_level("WARNING"):
        with pytest.raises(PublicAttentionValidationError) as exc_info:
            _snapshot_from_payload(
                payload,
                asset="APE",
                observed_at=NOW,
                provider_sources={SOURCE: "Source"},
                provider_citations={SOURCE},
            )

    error = exc_info.value
    assert error.validation_path == "quantitative_metrics[0].name"
    assert error.validation_code == "string_too_long"
    assert error.validation_error_count == 1
    assert secret_value not in str(error)
    assert secret_value not in caplog.text
    assert "path=quantitative_metrics[0].name" in caplog.text
    assert "code=string_too_long" in caplog.text


def test_public_attention_second_invalid_shape_reports_bounded_path_without_relaxing_model() -> None:
    payload = _public_payload()
    payload["qualitative_observations"][0]["text"] = "z" * 2001  # type: ignore[index]

    with pytest.raises(PublicAttentionValidationError) as exc_info:
        _snapshot_from_payload(
            payload,
            asset="2Z",
            observed_at=NOW,
            provider_sources={SOURCE: "Source"},
            provider_citations={SOURCE},
        )
    assert exc_info.value.validation_path == "qualitative_observations[0].text"
    assert exc_info.value.validation_code == "string_too_long"


def test_public_attention_transport_http_rate_limit_and_server_errors_are_distinct() -> None:
    async def transport_error() -> Exception:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("private transport detail", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OpenAIWebAttentionResearcher(
                api_key=SecretStr("test-key"),
                model=LLMModel.LUNA,
                http_client=http_client,
                max_attempts=1,
            )
            with pytest.raises(Exception) as exc_info:
                await client.research(asset="AAVE", symbols=("AAVE/USD",), observed_at=NOW)
            return exc_info.value

    async def http_error(status_code: int) -> Exception:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code, text="private body", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OpenAIWebAttentionResearcher(
                api_key=SecretStr("test-key"),
                model=LLMModel.LUNA,
                http_client=http_client,
                max_attempts=1,
            )
            with pytest.raises(Exception) as exc_info:
                await client.research(asset="APE", symbols=("APE/USD",), observed_at=NOW)
            return exc_info.value

    assert isinstance(asyncio.run(transport_error()), PublicAttentionTransportError)
    assert isinstance(asyncio.run(http_error(400)), PublicAttentionHTTPError)
    assert isinstance(asyncio.run(http_error(429)), PublicAttentionRateLimitError)
    assert isinstance(asyncio.run(http_error(503)), PublicAttentionServerError)


def test_public_attention_request_invariants_and_source_trust_are_unchanged() -> None:
    async def scenario() -> tuple[dict[str, object], object]:
        captured: dict[str, object] = {}
        payload = _public_payload(source_url=INVENTED)
        payload["sources"] = [
            {"title": "Invented", "url": INVENTED, "published_at": None}
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            return httpx.Response(200, json=_completed_response(payload), request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OpenAIWebAttentionResearcher(
                api_key=SecretStr("test-key"),
                model=LLMModel.LUNA,
                http_client=http_client,
                max_attempts=1,
            )
            snapshot = await client.research(
                asset="APE",
                symbols=("APE/USD",),
                observed_at=NOW,
            )
        return captured, snapshot

    request, snapshot = asyncio.run(scenario())
    assert request["store"] is False
    assert request["tools"] == [{"type": "web_search"}]
    assert request["include"] == ["web_search_call.action.sources"]
    assert request["text"]["format"]["strict"] is True  # type: ignore[index]
    assert snapshot.research_status is RadarStatus.AVAILABLE
    assert snapshot.quantitative_metrics[0].source_url is None
    assert INVENTED not in {source.url for source in snapshot.sources}
    assert [source.url for source in snapshot.sources] == [SOURCE]


def test_http_400_uses_schema_error_and_batch34_compatibility_aliases() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": {"type": "invalid_json_schema"}}, request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OpenAIWebAttentionResearcher(
                api_key=SecretStr("test-key"),
                model=LLMModel.LUNA,
                http_client=http_client,
                max_attempts=1,
            )
            with pytest.raises(PublicAttentionSchemaError) as exc_info:
                await client.research(asset="APE", symbols=("APE/USD",), observed_at=NOW)

        assert exc_info.value.status_code == 400
        assert PublicAttentionBadRequestError is PublicAttentionSchemaError
        assert PublicAttentionRequestError is PublicAttentionSchemaError
        assert PublicAttentionContractError is PublicAttentionSchemaError
        assert PublicAttentionResponseError is PublicAttentionHTTPError

    asyncio.run(scenario())
