from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import ai_spot_trader.market.attention as attention_module
from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.attention import (
    ActivityDataQuality,
    ActivityHorizonSnapshot,
    LiquidityRegime,
    MarketActivityAnalyzer,
    MarketActivitySnapshot,
    MarketActivityState,
    MarketAttentionOverview,
    MarketAttentionPolicy,
    MarketAttentionRadar,
    MarketCharacteristic,
    RadarInterestLevel,
    RadarStatus,
    _deterministic_radar_sort_key,
    _with_market_structure,
)
from ai_spot_trader.market.candles import Candle, CandleTimeframe

NOW = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)


def _market(symbol: str = "AAA/USD") -> ExecutableMarket:
    return ExecutableMarket(symbol=symbol, market_type=MarketType.SPOT)


def _horizon(
    timeframe: CandleTimeframe,
    *,
    volume_ratio: str = "1",
    acceleration: str = "0",
    price_return: str = "0",
    previous_return: str = "0",
    range_expansion: str = "1",
    volatility_expansion: str = "1",
    breakout_distance: str = "0",
) -> ActivityHorizonSnapshot:
    return ActivityHorizonSnapshot(
        timeframe=timeframe,
        volume_ratio=Decimal(volume_ratio),
        volume_acceleration=Decimal(acceleration),
        price_return=Decimal(price_return),
        previous_price_return=Decimal(previous_return),
        range_expansion_ratio=Decimal(range_expansion),
        volatility_expansion_ratio=Decimal(volatility_expansion),
        breakout_distance=Decimal(breakout_distance),
        observation_count=1,
        baseline_period_count=6,
        complete=True,
    )


def _snapshot(
    symbol: str = "AAA/USD",
    *,
    horizons: tuple[ActivityHorizonSnapshot, ...] | None = None,
    state: MarketActivityState = MarketActivityState.NORMAL,
    regime: LiquidityRegime = LiquidityRegime.MEDIUM,
    status: RadarStatus = RadarStatus.AVAILABLE,
) -> MarketActivitySnapshot:
    raw = MarketActivitySnapshot(
        market=_market(symbol),
        observed_at=NOW,
        status=status,
        activity_state=state,
        liquidity_regime=regime,
        freshness_seconds=Decimal("0"),
        horizons=horizons
        or tuple(_horizon(tf) for tf in (CandleTimeframe.M5, CandleTimeframe.M15, CandleTimeframe.H1, CandleTimeframe.H4)),
        data_quality=ActivityDataQuality.COMPLETE,
    )
    return _with_market_structure(raw)


def test_normal_market_stays_low_without_external_dependency() -> None:
    snapshot = _snapshot()
    assert snapshot.interest_level is RadarInterestLevel.LOW
    source = inspect.getsource(attention_module)
    assert "web_search" not in source
    assert "openai" not in source.lower()


def test_volume_anomaly_is_descriptive() -> None:
    horizons = (_horizon(CandleTimeframe.M5, volume_ratio="1.8"),) + tuple(
        _horizon(tf) for tf in (CandleTimeframe.M15, CandleTimeframe.H1, CandleTimeframe.H4)
    )
    snapshot = _snapshot(horizons=horizons)
    assert MarketCharacteristic.VOLUME_ANOMALY in snapshot.characteristics


def test_multi_horizon_trend_is_detected() -> None:
    snapshot = _snapshot(
        horizons=(
            _horizon(CandleTimeframe.M5, price_return="0.004"),
            _horizon(CandleTimeframe.M15, price_return="0.008"),
            _horizon(CandleTimeframe.H1, price_return="0.02"),
            _horizon(CandleTimeframe.H4, price_return="0.03"),
        )
    )
    assert MarketCharacteristic.TRENDING in snapshot.characteristics


def test_volatility_expansion_is_detected() -> None:
    snapshot = _snapshot(
        horizons=(
            _horizon(CandleTimeframe.M5, volatility_expansion="1.8"),
            _horizon(CandleTimeframe.M15),
            _horizon(CandleTimeframe.H1),
            _horizon(CandleTimeframe.H4),
        )
    )
    assert MarketCharacteristic.VOLATILITY_EXPANSION in snapshot.characteristics


def test_breakout_is_detected_without_buy_sell_semantics() -> None:
    snapshot = _snapshot(
        horizons=(
            _horizon(CandleTimeframe.M5, price_return="0.006", volume_ratio="1.4", breakout_distance="0.004"),
            _horizon(CandleTimeframe.M15),
            _horizon(CandleTimeframe.H1),
            _horizon(CandleTimeframe.H4),
        )
    )
    assert MarketCharacteristic.BREAKOUT_WATCH in snapshot.characteristics
    assert all(token not in str(snapshot.model_dump()) for token in ("BUY", "SELL", "HOLD"))


def test_reversal_is_detected() -> None:
    snapshot = _snapshot(
        horizons=(
            _horizon(CandleTimeframe.M5, price_return="0.004", previous_return="-0.004", volume_ratio="1.5"),
            _horizon(CandleTimeframe.M15),
            _horizon(CandleTimeframe.H1),
            _horizon(CandleTimeframe.H4),
        )
    )
    assert MarketCharacteristic.REVERSAL_WATCH in snapshot.characteristics


def test_consolidation_is_detected() -> None:
    snapshot = _snapshot(
        horizons=(
            _horizon(CandleTimeframe.M5, range_expansion="0.6"),
            _horizon(CandleTimeframe.M15, range_expansion="0.65"),
            _horizon(CandleTimeframe.H1),
            _horizon(CandleTimeframe.H4),
        )
    )
    assert MarketCharacteristic.CONSOLIDATING in snapshot.characteristics


def test_price_volume_divergence_is_detected() -> None:
    snapshot = _snapshot(
        horizons=(
            _horizon(CandleTimeframe.M5, price_return="0.004", volume_ratio="0.5"),
            _horizon(CandleTimeframe.M15),
            _horizon(CandleTimeframe.H1),
            _horizon(CandleTimeframe.H4),
        )
    )
    assert MarketCharacteristic.PRICE_VOLUME_DIVERGENCE in snapshot.characteristics


def test_deterministic_ranking_is_stable() -> None:
    snapshots = (
        _snapshot("AAA/USD", state=MarketActivityState.ELEVATED),
        _snapshot("BBB/USD", state=MarketActivityState.ACCELERATING),
        _snapshot("CCC/USD", state=MarketActivityState.VERY_HIGH),
    )
    first = sorted(snapshots, key=_deterministic_radar_sort_key, reverse=True)
    second = sorted(reversed(snapshots), key=_deterministic_radar_sort_key, reverse=True)
    assert [item.market.symbol for item in first] == [item.market.symbol for item in second]


def test_future_and_non_final_candles_are_excluded() -> None:
    analyzer = MarketActivityAnalyzer(baseline_periods=6, stale_after=timedelta(minutes=15))
    market = _market()
    future = Candle(
        symbol=market.symbol,
        market_type=market.market_type,
        timeframe=CandleTimeframe.M5,
        open_time=NOW,
        close_time=NOW + timedelta(minutes=5),
        open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"),
        volume=Decimal("999"), is_final=True, updated_at=NOW + timedelta(minutes=5),
    )
    non_final = Candle(
        symbol=market.symbol,
        market_type=market.market_type,
        timeframe=CandleTimeframe.M5,
        open_time=NOW - timedelta(minutes=5),
        close_time=NOW,
        open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"),
        volume=Decimal("999"), is_final=False, updated_at=NOW,
    )
    snapshot = analyzer.analyze(market=market, candles=(future, non_final), observed_at=NOW)
    assert snapshot.status is RadarStatus.PARTIAL
    assert snapshot.interest_level is RadarInterestLevel.LOW


def test_overview_remains_informative_only_and_v2() -> None:
    overview = MarketAttentionOverview(observed_at=NOW, status=RadarStatus.AVAILABLE)
    assert overview.informative_only is True
    assert overview.protocol_version == "market-attention-radar-v2"


def test_market_attention_module_remains_isolated_from_trading_execution() -> None:
    source = inspect.getsource(attention_module)
    forbidden = ("agent.", "risk", "broker", "market.discovery", "OpenAI", "web_search")
    for token in forbidden:
        assert token.lower() not in source.lower()


def test_policy_contains_no_external_research_budget() -> None:
    fields = MarketAttentionPolicy.model_fields
    assert all("web" not in name and "public_attention" not in name for name in fields)
