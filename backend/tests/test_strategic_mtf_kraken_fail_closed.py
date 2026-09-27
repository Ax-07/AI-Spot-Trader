import asyncio
from datetime import UTC, datetime

import pytest

from ai_spot_trader.domain.enums import MarketType, TradingStyle
from ai_spot_trader.domain.experiments import trading_style_context
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.integrations.kraken.errors import UnknownKrakenSymbolError
from ai_spot_trader.market.candles import CandleCache, CandleKey, CandleStreamService
from ai_spot_trader.market.strategic_context import StrategicMultiTimeframeContextService


class UnknownSymbolProvider:
    async def fetch_history(self, key: CandleKey, *, limit: int, before: datetime):
        raise UnknownKrakenSymbolError(
            f"no linear Kraken PERPETUAL mapped to {key.symbol} after catalogue refresh"
        )

    async def _stream(self):
        if False:
            yield None

    def stream(self, key: CandleKey):
        return self._stream()

    async def aclose(self) -> None:
        return None


class EmptyProvider:
    async def fetch_history(self, key: CandleKey, *, limit: int, before: datetime):
        return ()

    async def _stream(self):
        if False:
            yield None

    def stream(self, key: CandleKey):
        return self._stream()

    async def aclose(self) -> None:
        return None


def test_empty_candle_history_is_missing_but_unknown_market_stays_fail_closed() -> None:
    async def scenario() -> None:
        as_of = datetime(2026, 9, 26, 21, 0, tzinfo=UTC)
        market = ExecutableMarket(symbol="CFG/USD", market_type=MarketType.PERPETUAL)
        style = trading_style_context(TradingStyle.SCALP)

        empty_stream = CandleStreamService(EmptyProvider(), cache=CandleCache(max_depth=100))
        empty_builder = StrategicMultiTimeframeContextService(empty_stream)
        try:
            context = await empty_builder.build(
                markets=(market,), trading_style_context=style, as_of=as_of
            )
            assert all(
                timeframe.availability == "MISSING"
                for timeframe in context.markets[0].timeframes
            )
        finally:
            await empty_stream.aclose()

        failed_stream = CandleStreamService(
            UnknownSymbolProvider(), cache=CandleCache(max_depth=100)
        )
        failed_builder = StrategicMultiTimeframeContextService(failed_stream)
        try:
            with pytest.raises(UnknownKrakenSymbolError):
                await failed_builder.build(
                    markets=(market,), trading_style_context=style, as_of=as_of
                )
        finally:
            await failed_stream.aclose()

    asyncio.run(scenario())
