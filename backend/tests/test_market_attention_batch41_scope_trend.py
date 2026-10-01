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
    MarketActivityAnalyzer,
    MarketActivitySnapshot,
    MarketActivityState,
    MarketAttentionPolicy,
    MarketCharacteristic,
    RadarStatus,
)
from ai_spot_trader.market.attention_scope_trend import (
    MarketAttentionOverviewV4,
    MarketScope,
    ScopedTrendMarketAttentionRadar,
    TrendDirection,
    _normalize_trending,
    horizon_trend_direction,
    summarize_trend_direction,
)
from ai_spot_trader.market.candles import Candle, CandleKey, CandleTimeframe
from ai_spot_trader.market.microstructure import MicrostructurePolicy

NOW = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)


def _horizon(
    timeframe: CandleTimeframe,
    price_return: str | None,
    *,
    complete: bool = True,
) -> ActivityHorizonSnapshot:
    return ActivityHorizonSnapshot(
        timeframe=timeframe,
        price_return=Decimal(price_return) if price_return is not None else None,
        observation_count=1 if complete else 0,
        baseline_period_count=6 if complete else 0,
        complete=complete,
    )


def test_horizon_direction_reuses_material_return_thresholds_inclusively() -> None:
    cases = (
        (CandleTimeframe.M5, "0.003"),
        (CandleTimeframe.M15, "0.005"),
        (CandleTimeframe.H1, "0.010"),
        (CandleTimeframe.H4, "0.020"),
    )
    for timeframe, threshold in cases:
        assert horizon_trend_direction(_horizon(timeframe, threshold)) is TrendDirection.UP
        assert horizon_trend_direction(_horizon(timeframe, f"-{threshold}")) is TrendDirection.DOWN
    assert horizon_trend_direction(_horizon(CandleTimeframe.M5, "0.0029")) is TrendDirection.NEUTRAL
    assert horizon_trend_direction(_horizon(CandleTimeframe.M5, None)) is TrendDirection.UNKNOWN
    assert horizon_trend_direction(_horizon(CandleTimeframe.M5, "0.5", complete=False)) is TrendDirection.UNKNOWN


def test_global_direction_is_deterministic_multi_timeframe_and_conflict_aware() -> None:
    assert summarize_trend_direction(
        (
            _horizon(CandleTimeframe.M5, "0.004"),
            _horizon(CandleTimeframe.M15, "0.006"),
            _horizon(CandleTimeframe.H1, "0.005"),
            _horizon(CandleTimeframe.H4, "0.021"),
        )
    ) is TrendDirection.UP
    assert summarize_trend_direction(
        (
            _horizon(CandleTimeframe.M5, "-0.004"),
            _horizon(CandleTimeframe.M15, "-0.006"),
            _horizon(CandleTimeframe.H1, "-0.011"),
            _horizon(CandleTimeframe.H4, "0.005"),
        )
    ) is TrendDirection.DOWN
    assert summarize_trend_direction(
        (
            _horizon(CandleTimeframe.M5, "0.004"),
            _horizon(CandleTimeframe.M15, "0.006"),
            _horizon(CandleTimeframe.H1, "-0.011"),
            _horizon(CandleTimeframe.H4, "-0.021"),
        )
    ) is TrendDirection.MIXED
    assert summarize_trend_direction(
        (
            _horizon(CandleTimeframe.M5, "0.001"),
            _horizon(CandleTimeframe.M15, "-0.001"),
            _horizon(CandleTimeframe.H1, "0.005"),
            _horizon(CandleTimeframe.H4, "-0.005"),
        )
    ) is TrendDirection.NEUTRAL
    assert summarize_trend_direction(
        (
            _horizon(CandleTimeframe.M5, "0.004"),
            _horizon(CandleTimeframe.M15, "0.001"),
            _horizon(CandleTimeframe.H1, "0.005"),
            _horizon(CandleTimeframe.H4, "0.005"),
        )
    ) is TrendDirection.UNKNOWN


def _causal_history() -> tuple[Candle, ...]:
    rows: list[Candle] = []
    for index in range(404):
        open_time = NOW - timedelta(minutes=5 * (404 - index))
        close_time = open_time + timedelta(minutes=5)
        rows.append(
            Candle(
                symbol="BTC/USD",
                market_type=MarketType.SPOT,
                timeframe=CandleTimeframe.M5,
                open_time=open_time,
                close_time=close_time,
                open=Decimal("100"),
                high=Decimal("101"),
                low=Decimal("99"),
                close=Decimal("100"),
                volume=Decimal("1"),
                is_final=True,
                updated_at=close_time,
            )
        )
    return tuple(rows)


def test_trend_direction_inherits_finalized_candle_causality_without_lookahead() -> None:
    market = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT)
    analyzer = MarketActivityAnalyzer(
        baseline_periods=6,
        stale_after=timedelta(minutes=15),
    )
    baseline = _causal_history()
    future_open = NOW
    future_close = NOW + timedelta(minutes=5)
    future_final = Candle(
        symbol=market.symbol,
        market_type=market.market_type,
        timeframe=CandleTimeframe.M5,
        open_time=future_open,
        close_time=future_close,
        open=Decimal("100"),
        high=Decimal("250"),
        low=Decimal("1"),
        close=Decimal("250"),
        volume=Decimal("999999"),
        is_final=True,
        updated_at=future_close,
    )
    non_final = future_final.model_copy(
        update={
            "close_time": NOW,
            "open_time": NOW - timedelta(minutes=5),
            "is_final": False,
            "updated_at": NOW,
        }
    )

    clean = analyzer.analyze(market=market, candles=baseline, observed_at=NOW)
    contaminated = analyzer.analyze(
        market=market,
        candles=(*baseline, non_final, future_final),
        observed_at=NOW,
    )

    assert tuple(item.price_return for item in contaminated.horizons) == tuple(
        item.price_return for item in clean.horizons
    )
    assert summarize_trend_direction(contaminated.horizons) is summarize_trend_direction(
        clean.horizons
    )


def test_trending_characteristic_is_derived_from_the_same_direction_summary() -> None:
    market = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT)
    mixed = MarketActivitySnapshot(
        market=market,
        observed_at=NOW,
        status=RadarStatus.AVAILABLE,
        activity_state=MarketActivityState.NORMAL,
        horizons=(
            _horizon(CandleTimeframe.M5, "0.004"),
            _horizon(CandleTimeframe.M15, "0.006"),
            _horizon(CandleTimeframe.H1, "-0.011"),
            _horizon(CandleTimeframe.H4, "-0.021"),
        ),
        characteristics=(MarketCharacteristic.TRENDING,),
    )
    normalized_mixed = _normalize_trending(mixed)
    assert summarize_trend_direction(normalized_mixed.horizons) is TrendDirection.MIXED
    assert MarketCharacteristic.TRENDING not in normalized_mixed.characteristics

    aligned = mixed.model_copy(
        update={
            "horizons": (
                _horizon(CandleTimeframe.M5, "0.004"),
                _horizon(CandleTimeframe.M15, "0.006"),
                _horizon(CandleTimeframe.H1, "0.005"),
                _horizon(CandleTimeframe.H4, "0.021"),
            ),
            "characteristics": (),
        }
    )
    normalized_aligned = _normalize_trending(aligned)
    assert summarize_trend_direction(normalized_aligned.horizons) is TrendDirection.UP
    assert MarketCharacteristic.TRENDING in normalized_aligned.characteristics


class Catalogue:
    def __init__(self) -> None:
        self.markets = (
            ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),
            ExecutableMarket(symbol="ETH/USD", market_type=MarketType.SPOT),
            ExecutableMarket(symbol="BTC/USD", market_type=MarketType.PERPETUAL),
            ExecutableMarket(symbol="ETH/USD", market_type=MarketType.PERPETUAL),
        )

    async def list_markets(self):
        return self.markets

    async def aclose(self) -> None:
        return None


class Candles:
    def __init__(self) -> None:
        self.calls: list[CandleKey] = []

    async def history(self, key: CandleKey, *, limit: int = 1000):
        self.calls.append(key)
        return ()


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


def test_scope_filters_before_ohlcv_scan_and_prevents_cache_or_microstructure_leaks() -> None:
    async def scenario() -> None:
        candles = Candles()
        micro = Microstructure()
        radar = ScopedTrendMarketAttentionRadar(
            candle_service=candles,  # type: ignore[arg-type]
            catalogue=Catalogue(),
            microstructure_provider=micro,  # type: ignore[arg-type]
            policy=MarketAttentionPolicy(scan_limit=10, candle_limit=160),
            microstructure_policy=MicrostructurePolicy(),
        )

        all_snapshot = await radar.refresh_once(observed_at=NOW)
        assert all_snapshot.market_scope is MarketScope.ALL
        assert {call.market_type for call in candles.calls} == {MarketType.SPOT, MarketType.PERPETUAL}
        assert all_snapshot.catalogue_market_count == 4
        assert all_snapshot.microstructure_status_counts.NOT_APPLICABLE == 2
        assert len(micro.calls) == 4

        candles.calls.clear()
        micro.calls.clear()
        spot_snapshot = await radar.set_market_scope(
            MarketScope.SPOT,
            observed_at=NOW + timedelta(seconds=301),
        )
        assert spot_snapshot.market_scope is MarketScope.SPOT
        assert candles.calls and all(call.market_type is MarketType.SPOT for call in candles.calls)
        assert spot_snapshot.catalogue_market_count == 2
        assert spot_snapshot.fresh_market_type_counts.PERPETUAL == 0
        assert spot_snapshot.scanned_market_type_counts.PERPETUAL == 0
        assert len(micro.calls) == 4
        assert all(
            item.market_activity.market.market_type is MarketType.SPOT
            for item in spot_snapshot.shortlist
        )
        assert sum(spot_snapshot.liquidity_regime_counts.model_dump().values()) == (
            spot_snapshot.cached_activity_market_count
        )

        candles.calls.clear()
        micro.calls.clear()
        perp_snapshot = await radar.set_market_scope(
            MarketScope.PERPETUAL,
            observed_at=NOW + timedelta(seconds=302),
        )
        assert perp_snapshot.market_scope is MarketScope.PERPETUAL
        assert candles.calls and all(call.market_type is MarketType.PERPETUAL for call in candles.calls)
        assert micro.calls == []
        assert perp_snapshot.catalogue_market_count == 2
        assert perp_snapshot.cached_activity_market_count == 2
        assert perp_snapshot.fresh_market_type_counts.SPOT == 0
        assert perp_snapshot.scanned_market_type_counts.SPOT == 0
        assert perp_snapshot.microstructure_cached_market_count == 0
        assert perp_snapshot.microstructure_scanned_market_count == 0
        assert perp_snapshot.microstructure_status_counts.NOT_APPLICABLE == 2
        assert all(
            item.market_activity.market.market_type is MarketType.PERPETUAL
            for item in perp_snapshot.shortlist
        )
        assert sum(perp_snapshot.liquidity_regime_counts.model_dump().values()) == (
            perp_snapshot.cached_activity_market_count
        )

        candles.calls.clear()
        restored = await radar.set_market_scope(
            MarketScope.ALL,
            observed_at=NOW + timedelta(seconds=303),
        )
        assert restored.market_scope is MarketScope.ALL
        assert {call.market_type for call in candles.calls} == {
            MarketType.SPOT,
            MarketType.PERPETUAL,
        }
        assert all(
            item.market_activity.market.market_type in (MarketType.SPOT, MarketType.PERPETUAL)
            for item in restored.shortlist
        )
        await radar.aclose()

    asyncio.run(scenario())


class ScopeService:
    def __init__(self) -> None:
        self.requested: list[MarketScope] = []
        self._latest = MarketAttentionOverviewV4(
            observed_at=NOW,
            status=RadarStatus.AVAILABLE,
            market_scope=MarketScope.ALL,
        )

    @property
    def latest(self) -> MarketAttentionOverviewV4:
        return self._latest

    def history(self, *, limit: int = 24):
        return (self._latest,)

    async def set_market_scope(
        self,
        market_scope: MarketScope,
        *,
        observed_at: datetime | None = None,
    ) -> MarketAttentionOverviewV4:
        self.requested.append(market_scope)
        self._latest = self._latest.model_copy(update={"market_scope": market_scope})
        return self._latest


def test_scope_api_serializes_active_scope_and_rejects_invalid_values() -> None:
    app = FastAPI()
    service = ScopeService()
    app.state.market_attention = service
    app.include_router(market_attention_router)
    with TestClient(app) as client:
        response = client.put(
            "/api/v1/market-attention/scope",
            json={"market_scope": "SPOT"},
        )
        assert response.status_code == 200
        assert response.json()["protocol_version"] == "market-attention-radar-v4"
        assert response.json()["market_scope"] == "SPOT"
        invalid = client.put(
            "/api/v1/market-attention/scope",
            json={"market_scope": "FUTURES"},
        )
        assert invalid.status_code == 422
    assert service.requested == [MarketScope.SPOT]
