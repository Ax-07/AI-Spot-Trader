from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_spot_trader.api.routes.market_attention import router as market_attention_router
from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.attention import MarketAttentionPolicy, RadarStatus
from ai_spot_trader.market.attention_scope_trend import MarketAttentionOverviewV4, MarketScope
from ai_spot_trader.market.attention_structure import (
    MarketAttentionOverviewV5,
    StructuredMarketAttentionRadar,
)
from ai_spot_trader.market.candles import Candle, CandleKey, CandleTimeframe
from ai_spot_trader.market.microstructure import MicrostructurePolicy
from ai_spot_trader.market.structure import (
    MarketStructureAnalyzer,
    MarketStructurePolicy,
    MarketStructureState,
    MultiTimeframeStructureState,
    StructureEvent,
    SwingClassification,
    SwingKind,
    summarize_market_structures,
)

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def _policy(*, right: int = 1) -> MarketStructurePolicy:
    return MarketStructurePolicy(
        history_limit=40,
        min_history_candles=max(7, 1 + right + 3),
        pivot_left_bars=1,
        pivot_right_bars=right,
        equality_tolerance_bps=Decimal("0"),
        swing_display_limit=12,
        fetch_concurrency=4,
    )


def _candles(
    centers: list[str | int | Decimal],
    *,
    timeframe: CandleTimeframe = CandleTimeframe.M5,
    symbol: str = "BTC/USD",
    market_type: MarketType = MarketType.SPOT,
    final: bool = True,
) -> tuple[Candle, ...]:
    duration = timeframe.duration
    start = NOW - duration * len(centers)
    rows: list[Candle] = []
    for index, raw in enumerate(centers):
        center = Decimal(str(raw))
        open_time = start + duration * index
        close_time = open_time + duration
        rows.append(
            Candle(
                symbol=symbol,
                market_type=market_type,
                timeframe=timeframe,
                open_time=open_time,
                close_time=close_time,
                open=center,
                high=center + Decimal("1"),
                low=center - Decimal("1"),
                close=center,
                volume=Decimal("1"),
                is_final=final,
                updated_at=close_time if final else open_time,
            )
        )
    return tuple(rows)


def _analyze(centers: list[int], *, timeframe: CandleTimeframe = CandleTimeframe.M5):
    analyzer = MarketStructureAnalyzer(policy=_policy())
    return analyzer.analyze(
        timeframe=timeframe,
        candles=_candles(centers, timeframe=timeframe),
        observed_at=NOW,
    )


def test_detects_confirmed_swing_highs_and_higher_highs() -> None:
    result = _analyze([8, 10, 7, 12, 9, 14, 11, 13])
    assert [item.price for item in result.confirmed_swing_highs] == [
        Decimal("11"),
        Decimal("13"),
        Decimal("15"),
    ]
    assert [item.classification for item in result.confirmed_swing_highs] == [
        None,
        SwingClassification.HH,
        SwingClassification.HH,
    ]


def test_detects_confirmed_swing_lows_and_higher_lows() -> None:
    result = _analyze([8, 10, 7, 12, 9, 14, 11, 13])
    assert [item.price for item in result.confirmed_swing_lows] == [
        Decimal("6"),
        Decimal("8"),
        Decimal("10"),
    ]
    assert [item.classification for item in result.confirmed_swing_lows] == [
        None,
        SwingClassification.HL,
        SwingClassification.HL,
    ]


def test_classifies_lower_highs_and_lower_lows() -> None:
    result = _analyze([14, 12, 15, 10, 13, 8, 11, 6, 9, 7])
    highs = [item.classification for item in result.confirmed_swing_highs]
    lows = [item.classification for item in result.confirmed_swing_lows]
    assert highs[-2:] == [SwingClassification.LH, SwingClassification.LH]
    assert lows[-2:] == [SwingClassification.LL, SwingClassification.LL]


def test_bullish_structure_requires_repeated_hh_and_hl() -> None:
    result = _analyze([8, 10, 7, 12, 9, 14, 11, 13])
    assert result.state is MarketStructureState.BULLISH
    assert result.event is StructureEvent.BOS_UP
    assert result.sequence[-4:] == (
        SwingClassification.HH,
        SwingClassification.HL,
        SwingClassification.HH,
        SwingClassification.HL,
    ) or set(result.sequence[-4:]) == {SwingClassification.HH, SwingClassification.HL}


def test_bearish_structure_requires_repeated_lh_and_ll() -> None:
    result = _analyze([14, 12, 15, 10, 13, 8, 11, 6, 9, 7])
    assert result.state is MarketStructureState.BEARISH
    assert result.event in (StructureEvent.BOS_DOWN, None)
    assert result.sequence.count(SwingClassification.LH) >= 2
    assert result.sequence.count(SwingClassification.LL) >= 2


def test_transition_detects_bullish_geometry_breaking_down() -> None:
    result = _analyze([8, 10, 7, 12, 9, 11, 6, 10])
    assert result.state is MarketStructureState.TRANSITION
    assert SwingClassification.HH in result.sequence
    assert SwingClassification.HL in result.sequence
    assert SwingClassification.LH in result.sequence
    assert SwingClassification.LL in result.sequence
    assert result.event is StructureEvent.CHOCH_DOWN


def test_range_keeps_equal_levels_non_directional() -> None:
    result = _analyze([8, 10, 6, 10, 6, 10, 6, 10, 8])
    assert result.state is MarketStructureState.RANGE
    assert result.sequence == ()


def test_quasi_equal_swings_respect_the_configured_tolerance() -> None:
    analyzer = MarketStructureAnalyzer(
        policy=MarketStructurePolicy(
            history_limit=40,
            min_history_candles=7,
            pivot_left_bars=1,
            pivot_right_bars=1,
            equality_tolerance_bps=Decimal("2"),
            swing_display_limit=12,
        )
    )
    result = analyzer.analyze(
        timeframe=CandleTimeframe.M5,
        candles=_candles([8, 10, 7, Decimal("10.001"), 7, Decimal("10.002"), 8]),
        observed_at=NOW,
    )
    assert len(result.confirmed_swing_highs) == 3
    assert all(item.classification is None for item in result.confirmed_swing_highs)


def test_insufficient_history_is_unknown() -> None:
    analyzer = MarketStructureAnalyzer(policy=_policy())
    result = analyzer.analyze(
        timeframe=CandleTimeframe.M5,
        candles=_candles([8, 10, 7, 12]),
        observed_at=NOW,
    )
    assert result.state is MarketStructureState.UNKNOWN
    assert result.history_count == 4


def test_non_final_and_future_candles_do_not_change_structure() -> None:
    analyzer = MarketStructureAnalyzer(policy=_policy())
    clean = _candles([8, 10, 7, 12, 9, 14, 11, 13])
    baseline = analyzer.analyze(
        timeframe=CandleTimeframe.M5,
        candles=clean,
        observed_at=NOW,
    )
    non_final = Candle(
        symbol="BTC/USD",
        market_type=MarketType.SPOT,
        timeframe=CandleTimeframe.M5,
        open_time=NOW,
        close_time=NOW + timedelta(minutes=5),
        open=Decimal("13"),
        high=Decimal("1000"),
        low=Decimal("1"),
        close=Decimal("900"),
        volume=Decimal("999"),
        is_final=False,
        updated_at=NOW,
    )
    future_close = NOW + timedelta(minutes=10)
    future_final = non_final.model_copy(
        update={
            "open_time": NOW + timedelta(minutes=5),
            "close_time": future_close,
            "is_final": True,
            "updated_at": future_close,
        }
    )
    contaminated = analyzer.analyze(
        timeframe=CandleTimeframe.M5,
        candles=(*clean, non_final, future_final),
        observed_at=NOW,
    )
    assert contaminated.state is baseline.state
    assert contaminated.sequence == baseline.sequence
    assert contaminated.confirmed_swing_highs == baseline.confirmed_swing_highs
    assert contaminated.confirmed_swing_lows == baseline.confirmed_swing_lows


def test_pivot_is_not_visible_until_right_confirmation_bars_are_closed() -> None:
    analyzer = MarketStructureAnalyzer(policy=_policy(right=2))
    rows = _candles([8, 7, 8, 10, 7, 8, 9])
    before = analyzer.analyze(
        timeframe=CandleTimeframe.M5,
        candles=rows[:5],
        observed_at=rows[4].close_time,
    )
    after = analyzer.analyze(
        timeframe=CandleTimeframe.M5,
        candles=rows[:7],
        observed_at=rows[6].close_time,
    )
    pivot_open = rows[3].open_time
    assert all(item.open_time != pivot_open for item in before.confirmed_swing_highs)
    assert any(item.open_time == pivot_open for item in after.confirmed_swing_highs)
    confirmed = next(item for item in after.confirmed_swing_highs if item.open_time == pivot_open)
    assert confirmed.confirmed_at == rows[5].close_time


def test_confirmed_pivots_are_not_rewritten_when_later_candles_arrive() -> None:
    analyzer = MarketStructureAnalyzer(policy=_policy(right=2))
    rows = _candles([8, 7, 8, 10, 7, 8, 9, 11, 8])
    first = analyzer.analyze(
        timeframe=CandleTimeframe.M5,
        candles=rows[:7],
        observed_at=rows[6].close_time,
    )
    later = analyzer.analyze(
        timeframe=CandleTimeframe.M5,
        candles=rows,
        observed_at=NOW,
    )
    first_points = {
        (item.kind, item.open_time): (item.price, item.confirmed_at, item.classification)
        for item in (*first.confirmed_swing_highs, *first.confirmed_swing_lows)
    }
    later_points = {
        (item.kind, item.open_time): (item.price, item.confirmed_at, item.classification)
        for item in (*later.confirmed_swing_highs, *later.confirmed_swing_lows)
    }
    for key, value in first_points.items():
        assert later_points[key] == value


def test_each_timeframe_keeps_an_independent_native_structure() -> None:
    analyzer = MarketStructureAnalyzer(policy=_policy())
    patterns = {
        CandleTimeframe.M5: [14, 12, 15, 10, 13, 8, 11, 6, 9, 7],
        CandleTimeframe.M15: [14, 12, 15, 10, 13, 8, 11, 6, 9, 7],
        CandleTimeframe.H1: [8, 10, 7, 12, 9, 11, 6, 10],
        CandleTimeframe.H4: [8, 10, 7, 12, 9, 14, 11, 13],
    }
    frames = tuple(
        analyzer.analyze(
            timeframe=timeframe,
            candles=_candles(pattern, timeframe=timeframe),
            observed_at=NOW,
        )
        for timeframe, pattern in patterns.items()
    )
    summary = summarize_market_structures(observed_at=NOW, timeframes=frames)
    assert [item.timeframe for item in summary.timeframes] == list(patterns)
    assert [item.state for item in summary.timeframes] == [
        MarketStructureState.BEARISH,
        MarketStructureState.BEARISH,
        MarketStructureState.TRANSITION,
        MarketStructureState.BULLISH,
    ]
    assert summary.global_state is MultiTimeframeStructureState.MIXED


class _Catalogue:
    async def list_markets(self):
        return ()

    async def aclose(self) -> None:
        return None


class _NativeCandles:
    def __init__(self) -> None:
        self.calls: list[tuple[CandleKey, datetime, int]] = []

    async def history_as_of(self, key: CandleKey, *, as_of: datetime, limit: int = 1000):
        self.calls.append((key, as_of, limit))
        return ()

    async def history(self, key: CandleKey, *, limit: int = 1000):
        return ()


class _Microstructure:
    async def fetch_order_book(self, symbol: str, *, limit: int):
        raise RuntimeError("unused")

    async def fetch_recent_trades(self, symbol: str, *, limit: int):
        raise RuntimeError("unused")

    async def aclose(self) -> None:
        return None


def test_radar_requests_native_5m_15m_1h_4h_history_as_of_for_the_same_market() -> None:
    async def scenario() -> None:
        candles = _NativeCandles()
        radar = StructuredMarketAttentionRadar(
            candle_service=candles,  # type: ignore[arg-type]
            catalogue=_Catalogue(),
            microstructure_provider=_Microstructure(),  # type: ignore[arg-type]
            policy=MarketAttentionPolicy(scan_limit=10, candle_limit=160),
            microstructure_policy=MicrostructurePolicy(),
            structure_policy=MarketStructurePolicy(history_limit=100),
        )
        market = ExecutableMarket(symbol="PENDLE/USD", market_type=MarketType.SPOT)
        structure = await radar._market_structure_for_market(market, observed_at=NOW)
        assert [call[0].timeframe for call in candles.calls] == [
            CandleTimeframe.M5,
            CandleTimeframe.M15,
            CandleTimeframe.H1,
            CandleTimeframe.H4,
        ]
        assert all(call[0].symbol == "PENDLE/USD" for call in candles.calls)
        assert all(call[0].market_type is MarketType.SPOT for call in candles.calls)
        assert all(call[1] == NOW for call in candles.calls)
        assert all(call[2] == 100 for call in candles.calls)
        assert structure.global_state is MultiTimeframeStructureState.UNKNOWN

    asyncio.run(scenario())


class _V5Service:
    def __init__(self) -> None:
        self._latest = MarketAttentionOverviewV5.from_v4(
            MarketAttentionOverviewV4(
                observed_at=NOW,
                status=RadarStatus.AVAILABLE,
                market_scope=MarketScope.SPOT,
            )
        )

    @property
    def latest(self):
        return self._latest

    def history(self, *, limit: int = 24):
        return (self._latest,)

    async def set_market_scope(self, market_scope: MarketScope, *, observed_at=None):
        return self._latest.model_copy(update={"market_scope": market_scope})


def test_api_exposes_v5_structure_contract_without_breaking_v4_compatibility() -> None:
    app = FastAPI()
    app.state.market_attention = _V5Service()
    app.include_router(market_attention_router)
    with TestClient(app) as client:
        response = client.get("/api/v1/market-attention")
        assert response.status_code == 200
        assert response.json()["protocol_version"] == "market-attention-radar-v5"
        assert response.json()["market_scope"] == "SPOT"

    v4_app = FastAPI()
    v4_app.state.market_attention = type(
        "V4Service",
        (),
        {
            "latest": MarketAttentionOverviewV4(
                observed_at=NOW,
                status=RadarStatus.AVAILABLE,
                market_scope=MarketScope.ALL,
            ),
            "history": lambda self, limit=24: (self.latest,),
        },
    )()
    v4_app.include_router(market_attention_router)
    with TestClient(v4_app) as client:
        response = client.get("/api/v1/market-attention")
        assert response.status_code == 200
        assert response.json()["protocol_version"] == "market-attention-radar-v4"
