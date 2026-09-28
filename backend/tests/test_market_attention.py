from __future__ import annotations

import asyncio
import inspect
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

import ai_spot_trader.market.attention as attention_module
from ai_spot_trader.api.routes.market_attention import router as market_attention_router
from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.attention import (
    MarketActivityAnalyzer,
    MarketActivityState,
    MarketAttentionPolicy,
    MarketAttentionRadar,
    MarketAttentionOverview,
    PublicAttentionDirection,
    PublicAttentionSnapshot,
    RadarStatus,
)
from ai_spot_trader.market.candles import Candle, CandleKey, CandleTimeframe

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


def candle(
    index: int,
    *,
    symbol: str = "QNT/USD",
    market_type: MarketType = MarketType.SPOT,
    volume: str = "1",
    close: str = "100",
) -> Candle:
    open_time = NOW - timedelta(minutes=5 * (404 - index))
    close_time = open_time + timedelta(minutes=5)
    price = Decimal(close)
    return Candle(
        symbol=symbol,
        market_type=market_type,
        timeframe=CandleTimeframe.M5,
        open_time=open_time,
        close_time=close_time,
        open=price,
        high=price * Decimal("1.01"),
        low=price * Decimal("0.99"),
        close=price,
        volume=Decimal(volume),
        is_final=True,
        updated_at=close_time,
    )


def history(
    *,
    symbol: str = "QNT/USD",
    market_type: MarketType = MarketType.SPOT,
    baseline: str = "1",
    previous: str = "2",
    current: str = "6",
) -> tuple[Candle, ...]:
    rows: list[Candle] = []
    for index in range(404):
        volume = baseline
        if index >= 404 - 96 and index < 404 - 48:
            volume = previous
        elif index >= 404 - 48:
            volume = current
        rows.append(candle(index, symbol=symbol, market_type=market_type, volume=volume))
    return tuple(rows)


def test_market_activity_uses_relative_volume_and_detects_acceleration() -> None:
    analyzer = MarketActivityAnalyzer(baseline_periods=6, stale_after=timedelta(minutes=15))
    market = ExecutableMarket(symbol="QNT/USD", market_type=MarketType.SPOT)
    snapshot = analyzer.analyze(market=market, candles=history(), observed_at=NOW)
    h4 = snapshot.horizon(CandleTimeframe.H4)

    assert snapshot.status is RadarStatus.AVAILABLE
    assert snapshot.activity_state is MarketActivityState.VERY_HIGH
    assert h4 is not None and h4.complete is True
    assert h4.current_volume == Decimal("288")
    assert h4.previous_comparable_volume == Decimal("96")
    assert h4.baseline_volume == Decimal("48")
    assert h4.volume_ratio == Decimal("6")
    assert h4.volume_change == Decimal("2")
    assert h4.volume_acceleration == Decimal("1")


def test_market_activity_does_not_bridge_candle_gaps() -> None:
    analyzer = MarketActivityAnalyzer(baseline_periods=6, stale_after=timedelta(minutes=15))
    market = ExecutableMarket(symbol="QNT/USD", market_type=MarketType.SPOT)
    rows = list(history())
    del rows[-200]

    snapshot = analyzer.analyze(market=market, candles=tuple(rows), observed_at=NOW)
    h4 = snapshot.horizon(CandleTimeframe.H4)

    assert h4 is not None
    assert h4.complete is False
    assert h4.volume_ratio is None


def test_market_activity_keeps_spot_and_perpetual_separate() -> None:
    analyzer = MarketActivityAnalyzer(baseline_periods=6, stale_after=timedelta(minutes=15))
    spot_market = ExecutableMarket(symbol="QNT/USD", market_type=MarketType.SPOT)
    perp_market = ExecutableMarket(symbol="QNT/USD", market_type=MarketType.PERPETUAL)
    mixed = history(market_type=MarketType.SPOT) + history(market_type=MarketType.PERPETUAL)

    spot = analyzer.analyze(market=spot_market, candles=mixed, observed_at=NOW)
    perp = analyzer.analyze(market=perp_market, candles=mixed, observed_at=NOW)

    assert spot.market.market_type is MarketType.SPOT
    assert perp.market.market_type is MarketType.PERPETUAL
    assert spot.horizon(CandleTimeframe.H4).observation_count == 48  # type: ignore[union-attr]
    assert perp.horizon(CandleTimeframe.H4).observation_count == 48  # type: ignore[union-attr]


def test_market_activity_reports_insufficient_and_stale_data_without_fake_statistics() -> None:
    analyzer = MarketActivityAnalyzer(baseline_periods=6, stale_after=timedelta(minutes=15))
    market = ExecutableMarket(symbol="QNT/USD", market_type=MarketType.SPOT)
    insufficient = analyzer.analyze(market=market, candles=history()[-20:], observed_at=NOW)
    stale_now = NOW + timedelta(hours=2)
    stale = analyzer.analyze(market=market, candles=history(), observed_at=stale_now)

    assert insufficient.status is RadarStatus.PARTIAL
    assert insufficient.horizon(CandleTimeframe.H4).complete is False  # type: ignore[union-attr]
    assert insufficient.horizon(CandleTimeframe.H4).volume_ratio is None  # type: ignore[union-attr]
    assert stale.status is RadarStatus.STALE


class FakeCandleService:
    async def history(self, key: CandleKey, *, limit: int = 1000) -> tuple[Candle, ...]:
        return history(symbol=key.symbol, market_type=key.market_type)[-limit:]


class FakeCatalogue:
    def __init__(self, markets: tuple[ExecutableMarket, ...]) -> None:
        self.markets = markets
        self.closed = False

    async def list_markets(self) -> tuple[ExecutableMarket, ...]:
        return self.markets

    async def aclose(self) -> None:
        self.closed = True


class FakeResearcher:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[str] = []
        self.closed = False

    async def research(self, *, asset: str, symbols: tuple[str, ...], observed_at: datetime):
        self.calls.append(asset)
        if self.fail:
            raise TimeoutError("simulated web timeout")
        return PublicAttentionSnapshot(
            asset=asset,
            observed_at=observed_at,
            research_status=RadarStatus.AVAILABLE,
            attention_direction=PublicAttentionDirection.RISING,
            confidence_context="public activity is rising across cited sources",
        )

    async def aclose(self) -> None:
        self.closed = True


def test_radar_prefilters_candidates_bounds_web_calls_and_deduplicates_asset_research() -> None:
    async def scenario() -> None:
        markets = (
            ExecutableMarket(symbol="QNT/USD", market_type=MarketType.SPOT),
            ExecutableMarket(symbol="QNT/USD", market_type=MarketType.PERPETUAL),
            ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),
        )
        researcher = FakeResearcher()
        radar = MarketAttentionRadar(
            candle_service=FakeCandleService(),  # type: ignore[arg-type]
            catalogue=FakeCatalogue(markets),
            researcher=researcher,
            policy=MarketAttentionPolicy(
                scan_limit=10,
                candidate_limit=3,
                max_web_searches_per_refresh=2,
                candle_limit=404,
            ),
        )
        overview = await radar.refresh_once(observed_at=NOW)
        assert overview.candidate_market_count == 3
        assert overview.web_search_count == 2
        assert len(researcher.calls) == 2
        assert len(set(researcher.calls)) == 2
        assert overview.shortlist[0].attention_level.value in {"HIGH", "MEDIUM"}
        await radar.aclose()

    asyncio.run(scenario())


def test_radar_does_not_spend_web_searches_on_normal_market_activity() -> None:
    class NormalCandleService:
        async def history(
            self, key: CandleKey, *, limit: int = 1000
        ) -> tuple[Candle, ...]:
            return history(
                symbol=key.symbol,
                market_type=key.market_type,
                baseline="1",
                previous="1",
                current="1",
            )[-limit:]

    async def scenario() -> None:
        market = ExecutableMarket(symbol="QNT/USD", market_type=MarketType.SPOT)
        researcher = FakeResearcher()
        radar = MarketAttentionRadar(
            candle_service=NormalCandleService(),  # type: ignore[arg-type]
            catalogue=FakeCatalogue((market,)),
            researcher=researcher,
            policy=MarketAttentionPolicy(
                scan_limit=10,
                candidate_limit=1,
                max_web_searches_per_refresh=1,
                candle_limit=404,
            ),
        )
        overview = await radar.refresh_once(observed_at=NOW)
        assert overview.candidate_market_count == 0
        assert overview.web_search_count == 0
        assert researcher.calls == []
        await radar.aclose()

    asyncio.run(scenario())


def test_web_failure_never_fails_market_activity_refresh() -> None:
    async def scenario() -> None:
        market = ExecutableMarket(symbol="QNT/USD", market_type=MarketType.SPOT)
        radar = MarketAttentionRadar(
            candle_service=FakeCandleService(),  # type: ignore[arg-type]
            catalogue=FakeCatalogue((market,)),
            researcher=FakeResearcher(fail=True),
            policy=MarketAttentionPolicy(
                scan_limit=10,
                candidate_limit=1,
                max_web_searches_per_refresh=1,
                candle_limit=404,
            ),
        )
        overview = await radar.refresh_once(observed_at=NOW)
        assert overview.status is RadarStatus.PARTIAL
        assert overview.shortlist[0].market_activity.status is RadarStatus.AVAILABLE
        assert overview.shortlist[0].public_attention.research_status is RadarStatus.ERROR
        await radar.aclose()

    asyncio.run(scenario())


def test_radar_without_web_is_useful_market_only_and_not_configured_publicly() -> None:
    async def scenario() -> None:
        market = ExecutableMarket(symbol="QNT/USD", market_type=MarketType.SPOT)
        radar = MarketAttentionRadar(
            candle_service=FakeCandleService(),  # type: ignore[arg-type]
            catalogue=FakeCatalogue((market,)),
            researcher=None,
            policy=MarketAttentionPolicy(
                scan_limit=10,
                candidate_limit=1,
                max_web_searches_per_refresh=0,
                candle_limit=404,
            ),
        )
        overview = await radar.refresh_once(observed_at=NOW)
        item = overview.shortlist[0]
        assert item.market_activity.status is RadarStatus.AVAILABLE
        assert item.public_attention.research_status is RadarStatus.NOT_CONFIGURED
        assert item.cross_state.value == "MARKET_ONLY"
        await radar.aclose()

    asyncio.run(scenario())


def test_market_attention_api_is_read_only_and_exposes_latest_snapshot() -> None:
    class Reader:
        @property
        def latest(self) -> MarketAttentionOverview:
            return MarketAttentionOverview(observed_at=NOW, status=RadarStatus.PARTIAL)

        def history(self, *, limit: int = 24):
            return (self.latest,)

    app = FastAPI()
    app.state.market_attention = Reader()
    app.include_router(market_attention_router)
    with TestClient(app) as client:
        response = client.get("/api/v1/market-attention")
        history_response = client.get("/api/v1/market-attention/history?limit=1")
        assert response.status_code == 200
        assert response.json()["informative_only"] is True
        assert history_response.status_code == 200
        assert len(history_response.json()["items"]) == 1
        assert client.post("/api/v1/market-attention").status_code == 405


def test_radar_module_has_no_agent_risk_broker_or_market_discovery_dependency() -> None:
    source = inspect.getsource(attention_module)
    assert "ai_spot_trader.agent" not in source
    assert "ai_spot_trader.risk" not in source
    assert "ai_spot_trader.broker" not in source
    assert "ai_spot_trader.market.discovery" not in source
