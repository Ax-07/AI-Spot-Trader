from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from ai_spot_trader.domain.enums import DerivativeContractKind, MarketType
from ai_spot_trader.domain.models import DerivativeInstrument
from ai_spot_trader.integrations.kraken.analytics import (
    KrakenDerivativesAnalyticsClient,
    parse_kraken_open_interest_history,
)
from ai_spot_trader.integrations.kraken.errors import KrakenConnectionError, KrakenPayloadError

SINCE = datetime(2026, 10, 1, 0, 0, tzinfo=UTC)
UNTIL = datetime(2026, 10, 1, 3, 0, tzinfo=UTC)


def _instrument() -> DerivativeInstrument:
    return DerivativeInstrument(
        symbol="BTC/USD",
        venue_symbol="PF_XBTUSD",
        market_type=MarketType.PERPETUAL,
        contract_kind=DerivativeContractKind.LINEAR,
        underlying_asset="BTC",
        quote_asset="USD",
        contract_size=Decimal("1"),
        tick_size=Decimal("1"),
        min_order_quantity=Decimal("0.01"),
        initial_margin_rate=Decimal("0.10"),
        maintenance_margin_rate=Decimal("0.05"),
        max_leverage=Decimal("10"),
        funding_interval_seconds=Decimal("3600"),
    )


def _bucket(close: str, *, open_value: str | None = None) -> list[str]:
    resolved_open = open_value or close
    high = str(max(Decimal(resolved_open), Decimal(close)) + Decimal("1"))
    low = str(max(Decimal("0"), min(Decimal(resolved_open), Decimal(close)) - Decimal("1")))
    return [resolved_open, high, low, close]


def _payload(*values: object, more: bool = False) -> dict[str, object]:
    timestamps = [int(SINCE.timestamp()) + index * 3600 for index in range(len(values))]
    data = [value if isinstance(value, list) else _bucket(str(value)) for value in values]
    return {"result": {"timestamp": timestamps, "data": data, "more": more}}


def test_open_interest_parser_accepts_live_ohlc_shape_and_uses_bucket_close(
) -> None:
    payload = {
        "result": {
            "timestamp": [
                int(SINCE.timestamp()),
                int(SINCE.timestamp()) + 3600,
                int(SINCE.timestamp()) + 7200,
            ],
            "data": [
                ["100", "103", "98", "101"],
                ["101", "104", "100", "102.5"],
                ["102.5", "103", "97", "99"],
            ],
            "more": False,
        },
        "errors": [],
    }
    points = parse_kraken_open_interest_history(payload)
    assert [point.observed_at for point in points] == [
        SINCE,
        datetime(2026, 10, 1, 1, 0, tzinfo=UTC),
        datetime(2026, 10, 1, 2, 0, tzinfo=UTC),
    ]
    assert [point.value for point in points] == [Decimal("101"), Decimal("102.5"), Decimal("99")]
    assert points[0].open == Decimal("100")
    assert points[0].high == Decimal("103")
    assert points[0].low == Decimal("98")
    assert points[0].close == Decimal("101")


def test_open_interest_parser_accepts_pf_xbtusd_live_smoke_shape() -> None:
    payload = {
        "result": {
            "timestamp": [
                1791122400,
                1791126000,
                1791129600,
                1791133200,
                1791136800,
                1791140400,
            ],
            "data": [
                ["2113.6645", "2115.6165", "2109.5432", "2112.2841"],
                ["2112.2841", "2144.3341", "2109.0608", "2142.3721"],
                ["2142.3721", "2162.2428", "2139.8603", "2156.3522"],
                ["2156.3522", "2157.1081", "2154.2089", "2156.0687"],
                ["2156.0687", "2157.6094", "2151.077", "2151.584"],
                ["2151.584", "2153.2709", "2137.4065", "2137.5492"],
            ],
            "more": False,
        },
        "errors": [],
    }
    points = parse_kraken_open_interest_history(payload)
    assert len(points) == 6
    assert points[0].value == Decimal("2112.2841")
    assert points[-1].value == Decimal("2137.5492")
    assert all(points[index].open == points[index - 1].close for index in range(1, 6))


def test_open_interest_parser_accepts_empty_history() -> None:
    assert parse_kraken_open_interest_history(_payload()) == ()


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"result": []},
        {"result": {"timestamp": {}, "data": [], "more": False}},
        {"result": {"timestamp": [], "data": {}, "more": False}},
        {"result": {"timestamp": [], "data": [], "more": "false"}},
        {"result": {"timestamp": [1], "data": [], "more": False}},
        {"result": {"timestamp": [1], "data": [_bucket("1")], "more": True}},
        {"result": {"timestamp": [1], "data": ["1"], "more": False}},
        {"result": {"timestamp": [1], "data": [["1", "2", "0"]], "more": False}},
        {"result": {"timestamp": [1], "data": [["1", "2", "0", "1", "extra"]], "more": False}},
        {"result": {"timestamp": [], "data": [], "more": False}, "errors": "bad"},
        {"result": {"timestamp": [], "data": [], "more": False}, "errors": [{"msg": "bad"}]},
    ],
)
def test_open_interest_parser_rejects_unknown_or_truncated_shapes(payload: object) -> None:
    with pytest.raises(KrakenPayloadError):
        parse_kraken_open_interest_history(payload)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "-1"])
def test_open_interest_parser_rejects_non_finite_or_negative_values(value: str) -> None:
    payload = {
        "result": {
            "timestamp": [int(SINCE.timestamp())],
            "data": [["1", "2", "0", value]],
            "more": False,
        }
    }
    with pytest.raises(KrakenPayloadError):
        parse_kraken_open_interest_history(payload)


@pytest.mark.parametrize(
    "bucket",
    [
        ["5", "4", "3", "4"],  # open above high
        ["3", "4", "5", "4"],  # low above high
        ["3", "4", "2", "5"],  # close above high
        ["3", "4", "2", "1"],  # close below low
    ],
)
def test_open_interest_parser_rejects_incoherent_ohlc(bucket: list[str]) -> None:
    payload = {
        "result": {
            "timestamp": [int(SINCE.timestamp())],
            "data": [bucket],
            "more": False,
        }
    }
    with pytest.raises(KrakenPayloadError):
        parse_kraken_open_interest_history(payload)


@pytest.mark.parametrize("timestamp", ["bad", 1.5, None, True])
def test_open_interest_parser_rejects_invalid_timestamps(timestamp: object) -> None:
    payload = {"result": {"timestamp": [timestamp], "data": [_bucket("1")], "more": False}}
    with pytest.raises(KrakenPayloadError):
        parse_kraken_open_interest_history(payload)


def test_open_interest_parser_rejects_non_chronological_history() -> None:
    payload = {
        "result": {
            "timestamp": [int(SINCE.timestamp()) + 3600, int(SINCE.timestamp())],
            "data": [_bucket("1"), _bucket("2", open_value="1")],
            "more": False,
        }
    }
    with pytest.raises(KrakenPayloadError, match="strictly chronological"):
        parse_kraken_open_interest_history(payload)


def test_public_client_builds_official_analytics_route_and_causal_query() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_payload("100", "101", "102"))

    async def scenario() -> None:
        async with httpx.AsyncClient(
            base_url="https://futures.kraken.test/derivatives/api/v3",
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = KrakenDerivativesAnalyticsClient(
                "https://futures.kraken.test/derivatives/api/v3",
                client=http_client,
            )
            points = await client.fetch_open_interest_history(
                _instrument(),
                since=SINCE,
                until=UNTIL,
                interval_seconds=3600,
            )
            assert len(points) == 3

    asyncio.run(scenario())
    assert len(captured) == 1
    request = captured[0]
    assert request.url.path == "/api/charts/v1/analytics/PF_XBTUSD/open-interest"
    assert request.url.params["since"] == str(int(SINCE.timestamp()))
    assert request.url.params["to"] == str(int(UNTIL.timestamp()))
    assert request.url.params["interval"] == "3600"


def test_public_client_validates_time_bounds_and_supported_interval_before_network() -> None:
    async def scenario() -> None:
        client = KrakenDerivativesAnalyticsClient("https://futures.kraken.test/derivatives/api/v3")
        try:
            with pytest.raises(ValueError, match="newer"):
                await client.fetch_open_interest_history(
                    _instrument(), since=UNTIL, until=SINCE, interval_seconds=3600
                )
            with pytest.raises(ValueError, match="unsupported"):
                await client.fetch_open_interest_history(
                    _instrument(), since=SINCE, until=UNTIL, interval_seconds=123
                )
        finally:
            await client.aclose()

    asyncio.run(scenario())


def test_public_client_maps_http_and_invalid_json_to_existing_kraken_errors() -> None:
    async def run(handler) -> None:
        async with httpx.AsyncClient(
            base_url="https://futures.kraken.test/derivatives/api/v3",
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = KrakenDerivativesAnalyticsClient(
                "https://futures.kraken.test/derivatives/api/v3",
                client=http_client,
            )
            await client.fetch_open_interest_history(
                _instrument(), since=SINCE, until=UNTIL, interval_seconds=3600
            )

    with pytest.raises(KrakenConnectionError):
        asyncio.run(run(lambda request: httpx.Response(500, request=request)))
    with pytest.raises(KrakenPayloadError):
        asyncio.run(
            run(
                lambda request: httpx.Response(
                    200,
                    text="not json",
                    request=request,
                )
            )
        )
