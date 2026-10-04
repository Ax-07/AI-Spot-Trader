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
    parse_kraken_funding_history,
    parse_kraken_liquidation_volume_history,
)
from ai_spot_trader.integrations.kraken.errors import KrakenPayloadError

SINCE = datetime(2026, 10, 4, 0, 0, tzinfo=UTC)
UNTIL = datetime(2026, 10, 4, 6, 0, tzinfo=UTC)


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


def _timestamps(count: int) -> list[int]:
    return [int(SINCE.timestamp()) + index * 3600 for index in range(count)]


def _funding_timestamps(count: int) -> list[int]:
    return [timestamp * 1000 for timestamp in _timestamps(count)]


def test_funding_parser_keeps_absolute_and_relative_rates_separate() -> None:
    payload = {
        "result": {
            "timestamp": _funding_timestamps(3),
            "data": {
                "rate": [
                    ["-2", "2", "-3", "1"],
                    ["1", "3", "0", "2"],
                    ["2", "2.5", "-1", "-0.5"],
                ],
                "relativeRate": [
                    ["-0.0002", "0.0002", "-0.0003", "0.0001"],
                    ["0.0001", "0.0003", "0", "0.0002"],
                    ["0.0002", "0.00025", "-0.0001", "-0.00005"],
                ],
            },
            "more": False,
        },
        "errors": [],
    }
    points = parse_kraken_funding_history(payload)
    assert [point.rate for point in points] == [Decimal("1"), Decimal("2"), Decimal("-0.5")]
    assert [point.relative_rate for point in points] == [
        Decimal("0.0001"),
        Decimal("0.0002"),
        Decimal("-0.00005"),
    ]
    assert points[0].rate_open == Decimal("-2")
    assert points[0].relative_rate_low == Decimal("-0.0003")
    assert points[0].observed_at == SINCE



def test_live_kraken_timestamp_units_are_series_specific() -> None:
    funding_payload = {
        "result": {
            "timestamp": [1791129600000, 1791133200000],
            "data": {
                "rate": [
                    ["0.4388494204878883", "0.520090974837305", "0.4388494204878883", "0.520090974837305"],
                    ["0.520090974837305", "0.73257827554118", "0.520090974837305", "0.73257827554118"],
                ],
                "relativeRate": [
                    ["0.000005146408333333", "0.000006101558333333", "0.000005146408333333", "0.000006101558333333"],
                    ["0.000006101558333333", "0.000008582970833333", "0.000006101558333333", "0.000008582970833333"],
                ],
            },
            "more": False,
        },
        "errors": [],
    }
    liquidation_payload = {
        "result": {
            "timestamp": [1791129600, 1791133200],
            "data": ["0", "0.2208"],
            "more": False,
        },
        "errors": [],
    }

    funding = parse_kraken_funding_history(funding_payload)
    liquidation = parse_kraken_liquidation_volume_history(liquidation_payload)

    assert funding[0].observed_at == liquidation[0].observed_at
    assert funding[1].observed_at == liquidation[1].observed_at
    assert funding[0].relative_rate == Decimal("0.000006101558333333")
    assert liquidation[1].value == Decimal("0.2208")

def test_funding_parser_accepts_empty_dedicated_schema() -> None:
    payload = {
        "result": {
            "timestamp": [],
            "data": {"rate": [], "relativeRate": []},
            "more": False,
        },
        "errors": [],
    }
    assert parse_kraken_funding_history(payload) == ()


@pytest.mark.parametrize(
    "payload",
    [
        {"result": {"timestamp": [], "data": [], "more": False}},
        {"result": {"timestamp": [], "data": {"rate": []}, "more": False}},
        {
            "result": {
                "timestamp": [1],
                "data": {"rate": [], "relativeRate": []},
                "more": False,
            }
        },
        {
            "result": {
                "timestamp": [1],
                "data": {"rate": [["1", "2", "0", "1"]], "relativeRate": ["1"]},
                "more": False,
            }
        },
        {
            "result": {
                "timestamp": [1],
                "data": {
                    "rate": [["1", "2", "0", "1"]],
                    "relativeRate": [["1", "2", "0", "1"]],
                },
                "more": True,
            }
        },
    ],
)
def test_funding_parser_fails_closed_on_unknown_or_truncated_shapes(payload: object) -> None:
    with pytest.raises(KrakenPayloadError):
        parse_kraken_funding_history(payload)


def test_liquidation_parser_accepts_documented_scalar_total_without_direction() -> None:
    payload = {
        "result": {
            "timestamp": _timestamps(3),
            "data": ["0", "125000.5", 50],
            "more": False,
        },
        "errors": [],
    }
    points = parse_kraken_liquidation_volume_history(payload)
    assert [point.value for point in points] == [Decimal("0"), Decimal("125000.5"), Decimal("50")]
    assert all(point.bucket_kind == "SCALAR" for point in points)
    assert all(point.open is None and point.close is None for point in points)


def test_liquidation_parser_accepts_generic_ohlc_variant_without_directional_labels() -> None:
    payload = {
        "result": {
            "timestamp": _timestamps(2),
            "data": [
                ["10", "15", "5", "12"],
                ["12", "20", "8", "18"],
            ],
            "more": False,
        }
    }
    points = parse_kraken_liquidation_volume_history(payload)
    assert points[0].bucket_kind == "OHLC"
    assert points[0].value == Decimal("12")
    assert points[0].open == Decimal("10")
    assert points[0].close == Decimal("12")


@pytest.mark.parametrize("value", ["-1", "NaN", None, True, {"buy": "1"}])
def test_liquidation_parser_rejects_invalid_or_directional_invented_shapes(value: object) -> None:
    payload = {
        "result": {
            "timestamp": [int(SINCE.timestamp())],
            "data": [value],
            "more": False,
        }
    }
    with pytest.raises(KrakenPayloadError):
        parse_kraken_liquidation_volume_history(payload)


def test_public_client_uses_official_funding_and_liquidation_routes() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.url.path.endswith("/funding"):
            payload = {
                "result": {
                    "timestamp": [],
                    "data": {"rate": [], "relativeRate": []},
                    "more": False,
                },
                "errors": [],
            }
        else:
            payload = {"result": {"timestamp": [], "data": [], "more": False}, "errors": []}
        return httpx.Response(200, json=payload)

    async def scenario() -> None:
        async with httpx.AsyncClient(
            base_url="https://futures.kraken.test/derivatives/api/v3",
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = KrakenDerivativesAnalyticsClient(
                "https://futures.kraken.test/derivatives/api/v3",
                client=http_client,
            )
            await client.fetch_funding_history(
                _instrument(), since=SINCE, until=UNTIL, interval_seconds=3600
            )
            await client.fetch_liquidation_volume_history(
                _instrument(), since=SINCE, until=UNTIL, interval_seconds=3600
            )

    asyncio.run(scenario())
    assert [request.url.path for request in captured] == [
        "/api/charts/v1/analytics/PF_XBTUSD/funding",
        "/api/charts/v1/analytics/PF_XBTUSD/liquidation-volume",
    ]
    for request in captured:
        assert request.url.params["since"] == str(int(SINCE.timestamp()))
        assert request.url.params["to"] == str(int(UNTIL.timestamp()))
        assert request.url.params["interval"] == "3600"
