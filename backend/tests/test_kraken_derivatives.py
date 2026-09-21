from datetime import UTC, datetime
from decimal import Decimal

from ai_spot_trader.domain.enums import DerivativeContractKind, MarketType
from ai_spot_trader.integrations.kraken.derivatives import (
    parse_kraken_derivatives_instruments,
    parse_kraken_derivatives_ticker,
)


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
                    {"numNonContractUnits": 0, "initialMargin": 0.02, "maintenanceMargin": 0.01}
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


def test_parse_kraken_derivative_metadata_and_conservative_margin() -> None:
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
    assert inverse.contract_kind is DerivativeContractKind.INVERSE
    assert future.market_type is MarketType.FUTURE
    assert future.expires_at == datetime(2026, 12, 25, 15, 0, tzinfo=UTC)


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
