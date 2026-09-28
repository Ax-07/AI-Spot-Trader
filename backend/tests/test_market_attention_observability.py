from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_spot_trader.api.routes.market_attention import router as market_attention_router
from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.attention import (
    ActivityHorizonSnapshot,
    MarketActivitySnapshot,
    MarketActivityState,
    MarketAttentionPolicy,
    MarketAttentionRadar,
    PublicAttentionDirection,
    PublicAttentionSnapshot,
    RadarStatus,
)
from ai_spot_trader.market.candles import Candle, CandleKey, CandleTimeframe

NOW = datetime(2026, 9, 28, 14, 0, tzinfo=UTC)


def _market(symbol: str) -> ExecutableMarket:
    return ExecutableMarket(symbol=symbol, market_type=MarketType.SPOT)


def _candles(
    symbol: str,
    *,
    anchor: datetime = NOW,
    last_volume: str = "1",
    count: int = 404,
) -> tuple[Candle, ...]:
    rows: list[Candle] = []
    for index in range(count):
        open_time = anchor - timedelta(minutes=5 * (count - index))
        close_time = open_time + timedelta(minutes=5)
        volume = Decimal(last_volume if index == count - 1 else "1")
        rows.append(
            Candle(
                symbol=symbol,
                market_type=MarketType.SPOT,
                timeframe=CandleTimeframe.M5,
                open_time=open_time,
                close_time=close_time,
                open=Decimal("100"),
                high=Decimal("101"),
                low=Decimal("99"),
                close=Decimal("100"),
                volume=volume,
                is_final=True,
                updated_at=close_time,
            )
        )
    return tuple(rows)


class Catalogue:
    def __init__(self, markets: tuple[ExecutableMarket, ...]) -> None:
        self.markets = markets

    async def list_markets(self) -> tuple[ExecutableMarket, ...]:
        return self.markets

    async def aclose(self) -> None:
        return None


class CandleService:
    def __init__(self, rows: dict[str, tuple[Candle, ...] | Exception]) -> None:
        self.rows = rows

    async def history(self, key: CandleKey, *, limit: int = 1000) -> tuple[Candle, ...]:
        value = self.rows[key.symbol]
        if isinstance(value, Exception):
            raise value
        return value[-limit:]


class Researcher:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def research(self, *, asset: str, symbols: tuple[str, ...], observed_at: datetime):
        self.calls.append(asset)
        return PublicAttentionSnapshot(
            asset=asset,
            observed_at=observed_at,
            research_status=RadarStatus.AVAILABLE,
            attention_direction=PublicAttentionDirection.STABLE,
            confidence_context="diagnostic test",
        )

    async def aclose(self) -> None:
        return None


def _policy(**updates: object) -> MarketAttentionPolicy:
    values: dict[str, object] = {
        "scan_limit": 10,
        "candidate_limit": 10,
        "diagnostic_market_limit": 10,
        "max_web_searches_per_refresh": 10,
        "candle_limit": 404,
    }
    values.update(updates)
    return MarketAttentionPolicy(**values)


def test_overview_counts_status_and_activity_state_for_fresh_cache_only() -> None:
    async def scenario() -> None:
        markets = (_market("AAA/USD"), _market("BBB/USD"), _market("CCC/USD"), _market("DDD/USD"))
        radar = MarketAttentionRadar(
            candle_service=CandleService(
                {
                    "AAA/USD": _candles("AAA/USD", last_volume="1.20"),
                    "BBB/USD": _candles("BBB/USD", count=20),
                    "CCC/USD": _candles("CCC/USD", anchor=NOW - timedelta(hours=2)),
                    "DDD/USD": RuntimeError("simulated candle failure"),
                }
            ),  # type: ignore[arg-type]
            catalogue=Catalogue(markets),
            researcher=None,
            policy=_policy(max_web_searches_per_refresh=0),
        )

        expired = MarketActivitySnapshot(
            market=_market("OLD/USD"),
            observed_at=NOW - timedelta(hours=1),
            status=RadarStatus.AVAILABLE,
            activity_state=MarketActivityState.VERY_HIGH,
            freshness_seconds=Decimal("0"),
            horizons=(),
        )
        radar._activity_cache[expired.market] = expired

        overview = await radar.refresh_once(observed_at=NOW)

        assert overview.cached_activity_market_count == 4
        assert overview.activity_status_counts.model_dump() == {
            "AVAILABLE": 1,
            "PARTIAL": 1,
            "STALE": 1,
            "ERROR": 1,
        }
        assert sum(overview.activity_state_counts.model_dump().values()) == 4
        assert overview.activity_state_counts.VERY_HIGH == 0
        assert overview.activity_state_counts.UNKNOWN >= 1
        await radar.aclose()

    asyncio.run(scenario())


def test_activity_state_counts_cover_all_states_and_ignore_expired_snapshots() -> None:
    async def scenario() -> None:
        radar = MarketAttentionRadar(
            candle_service=CandleService({}),  # type: ignore[arg-type]
            catalogue=Catalogue(()),
            researcher=None,
            policy=_policy(max_web_searches_per_refresh=0),
        )
        states = (
            MarketActivityState.UNKNOWN,
            MarketActivityState.NORMAL,
            MarketActivityState.ELEVATED,
            MarketActivityState.ACCELERATING,
            MarketActivityState.VERY_HIGH,
        )
        for index, state in enumerate(states):
            snapshot = MarketActivitySnapshot(
                market=_market(f"S{index}/USD"),
                observed_at=NOW,
                status=RadarStatus.AVAILABLE,
                activity_state=state,
                freshness_seconds=Decimal("0"),
                horizons=(),
            )
            radar._activity_cache[snapshot.market] = snapshot
        expired = MarketActivitySnapshot(
            market=_market("EXPIRED/USD"),
            observed_at=NOW - timedelta(hours=1),
            status=RadarStatus.AVAILABLE,
            activity_state=MarketActivityState.VERY_HIGH,
            freshness_seconds=Decimal("0"),
            horizons=(),
        )
        radar._activity_cache[expired.market] = expired

        overview = await radar.refresh_once(observed_at=NOW)

        assert overview.cached_activity_market_count == 5
        assert overview.activity_state_counts.model_dump() == {
            "UNKNOWN": 1,
            "NORMAL": 1,
            "ELEVATED": 1,
            "ACCELERATING": 1,
            "VERY_HIGH": 1,
        }
        await radar.aclose()

    asyncio.run(scenario())


def test_normal_markets_are_ranked_below_threshold_with_best_horizon() -> None:
    async def scenario() -> None:
        markets = (_market("AAA/USD"), _market("BBB/USD"))
        researcher = Researcher()
        radar = MarketAttentionRadar(
            candle_service=CandleService(
                {
                    "AAA/USD": _candles("AAA/USD", last_volume="1.31"),
                    "BBB/USD": _candles("BBB/USD", last_volume="1.27"),
                }
            ),  # type: ignore[arg-type]
            catalogue=Catalogue(markets),
            researcher=researcher,
            policy=_policy(),
        )

        overview = await radar.refresh_once(observed_at=NOW)

        assert overview.status is RadarStatus.AVAILABLE
        assert overview.candidate_market_count == 0
        assert overview.web_search_count == 0
        assert researcher.calls == []
        assert [item.market.symbol for item in overview.subthreshold_activity] == [
            "AAA/USD",
            "BBB/USD",
        ]
        assert overview.subthreshold_activity[0].peak_volume_ratio == Decimal("1.31")
        assert overview.subthreshold_activity[0].peak_timeframe is CandleTimeframe.M5
        await radar.aclose()

    asyncio.run(scenario())


def test_subthreshold_diagnostics_never_become_candidates_or_trigger_web_research() -> None:
    async def scenario() -> None:
        markets = (_market("NORMAL/USD"), _market("HOT/USD"))
        researcher = Researcher()
        radar = MarketAttentionRadar(
            candle_service=CandleService(
                {
                    "NORMAL/USD": _candles("NORMAL/USD", last_volume="1.39"),
                    "HOT/USD": _candles("HOT/USD", last_volume="1.50"),
                }
            ),  # type: ignore[arg-type]
            catalogue=Catalogue(markets),
            researcher=researcher,
            policy=_policy(),
        )

        overview = await radar.refresh_once(observed_at=NOW)

        assert [item.market.symbol for item in overview.subthreshold_activity] == ["NORMAL/USD"]
        assert [item.market_activity.market.symbol for item in overview.shortlist] == ["HOT/USD"]
        assert researcher.calls == ["HOT"]
        assert overview.web_search_count == 1
        await radar.aclose()

    asyncio.run(scenario())


def test_empty_shortlist_with_healthy_available_activity_is_operational() -> None:
    async def scenario() -> None:
        market = _market("AAA/USD")
        radar = MarketAttentionRadar(
            candle_service=CandleService({"AAA/USD": _candles("AAA/USD", last_volume="1.10")}),  # type: ignore[arg-type]
            catalogue=Catalogue((market,)),
            researcher=Researcher(),
            policy=_policy(),
        )

        overview = await radar.refresh_once(observed_at=NOW)
        assert overview.status is RadarStatus.AVAILABLE
        assert overview.candidate_market_count == 0
        await radar.aclose()

    asyncio.run(scenario())


def test_empty_shortlist_with_no_available_activity_remains_partial() -> None:
    async def scenario() -> None:
        market = _market("AAA/USD")
        radar = MarketAttentionRadar(
            candle_service=CandleService({"AAA/USD": _candles("AAA/USD", count=20)}),  # type: ignore[arg-type]
            catalogue=Catalogue((market,)),
            researcher=Researcher(),
            policy=_policy(),
        )

        overview = await radar.refresh_once(observed_at=NOW)
        assert overview.status is RadarStatus.PARTIAL
        assert overview.activity_status_counts.PARTIAL == 1
        await radar.aclose()

    asyncio.run(scenario())


def test_read_only_api_exposes_additive_observability_fields() -> None:
    market = _market("AAA/USD")
    horizon = ActivityHorizonSnapshot(
        timeframe=CandleTimeframe.M5,
        volume_ratio=Decimal("1.31"),
        observation_count=1,
        baseline_period_count=6,
        complete=True,
    )
    activity = MarketActivitySnapshot(
        market=market,
        observed_at=NOW,
        status=RadarStatus.AVAILABLE,
        activity_state=MarketActivityState.NORMAL,
        freshness_seconds=Decimal("0"),
        horizons=(horizon,),
    )

    class Reader:
        @property
        def latest(self):
            from ai_spot_trader.market.attention import (
                ActivityStateCounts,
                ActivityStatusCounts,
                MarketAttentionOverview,
                SubthresholdActivitySnapshot,
            )

            return MarketAttentionOverview(
                observed_at=NOW,
                status=RadarStatus.AVAILABLE,
                cached_activity_market_count=1,
                activity_status_counts=ActivityStatusCounts(AVAILABLE=1),
                activity_state_counts=ActivityStateCounts(NORMAL=1),
                subthreshold_activity=(
                    SubthresholdActivitySnapshot(
                        market=market,
                        peak_volume_ratio=Decimal("1.31"),
                        peak_timeframe=CandleTimeframe.M5,
                    ),
                ),
            )

        def history(self, *, limit: int = 24):
            return (self.latest,)

    app = FastAPI()
    app.state.market_attention = Reader()
    app.include_router(market_attention_router)

    with TestClient(app) as client:
        response = client.get("/api/v1/market-attention")
        payload = response.json()
        assert response.status_code == 200
        assert payload["activity_status_counts"]["AVAILABLE"] == 1
        assert payload["activity_state_counts"]["NORMAL"] == 1
        assert payload["subthreshold_activity"][0]["market"]["symbol"] == "AAA/USD"
        assert client.post("/api/v1/market-attention").status_code == 405
