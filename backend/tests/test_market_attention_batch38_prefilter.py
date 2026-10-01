from __future__ import annotations

import asyncio
import inspect
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import ai_spot_trader.market.attention as attention_module
from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.attention import (
    ActivityHorizonSnapshot,
    MarketActivityAnalyzer,
    MarketActivitySnapshot,
    MarketActivityState,
    MarketAttentionOverview,
    MarketAttentionPolicy,
    MarketAttentionRadar,
    MarketCharacteristic,
    LiquidityRegime,
    PublicAttentionDirection,
    PublicAttentionSnapshot,
    PublicResearchSkipReason,
    PublicResearchTrigger,
    RadarInterestLevel,
    RadarStatus,
    _deterministic_radar_sort_key,
    _with_market_structure,
)
from ai_spot_trader.market.candles import Candle, CandleKey, CandleTimeframe

NOW = datetime(2026, 10, 1, 6, 0, tzinfo=UTC)


def _candle(
    index: int,
    *,
    symbol: str = "AAA/USD",
    volume: str = "1",
    open_price: Decimal = Decimal("100"),
    close_price: Decimal = Decimal("100"),
) -> Candle:
    open_time = NOW - timedelta(minutes=5 * (404 - index))
    close_time = open_time + timedelta(minutes=5)
    return Candle(
        symbol=symbol,
        market_type=MarketType.SPOT,
        timeframe=CandleTimeframe.M5,
        open_time=open_time,
        close_time=close_time,
        open=open_price,
        high=max(open_price, close_price) * Decimal("1.001"),
        low=min(open_price, close_price) * Decimal("0.999"),
        close=close_price,
        volume=Decimal(volume),
        is_final=True,
        updated_at=close_time,
    )


def _history(
    *,
    symbol: str = "AAA/USD",
    baseline: str = "1",
    previous: str = "1",
    current: str = "1",
    current_step: Decimal = Decimal("0"),
) -> tuple[Candle, ...]:
    rows: list[Candle] = []
    price = Decimal("100")
    for index in range(404):
        volume = baseline
        if 404 - 96 <= index < 404 - 48:
            volume = previous
        elif index >= 404 - 48:
            volume = current
        open_price = price
        if index >= 404 - 48:
            price = price * (Decimal(1) + current_step)
        rows.append(
            _candle(
                index,
                symbol=symbol,
                volume=volume,
                open_price=open_price,
                close_price=price,
            )
        )
    return tuple(rows)


def _analyze(**kwargs: object) -> MarketActivitySnapshot:
    analyzer = MarketActivityAnalyzer(
        baseline_periods=6,
        stale_after=timedelta(minutes=15),
    )
    market = ExecutableMarket(symbol="AAA/USD", market_type=MarketType.SPOT)
    return analyzer.analyze(
        market=market,
        candles=_history(**kwargs),
        observed_at=NOW,
    )


def _horizon(
    timeframe: CandleTimeframe,
    *,
    volume_ratio: str = "1",
    price_return: str = "0",
    previous_price_return: str = "0",
    range_expansion_ratio: str = "1",
    breakout_distance: str = "0",
) -> ActivityHorizonSnapshot:
    return ActivityHorizonSnapshot(
        timeframe=timeframe,
        volume_ratio=Decimal(volume_ratio),
        price_return=Decimal(price_return),
        previous_price_return=Decimal(previous_price_return),
        price_range=Decimal("0.01"),
        baseline_price_range=Decimal("0.01"),
        range_expansion_ratio=Decimal(range_expansion_ratio),
        realized_volatility=Decimal("0.01"),
        baseline_realized_volatility=Decimal("0.01"),
        volatility_expansion_ratio=Decimal(range_expansion_ratio),
        breakout_distance=Decimal(breakout_distance),
        observation_count=1,
        baseline_period_count=6,
        complete=True,
    )


def _snapshot(
    *,
    symbol: str = "AAA/USD",
    horizons: tuple[ActivityHorizonSnapshot, ...],
    activity_state: MarketActivityState = MarketActivityState.NORMAL,
) -> MarketActivitySnapshot:
    raw = MarketActivitySnapshot(
        market=ExecutableMarket(symbol=symbol, market_type=MarketType.SPOT),
        observed_at=NOW,
        status=RadarStatus.AVAILABLE,
        activity_state=activity_state,
        horizons=horizons,
    )
    return _with_market_structure(raw)


class _Catalogue:
    def __init__(self, markets: tuple[ExecutableMarket, ...]) -> None:
        self.markets = markets

    async def list_markets(self) -> tuple[ExecutableMarket, ...]:
        return self.markets

    async def aclose(self) -> None:
        return None


class _Candles:
    async def history(self, key: CandleKey, *, limit: int = 1000) -> tuple[Candle, ...]:
        return _history(symbol=key.symbol, current="3", previous="1.2", current_step=Decimal("0.001"))[-limit:]


class _Researcher:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def research(
        self,
        *,
        asset: str,
        symbols: tuple[str, ...],
        observed_at: datetime,
    ) -> PublicAttentionSnapshot:
        self.calls.append(asset)
        return PublicAttentionSnapshot(
            asset=asset,
            observed_at=observed_at,
            research_status=RadarStatus.AVAILABLE,
            attention_direction=PublicAttentionDirection.STABLE,
            confidence_context="Public context observed from cited sources.",
        )

    async def aclose(self) -> None:
        return None


def test_normal_market_stays_low_and_requires_no_public_research() -> None:
    snapshot = _analyze()
    assert snapshot.activity_state is MarketActivityState.NORMAL
    assert snapshot.interest_level is RadarInterestLevel.LOW
    assert snapshot.characteristics == ()


def test_isolated_volume_anomaly_is_not_enough_for_web_research() -> None:
    snapshot = _analyze(current="1.5")
    assert MarketCharacteristic.VOLUME_ANOMALY in snapshot.characteristics
    assert snapshot.interest_level is RadarInterestLevel.LOW


def test_multi_horizon_trend_and_breakout_become_high_interest() -> None:
    snapshot = _snapshot(
        horizons=(
            _horizon(CandleTimeframe.M5, volume_ratio="1.4", price_return="0.004"),
            _horizon(CandleTimeframe.M15, volume_ratio="1.5", price_return="0.008", range_expansion_ratio="1.6", breakout_distance="0.004"),
            _horizon(CandleTimeframe.H1, volume_ratio="1.6", price_return="0.018", range_expansion_ratio="1.6", breakout_distance="0.006"),
            _horizon(CandleTimeframe.H4, volume_ratio="1.5", price_return="0.03"),
        ),
        activity_state=MarketActivityState.ACCELERATING,
    )
    assert MarketCharacteristic.TRENDING in snapshot.characteristics
    assert MarketCharacteristic.BREAKOUT_WATCH in snapshot.characteristics
    assert snapshot.interest_level in {RadarInterestLevel.HIGH, RadarInterestLevel.VERY_HIGH}


def test_reversal_watch_can_become_high_interest_without_directional_signal() -> None:
    snapshot = _snapshot(
        horizons=(
            _horizon(CandleTimeframe.M5, volume_ratio="1.4"),
            _horizon(CandleTimeframe.M15, volume_ratio="1.5", price_return="0.008", previous_price_return="-0.009", range_expansion_ratio="1.4"),
            _horizon(CandleTimeframe.H1, volume_ratio="1.6", price_return="0.015", previous_price_return="-0.018", range_expansion_ratio="1.5"),
            _horizon(CandleTimeframe.H4, volume_ratio="1.3"),
        ),
        activity_state=MarketActivityState.ACCELERATING,
    )
    assert MarketCharacteristic.REVERSAL_WATCH in snapshot.characteristics
    assert snapshot.interest_level in {RadarInterestLevel.HIGH, RadarInterestLevel.VERY_HIGH}
    source = inspect.getsource(attention_module)
    assert "TradingAction" not in source


def test_fresh_public_cache_prevents_repeat_search() -> None:
    async def scenario() -> None:
        market = ExecutableMarket(symbol="AAA/USD", market_type=MarketType.SPOT)
        researcher = _Researcher()
        radar = MarketAttentionRadar(
            candle_service=_Candles(),  # type: ignore[arg-type]
            catalogue=_Catalogue((market,)),
            researcher=researcher,
            policy=MarketAttentionPolicy(
                scan_limit=10,
                candidate_limit=1,
                max_web_searches_per_refresh=1,
                candle_limit=404,
            ),
        )
        activity = _analyze(current="3", previous="1.2", current_step=Decimal("0.001")).model_copy(
            update={"interest_level": RadarInterestLevel.HIGH}
        )
        _first, first_decisions, first_count = await radar._public_attention((activity,), now=NOW)
        _second, second_decisions, second_count = await radar._public_attention(
            (activity,), now=NOW + timedelta(minutes=5)
        )
        assert first_count == 1
        assert first_decisions["AAA"].performed is True
        assert second_count == 0
        assert second_decisions["AAA"].cache_used is True
        assert second_decisions["AAA"].skip_reason is PublicResearchSkipReason.CACHE_FRESH

    asyncio.run(scenario())


def test_significant_interest_change_can_refresh_before_two_hour_ttl_after_cooldown() -> None:
    async def scenario() -> None:
        market = ExecutableMarket(symbol="AAA/USD", market_type=MarketType.SPOT)
        researcher = _Researcher()
        radar = MarketAttentionRadar(
            candle_service=_Candles(),  # type: ignore[arg-type]
            catalogue=_Catalogue((market,)),
            researcher=researcher,
            policy=MarketAttentionPolicy(
                scan_limit=10,
                candidate_limit=1,
                max_web_searches_per_refresh=1,
                candle_limit=404,
                public_attention_ttl_seconds=7200,
                public_attention_event_cooldown_seconds=900,
            ),
        )
        base = _analyze(current="3", previous="1.2", current_step=Decimal("0.001")).model_copy(
            update={
                "interest_level": RadarInterestLevel.HIGH,
                "characteristics": (MarketCharacteristic.VOLUME_ANOMALY,),
            }
        )
        await radar._public_attention((base,), now=NOW)
        escalated = base.model_copy(
            update={
                "interest_level": RadarInterestLevel.VERY_HIGH,
                "characteristics": (
                    MarketCharacteristic.VOLUME_ANOMALY,
                    MarketCharacteristic.BREAKOUT_WATCH,
                ),
            }
        )
        _results, decisions, count = await radar._public_attention(
            (escalated,), now=NOW + timedelta(minutes=20)
        )
        assert count == 1
        assert decisions["AAA"].event_refresh is True
        assert decisions["AAA"].trigger in {
            PublicResearchTrigger.INTEREST_ESCALATION,
            PublicResearchTrigger.BREAKOUT_EVENT,
        }

    asyncio.run(scenario())


def test_public_research_budget_default_is_two_and_runtime_cap_is_three() -> None:
    assert MarketAttentionPolicy().max_web_searches_per_refresh == 2
    # Legacy/internal policies above 3 remain loadable, but runtime never spends above 3.
    assert MarketAttentionPolicy(max_web_searches_per_refresh=8).max_web_searches_per_refresh == 8


def test_public_research_never_bursts_above_refresh_budget() -> None:
    async def scenario() -> None:
        markets = tuple(
            ExecutableMarket(symbol=f"{asset}/USD", market_type=MarketType.SPOT)
            for asset in ("AAA", "BBB", "CCC", "DDD")
        )
        researcher = _Researcher()
        radar = MarketAttentionRadar(
            candle_service=_Candles(),  # type: ignore[arg-type]
            catalogue=_Catalogue(markets),
            researcher=researcher,
            policy=MarketAttentionPolicy(
                scan_limit=10,
                candidate_limit=4,
                max_web_searches_per_refresh=2,
                candle_limit=404,
            ),
        )
        template = _analyze(current="3", previous="1.2", current_step=Decimal("0.001"))
        activities = tuple(
            template.model_copy(update={"market": market, "interest_level": RadarInterestLevel.HIGH})
            for market in markets
        )
        _results, decisions, count = await radar._public_attention(activities, now=NOW)
        assert count == 2
        assert len(researcher.calls) == 2
        assert sum(item.skip_reason is PublicResearchSkipReason.BUDGET_EXHAUSTED for item in decisions.values()) == 2

    asyncio.run(scenario())



def test_legacy_policy_above_three_is_clamped_at_runtime() -> None:
    async def scenario() -> None:
        markets = tuple(
            ExecutableMarket(symbol=f"{asset}/USD", market_type=MarketType.SPOT)
            for asset in ("AAA", "BBB", "CCC", "DDD")
        )
        researcher = _Researcher()
        radar = MarketAttentionRadar(
            candle_service=_Candles(),  # type: ignore[arg-type]
            catalogue=_Catalogue(markets),
            researcher=researcher,
            policy=MarketAttentionPolicy(
                scan_limit=10,
                candidate_limit=10,
                max_web_searches_per_refresh=8,
                candle_limit=404,
            ),
        )
        template = _analyze(current="3", previous="1.2", current_step=Decimal("0.001"))
        activities = tuple(
            template.model_copy(update={"market": market, "interest_level": RadarInterestLevel.HIGH})
            for market in markets
        )
        _results, _decisions, count = await radar._public_attention(activities, now=NOW)
        assert count == 3
        assert len(researcher.calls) == 3

    asyncio.run(scenario())

def test_deterministic_ranking_is_stable() -> None:
    a = _snapshot(
        symbol="AAA/USD",
        horizons=(_horizon(CandleTimeframe.M15, volume_ratio="2"),),
        activity_state=MarketActivityState.ACCELERATING,
    )
    b = _snapshot(
        symbol="BBB/USD",
        horizons=(_horizon(CandleTimeframe.M15, volume_ratio="1.6"),),
        activity_state=MarketActivityState.ELEVATED,
    )
    first = sorted((a, b), key=_deterministic_radar_sort_key, reverse=True)
    second = sorted((b, a), key=_deterministic_radar_sort_key, reverse=True)
    assert [item.market.symbol for item in first] == [item.market.symbol for item in second]


def test_insufficient_history_fails_soft_without_inventing_interest() -> None:
    analyzer = MarketActivityAnalyzer(baseline_periods=6, stale_after=timedelta(minutes=15))
    market = ExecutableMarket(symbol="AAA/USD", market_type=MarketType.SPOT)
    snapshot = analyzer.analyze(
        market=market,
        candles=_history()[-10:],
        observed_at=NOW,
    )
    assert snapshot.status is RadarStatus.PARTIAL
    assert snapshot.interest_level is RadarInterestLevel.LOW
    assert snapshot.characteristics == ()


def test_future_candles_are_excluded_from_analysis() -> None:
    analyzer = MarketActivityAnalyzer(baseline_periods=6, stale_after=timedelta(minutes=15))
    market = ExecutableMarket(symbol="AAA/USD", market_type=MarketType.SPOT)
    rows = list(_history())
    future_open = NOW + timedelta(minutes=5)
    rows.append(
        Candle(
            symbol="AAA/USD",
            market_type=MarketType.SPOT,
            timeframe=CandleTimeframe.M5,
            open_time=future_open,
            close_time=future_open + timedelta(minutes=5),
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=Decimal("999999"),
            is_final=True,
            updated_at=future_open + timedelta(minutes=5),
        )
    )
    snapshot = analyzer.analyze(market=market, candles=tuple(rows), observed_at=NOW)
    assert snapshot.observed_at == NOW
    assert all(item.current_volume != Decimal("999999") for item in snapshot.horizons if item.current_volume is not None)


def test_overview_remains_informative_only() -> None:
    overview = MarketAttentionOverview(observed_at=NOW, status=RadarStatus.AVAILABLE)
    assert overview.informative_only is True
    try:
        MarketAttentionOverview(observed_at=NOW, status=RadarStatus.AVAILABLE, informative_only=False)
    except ValueError:
        pass
    else:
        raise AssertionError("Market Attention must reject informative_only=False")


def test_market_attention_module_remains_isolated_from_trading_execution() -> None:
    source = inspect.getsource(attention_module)
    assert "ai_spot_trader.agent" not in source
    assert "ai_spot_trader.risk" not in source
    assert "ai_spot_trader.broker" not in source
    assert "ai_spot_trader.market.discovery" not in source


def test_candidate_diversification_preserves_micro_regime_before_final_ranking() -> None:
    """Batch 38 must not let liquidity-aware ranking erase the v1 regime diversity invariant."""

    def structured(
        symbol: str,
        *,
        ratio: str,
        state: MarketActivityState,
        liquidity: LiquidityRegime,
    ) -> MarketActivitySnapshot:
        raw = MarketActivitySnapshot(
            market=ExecutableMarket(symbol=symbol, market_type=MarketType.SPOT),
            observed_at=NOW,
            status=RadarStatus.AVAILABLE,
            activity_state=state,
            liquidity_regime=liquidity,
            horizons=(
                _horizon(CandleTimeframe.M15, volume_ratio=ratio),
            ),
        )
        return _with_market_structure(raw)

    async def scenario() -> None:
        radar = MarketAttentionRadar(
            candle_service=_Candles(),  # type: ignore[arg-type]
            catalogue=_Catalogue(()),
            researcher=None,
            policy=MarketAttentionPolicy(
                scan_limit=10,
                candidate_limit=2,
                max_web_searches_per_refresh=0,
                candle_limit=404,
            ),
        )
        activities = (
            structured(
                "MICRO/USD",
                ratio="8",
                state=MarketActivityState.VERY_HIGH,
                liquidity=LiquidityRegime.MICRO,
            ),
            structured(
                "MID/USD",
                ratio="3",
                state=MarketActivityState.VERY_HIGH,
                liquidity=LiquidityRegime.MEDIUM,
            ),
            structured(
                "BIG/USD",
                ratio="2",
                state=MarketActivityState.ELEVATED,
                liquidity=LiquidityRegime.VERY_HIGH,
            ),
        )

        candidates = radar._candidates_from(activities)
        symbols = {item.market.symbol for item in candidates}
        regimes = {item.liquidity_regime for item in candidates}

        assert len(candidates) == 2
        assert "MICRO/USD" in symbols
        assert len(regimes) == 2
        await radar.aclose()

    asyncio.run(scenario())
