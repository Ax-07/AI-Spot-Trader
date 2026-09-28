from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.attention import (
    MarketAttentionPolicy,
    MarketAttentionRadar,
    _scan_allocations,
)
from ai_spot_trader.market.candles import CandleKey

NOW = datetime(2026, 9, 28, 18, 30, tzinfo=UTC)


def _market(prefix: str, index: int, market_type: MarketType) -> ExecutableMarket:
    return ExecutableMarket(symbol=f"{prefix}{index:03d}/USD", market_type=market_type)


def _markets(*, spot: int, perpetual: int) -> tuple[ExecutableMarket, ...]:
    rows = [
        *(_market("S", index, MarketType.SPOT) for index in range(spot)),
        *(_market("P", index, MarketType.PERPETUAL) for index in range(perpetual)),
    ]
    return tuple(sorted(rows, key=lambda item: (item.market_type.value, item.symbol)))


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
        raise AssertionError("a stratified scan alone must never trigger public research")

    async def aclose(self) -> None:
        return None


def _radar(
    markets: tuple[ExecutableMarket, ...],
    *,
    scan_limit: int = 10,
    researcher=None,
) -> MarketAttentionRadar:
    return MarketAttentionRadar(
        candle_service=EmptyCandleService(),  # type: ignore[arg-type]
        catalogue=Catalogue(markets),
        researcher=researcher,
        policy=MarketAttentionPolicy(
            scan_limit=scan_limit,
            candidate_limit=20,
            diagnostic_market_limit=10,
            max_web_searches_per_refresh=8,
            candle_limit=404,
        ),
    )


def _type_counts(batch: tuple[ExecutableMarket, ...]) -> dict[MarketType, int]:
    return {
        market_type: sum(item.market_type is market_type for item in batch)
        for market_type in (MarketType.SPOT, MarketType.PERPETUAL)
    }


def test_scan_allocation_is_proportional_bounded_and_represents_both_families() -> None:
    balanced = _scan_allocations(
        {MarketType.SPOT: 100, MarketType.PERPETUAL: 100},
        limit=120,
    )
    imbalanced = _scan_allocations(
        {MarketType.SPOT: 1000, MarketType.PERPETUAL: 1},
        limit=120,
    )

    assert balanced == {MarketType.SPOT: 60, MarketType.PERPETUAL: 60}
    assert imbalanced == {MarketType.SPOT: 119, MarketType.PERPETUAL: 1}
    assert sum(balanced.values()) == 120
    assert sum(imbalanced.values()) == 120


def test_scan_allocation_handles_single_family_and_catalogue_smaller_than_limit() -> None:
    assert _scan_allocations(
        {MarketType.SPOT: 7, MarketType.PERPETUAL: 0},
        limit=120,
    ) == {MarketType.SPOT: 7, MarketType.PERPETUAL: 0}
    assert _scan_allocations(
        {MarketType.SPOT: 0, MarketType.PERPETUAL: 9},
        limit=120,
    ) == {MarketType.SPOT: 0, MarketType.PERPETUAL: 9}
    assert _scan_allocations(
        {MarketType.SPOT: 3, MarketType.PERPETUAL: 4},
        limit=120,
    ) == {MarketType.SPOT: 3, MarketType.PERPETUAL: 4}


def test_each_refresh_contains_spot_and_perpetual_when_both_are_available() -> None:
    radar = _radar(_markets(spot=40, perpetual=20), scan_limit=10)
    batch = radar._next_scan_batch(radar._catalogue_provider.markets)  # type: ignore[attr-defined]
    counts = _type_counts(batch)

    assert len(batch) == 10
    assert counts[MarketType.SPOT] > 0
    assert counts[MarketType.PERPETUAL] > 0


def test_rotation_has_no_starvation_for_either_family() -> None:
    markets = _markets(spot=23, perpetual=7)
    radar = _radar(markets, scan_limit=10)
    seen = {MarketType.SPOT: set(), MarketType.PERPETUAL: set()}

    for _ in range(4):
        for market in radar._next_scan_batch(markets):
            seen[market.market_type].add(market.symbol)

    assert seen[MarketType.SPOT] == {
        market.symbol for market in markets if market.market_type is MarketType.SPOT
    }
    assert seen[MarketType.PERPETUAL] == {
        market.symbol for market in markets if market.market_type is MarketType.PERPETUAL
    }


def test_family_cursors_are_independent_and_wrap_independently() -> None:
    markets = _markets(spot=12, perpetual=2)
    radar = _radar(markets, scan_limit=10)

    radar._next_scan_batch(markets)
    assert radar._scan_cursors == {MarketType.SPOT: 9, MarketType.PERPETUAL: 1}

    radar._next_scan_batch(markets)
    assert radar._scan_cursors == {MarketType.SPOT: 6, MarketType.PERPETUAL: 0}

    radar._next_scan_batch(markets)
    assert radar._scan_cursors == {MarketType.SPOT: 3, MarketType.PERPETUAL: 1}


def test_rotation_is_independent_from_activity_cache_and_ratios() -> None:
    markets = _markets(spot=12, perpetual=8)
    clean = _radar(markets, scan_limit=10)
    with_cache = _radar(markets, scan_limit=10)
    with_cache._activity_cache[markets[0]] = object()  # type: ignore[assignment]

    assert clean._next_scan_batch(markets) == with_cache._next_scan_batch(markets)


def test_refresh_exposes_scanned_and_fresh_counts_by_market_type_without_web_search() -> None:
    async def scenario() -> None:
        markets = _markets(spot=8, perpetual=8)
        researcher = NoResearchExpected()
        radar = _radar(markets, scan_limit=10, researcher=researcher)

        overview = await radar.refresh_once(observed_at=NOW)

        assert overview.scanned_market_count == 10
        assert overview.scanned_market_type_counts.model_dump() == {"SPOT": 5, "PERPETUAL": 5}
        assert overview.fresh_market_type_counts.model_dump() == {"SPOT": 5, "PERPETUAL": 5}
        assert overview.cached_activity_market_count == 10
        assert overview.candidate_market_count == 0
        assert overview.web_search_count == 0
        assert researcher.calls == 0
        await radar.aclose()

    asyncio.run(scenario())


def test_refresh_with_only_spot_or_only_perpetual_uses_available_capacity() -> None:
    async def scenario() -> None:
        spot_radar = _radar(_markets(spot=12, perpetual=0), scan_limit=10)
        spot = await spot_radar.refresh_once(observed_at=NOW)
        assert spot.scanned_market_type_counts.model_dump() == {"SPOT": 10, "PERPETUAL": 0}
        await spot_radar.aclose()

        perp_radar = _radar(_markets(spot=0, perpetual=12), scan_limit=10)
        perp = await perp_radar.refresh_once(observed_at=NOW)
        assert perp.scanned_market_type_counts.model_dump() == {"SPOT": 0, "PERPETUAL": 10}
        await perp_radar.aclose()

    asyncio.run(scenario())
