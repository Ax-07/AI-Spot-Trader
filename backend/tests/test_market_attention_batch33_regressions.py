from __future__ import annotations

import asyncio
import inspect
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import ai_spot_trader.market.attention as attention_module
from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.attention import (
    MarketAttentionPolicy,
    MarketAttentionRadar,
    _scan_allocations,
    _spot_usd_notional,
)
from ai_spot_trader.market.candles import Candle, CandleKey, CandleTimeframe

NOW = datetime(2026, 9, 29, 8, 0, tzinfo=UTC)


class Catalogue:
    def __init__(self, markets: tuple[ExecutableMarket, ...]) -> None:
        self.markets = markets

    async def list_markets(self) -> tuple[ExecutableMarket, ...]:
        return self.markets

    async def aclose(self) -> None:
        return None


class EmptyCandleService:
    async def history(self, key: CandleKey, *, limit: int = 1000):
        return ()


class NoResearchExpected:
    def __init__(self) -> None:
        self.calls = 0

    async def research(self, *, asset: str, symbols: tuple[str, ...], observed_at: datetime):
        self.calls += 1
        raise AssertionError("scan-only refresh must not trigger public research")

    async def aclose(self) -> None:
        return None


def _market(prefix: str, index: int, market_type: MarketType) -> ExecutableMarket:
    return ExecutableMarket(symbol=f"{prefix}{index:03d}/USD", market_type=market_type)


def _candle(symbol: str, market_type: MarketType, *, volume: str = "2", close: str = "10") -> Candle:
    return Candle(
        symbol=symbol,
        market_type=market_type,
        timeframe=CandleTimeframe.M5,
        open_time=NOW - timedelta(minutes=5),
        close_time=NOW,
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=Decimal(volume),
        is_final=True,
        updated_at=NOW,
    )


def test_batch32_rotation_allocation_remains_100_spot_20_perpetual() -> None:
    assert _scan_allocations(
        {MarketType.SPOT: 100, MarketType.PERPETUAL: 20},
        limit=120,
    ) == {MarketType.SPOT: 100, MarketType.PERPETUAL: 20}


def test_scan_only_refresh_keeps_web_budget_bounded_and_does_not_research() -> None:
    async def scenario() -> None:
        markets = tuple(
            [*(_market("S", i, MarketType.SPOT) for i in range(100))]
            + [*(_market("P", i, MarketType.PERPETUAL) for i in range(20))]
        )
        researcher = NoResearchExpected()
        radar = MarketAttentionRadar(
            candle_service=EmptyCandleService(),  # type: ignore[arg-type]
            catalogue=Catalogue(markets),
            researcher=researcher,  # type: ignore[arg-type]
            policy=MarketAttentionPolicy(
                scan_limit=120,
                candidate_limit=20,
                max_web_searches_per_refresh=8,
                candle_limit=404,
            ),
        )
        overview = await radar.refresh_once(observed_at=NOW)
        assert overview.scanned_market_type_counts.model_dump() == {"SPOT": 100, "PERPETUAL": 20}
        assert overview.web_search_count == 0
        assert overview.candidate_market_count == 0
        assert researcher.calls == 0
        await radar.aclose()

    asyncio.run(scenario())


def test_batch31_notional_semantics_remain_spot_usd_only() -> None:
    spot_usd = ExecutableMarket(symbol="AAA/USD", market_type=MarketType.SPOT)
    spot_eur = ExecutableMarket(symbol="AAA/EUR", market_type=MarketType.SPOT)
    perpetual = ExecutableMarket(symbol="AAA/USD", market_type=MarketType.PERPETUAL)

    assert _spot_usd_notional((_candle("AAA/USD", MarketType.SPOT),), market=spot_usd) == Decimal("20")
    assert _spot_usd_notional((_candle("AAA/EUR", MarketType.SPOT),), market=spot_eur) is None
    assert _spot_usd_notional((_candle("AAA/USD", MarketType.PERPETUAL),), market=perpetual) is None


def test_market_attention_module_keeps_trading_dependencies_absent() -> None:
    source = inspect.getsource(attention_module)
    assert "ai_spot_trader.agent" not in source
    assert "ai_spot_trader.risk" not in source
    assert "ai_spot_trader.broker" not in source
    assert "ai_spot_trader.market.discovery" not in source
