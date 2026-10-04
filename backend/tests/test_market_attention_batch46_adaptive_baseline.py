from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.attention import (
    ActivityAnomalyMethod,
    ActivityDataQuality,
    ActivityHorizonSnapshot,
    MarketActivityAnalyzer,
    MarketActivitySnapshot,
    MarketActivityState,
    MarketAttentionPolicy,
    MarketAttentionRadar,
    MarketCharacteristic,
    RadarStatus,
    _adaptive_activity_state,
    _activity_sort_key,
    _market_characteristics,
    _median_absolute_deviation,
    _robust_anomaly,
)
from ai_spot_trader.market.candles import Candle, CandleTimeframe

NOW = datetime(2026, 10, 4, 0, 0, tzinfo=UTC)


def _market(market_type: MarketType = MarketType.SPOT) -> ExecutableMarket:
    return ExecutableMarket(symbol="AAA/USD", market_type=market_type)


def _candles(
    volumes: list[Decimal],
    *,
    market_type: MarketType = MarketType.SPOT,
    start_price: Decimal = Decimal("100"),
    price_step: Decimal = Decimal("0"),
    final: bool = True,
    end_at: datetime = NOW,
) -> tuple[Candle, ...]:
    rows: list[Candle] = []
    count = len(volumes)
    for index, volume in enumerate(volumes):
        open_time = end_at - timedelta(minutes=5 * (count - index))
        close_time = open_time + timedelta(minutes=5)
        open_price = start_price + price_step * index
        close_price = open_price + price_step
        high = max(open_price, close_price) + Decimal("0.1")
        low = min(open_price, close_price) - Decimal("0.1")
        rows.append(
            Candle(
                symbol="AAA/USD",
                market_type=market_type,
                timeframe=CandleTimeframe.M5,
                open_time=open_time,
                close_time=close_time,
                open=open_price,
                high=high,
                low=low,
                close=close_price,
                volume=volume,
                is_final=final,
                updated_at=close_time,
            )
        )
    return tuple(rows)


def _horizon(
    volumes: list[int | str],
    *,
    market_type: MarketType = MarketType.SPOT,
    price_step: Decimal = Decimal("0"),
):
    analyzer = MarketActivityAnalyzer(baseline_periods=12, stale_after=timedelta(minutes=15))
    candles = _candles(
        [Decimal(str(value)) for value in volumes],
        market_type=market_type,
        price_step=price_step,
    )
    return analyzer._horizon(  # noqa: SLF001 - targeted canonical analyzer regression
        candles,
        CandleTimeframe.M5,
        market=_market(market_type),
        missing_intervals_mean_no_trades=(market_type is MarketType.SPOT),
    )


def _adaptive_horizon(
    *,
    score: str,
    previous_score: str = "0",
    ratio: str = "1",
) -> ActivityHorizonSnapshot:
    current = Decimal(score)
    previous = Decimal(previous_score)
    return ActivityHorizonSnapshot(
        timeframe=CandleTimeframe.M5,
        volume_ratio=Decimal(ratio),
        volume_anomaly_score=current,
        previous_volume_anomaly_score=previous,
        volume_anomaly_acceleration=current - previous,
        volume_anomaly_method=ActivityAnomalyMethod.ROBUST_MAD,
        observation_count=1,
        baseline_period_count=12,
        complete=True,
    )


def test_batch46_policy_default_keeps_h4_inside_default_fetch_limit() -> None:
    policy = MarketAttentionPolicy()
    assert policy.baseline_periods == 12
    assert 48 * (policy.baseline_periods + 2) == 672
    assert 672 <= policy.candle_limit == 720


def test_default_target_uses_twelve_h4_periods_when_history_is_available() -> None:
    analyzer = MarketActivityAnalyzer(stale_after=timedelta(minutes=15))
    snapshot = analyzer.analyze(
        market=_market(),
        candles=_candles([Decimal("100")] * 720),
        observed_at=NOW,
        missing_intervals_mean_no_trades=True,
    )
    h4 = snapshot.horizon(CandleTimeframe.H4)
    assert h4 is not None
    assert h4.complete is True
    assert h4.baseline_period_count == 12
    assert snapshot.status is RadarStatus.AVAILABLE


def test_default_target_degrades_to_six_h4_periods_for_historical_420_candle_configs() -> None:
    analyzer = MarketActivityAnalyzer(stale_after=timedelta(minutes=15))
    volumes = [Decimal("1")] * 420
    volumes[-48:] = [Decimal("10")] * 48
    snapshot = analyzer.analyze(
        market=_market(),
        candles=_candles(volumes),
        observed_at=NOW,
        missing_intervals_mean_no_trades=True,
    )
    h4 = snapshot.horizon(CandleTimeframe.H4)
    assert h4 is not None
    assert h4.complete is True
    assert h4.baseline_period_count == 6
    assert h4.volume_ratio == Decimal("10")
    assert snapshot.status is RadarStatus.AVAILABLE
    assert snapshot.activity_state is MarketActivityState.VERY_HIGH


def test_history_below_six_h4_periods_remains_explicitly_insufficient() -> None:
    analyzer = MarketActivityAnalyzer(stale_after=timedelta(minutes=15))
    snapshot = analyzer.analyze(
        market=_market(),
        candles=_candles([Decimal("100")] * 335),
        observed_at=NOW,
        missing_intervals_mean_no_trades=True,
    )
    h4 = snapshot.horizon(CandleTimeframe.H4)
    assert h4 is not None
    assert h4.complete is False
    assert h4.baseline_period_count == 4
    assert h4.data_quality is ActivityDataQuality.INSUFFICIENT_HISTORY


def test_median_absolute_deviation_and_normalized_score_are_exact_and_deterministic() -> None:
    values = tuple(Decimal(value) for value in (8, 9, 10, 10, 11, 12))
    mad = _median_absolute_deviation(values, center=Decimal("10"))
    assert mad == Decimal("1")
    first = _robust_anomaly(
        Decimal("13"), baseline=Decimal("10"), mad=mad, fallback_ratio=Decimal("1.3")
    )
    second = _robust_anomaly(
        Decimal("13"), baseline=Decimal("10"), mad=mad, fallback_ratio=Decimal("1.3")
    )
    assert first == second
    score, method = first
    assert method is ActivityAnomalyMethod.ROBUST_MAD
    assert score == Decimal("3") / Decimal("1.4826")


def test_current_and_previous_windows_do_not_contaminate_historical_baseline() -> None:
    baseline = [99, 100, 101, 100, 98, 102, 99, 101, 100, 100, 99, 101]
    horizon = _horizon([*baseline, 5000, 130])
    assert horizon.baseline_period_count == 12
    assert horizon.baseline_volume == Decimal("100")
    assert horizon.previous_comparable_volume == Decimal("5000")
    assert horizon.current_volume == Decimal("130")


def test_stable_market_detects_moderate_ratio_as_strong_robust_anomaly() -> None:
    baseline = [99, 100, 101, 100, 98, 102, 99, 101, 100, 100, 99, 101]
    horizon = _horizon([*baseline, 100, 130])
    assert horizon.volume_ratio == Decimal("1.3")
    assert horizon.volume_anomaly_method is ActivityAnomalyMethod.ROBUST_MAD
    assert horizon.volume_anomaly_score is not None
    assert horizon.volume_anomaly_score >= Decimal("5")
    assert _adaptive_activity_state((horizon,)) is MarketActivityState.VERY_HIGH


def test_erratic_market_does_not_promote_legacy_ratio_when_mad_is_available() -> None:
    baseline = [20, 160, 30, 150, 40, 140, 50, 130, 60, 120, 70, 110]
    horizon = _horizon([*baseline, 90, 140])
    assert horizon.volume_ratio is not None and horizon.volume_ratio >= Decimal("1.40")
    assert horizon.volume_anomaly_method is ActivityAnomalyMethod.ROBUST_MAD
    assert horizon.volume_anomaly_score is not None
    assert horizon.volume_anomaly_score < Decimal("2")
    assert _adaptive_activity_state((horizon,)) is MarketActivityState.NORMAL


def test_single_historical_outlier_does_not_destroy_robust_center_or_dispersion() -> None:
    baseline = [99, 100, 101, 100, 99, 101, 1000, 100, 99, 101, 100, 100]
    horizon = _horizon([*baseline, 100, 110])
    assert horizon.baseline_volume == Decimal("100")
    assert horizon.baseline_volume_mad == Decimal("1")
    assert horizon.volume_anomaly_score is not None
    assert horizon.volume_anomaly_score > Decimal("5")


def test_zero_mad_never_fabricates_infinite_score_and_exposes_ratio_fallback() -> None:
    horizon = _horizon([*[100] * 12, 100, 130])
    assert horizon.baseline_volume_mad == Decimal("0")
    assert horizon.volume_anomaly_score is None
    assert horizon.volume_anomaly_method is ActivityAnomalyMethod.LEGACY_RATIO_FALLBACK
    assert _adaptive_activity_state((horizon,)) is MarketActivityState.NORMAL


def test_zero_baseline_and_zero_mad_are_unavailable_not_infinite() -> None:
    horizon = _horizon([*[0] * 12, 0, 10])
    assert horizon.volume_ratio is None
    assert horizon.baseline_volume_mad == Decimal("0")
    assert horizon.volume_anomaly_score is None
    assert horizon.volume_anomaly_method is ActivityAnomalyMethod.UNAVAILABLE


def test_adaptive_activity_state_covers_elevated_accelerating_and_very_high() -> None:
    assert _adaptive_activity_state((_adaptive_horizon(score="2.1"),)) is MarketActivityState.ELEVATED
    assert _adaptive_activity_state(
        (_adaptive_horizon(score="4.0", previous_score="2.5"),)
    ) is MarketActivityState.ACCELERATING
    assert _adaptive_activity_state(
        (_adaptive_horizon(score="5.1", previous_score="4.8"),)
    ) is MarketActivityState.VERY_HIGH


def test_relative_activity_score_is_directionally_symmetric() -> None:
    baseline = [99, 100, 101, 100, 98, 102, 99, 101, 100, 100, 99, 101]
    up = _horizon([*baseline, 100, 110], price_step=Decimal("0.1"))
    down = _horizon([*baseline, 100, 110], price_step=Decimal("-0.1"))
    assert up.volume_anomaly_score == down.volume_anomaly_score


def test_spot_and_perpetual_share_same_relative_volume_statistics_without_perp_notionalization() -> None:
    baseline = [99, 100, 101, 100, 98, 102, 99, 101, 100, 100, 99, 101]
    spot = _horizon([*baseline, 100, 110], market_type=MarketType.SPOT)
    perp = _horizon([*baseline, 100, 110], market_type=MarketType.PERPETUAL)
    assert spot.volume_anomaly_score == perp.volume_anomaly_score
    assert spot.current_notional_usd is not None
    assert perp.current_notional_usd is None


def test_activity_sort_is_deterministic_and_prefers_robust_intensity() -> None:
    market = _market()
    low = MarketActivitySnapshot(
        market=market,
        observed_at=NOW,
        status=RadarStatus.AVAILABLE,
        activity_state=MarketActivityState.ELEVATED,
        horizons=(_adaptive_horizon(score="2.1"),),
    )
    high = low.model_copy(update={"horizons": (_adaptive_horizon(score="4.2"),)})
    assert _activity_sort_key(high) > _activity_sort_key(low)
    assert _activity_sort_key(high) == _activity_sort_key(high)

def test_analyze_excludes_future_and_non_final_candles_from_adaptive_baseline() -> None:
    analyzer = MarketActivityAnalyzer(baseline_periods=12, stale_after=timedelta(minutes=15))
    market = _market()
    history = list(_candles([Decimal("100")] * 672, end_at=NOW))
    last_close = history[-1].close_time
    non_final = history[-1].model_copy(
        update={
            "open_time": last_close,
            "close_time": last_close + timedelta(minutes=5),
            "volume": Decimal("9999"),
            "is_final": False,
            "updated_at": last_close + timedelta(minutes=5),
        }
    )
    future = non_final.model_copy(
        update={
            "open_time": NOW + timedelta(minutes=5),
            "close_time": NOW + timedelta(minutes=10),
            "volume": Decimal("9999"),
            "is_final": True,
            "updated_at": NOW + timedelta(minutes=10),
        }
    )
    snapshot = analyzer.analyze(
        market=market,
        candles=tuple([*history, non_final, future]),
        observed_at=NOW,
        missing_intervals_mean_no_trades=True,
    )
    h5 = snapshot.horizon(CandleTimeframe.M5)
    assert h5 is not None
    assert h5.current_volume == Decimal("100")
    assert h5.volume_anomaly_method is ActivityAnomalyMethod.LEGACY_RATIO_FALLBACK


def test_insufficient_history_does_not_invent_adaptive_statistics() -> None:
    analyzer = MarketActivityAnalyzer(baseline_periods=12, stale_after=timedelta(minutes=15))
    snapshot = analyzer.analyze(
        market=_market(),
        candles=_candles([Decimal("100")] * 20),
        observed_at=NOW,
        missing_intervals_mean_no_trades=True,
    )
    h4 = snapshot.horizon(CandleTimeframe.H4)
    assert h4 is not None
    assert h4.complete is False
    assert h4.data_quality is ActivityDataQuality.INSUFFICIENT_HISTORY
    assert h4.volume_anomaly_score is None
    assert h4.volume_anomaly_method is ActivityAnomalyMethod.UNAVAILABLE


def test_missing_interval_remains_no_trade_gap_for_spot_and_discontinuous_for_perp() -> None:
    volumes = [Decimal("100")] * 14
    spot_candles = list(_candles(volumes, market_type=MarketType.SPOT))
    perp_candles = list(_candles(volumes, market_type=MarketType.PERPETUAL))
    del spot_candles[5]
    del perp_candles[5]
    analyzer = MarketActivityAnalyzer(baseline_periods=12, stale_after=timedelta(minutes=15))
    spot = analyzer._horizon(  # noqa: SLF001
        tuple(spot_candles),
        CandleTimeframe.M5,
        market=_market(MarketType.SPOT),
        missing_intervals_mean_no_trades=True,
    )
    perp = analyzer._horizon(  # noqa: SLF001
        tuple(perp_candles),
        CandleTimeframe.M5,
        market=_market(MarketType.PERPETUAL),
        missing_intervals_mean_no_trades=False,
    )
    assert spot.data_quality is ActivityDataQuality.NO_TRADE_GAPS
    assert spot.no_trade_interval_count == 1
    assert perp.data_quality is ActivityDataQuality.DISCONTINUOUS_HISTORY
    assert perp.complete is False


def test_volume_characteristic_uses_robust_score_before_legacy_ratio() -> None:
    horizon = _adaptive_horizon(score="2.2", ratio="1.30")
    snapshot = MarketActivitySnapshot(
        market=_market(),
        observed_at=NOW,
        status=RadarStatus.AVAILABLE,
        activity_state=MarketActivityState.ELEVATED,
        horizons=(horizon,),
    )
    characteristics = _market_characteristics(snapshot)
    assert MarketCharacteristic.VOLUME_ANOMALY in characteristics


class _Catalogue:
    async def list_markets(self):
        return ()

    async def aclose(self):
        return None


class _Candles:
    async def history(self, key, *, limit: int = 1000):
        return ()


def test_candidate_limit_remains_hard_bounded_with_adaptive_sorting() -> None:
    radar = MarketAttentionRadar(
        candle_service=_Candles(),  # type: ignore[arg-type]
        catalogue=_Catalogue(),  # type: ignore[arg-type]
        policy=MarketAttentionPolicy(candidate_limit=2),
    )
    snapshots = tuple(
        MarketActivitySnapshot(
            market=ExecutableMarket(symbol=f"A{index}/USD", market_type=MarketType.SPOT),
            observed_at=NOW,
            status=RadarStatus.AVAILABLE,
            activity_state=MarketActivityState.ELEVATED,
            horizons=(_adaptive_horizon(score=str(2 + index / 10)),),
        )
        for index in range(5)
    )
    selected = radar._candidates_from(snapshots)  # noqa: SLF001
    assert len(selected) == 2
    assert _activity_sort_key(selected[0]) >= _activity_sort_key(selected[1])



def test_volatility_expansion_uses_adaptive_range_or_volatility_score() -> None:
    horizon = ActivityHorizonSnapshot(
        timeframe=CandleTimeframe.M5,
        volume_ratio=Decimal("1"),
        volume_anomaly_score=Decimal("0"),
        volume_anomaly_method=ActivityAnomalyMethod.ROBUST_MAD,
        range_expansion_ratio=Decimal("1.10"),
        range_anomaly_score=Decimal("2.2"),
        range_anomaly_method=ActivityAnomalyMethod.ROBUST_MAD,
        volatility_expansion_ratio=Decimal("1.10"),
        volatility_anomaly_score=Decimal("0.4"),
        volatility_anomaly_method=ActivityAnomalyMethod.ROBUST_MAD,
        observation_count=1,
        baseline_period_count=12,
        complete=True,
    )
    snapshot = MarketActivitySnapshot(
        market=_market(), observed_at=NOW, status=RadarStatus.AVAILABLE,
        activity_state=MarketActivityState.NORMAL, horizons=(horizon,),
    )
    assert MarketCharacteristic.VOLATILITY_EXPANSION in _market_characteristics(snapshot)


def test_consolidating_uses_negative_adaptive_range_scores_across_horizons() -> None:
    def compressed(timeframe: CandleTimeframe) -> ActivityHorizonSnapshot:
        return ActivityHorizonSnapshot(
            timeframe=timeframe,
            volume_ratio=Decimal("1"),
            volume_anomaly_score=Decimal("0"),
            volume_anomaly_method=ActivityAnomalyMethod.ROBUST_MAD,
            range_expansion_ratio=Decimal("0.95"),
            range_anomaly_score=Decimal("-2.2"),
            range_anomaly_method=ActivityAnomalyMethod.ROBUST_MAD,
            observation_count=1,
            baseline_period_count=12,
            complete=True,
        )

    snapshot = MarketActivitySnapshot(
        market=_market(), observed_at=NOW, status=RadarStatus.AVAILABLE,
        activity_state=MarketActivityState.NORMAL,
        horizons=(compressed(CandleTimeframe.M5), compressed(CandleTimeframe.M15)),
    )
    assert MarketCharacteristic.CONSOLIDATING in _market_characteristics(snapshot)


def test_breakout_and_reversal_confirmations_use_adaptive_activity_without_changing_price_rules() -> None:
    breakout = ActivityHorizonSnapshot(
        timeframe=CandleTimeframe.M5,
        volume_ratio=Decimal("1.05"),
        volume_anomaly_score=Decimal("1.6"),
        volume_anomaly_method=ActivityAnomalyMethod.ROBUST_MAD,
        price_return=Decimal("0.004"),
        breakout_distance=Decimal("0.003"),
        observation_count=1,
        baseline_period_count=12,
        complete=True,
    )
    reversal = ActivityHorizonSnapshot(
        timeframe=CandleTimeframe.M5,
        volume_ratio=Decimal("1.05"),
        volume_anomaly_score=Decimal("1.6"),
        volume_anomaly_method=ActivityAnomalyMethod.ROBUST_MAD,
        price_return=Decimal("-0.004"),
        previous_price_return=Decimal("0.004"),
        observation_count=1,
        baseline_period_count=12,
        complete=True,
    )
    breakout_snapshot = MarketActivitySnapshot(
        market=_market(), observed_at=NOW, status=RadarStatus.AVAILABLE,
        activity_state=MarketActivityState.NORMAL, horizons=(breakout,),
    )
    reversal_snapshot = breakout_snapshot.model_copy(update={"horizons": (reversal,)})
    assert MarketCharacteristic.BREAKOUT_WATCH in _market_characteristics(breakout_snapshot)
    assert MarketCharacteristic.REVERSAL_WATCH in _market_characteristics(reversal_snapshot)


def test_price_volume_divergence_uses_signed_adaptive_volume_anomaly() -> None:
    low_volume_move = ActivityHorizonSnapshot(
        timeframe=CandleTimeframe.M5,
        volume_ratio=Decimal("0.95"),
        volume_anomaly_score=Decimal("-2.5"),
        volume_anomaly_method=ActivityAnomalyMethod.ROBUST_MAD,
        price_return=Decimal("0.004"),
        observation_count=1,
        baseline_period_count=12,
        complete=True,
    )
    high_volume_flat = ActivityHorizonSnapshot(
        timeframe=CandleTimeframe.M5,
        volume_ratio=Decimal("1.10"),
        volume_anomaly_score=Decimal("3.2"),
        volume_anomaly_method=ActivityAnomalyMethod.ROBUST_MAD,
        price_return=Decimal("0.001"),
        observation_count=1,
        baseline_period_count=12,
        complete=True,
    )
    for horizon in (low_volume_move, high_volume_flat):
        snapshot = MarketActivitySnapshot(
            market=_market(), observed_at=NOW, status=RadarStatus.AVAILABLE,
            activity_state=MarketActivityState.NORMAL, horizons=(horizon,),
        )
        assert MarketCharacteristic.PRICE_VOLUME_DIVERGENCE in _market_characteristics(snapshot)
