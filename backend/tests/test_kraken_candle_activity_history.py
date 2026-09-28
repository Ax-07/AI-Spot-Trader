from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from ai_spot_trader.domain.enums import DerivativeContractKind, MarketType
from ai_spot_trader.domain.models import DerivativeInstrument
from ai_spot_trader.integrations.kraken.candles import KrakenCandleProvider
from ai_spot_trader.integrations.kraken.errors import KrakenConnectionError, KrakenPayloadError
from ai_spot_trader.market.candles import CandleKey, CandleTimeframe

NOW = datetime(2026, 9, 28, 14, 0, tzinfo=UTC)


def _instrument() -> DerivativeInstrument:
    return DerivativeInstrument(
        symbol="BTC/USD",
        venue_symbol="PF_XBTUSD",
        market_type=MarketType.PERPETUAL,
        contract_kind=DerivativeContractKind.LINEAR,
        underlying_asset="BTC",
        quote_asset="USD",
        contract_size=Decimal("1"),
        tick_size=Decimal("0.5"),
        min_order_quantity=Decimal("0.001"),
        initial_margin_rate=Decimal("0.1"),
        maintenance_margin_rate=Decimal("0.05"),
        max_leverage=Decimal("10"),
        funding_interval_seconds=Decimal("3600"),
    )


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


class FakeCharts:
    def __init__(self, payload: object | None = None, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error
        self.calls: list[tuple[str, dict[str, int]]] = []

    async def get(self, path: str, *, params: dict[str, int]) -> FakeResponse:
        self.calls.append((path, params))
        if self.error is not None:
            raise self.error
        return FakeResponse(self.payload)

    async def aclose(self) -> None:
        return None


async def _provider(charts: FakeCharts) -> KrakenCandleProvider:
    provider = KrakenCandleProvider(
        spot_rest_url="https://spot.invalid",
        spot_ws_url="wss://spot.invalid",
        derivatives_rest_url="https://futures.invalid/derivatives/api/v3",
    )
    await provider._charts.aclose()
    provider._charts = charts  # type: ignore[assignment]
    provider._instrument_cache = {"BTC/USD": _instrument()}
    return provider


def _payload() -> dict[str, object]:
    return {
        "candles": [
            {
                "time": int((NOW - timedelta(minutes=10)).timestamp()),
                "open": "100",
                "high": "102",
                "low": "99",
                "close": "101",
                "volume": "12.5",
            },
            {
                "time": int((NOW - timedelta(minutes=5)).timestamp()),
                "open": "101",
                "high": "103",
                "low": "100",
                "close": "102",
                "volume": "8.25",
            },
        ]
    }


def test_perpetual_history_uses_trade_candles_mapped_venue_symbol_and_time_window() -> None:
    async def scenario() -> None:
        charts = FakeCharts(payload=_payload())
        provider = await _provider(charts)
        try:
            rows = await provider.fetch_history(
                CandleKey(
                    symbol="BTC/USD",
                    market_type=MarketType.PERPETUAL,
                    timeframe=CandleTimeframe.M5,
                ),
                limit=8,
                before=NOW,
            )
        finally:
            await provider.aclose()

        assert len(rows) == 2
        assert rows[-1].volume == Decimal("8.25")
        assert charts.calls == [
            (
                "trade/PF_XBTUSD/5m",
                {
                    "from": int((NOW - timedelta(minutes=50)).timestamp()),
                    "to": int(NOW.timestamp()),
                    "count": 8,
                },
            )
        ]
        assert charts.calls[0][1]["count"] == 8

    asyncio.run(scenario())


def test_perpetual_chart_transport_failure_stays_a_real_error() -> None:
    async def scenario() -> None:
        request = httpx.Request("GET", "https://futures.invalid/api/charts/v1/trade/PF_XBTUSD/5m")
        charts = FakeCharts(error=httpx.ConnectError("offline", request=request))
        provider = await _provider(charts)
        try:
            with pytest.raises(KrakenConnectionError):
                await provider.fetch_history(
                    CandleKey(
                        symbol="BTC/USD",
                        market_type=MarketType.PERPETUAL,
                        timeframe=CandleTimeframe.M5,
                    ),
                    limit=8,
                    before=NOW,
                )
        finally:
            await provider.aclose()

    asyncio.run(scenario())


def test_perpetual_chart_invalid_payload_is_diagnosed_as_payload_error() -> None:
    async def scenario() -> None:
        charts = FakeCharts(payload={"candles": [{"time": "bad"}]})
        provider = await _provider(charts)
        try:
            with pytest.raises(KrakenPayloadError):
                await provider.fetch_history(
                    CandleKey(
                        symbol="BTC/USD",
                        market_type=MarketType.PERPETUAL,
                        timeframe=CandleTimeframe.M5,
                    ),
                    limit=8,
                    before=NOW,
                )
        finally:
            await provider.aclose()

    asyncio.run(scenario())
