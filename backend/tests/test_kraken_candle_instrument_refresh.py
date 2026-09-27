import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai_spot_trader.domain.enums import DerivativeContractKind, MarketType
from ai_spot_trader.domain.models import DerivativeInstrument
from ai_spot_trader.integrations.kraken.candles import KrakenCandleProvider
from ai_spot_trader.integrations.kraken.derivatives import (
    build_kraken_linear_perpetual_instrument_map,
)
from ai_spot_trader.integrations.kraken.errors import UnknownKrakenSymbolError
from ai_spot_trader.market.candles import CandleKey, CandleTimeframe

NOW = datetime(2026, 9, 26, 21, 0, tzinfo=UTC)


def _linear_perpetual(symbol: str, venue_symbol: str) -> DerivativeInstrument:
    base, quote = symbol.split("/", 1)
    return DerivativeInstrument(
        symbol=symbol,
        venue_symbol=venue_symbol,
        market_type=MarketType.PERPETUAL,
        contract_kind=DerivativeContractKind.LINEAR,
        underlying_asset=base,
        quote_asset=quote,
        contract_size=Decimal("1"),
        tick_size=Decimal("0.0001"),
        min_order_quantity=Decimal("0.001"),
        initial_margin_rate=Decimal("0.1"),
        maintenance_margin_rate=Decimal("0.05"),
        max_leverage=Decimal("10"),
        funding_interval_seconds=Decimal("3600"),
    )


def test_linear_perpetual_mapping_is_deterministic_across_catalogue_order() -> None:
    later = _linear_perpetual("CFG/USD", "PF_Z_CFGUSD")
    earlier = _linear_perpetual("CFG/USD", "PF_A_CFGUSD")

    first = build_kraken_linear_perpetual_instrument_map((later, earlier))
    second = build_kraken_linear_perpetual_instrument_map((earlier, later))

    assert first["CFG/USD"].venue_symbol == "PF_A_CFGUSD"
    assert second["CFG/USD"].venue_symbol == "PF_A_CFGUSD"



class FakeDerivativesClient:
    def __init__(self, catalogues: list[tuple[DerivativeInstrument, ...]]) -> None:
        self.catalogues = catalogues
        self.calls = 0

    async def fetch_instruments(self) -> tuple[DerivativeInstrument, ...]:
        index = min(self.calls, len(self.catalogues) - 1)
        self.calls += 1
        return self.catalogues[index]

    async def aclose(self) -> None:
        return None


class FakeChartsResponse:
    def __init__(self, payload: object) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._payload


class FakeChartsClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, int]]] = []

    async def get(self, path: str, *, params: dict[str, int]) -> FakeChartsResponse:
        self.calls.append((path, params))
        candle_time = NOW - timedelta(hours=2)
        return FakeChartsResponse(
            {
                "candles": [
                    {
                        "time": int(candle_time.timestamp()),
                        "open": "1.0",
                        "high": "1.1",
                        "low": "0.9",
                        "close": "1.05",
                        "volume": "10",
                    }
                ]
            }
        )

    async def aclose(self) -> None:
        return None


async def _provider_with_fakes(
    catalogues: list[tuple[DerivativeInstrument, ...]],
) -> tuple[KrakenCandleProvider, FakeDerivativesClient, FakeChartsClient]:
    provider = KrakenCandleProvider(
        spot_rest_url="https://spot.invalid",
        spot_ws_url="wss://spot.invalid",
        derivatives_rest_url="https://futures.invalid",
    )
    await provider._derivatives.aclose()
    await provider._charts.aclose()
    derivatives = FakeDerivativesClient(catalogues)
    charts = FakeChartsClient()
    provider._derivatives = derivatives  # type: ignore[assignment]
    provider._charts = charts  # type: ignore[assignment]
    return provider, derivatives, charts


def test_perpetual_candles_refresh_stale_catalogue_once_and_resolve_new_symbol() -> None:
    async def scenario() -> None:
        btc = _linear_perpetual("BTC/USD", "PF_XBTUSD")
        cfg = _linear_perpetual("CFG/USD", "PF_CFGUSD")
        provider, derivatives, charts = await _provider_with_fakes(
            [(btc,), (btc, cfg)]
        )
        try:
            assert (await provider._instrument("BTC/USD")).venue_symbol == "PF_XBTUSD"
            assert derivatives.calls == 1

            rows = await asyncio.gather(
                *(
                    provider.fetch_history(
                        CandleKey(
                            symbol="CFG/USD",
                            market_type=MarketType.PERPETUAL,
                            timeframe=timeframe,
                        ),
                        limit=8,
                        before=NOW,
                    )
                    for timeframe in (
                        CandleTimeframe.M1,
                        CandleTimeframe.M5,
                        CandleTimeframe.M15,
                        CandleTimeframe.M30,
                    )
                )
            )

            assert derivatives.calls == 2
            assert len(charts.calls) == 4
            assert all(batch and batch[0].symbol == "CFG/USD" for batch in rows)
            assert all("PF_CFGUSD" in path for path, _ in charts.calls)
        finally:
            await provider.aclose()

    asyncio.run(scenario())


def test_cold_missing_perpetual_uses_single_catalogue_load_then_fails_closed() -> None:
    async def scenario() -> None:
        btc = _linear_perpetual("BTC/USD", "PF_XBTUSD")
        provider, derivatives, charts = await _provider_with_fakes([(btc,)])
        try:
            with pytest.raises(UnknownKrakenSymbolError, match="after catalogue refresh"):
                await provider._instrument("CFG/USD")
            assert derivatives.calls == 1
            assert charts.calls == []
        finally:
            await provider.aclose()

    asyncio.run(scenario())


def test_perpetual_symbol_still_missing_after_refresh_remains_fail_closed() -> None:
    async def scenario() -> None:
        btc = _linear_perpetual("BTC/USD", "PF_XBTUSD")
        provider, derivatives, charts = await _provider_with_fakes([(btc,), (btc,)])
        try:
            await provider._instrument("BTC/USD")
            with pytest.raises(UnknownKrakenSymbolError, match="after catalogue refresh"):
                await provider.fetch_history(
                    CandleKey(
                        symbol="CFG/USD",
                        market_type=MarketType.PERPETUAL,
                        timeframe=CandleTimeframe.M1,
                    ),
                    limit=8,
                    before=NOW,
                )
            assert derivatives.calls == 2
            assert charts.calls == []
        finally:
            await provider.aclose()

    asyncio.run(scenario())


def test_cached_perpetual_symbol_does_not_trigger_extra_catalogue_refresh() -> None:
    async def scenario() -> None:
        btc = _linear_perpetual("BTC/USD", "PF_XBTUSD")
        provider, derivatives, _ = await _provider_with_fakes([(btc,)])
        try:
            first = await provider._instrument("BTC/USD")
            second = await provider._instrument("BTC/USD")
            assert first is second
            assert derivatives.calls == 1
        finally:
            await provider.aclose()

    asyncio.run(scenario())
