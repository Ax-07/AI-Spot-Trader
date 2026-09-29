from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.integrations.kraken.candles import KrakenCandleProvider
from ai_spot_trader.integrations.kraken.errors import KrakenAPIError, UnknownKrakenSymbolError
from ai_spot_trader.market.candles import CandleKey, CandleTimeframe

NOW = datetime(2026, 9, 29, 8, 0, tzinfo=UTC)


class FakeRegistry:
    def __init__(self, symbols: set[str]) -> None:
        self.symbols = {symbol.upper() for symbol in symbols}

    def normalize(self, symbol: str) -> str:
        normalized = symbol.strip().upper()
        if normalized not in self.symbols:
            raise UnknownKrakenSymbolError(f"unknown Kraken Spot symbol: {symbol!r}")
        return normalized


class FakeSpotRest:
    def __init__(self, registries: list[FakeRegistry]) -> None:
        self.registries = registries
        self.registry_calls = 0
        self.ohlc_calls: list[str] = []

    async def fetch_pair_registry(self) -> FakeRegistry:
        index = min(self.registry_calls, len(self.registries) - 1)
        self.registry_calls += 1
        await asyncio.sleep(0)
        return self.registries[index]

    async def fetch_ohlcv_history(self, symbol: str, *, interval_minutes: int, since: datetime):
        self.ohlc_calls.append(symbol)
        started_at = NOW - timedelta(minutes=10)
        return (
            SimpleNamespace(
                started_at=started_at,
                closed_at=started_at + timedelta(minutes=5),
                open_price=Decimal("1"),
                high_price=Decimal("1.1"),
                low_price=Decimal("0.9"),
                close_price=Decimal("1.05"),
                volume=Decimal("10"),
                is_final=True,
                updated_at=started_at + timedelta(minutes=5),
            ),
        )

    async def aclose(self) -> None:
        return None


class FailingSpotRest(FakeSpotRest):
    async def fetch_pair_registry(self) -> FakeRegistry:
        self.registry_calls += 1
        await asyncio.sleep(0)
        raise KrakenAPIError("Kraken AssetPairs returned an API error")


async def _provider(rest: FakeSpotRest) -> KrakenCandleProvider:
    provider = KrakenCandleProvider(
        spot_rest_url="https://spot.invalid",
        spot_ws_url="wss://spot.invalid",
        derivatives_rest_url="https://futures.invalid",
    )
    await provider._spot_rest.aclose()
    provider._spot_rest = rest  # type: ignore[assignment]
    return provider


def _key(symbol: str) -> CandleKey:
    return CandleKey(symbol=symbol, market_type=MarketType.SPOT, timeframe=CandleTimeframe.M5)


def test_successive_spot_histories_reuse_one_asset_pairs_registry() -> None:
    async def scenario() -> None:
        rest = FakeSpotRest([FakeRegistry({"AAA/USD", "BBB/USD"})])
        provider = await _provider(rest)
        try:
            first = await provider.fetch_history(_key("AAA/USD"), limit=8, before=NOW)
            second = await provider.fetch_history(_key("BBB/USD"), limit=8, before=NOW)
        finally:
            await provider.aclose()

        assert rest.registry_calls == 1
        assert rest.ohlc_calls == ["AAA/USD", "BBB/USD"]
        assert first[0].symbol == "AAA/USD"
        assert second[0].symbol == "BBB/USD"

    asyncio.run(scenario())


def test_concurrent_cold_spot_histories_single_flight_registry_load() -> None:
    async def scenario() -> None:
        symbols = {f"A{index}/USD" for index in range(8)}
        rest = FakeSpotRest([FakeRegistry(symbols)])
        provider = await _provider(rest)
        try:
            rows = await asyncio.gather(
                *(provider.fetch_history(_key(symbol), limit=8, before=NOW) for symbol in symbols)
            )
        finally:
            await provider.aclose()

        assert rest.registry_calls == 1
        assert len(rest.ohlc_calls) == 8
        assert all(batch for batch in rows)

    asyncio.run(scenario())


def test_warm_missing_spot_symbol_triggers_one_controlled_refresh() -> None:
    async def scenario() -> None:
        rest = FakeSpotRest(
            [
                FakeRegistry({"AAA/USD"}),
                FakeRegistry({"AAA/USD", "NEW/USD"}),
            ]
        )
        provider = await _provider(rest)
        try:
            await provider.fetch_history(_key("AAA/USD"), limit=8, before=NOW)
            rows = await asyncio.gather(
                *(provider.fetch_history(_key("NEW/USD"), limit=8, before=NOW) for _ in range(4))
            )
        finally:
            await provider.aclose()

        assert rest.registry_calls == 2
        assert all(batch[0].symbol == "NEW/USD" for batch in rows)

    asyncio.run(scenario())


def test_spot_symbol_still_missing_after_refresh_fails_closed() -> None:
    async def scenario() -> None:
        rest = FakeSpotRest([FakeRegistry({"AAA/USD"}), FakeRegistry({"AAA/USD"})])
        provider = await _provider(rest)
        try:
            await provider._spot_symbol("AAA/USD")
            with pytest.raises(UnknownKrakenSymbolError):
                await provider._spot_symbol("MISSING/USD")
        finally:
            await provider.aclose()

        assert rest.registry_calls == 2
        assert rest.ohlc_calls == []

    asyncio.run(scenario())


def test_cold_missing_spot_symbol_loads_catalogue_once_then_fails_closed() -> None:
    async def scenario() -> None:
        rest = FakeSpotRest([FakeRegistry({"AAA/USD"})])
        provider = await _provider(rest)
        try:
            with pytest.raises(UnknownKrakenSymbolError):
                await provider._spot_symbol("MISSING/USD")
        finally:
            await provider.aclose()

        assert rest.registry_calls == 1

    asyncio.run(scenario())

def test_concurrent_registry_failure_is_fail_fast_after_one_provider_call() -> None:
    async def scenario() -> None:
        rest = FailingSpotRest([FakeRegistry({"AAA/USD"})])
        provider = await _provider(rest)
        try:
            results = await asyncio.gather(
                *(provider._spot_symbol(f"A{index}/USD") for index in range(20)),
                return_exceptions=True,
            )
        finally:
            await provider.aclose()

        assert rest.registry_calls == 1
        assert all(isinstance(result, KrakenAPIError) for result in results)

    asyncio.run(scenario())

