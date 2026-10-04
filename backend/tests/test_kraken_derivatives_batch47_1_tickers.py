from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from ai_spot_trader.integrations.kraken.derivatives import (
    KrakenDerivativesPublicClient,
    parse_kraken_derivatives_tickers,
)
from ai_spot_trader.integrations.kraken.errors import KrakenPayloadError


def _payload(*rows: object) -> dict[str, object]:
    return {
        "result": "success",
        "serverTime": "2026-10-04T12:00:00Z",
        "tickers": list(rows),
    }


def _ticker(symbol: str = "PF_XBTUSD", **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "symbol": symbol,
        "markPrice": "65000.5",
        "indexPrice": "64990.25",
        "volumeQuote": "123456789.50",
        "openInterest": "12345.75",
        "fundingRate": "6.5",
        "fundingRatePrediction": "7.25",
        "suspended": False,
        "postOnly": False,
    }
    value.update(overrides)
    return value


def test_bulk_ticker_parser_preserves_all_demonstrated_fields_and_server_time() -> None:
    parsed = parse_kraken_derivatives_tickers(
        _payload(
            _ticker(),
            _ticker("PF_ETHUSD", markPrice="3500", openInterest="777"),
        )
    )

    assert len(parsed) == 2
    btc = parsed[0]
    assert btc.venue_symbol == "PF_XBTUSD"
    assert btc.observed_at == datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
    assert btc.mark_price == Decimal("65000.5")
    assert btc.index_price == Decimal("64990.25")
    assert btc.volume_quote == Decimal("123456789.50")
    assert btc.open_interest == Decimal("12345.75")
    assert btc.funding_rate_raw == Decimal("6.5")
    assert btc.funding_rate_prediction_raw == Decimal("7.25")
    assert btc.suspended is False
    assert btc.post_only is False


def test_bulk_ticker_parser_keeps_optional_fields_absent_without_inventing_units() -> None:
    parsed = parse_kraken_derivatives_tickers(
        _payload(
            {
                "symbol": "PF_SOLUSD",
                "markPrice": "180",
                "suspended": False,
            }
        )
    )

    (sol,) = parsed
    assert sol.mark_price == Decimal("180")
    assert sol.index_price is None
    assert sol.volume_quote is None
    assert sol.open_interest is None
    assert sol.funding_rate_raw is None
    assert sol.funding_rate_prediction_raw is None


def test_bulk_ticker_parser_retains_suspended_status_for_descriptive_context() -> None:
    (ticker,) = parse_kraken_derivatives_tickers(_payload(_ticker(suspended=True)))
    assert ticker.suspended is True


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {"result": "error", "serverTime": "2026-10-04T12:00:00Z", "tickers": []},
        {"result": "success", "serverTime": "2026-10-04T12:00:00Z", "tickers": {}},
        {"result": "success", "serverTime": "bad", "tickers": []},
    ],
)
def test_bulk_ticker_parser_rejects_invalid_root_api_and_array_shapes(payload: object) -> None:
    with pytest.raises(KrakenPayloadError):
        parse_kraken_derivatives_tickers(payload)


@pytest.mark.parametrize("bad_symbol", [None, "", "   ", 123])
def test_bulk_ticker_parser_rejects_invalid_symbol(bad_symbol: object) -> None:
    with pytest.raises(KrakenPayloadError, match="ticker symbol"):
        parse_kraken_derivatives_tickers(
            _payload(_ticker(symbol=bad_symbol))  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("markPrice", "NaN"),
        ("markPrice", "Infinity"),
        ("indexPrice", "-Infinity"),
        ("volumeQuote", "-1"),
        ("openInterest", "-0.01"),
        ("fundingRate", "NaN"),
        ("fundingRatePrediction", "Infinity"),
        ("markPrice", 0),
        ("indexPrice", -1),
    ],
)
def test_bulk_ticker_parser_rejects_non_finite_or_invalid_numeric_values(
    field: str,
    value: object,
) -> None:
    with pytest.raises(KrakenPayloadError):
        parse_kraken_derivatives_tickers(_payload(_ticker(**{field: value})))


def test_bulk_ticker_parser_rejects_duplicate_symbols() -> None:
    with pytest.raises(KrakenPayloadError, match="duplicate symbol"):
        parse_kraken_derivatives_tickers(_payload(_ticker(), _ticker()))


def test_public_client_fetch_tickers_uses_one_bulk_public_request() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json=_payload(_ticker()))

    async def scenario() -> None:
        async with httpx.AsyncClient(
            base_url="https://futures.kraken.test/derivatives/api/v3",
            transport=httpx.MockTransport(handler),
        ) as http_client:
            client = KrakenDerivativesPublicClient(
                "https://futures.kraken.test/derivatives/api/v3",
                client=http_client,
            )
            (ticker,) = await client.fetch_tickers()
            assert ticker.open_interest == Decimal("12345.75")
            assert ticker.volume_quote == Decimal("123456789.50")

    asyncio.run(scenario())
    assert calls == ["/derivatives/api/v3/tickers"]
