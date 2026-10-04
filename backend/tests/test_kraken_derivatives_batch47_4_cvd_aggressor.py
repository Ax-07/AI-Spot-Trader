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
    parse_kraken_aggressor_differential_history,
    parse_kraken_cvd_history,
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


def test_cvd_parser_accepts_live_snake_case_schema_when_side_arrays_align() -> None:
    payload = {
        "result": {
            "timestamp": _timestamps(3),
            "data": {
                "buy_volume": ["10.5", "9", "14.25"],
                "sell_volume": ["8", "11.5", "7"],
                "cvd": ["2.5", "0", "7.25"],
            },
            "more": False,
        },
        "errors": [],
    }
    points = parse_kraken_cvd_history(payload)
    assert points[0].observed_at == SINCE
    assert points[0].buy_volume == Decimal("10.5")
    assert points[1].sell_volume == Decimal("11.5")
    assert points[2].cvd == Decimal("7.25")


def test_cvd_parser_accepts_documented_camel_case_compatibility_shape() -> None:
    payload = {
        "result": {
            "timestamp": _timestamps(2),
            "data": {
                "buyVolume": ["1", "2"],
                "sellVolume": ["3", "1"],
                "cvd": ["-2", "-1"],
            },
            "more": False,
        },
        "errors": [],
    }
    points = parse_kraken_cvd_history(payload)
    assert [point.cvd for point in points] == [Decimal("-2"), Decimal("-1")]


def test_live_cvd_regression_keeps_cvd_when_side_arrays_are_not_alignable() -> None:
    payload = {
        "result": {
            "timestamp": [
                1791136800, 1791140400, 1791144000,
                1791147600, 1791151200, 1791154800,
            ],
            "data": {
                "buy_volume": [
                    "121.626", "222.3553", "136.4978",
                    "113.5224", "324.7907", "204.534",
                ],
                "sell_volume": ["220.1904", "136.6098", "221.7902", "38.4275"],
                "cvd": [
                    "-3.1094", "-0.9445", "45.3264",
                    "22.239", "125.2395", "291.346",
                ],
            },
            "more": False,
        },
        "errors": [],
    }
    points = parse_kraken_cvd_history(payload)
    assert len(points) == 6
    assert points[0].observed_at == datetime.fromtimestamp(1791136800, tz=UTC)
    assert points[-1].observed_at == datetime.fromtimestamp(1791154800, tz=UTC)
    assert points[-1].cvd == Decimal("291.346")
    assert all(point.buy_volume is None and point.sell_volume is None for point in points)


def test_live_aggressor_regression_confirms_signed_scalars_and_epoch_seconds() -> None:
    payload = {
        "result": {
            "timestamp": [
                1791136800, 1791140400, 1791144000,
                1791147600, 1791151200, 1791154800,
            ],
            "data": [
                "3.1094", "-2.1649", "-46.2709",
                "23.0874", "-103.0005", "-166.1065",
            ],
            "more": False,
        },
        "errors": [],
    }
    points = parse_kraken_aggressor_differential_history(payload)
    assert len(points) == 6
    assert points[0].observed_at == datetime.fromtimestamp(1791136800, tz=UTC)
    assert points[-1].value == Decimal("-166.1065")



@pytest.mark.parametrize(
    "payload",
    [
        {"result": {"timestamp": [1], "data": {"buy_volume": [], "sell_volume": [], "cvd": []}, "more": False}},
        {"result": {"timestamp": [1], "data": {"buyVolume": ["1"], "sellVolume": ["1"]}, "more": False}},
        {"result": {"timestamp": [1], "data": {"buyVolume": ["-1"], "sellVolume": ["1"], "cvd": ["0"]}, "more": False}},
        {"result": {"timestamp": [1], "data": {"buyVolume": ["NaN"], "sellVolume": ["1"], "cvd": ["0"]}, "more": False}},
        {"result": {"timestamp": [1], "data": {"buyVolume": ["1"], "sellVolume": ["Infinity"], "cvd": ["0"]}, "more": False}},
        {"result": {"timestamp": [1], "data": {"buyVolume": ["1"], "sellVolume": ["1"], "cvd": ["0"]}, "more": True}},
        {"result": {"timestamp": [1], "data": {"buyVolume": ["1"], "sellVolume": ["1"], "cvd": ["0"]}, "more": False}, "errors": ["bad"]},
        {"result": {"timestamp": [2, 1], "data": {"buyVolume": ["1", "1"], "sellVolume": ["1", "1"], "cvd": ["0", "0"]}, "more": False}},
    ],
)
def test_cvd_parser_fails_closed(payload: object) -> None:
    with pytest.raises(KrakenPayloadError):
        parse_kraken_cvd_history(payload)


def test_aggressor_parser_accepts_signed_scalar_values() -> None:
    payload = {
        "result": {
            "timestamp": _timestamps(3),
            "data": ["12.5", "-7.25", "0"],
            "more": False,
        },
        "errors": [],
    }
    points = parse_kraken_aggressor_differential_history(payload)
    assert [point.value for point in points] == [
        Decimal("12.5"),
        Decimal("-7.25"),
        Decimal("0"),
    ]
    assert points[0].observed_at == SINCE


@pytest.mark.parametrize("value", ["NaN", "Infinity", None, True, ["1", "2", "0", "1"], {"value": "1"}])
def test_aggressor_parser_rejects_non_finite_or_non_scalar_shapes(value: object) -> None:
    payload = {"result": {"timestamp": [int(SINCE.timestamp())], "data": [value], "more": False}}
    with pytest.raises(KrakenPayloadError):
        parse_kraken_aggressor_differential_history(payload)


def test_new_analytics_routes_reuse_canonical_public_client() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.url.path.endswith("/cvd"):
            payload = {
                "result": {
                    "timestamp": [],
                    "data": {"buy_volume": [], "sell_volume": [], "cvd": []},
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
            await client.fetch_cvd_history(
                _instrument(), since=SINCE, until=UNTIL, interval_seconds=3600
            )
            await client.fetch_aggressor_differential_history(
                _instrument(), since=SINCE, until=UNTIL, interval_seconds=3600
            )

    asyncio.run(scenario())
    assert [request.url.path for request in captured] == [
        "/api/charts/v1/analytics/PF_XBTUSD/cvd",
        "/api/charts/v1/analytics/PF_XBTUSD/aggressor-differential",
    ]
    for request in captured:
        assert request.url.params["since"] == str(int(SINCE.timestamp()))
        assert request.url.params["to"] == str(int(UNTIL.timestamp()))
        assert request.url.params["interval"] == "3600"


@pytest.mark.parametrize(
    "payload",
    [
        {"result": {"timestamp": [1], "data": [], "more": True}},
        {"result": {"timestamp": [1], "data": [], "more": False}, "errors": ["bad"]},
        {"result": {"timestamp": [1, 2], "data": ["1"], "more": False}},
        {"result": {"timestamp": [2, 1], "data": ["1", "2"], "more": False}},
    ],
)
def test_aggressor_parser_fails_closed_on_truncated_errors_or_chronology(payload: object) -> None:
    with pytest.raises(KrakenPayloadError):
        parse_kraken_aggressor_differential_history(payload)
