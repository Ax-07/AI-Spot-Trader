from __future__ import annotations

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.attention import MarketAttentionPolicy, MarketAttentionRadar, _scan_allocations


def _market(prefix: str, index: int, market_type: MarketType) -> ExecutableMarket:
    return ExecutableMarket(symbol=f"{prefix}{index:03d}/USD", market_type=market_type)


class Catalogue:
    def __init__(self, markets): self.markets = markets
    async def list_markets(self): return self.markets
    async def aclose(self): return None


class EmptyCandles:
    async def history(self, key, *, limit: int = 1000): return ()


def test_scan_allocation_is_proportional_bounded_and_represents_both_families() -> None:
    allocation = _scan_allocations({MarketType.SPOT: 100, MarketType.PERPETUAL: 20}, limit=60)
    assert sum(allocation.values()) == 60
    assert allocation[MarketType.SPOT] > 0
    assert allocation[MarketType.PERPETUAL] > 0


def test_scan_allocation_handles_single_family_and_small_catalogue() -> None:
    assert _scan_allocations({MarketType.SPOT: 4, MarketType.PERPETUAL: 0}, limit=10) == {MarketType.SPOT: 4, MarketType.PERPETUAL: 0}


def test_family_cursors_rotate_without_starvation() -> None:
    markets = tuple([*(_market("S", i, MarketType.SPOT) for i in range(16)), *(_market("P", i, MarketType.PERPETUAL) for i in range(8))])
    radar = MarketAttentionRadar(
        candle_service=EmptyCandles(), catalogue=Catalogue(markets),  # type: ignore[arg-type]
        policy=MarketAttentionPolicy(scan_limit=10, candle_limit=160),
    )
    first = radar._next_scan_batch(markets)
    second = radar._next_scan_batch(markets)
    assert first != second
    assert {item.market_type for item in first} == {MarketType.SPOT, MarketType.PERPETUAL}
    assert {item.market_type for item in second} == {MarketType.SPOT, MarketType.PERPETUAL}
