from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_spot_trader.api.routes.market_attention import router as market_attention_router
from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.integrations.coinpaprika import (
    CoinPaprikaMarketMetadataProvider,
    parse_coinpaprika_tickers,
)
from ai_spot_trader.market.attention import MarketAttentionPolicy, RadarStatus
from ai_spot_trader.market.attention_filters import (
    MARKET_CAP_MICRO_MAX_USD,
    MARKET_CAP_MID_MAX_USD,
    MARKET_CAP_SMALL_MAX_USD,
    FilteredStructuredMarketAttentionRadar,
    MarketAttentionFilters,
    MarketAttentionOverviewV6,
    MarketCapCategory,
    MarketMetadataSnapshot,
    _causal_spot_volume_24h_usd,
    market_cap_category,
)
from ai_spot_trader.market.attention_scope_trend import MarketScope
from ai_spot_trader.market.candles import Candle, CandleKey, CandleTimeframe
from ai_spot_trader.market.microstructure import MicrostructurePolicy
from ai_spot_trader.market.structure import MarketStructurePolicy

NOW = datetime(2026, 10, 2, 10, 0, tzinfo=UTC)


def _candle(
    *,
    symbol: str,
    timeframe: CandleTimeframe,
    index: int,
    count: int,
    volume: Decimal,
    price: Decimal = Decimal("100"),
) -> Candle:
    duration = timeframe.duration
    open_time = NOW - duration * (count - index)
    close_time = open_time + duration
    return Candle(
        symbol=symbol,
        market_type=MarketType.SPOT,
        timeframe=timeframe,
        open_time=open_time,
        close_time=close_time,
        open=price,
        high=price + Decimal("1"),
        low=price - Decimal("1"),
        close=price,
        volume=volume,
        is_final=True,
        updated_at=close_time,
    )


def _activity_history(symbol: str, *, high_volume: bool) -> tuple[Candle, ...]:
    count = 420
    rows: list[Candle] = []
    for index in range(count):
        volume = Decimal("1")
        if high_volume and index >= count - 48:
            volume = Decimal("10")
        if not high_volume:
            volume = Decimal("0.01")
        rows.append(
            _candle(
                symbol=symbol,
                timeframe=CandleTimeframe.M5,
                index=index,
                count=count,
                volume=volume,
            )
        )
    return tuple(rows)


def _structure_history(symbol: str, timeframe: CandleTimeframe) -> tuple[Candle, ...]:
    count = 100
    return tuple(
        _candle(
            symbol=symbol,
            timeframe=timeframe,
            index=index,
            count=count,
            volume=Decimal("1"),
            price=Decimal("100") + Decimal(index % 7),
        )
        for index in range(count)
    )


def test_market_cap_categories_use_centralized_inclusive_boundaries() -> None:
    assert market_cap_category(None) is MarketCapCategory.UNKNOWN
    assert market_cap_category(MARKET_CAP_MICRO_MAX_USD - 1) is MarketCapCategory.MICRO
    assert market_cap_category(MARKET_CAP_MICRO_MAX_USD) is MarketCapCategory.SMALL
    assert market_cap_category(MARKET_CAP_SMALL_MAX_USD) is MarketCapCategory.MID
    assert market_cap_category(MARKET_CAP_MID_MAX_USD) is MarketCapCategory.LARGE


def test_filter_model_is_disabled_by_default_and_validates_market_cap_range() -> None:
    filters = MarketAttentionFilters()
    assert filters.market_scope is MarketScope.ALL
    assert filters.min_volume_24h_usd is None
    assert filters.market_cap_categories == ()
    assert not filters.market_cap_filter_enabled

    with pytest.raises(ValueError):
        MarketAttentionFilters(
            min_market_cap_usd=Decimal("1000"),
            max_market_cap_usd=Decimal("999"),
        )
    with pytest.raises(ValueError):
        MarketAttentionFilters(market_cap_categories=(MarketCapCategory.UNKNOWN,))


def test_causal_volume_24h_uses_only_finalized_candles_available_at_as_of() -> None:
    rows = tuple(
        _candle(
            symbol="BTC/USD",
            timeframe=CandleTimeframe.M5,
            index=index,
            count=300,
            volume=Decimal("2"),
        )
        for index in range(300)
    )
    future = rows[-1].model_copy(
        update={
            "open_time": NOW,
            "close_time": NOW + timedelta(minutes=5),
            "updated_at": NOW + timedelta(minutes=5),
            "volume": Decimal("999999"),
        }
    )
    value = _causal_spot_volume_24h_usd((*rows, future), as_of=NOW)
    assert value == Decimal(288 * 2 * 100)

    insufficient = tuple(item for item in rows if item.open_time >= NOW - timedelta(hours=12))
    assert _causal_spot_volume_24h_usd(insufficient, as_of=NOW) is None


def test_coinpaprika_mapping_rejects_ambiguous_duplicate_symbols() -> None:
    payload = [
        {
            "id": "abc-low",
            "symbol": "ABC",
            "rank": 500,
            "circulating_supply": 100,
            "last_updated": "2026-10-02T09:00:00Z",
            "quotes": {"USD": {"market_cap": 10_000}},
        },
        {
            "id": "abc-main",
            "symbol": "ABC",
            "rank": 50,
            "circulating_supply": 200,
            "last_updated": "2026-10-02T09:05:00Z",
            "quotes": {"USD": {"market_cap": 20_000}},
        },
    ]
    parsed = parse_coinpaprika_tickers(payload, observed_at=NOW)
    assert "ABC" not in parsed


def test_coinpaprika_provider_cache_is_fail_soft() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                text=json.dumps(
                    [
                        {
                            "symbol": "BTC",
                            "rank": 1,
                            "circulating_supply": 20_000_000,
                            "quotes": {"USD": {"market_cap": 1_000_000_000_000}},
                        }
                    ]
                ),
            )
        return httpx.Response(503, text="unavailable")

    async def scenario() -> None:
        client = httpx.AsyncClient(
            base_url="https://example.invalid/v1",
            transport=httpx.MockTransport(handler),
        )
        provider = CoinPaprikaMarketMetadataProvider(
            client=client,
            cache_ttl=timedelta(microseconds=1),
        )
        first = await provider.metadata_by_symbol()
        await asyncio.sleep(0)
        second = await provider.metadata_by_symbol()
        assert first["BTC"].market_cap_rank == 1
        assert second == first
        await client.aclose()

    asyncio.run(scenario())


class Catalogue:
    markets = (
        ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),
        ExecutableMarket(symbol="ETH/USD", market_type=MarketType.SPOT),
        ExecutableMarket(symbol="DOGE/USD", market_type=MarketType.SPOT),
    )

    async def list_markets(self):
        return self.markets

    async def aclose(self) -> None:
        return None


class Cache:
    def __init__(self, history: dict[CandleKey, tuple[Candle, ...]]) -> None:
        self.history_map = history

    def history_as_of(self, key: CandleKey, *, as_of: datetime, limit: int | None = None):
        rows = tuple(
            item
            for item in self.history_map.get(key, ())
            if item.updated_at <= as_of and item.close_time <= as_of
        )
        return rows if limit is None else rows[-limit:]


class Candles:
    def __init__(self) -> None:
        self.activity_calls: list[CandleKey] = []
        self.structure_calls: list[CandleKey] = []
        activity = {
            CandleKey(symbol="BTC/USD", market_type=MarketType.SPOT, timeframe=CandleTimeframe.M5): _activity_history(
                "BTC/USD", high_volume=True
            ),
            CandleKey(symbol="ETH/USD", market_type=MarketType.SPOT, timeframe=CandleTimeframe.M5): _activity_history(
                "ETH/USD", high_volume=False
            ),
            CandleKey(symbol="DOGE/USD", market_type=MarketType.SPOT, timeframe=CandleTimeframe.M5): _activity_history(
                "DOGE/USD", high_volume=True
            ),
        }
        self.cache = Cache(activity)
        self._activity = activity

    async def history(self, key: CandleKey, *, limit: int = 1000):
        self.activity_calls.append(key)
        return self._activity.get(key, ())[-limit:]

    async def history_as_of(
        self,
        key: CandleKey,
        *,
        as_of: datetime,
        limit: int = 1000,
    ):
        self.structure_calls.append(key)
        return _structure_history(key.symbol, key.timeframe)[-limit:]


class Microstructure:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def fetch_order_book(self, symbol: str, *, limit: int):
        self.calls.append(("book", symbol))
        raise RuntimeError("test book unavailable")

    async def fetch_recent_trades(self, symbol: str, *, limit: int):
        self.calls.append(("trades", symbol))
        raise RuntimeError("test trades unavailable")

    async def aclose(self) -> None:
        return None


class Metadata:
    async def metadata_by_symbol(self):
        return {
            "BTC": MarketMetadataSnapshot(
                asset_symbol="BTC",
                market_cap_usd=Decimal("1000000000000"),
                market_cap_rank=1,
                circulating_supply=Decimal("20000000"),
                observed_at=NOW,
                provider="TEST",
            ),
            "ETH": MarketMetadataSnapshot(
                asset_symbol="ETH",
                market_cap_usd=Decimal("400000000000"),
                market_cap_rank=2,
                circulating_supply=Decimal("120000000"),
                observed_at=NOW,
                provider="TEST",
            ),
            "DOGE": MarketMetadataSnapshot(
                asset_symbol="DOGE",
                market_cap_usd=Decimal("50000000"),
                market_cap_rank=50,
                circulating_supply=Decimal("1000000000"),
                observed_at=NOW,
                provider="TEST",
            ),
        }

    async def aclose(self) -> None:
        return None


def test_scope_volume_and_market_cap_filters_run_before_expensive_enrichment() -> None:
    async def scenario() -> None:
        candles = Candles()
        micro = Microstructure()
        radar = FilteredStructuredMarketAttentionRadar(
            candle_service=candles,  # type: ignore[arg-type]
            catalogue=Catalogue(),
            microstructure_provider=micro,  # type: ignore[arg-type]
            metadata_provider=Metadata(),
            policy=MarketAttentionPolicy(
                scan_limit=10,
                candle_limit=420,
                candidate_limit=10,
            ),
            microstructure_policy=MicrostructurePolicy(market_limit_per_refresh=10),
            structure_policy=MarketStructurePolicy(
                history_limit=40,
                min_history_candles=20,
                fetch_concurrency=4,
            ),
        )
        snapshot = await radar.set_filters(
            MarketAttentionFilters(
                market_scope=MarketScope.SPOT,
                min_volume_24h_usd=Decimal("72000"),
                market_cap_categories=(MarketCapCategory.LARGE,),
            ),
            observed_at=NOW,
        )

        assert snapshot.protocol_version == "market-attention-radar-v6"
        assert snapshot.filters.min_volume_24h_usd == Decimal("72000")
        assert snapshot.filters.market_cap_categories == (MarketCapCategory.LARGE,)

        scanned_symbols = {call.symbol for call in candles.activity_calls}
        assert scanned_symbols == {"BTC/USD", "ETH/USD"}
        assert "DOGE/USD" not in scanned_symbols  # cap filter before OHLCV

        assert {symbol for _kind, symbol in micro.calls} == {"BTC/USD"}
        assert candles.structure_calls
        assert {call.symbol for call in candles.structure_calls} == {"BTC/USD"}
        assert {call.timeframe for call in candles.structure_calls} == {
            CandleTimeframe.M5,
            CandleTimeframe.M15,
            CandleTimeframe.H1,
            CandleTimeframe.H4,
        }

        assert snapshot.cached_activity_market_count == 1
        assert snapshot.candidate_market_count == 1
        candidate = snapshot.shortlist[0]
        assert candidate.market_activity.market.symbol == "BTC/USD"
        assert candidate.volume_24h_usd is not None
        assert candidate.volume_24h_usd == Decimal("72000")
        assert candidate.market_cap_category is MarketCapCategory.LARGE
        assert candidate.market_cap_provider == "TEST"
        await radar.aclose()

    asyncio.run(scenario())


class FilterService:
    def __init__(self) -> None:
        self._filters = MarketAttentionFilters()
        self._latest = MarketAttentionOverviewV6(
            observed_at=NOW,
            status=RadarStatus.AVAILABLE,
            market_scope=MarketScope.ALL,
            filters=self._filters,
        )

    @property
    def latest(self):
        return self._latest

    @property
    def filters(self) -> MarketAttentionFilters:
        return self._filters

    def history(self, *, limit: int = 24):
        return (self._latest,)

    async def set_filters(self, filters: MarketAttentionFilters, *, observed_at=None):
        self._filters = filters
        self._latest = self._latest.model_copy(
            update={"market_scope": filters.market_scope, "filters": filters}
        )
        return self._latest

    async def set_market_scope(self, market_scope: MarketScope, *, observed_at=None):
        return await self.set_filters(
            self._filters.model_copy(update={"market_scope": market_scope})
        )


def test_filter_api_get_put_and_validation() -> None:
    app = FastAPI()
    service = FilterService()
    app.state.market_attention = service
    app.include_router(market_attention_router)

    with TestClient(app) as client:
        current = client.get("/api/v1/market-attention/filters")
        assert current.status_code == 200
        assert current.json()["min_volume_24h_usd"] is None

        changed = client.put(
            "/api/v1/market-attention/filters",
            json={
                "market_scope": "SPOT",
                "min_volume_24h_usd": "500000",
                "market_cap_categories": ["MID", "LARGE"],
                "min_market_cap_usd": None,
                "max_market_cap_usd": None,
            },
        )
        assert changed.status_code == 200
        body = changed.json()
        assert body["protocol_version"] == "market-attention-radar-v6"
        assert body["filters"]["market_scope"] == "SPOT"
        assert body["filters"]["min_volume_24h_usd"] == "500000"

        invalid = client.put(
            "/api/v1/market-attention/filters",
            json={
                "market_scope": "SPOT",
                "min_volume_24h_usd": None,
                "market_cap_categories": [],
                "min_market_cap_usd": "1000",
                "max_market_cap_usd": "10",
            },
        )
        assert invalid.status_code == 422
