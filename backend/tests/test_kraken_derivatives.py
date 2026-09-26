from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from ai_spot_trader.domain.derivative_margin import TieredDerivativeInstrument
from ai_spot_trader.domain.enums import DerivativeContractKind, MarketType
from ai_spot_trader.domain.models import DerivativeInstrument
from ai_spot_trader.integrations.kraken.derivatives import (
    parse_kraken_derivatives_instruments,
    parse_kraken_derivatives_ticker,
)
from ai_spot_trader.integrations.kraken.errors import KrakenPayloadError


def instruments_payload() -> dict[str, object]:
    return {
        "result": "success",
        "serverTime": "2026-09-21T12:00:00Z",
        "instruments": [
            {
                "symbol": "PF_XBTUSD",
                "base": "XBT",
                "quote": "USD",
                "type": "flexible_futures",
                "tickSize": 1,
                "contractSize": 1,
                "tradeable": True,
                "maxPositionSize": 1000,
                "contractValueTradePrecision": 4,
                "marginLevels": [
                    {"numNonContractUnits": 0, "initialMargin": 0.02, "maintenanceMargin": 0.01}
                ],
                "retailMarginLevels": [
                    {"numNonContractUnits": 0, "initialMargin": 0.10, "maintenanceMargin": 0.05}
                ],
            },
            {
                "symbol": "PI_XBTUSD",
                "base": "XBT",
                "quote": "USD",
                "type": "inverse_futures",
                "tickSize": 1,
                "contractSize": 1,
                "tradeable": True,
                "contractValueTradePrecision": 0,
                "marginLevels": [
                    {"contracts": 0, "initialMargin": 0.02, "maintenanceMargin": 0.01}
                ],
            },
            {
                "symbol": "FF_XBTUSD_261225",
                "base": "XBT",
                "quote": "USD",
                "type": "futures_vanilla",
                "lastTradingTime": "2026-12-25T15:00:00Z",
                "tickSize": 1,
                "contractSize": 1,
                "tradeable": True,
                "contractValueTradePrecision": 0,
                "marginLevels": [
                    {"numNonContractUnits": 0, "initialMargin": 0.10, "maintenanceMargin": 0.05}
                ],
            },
        ],
    }


def test_parse_kraken_derivative_metadata_and_retail_margin_schedule() -> None:
    parsed = parse_kraken_derivatives_instruments(instruments_payload())
    linear = next(item for item in parsed if item.venue_symbol == "PF_XBTUSD")
    inverse = next(item for item in parsed if item.venue_symbol == "PI_XBTUSD")
    future = next(item for item in parsed if item.venue_symbol == "FF_XBTUSD_261225")

    assert linear.symbol == "BTC/USD"
    assert linear.market_type is MarketType.PERPETUAL
    assert linear.contract_kind is DerivativeContractKind.LINEAR
    assert linear.min_order_quantity == Decimal("0.0001")
    assert linear.initial_margin_rate == Decimal("0.1")
    assert linear.maintenance_margin_rate == Decimal("0.05")
    assert linear.max_leverage == Decimal("10")
    assert isinstance(linear, TieredDerivativeInstrument)
    assert linear.margin_schedule_source == "retailMarginLevels"
    assert inverse.contract_kind is DerivativeContractKind.INVERSE
    assert future.market_type is MarketType.FUTURE
    assert future.expires_at == datetime(2026, 12, 25, 15, 0, tzinfo=UTC)


def test_parse_negative_contract_value_trade_precision() -> None:
    payload = instruments_payload()
    instruments = payload["instruments"]
    assert isinstance(instruments, list)
    instruments.append(
        {
            "symbol": "PF_PEPEUSD",
            "base": "PEPE",
            "quote": "USD",
            "type": "flexible_futures",
            "tickSize": "0.0000001",
            "contractSize": 1,
            "tradeable": True,
            "contractValueTradePrecision": -3,
            "marginLevels": [
                {"numNonContractUnits": 0, "initialMargin": 0.10, "maintenanceMargin": 0.05}
            ],
        }
    )

    parsed = parse_kraken_derivatives_instruments(payload)
    pepe = next(item for item in parsed if item.venue_symbol == "PF_PEPEUSD")
    bitcoin = next(item for item in parsed if item.venue_symbol == "PF_XBTUSD")

    assert pepe.min_order_quantity == Decimal("1000")
    assert bitcoin.min_order_quantity == Decimal("0.0001")


def test_parse_margin_schedules_mapping_without_guessing_account_tier() -> None:
    payload = {
        "result": "success",
        "instruments": [
            {
                "symbol": "PF_ETHUSD",
                "base": "ETH",
                "quote": "USD",
                "type": "flexible_futures",
                "tickSize": "0.1",
                "contractSize": 1,
                "tradeable": True,
                "maxPositionSize": 50000,
                "contractValueTradePrecision": 3,
                "marginSchedules": {
                    "standard": {
                        "contracts": 0,
                        "initialMargin": "0.02",
                        "maintenanceMargin": "0.01",
                    },
                    "retail": {
                        "numNonContractUnits": 0,
                        "initialMargin": "0.10",
                        "maintenanceMargin": "0.05",
                    },
                },
            }
        ],
    }

    (instrument,) = parse_kraken_derivatives_instruments(payload)

    assert instrument.symbol == "ETH/USD"
    assert instrument.min_order_quantity == Decimal("0.001")
    assert instrument.initial_margin_rate == Decimal("0.10")
    assert instrument.maintenance_margin_rate == Decimal("0.05")
    assert instrument.max_leverage == Decimal("10")
    assert not isinstance(instrument, TieredDerivativeInstrument)


def test_parse_nested_margin_schedules_from_public_kraken_shape() -> None:
    payload = {
        "result": "success",
        "instruments": [
            {
                "symbol": "PF_ETHUSD",
                "base": "ETH",
                "quote": "USD",
                "type": "flexible_futures",
                "tickSize": "0.1",
                "contractSize": 1,
                "tradeable": True,
                "contractValueTradePrecision": 3,
                "marginLevels": [
                    {
                        "numNonContractUnits": 0,
                        "initialMargin": "0.01",
                        "maintenanceMargin": "0.005",
                    }
                ],
                "marginSchedules": {
                    "europa": {
                        "retail": [
                            {
                                "numNonContractUnits": 0,
                                "initialMargin": "0.10",
                                "maintenanceMargin": "0.05",
                            }
                        ],
                        "professional": [
                            {
                                "numNonContractUnits": 0,
                                "initialMargin": "0.10",
                                "maintenanceMargin": "0.05",
                            }
                        ],
                    },
                    "dlt": {
                        "retail": [
                            {
                                "numNonContractUnits": 0,
                                "initialMargin": "0.50",
                                "maintenanceMargin": "0.25",
                            }
                        ],
                        "professional": [
                            {
                                "numNonContractUnits": 0,
                                "initialMargin": "0.02",
                                "maintenanceMargin": "0.01",
                            }
                        ],
                    },
                },
            }
        ],
    }

    (instrument,) = parse_kraken_derivatives_instruments(payload)

    # Direct generic levels plus incompatible named account/regulatory schedules are ambiguous.
    # Keep the conservative scalar fallback instead of inventing one mixed tier curve.
    assert not isinstance(instrument, TieredDerivativeInstrument)
    assert instrument.symbol == "ETH/USD"
    assert instrument.initial_margin_rate == Decimal("0.50")
    assert instrument.maintenance_margin_rate == Decimal("0.25")
    assert instrument.max_leverage == Decimal("2")


def test_nested_margin_schedules_still_fail_closed_on_malformed_leaf() -> None:
    payload = {
        "result": "success",
        "instruments": [
            {
                "symbol": "PF_ETHUSD",
                "base": "ETH",
                "quote": "USD",
                "type": "flexible_futures",
                "tickSize": "0.1",
                "contractSize": 1,
                "tradeable": True,
                "contractValueTradePrecision": 3,
                "marginSchedules": {
                    "europa": {
                        "retail": [
                            {
                                "numNonContractUnits": 0,
                                "maintenanceMargin": "0.05",
                            }
                        ]
                    }
                },
            }
        ],
    }

    with pytest.raises(KrakenPayloadError, match="initialMargin is invalid"):
        parse_kraken_derivatives_instruments(payload)


def test_retail_margin_levels_preserve_sorted_position_size_tiers() -> None:
    payload = {
        "result": "success",
        "instruments": [
            {
                "symbol": "PF_ACEUSD",
                "base": "ACE",
                "quote": "USD",
                "type": "flexible_futures",
                "tickSize": "0.0001",
                "contractSize": 1,
                "tradeable": True,
                "contractValueTradePrecision": 0,
                "retailMarginLevels": [
                    {
                        "numNonContractUnits": 2_000_000,
                        "initialMargin": "0.50",
                        "maintenanceMargin": "0.25",
                    },
                    {
                        "numNonContractUnits": 0,
                        "initialMargin": "0.10",
                        "maintenanceMargin": "0.05",
                    },
                    {
                        "numNonContractUnits": 250_000,
                        "initialMargin": "0.20",
                        "maintenanceMargin": "0.10",
                    },
                    {
                        "numNonContractUnits": 1_000_000,
                        "initialMargin": "0.30",
                        "maintenanceMargin": "0.15",
                    },
                ],
            }
        ],
    }

    (instrument,) = parse_kraken_derivatives_instruments(payload)

    assert isinstance(instrument, TieredDerivativeInstrument)
    assert tuple(tier.threshold for tier in instrument.margin_tiers) == (
        Decimal("0"),
        Decimal("250000"),
        Decimal("1000000"),
        Decimal("2000000"),
    )
    assert instrument.initial_margin_rate == Decimal("0.10")
    assert instrument.max_leverage == Decimal("10")


def test_margin_levels_contract_thresholds_are_preserved() -> None:
    payload = {
        "result": "success",
        "instruments": [
            {
                "symbol": "PI_XBTUSD",
                "base": "XBT",
                "quote": "USD",
                "type": "inverse_futures",
                "tickSize": "0.5",
                "contractSize": 1,
                "tradeable": True,
                "contractValueTradePrecision": 0,
                "marginLevels": [
                    {"contracts": 0, "initialMargin": "0.02", "maintenanceMargin": "0.01"},
                    {"contracts": 500000, "initialMargin": "0.04", "maintenanceMargin": "0.02"},
                ],
            }
        ],
    }

    (instrument,) = parse_kraken_derivatives_instruments(payload)

    assert isinstance(instrument, TieredDerivativeInstrument)
    assert all(tier.threshold_basis == "CONTRACTS" for tier in instrument.margin_tiers)
    assert instrument.margin_tiers[1].threshold == Decimal("500000")


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ("missing_precision", "contractValueTradePrecision is missing"),
        ("malformed_margin_entry", "marginLevels contains an invalid margin level"),
        ("maintenance_above_initial", "maintenanceMargin cannot exceed initialMargin"),
        ("negative_margin_threshold", "numNonContractUnits cannot be negative"),
        ("invalid_tradeable", "tradeable flag is invalid"),
        ("max_position_below_minimum", "maxPositionSize cannot be smaller"),
        ("duplicate_threshold", "duplicate margin thresholds"),
        ("decreasing_initial", "initialMargin cannot decrease by size"),
    ],
)
def test_instrument_parser_fails_closed_on_incoherent_public_metadata(
    mutation: str,
    match: str,
) -> None:
    payload = instruments_payload()
    instruments = payload["instruments"]
    assert isinstance(instruments, list)
    raw = instruments[0]
    assert isinstance(raw, dict)

    if mutation == "missing_precision":
        raw.pop("contractValueTradePrecision")
    elif mutation == "malformed_margin_entry":
        raw["marginLevels"] = ["bad-row"]
    elif mutation == "maintenance_above_initial":
        raw["marginLevels"] = [
            {"numNonContractUnits": 0, "initialMargin": 0.02, "maintenanceMargin": 0.03}
        ]
    elif mutation == "negative_margin_threshold":
        raw["marginLevels"] = [
            {"numNonContractUnits": -1, "initialMargin": 0.02, "maintenanceMargin": 0.01}
        ]
    elif mutation == "invalid_tradeable":
        raw["tradeable"] = "true"
    elif mutation == "max_position_below_minimum":
        raw["maxPositionSize"] = "0.00001"
    elif mutation == "duplicate_threshold":
        raw["retailMarginLevels"] = [
            {"numNonContractUnits": 0, "initialMargin": 0.10, "maintenanceMargin": 0.05},
            {"numNonContractUnits": 0, "initialMargin": 0.20, "maintenanceMargin": 0.10},
        ]
    elif mutation == "decreasing_initial":
        raw["retailMarginLevels"] = [
            {"numNonContractUnits": 0, "initialMargin": 0.20, "maintenanceMargin": 0.10},
            {"numNonContractUnits": 250000, "initialMargin": 0.10, "maintenanceMargin": 0.05},
        ]
    else:  # pragma: no cover - guards the test table itself.
        raise AssertionError(f"unknown mutation {mutation}")

    with pytest.raises(KrakenPayloadError, match=match):
        parse_kraken_derivatives_instruments(payload)


def test_non_tradeable_instrument_is_ignored_before_optional_metadata_validation() -> None:
    payload = instruments_payload()
    instruments = payload["instruments"]
    assert isinstance(instruments, list)
    raw = deepcopy(instruments[0])
    assert isinstance(raw, dict)
    raw["symbol"] = "PF_DISABLEDUSD"
    raw["base"] = "DISABLED"
    raw["tradeable"] = False
    raw.pop("contractValueTradePrecision")
    raw.pop("marginLevels")
    raw.pop("retailMarginLevels")
    instruments.insert(0, raw)

    parsed = parse_kraken_derivatives_instruments(payload)

    assert all(item.venue_symbol != "PF_DISABLEDUSD" for item in parsed)


def test_ticker_normalizes_mark_index_and_per_contract_funding() -> None:
    instrument = next(
        item
        for item in parse_kraken_derivatives_instruments(instruments_payload())
        if item.venue_symbol == "PF_XBTUSD"
    )
    payload = {
        "result": "success",
        "serverTime": "2026-09-21T12:00:01Z",
        "ticker": {
            "symbol": "PF_XBTUSD",
            "markPrice": 65000,
            "indexPrice": 64990,
            "fundingRate": 6.5,
            "suspended": False,
            "postOnly": False,
        },
    }
    observed_at, mark, index, funding = parse_kraken_derivatives_ticker(
        payload,
        instrument=instrument,
    )
    assert observed_at == datetime(2026, 9, 21, 12, 0, 1, tzinfo=UTC)
    assert mark == Decimal("65000")
    assert index == Decimal("64990")
    assert funding == Decimal("0.0001")


def _ticker_payload(**ticker_overrides: object) -> dict[str, object]:
    ticker: dict[str, object] = {
        "symbol": "PF_XBTUSD",
        "markPrice": 65000,
        "indexPrice": 64990,
        "fundingRate": 6.5,
    }
    ticker.update(ticker_overrides)
    return {
        "result": "success",
        "serverTime": "2026-09-21T12:00:01Z",
        "ticker": ticker,
    }


def _linear_instrument() -> DerivativeInstrument:
    return next(
        item
        for item in parse_kraken_derivatives_instruments(instruments_payload())
        if item.venue_symbol == "PF_XBTUSD"
    )


def test_ticker_does_not_fallback_to_last_when_mark_price_is_missing() -> None:
    payload = _ticker_payload(last=64950)
    ticker = payload["ticker"]
    assert isinstance(ticker, dict)
    ticker.pop("markPrice")

    with pytest.raises(KrakenPayloadError, match="markPrice is invalid"):
        parse_kraken_derivatives_ticker(payload, instrument=_linear_instrument())


@pytest.mark.parametrize(
    ("flag", "value", "match"),
    [
        ("suspended", True, "ticker is suspended"),
        ("postOnly", True, "ticker is post-only"),
        ("suspended", "false", "ticker suspended flag is invalid"),
        ("postOnly", 0, "ticker postOnly flag is invalid"),
    ],
)
def test_ticker_fails_closed_on_non_executable_or_malformed_status(
    flag: str,
    value: object,
    match: str,
) -> None:
    payload = _ticker_payload(**{flag: value})

    with pytest.raises(KrakenPayloadError, match=match):
        parse_kraken_derivatives_ticker(payload, instrument=_linear_instrument())


def test_ticker_rejects_conflicting_post_only_aliases() -> None:
    payload = _ticker_payload(postOnly=False, post_only=True)

    with pytest.raises(KrakenPayloadError, match="ticker postOnly aliases conflict"):
        parse_kraken_derivatives_ticker(payload, instrument=_linear_instrument())
