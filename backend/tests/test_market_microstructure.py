from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.microstructure import (
    MarketMicrostructureAnalyzer,
    MicrostructureCharacteristic,
    MicrostructureDataQuality,
    MicrostructurePolicy,
    MicrostructureStatus,
    OrderBookLevel,
    OrderBookSnapshot,
    RecentTrade,
    RecentTradesSnapshot,
    TradeSide,
)

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
MARKET = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT)


def _book(
    *,
    bids: tuple[tuple[str, str], ...] = (("100", "1"), ("99", "2")),
    asks: tuple[tuple[str, str], ...] = (("101", "1"), ("102", "2")),
    observed_at: datetime = NOW,
) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        observed_at=observed_at,
        bids=tuple(OrderBookLevel(price=Decimal(p), volume_base=Decimal(v)) for p, v in bids),
        asks=tuple(OrderBookLevel(price=Decimal(p), volume_base=Decimal(v)) for p, v in asks),
    )


def _trades(rows: tuple[tuple[int, str, str, TradeSide | None], ...]) -> RecentTradesSnapshot:
    return RecentTradesSnapshot(
        observed_at=NOW,
        trades=tuple(
            RecentTrade(
                price=Decimal(price),
                volume_base=Decimal(volume),
                occurred_at=NOW - timedelta(seconds=age),
                side=side,
                trade_id=index,
            )
            for index, (age, price, volume, side) in enumerate(rows)
        ),
    )


def test_best_bid_ask_mid_and_spread_are_correct() -> None:
    snapshot = MarketMicrostructureAnalyzer().analyze(
        market=MARKET,
        observed_at=NOW,
        book=_book(),
        trades=_trades(()),
    )
    assert snapshot.best_bid == Decimal("100")
    assert snapshot.best_ask == Decimal("101")
    assert snapshot.mid_price == Decimal("100.5")
    assert snapshot.spread_absolute == Decimal("1")
    assert snapshot.spread_bps == Decimal("1") * Decimal("10000") / Decimal("100.5")


def test_depth_and_book_imbalance_use_quote_notional() -> None:
    snapshot = MarketMicrostructureAnalyzer().analyze(
        market=MARKET,
        observed_at=NOW,
        book=_book(bids=(("100", "2"),), asks=(("101", "1"),)),
        trades=_trades(()),
    )
    assert snapshot.bid_depth_base == Decimal("2")
    assert snapshot.ask_depth_base == Decimal("1")
    assert snapshot.bid_depth_quote == Decimal("200")
    assert snapshot.ask_depth_quote == Decimal("101")
    assert snapshot.total_depth_quote == Decimal("301")
    assert snapshot.book_imbalance == Decimal("99") / Decimal("301")


def test_unordered_and_duplicate_levels_are_normalized() -> None:
    snapshot = MarketMicrostructureAnalyzer().analyze(
        market=MARKET,
        observed_at=NOW,
        book=_book(
            bids=(("99", "1"), ("100", "1"), ("100", "2")),
            asks=(("102", "1"), ("101", "2"), ("101", "1")),
        ),
        trades=_trades(()),
    )
    assert snapshot.best_bid == Decimal("100")
    assert snapshot.best_ask == Decimal("101")
    assert snapshot.bid_depth_base == Decimal("4")
    assert snapshot.ask_depth_base == Decimal("4")


def test_empty_book_is_fail_soft_and_keeps_trade_metrics() -> None:
    trades = _trades(((10, "100", "1", TradeSide.BUY),))
    snapshot = MarketMicrostructureAnalyzer().analyze(
        market=MARKET,
        observed_at=NOW,
        book=OrderBookSnapshot(observed_at=NOW, bids=(), asks=()),
        trades=trades,
    )
    assert snapshot.best_bid is None
    assert snapshot.trade_count == 1
    assert snapshot.status is MicrostructureStatus.PARTIAL
    assert snapshot.error_type == "InvalidOrEmptyOrderBook"


def test_trade_count_volume_average_and_median_are_correct() -> None:
    snapshot = MarketMicrostructureAnalyzer().analyze(
        market=MARKET,
        observed_at=NOW,
        book=_book(),
        trades=_trades(
            (
                (10, "100", "1", TradeSide.BUY),
                (20, "101", "2", TradeSide.SELL),
                (30, "102", "3", TradeSide.BUY),
            )
        ),
    )
    assert snapshot.trade_count == 3
    assert snapshot.trade_volume_base == Decimal("6")
    assert snapshot.trade_volume_quote == Decimal("608")
    assert snapshot.average_trade_size_base == Decimal("2")
    assert snapshot.median_trade_size_base == Decimal("2")


def test_trade_rate_and_activity_surge_are_detected() -> None:
    rows = tuple((10 + index, "100", "1", TradeSide.BUY) for index in range(6)) + (
        (120, "100", "1", TradeSide.SELL),
        (240, "100", "1", TradeSide.SELL),
    )
    snapshot = MarketMicrostructureAnalyzer().analyze(
        market=MARKET,
        observed_at=NOW,
        book=_book(),
        trades=_trades(rows),
    )
    assert snapshot.trade_rate_per_minute == Decimal("6")
    assert snapshot.baseline_trade_rate_per_minute == Decimal("0.5")
    assert snapshot.trade_activity_ratio == Decimal("12")
    assert MicrostructureCharacteristic.TRADE_ACTIVITY_SURGE in snapshot.characteristics


def test_trade_activity_fade_is_detected() -> None:
    rows = ((10, "100", "1", TradeSide.BUY),) + tuple(
        (90 + index * 20, "100", "1", TradeSide.SELL) for index in range(8)
    )
    snapshot = MarketMicrostructureAnalyzer().analyze(
        market=MARKET,
        observed_at=NOW,
        book=_book(),
        trades=_trades(rows),
    )
    assert snapshot.trade_activity_ratio is not None
    assert snapshot.trade_activity_ratio <= Decimal("0.5")
    assert MicrostructureCharacteristic.TRADE_ACTIVITY_FADE in snapshot.characteristics


def test_unknown_provider_side_never_invents_buy_sell_metrics() -> None:
    snapshot = MarketMicrostructureAnalyzer().analyze(
        market=MARKET,
        observed_at=NOW,
        book=_book(),
        trades=_trades(
            (
                (10, "100", "1", TradeSide.BUY),
                (20, "100", "1", None),
            )
        ),
    )
    assert snapshot.provider_side_coverage == Decimal("0.5")
    assert snapshot.buy_volume_base is None
    assert snapshot.sell_volume_base is None
    assert snapshot.buy_sell_imbalance is None
    assert MicrostructureCharacteristic.BUY_PRESSURE not in snapshot.characteristics
    assert MicrostructureCharacteristic.SELL_PRESSURE not in snapshot.characteristics


def test_complete_provider_side_exposes_descriptive_pressure() -> None:
    snapshot = MarketMicrostructureAnalyzer().analyze(
        market=MARKET,
        observed_at=NOW,
        book=_book(),
        trades=_trades(
            (
                (10, "100", "4", TradeSide.BUY),
                (20, "100", "1", TradeSide.SELL),
            )
        ),
    )
    assert snapshot.provider_side_coverage == Decimal("1")
    assert snapshot.buy_volume_base == Decimal("4")
    assert snapshot.sell_volume_base == Decimal("1")
    assert snapshot.buy_sell_imbalance == Decimal("0.6")
    assert MicrostructureCharacteristic.BUY_PRESSURE in snapshot.characteristics


def test_theoretical_buy_slippage_walks_asks_without_order() -> None:
    analyzer = MarketMicrostructureAnalyzer(
        policy=MicrostructurePolicy(slippage_notionals_quote=(Decimal("150"),))
    )
    snapshot = analyzer.analyze(
        market=MARKET,
        observed_at=NOW,
        book=_book(bids=(("99", "5"),), asks=(("100", "1"), ("101", "1"))),
        trades=_trades(()),
    )
    estimate = snapshot.slippage_for("BUY", Decimal("150"))
    assert estimate is not None
    expected_base = Decimal("1") + Decimal("50") / Decimal("101")
    assert estimate.consumed_volume_base == expected_base
    assert estimate.estimated_vwap == Decimal("150") / expected_base
    assert estimate.slippage_bps is not None and estimate.slippage_bps > 0
    assert estimate.insufficient_depth is False


def test_theoretical_sell_slippage_walks_bids_without_order() -> None:
    analyzer = MarketMicrostructureAnalyzer(
        policy=MicrostructurePolicy(slippage_notionals_quote=(Decimal("150"),))
    )
    snapshot = analyzer.analyze(
        market=MARKET,
        observed_at=NOW,
        book=_book(bids=(("100", "1"), ("99", "1")), asks=(("101", "5"),)),
        trades=_trades(()),
    )
    estimate = snapshot.slippage_for("SELL", Decimal("150"))
    assert estimate is not None
    expected_base = Decimal("1") + Decimal("50") / Decimal("99")
    assert estimate.consumed_volume_base == expected_base
    assert estimate.estimated_vwap == Decimal("150") / expected_base
    assert estimate.slippage_bps is not None and estimate.slippage_bps > 0
    assert estimate.insufficient_depth is False


def test_insufficient_depth_is_explicit_and_has_no_fake_vwap() -> None:
    analyzer = MarketMicrostructureAnalyzer(
        policy=MicrostructurePolicy(slippage_notionals_quote=(Decimal("5000"),))
    )
    snapshot = analyzer.analyze(
        market=MARKET,
        observed_at=NOW,
        book=_book(bids=(("100", "1"),), asks=(("101", "1"),)),
        trades=_trades(()),
    )
    estimate = snapshot.slippage_for("BUY", Decimal("5000"))
    assert estimate is not None
    assert estimate.insufficient_depth is True
    assert estimate.estimated_vwap is None
    assert estimate.slippage_bps is None


def test_depth_bands_are_bounded_around_mid() -> None:
    analyzer = MarketMicrostructureAnalyzer(
        policy=MicrostructurePolicy(depth_bands_bps=(5, 50))
    )
    snapshot = analyzer.analyze(
        market=MARKET,
        observed_at=NOW,
        book=_book(
            bids=(("100", "1"), ("99", "10")),
            asks=(("100.04", "2"), ("101", "10")),
        ),
        trades=_trades(()),
    )
    assert [item.band_bps for item in snapshot.depth_bands] == [5, 50]
    assert snapshot.depth_bands[0].bid_depth_base == Decimal("1")
    assert snapshot.depth_bands[0].ask_depth_base == Decimal("2")


def test_stale_trade_and_book_snapshots_are_detected() -> None:
    old = NOW - timedelta(minutes=20)
    analyzer = MarketMicrostructureAnalyzer(policy=MicrostructurePolicy(stale_after_seconds=420))
    snapshot = analyzer.analyze(
        market=MARKET,
        observed_at=NOW,
        book=_book(observed_at=old),
        trades=RecentTradesSnapshot(observed_at=old, trades=()),
    )
    assert snapshot.status is MicrostructureStatus.STALE
    assert snapshot.data_quality is MicrostructureDataQuality.STALE


def test_one_missing_component_is_partial_not_error() -> None:
    snapshot = MarketMicrostructureAnalyzer().analyze(
        market=MARKET,
        observed_at=NOW,
        book=_book(),
        trades=None,
        errors=("KrakenTimeoutError",),
    )
    assert snapshot.status is MicrostructureStatus.PARTIAL
    assert snapshot.data_quality is MicrostructureDataQuality.PARTIAL
    assert snapshot.best_bid is not None
    assert snapshot.trade_count is None


def test_both_missing_components_with_errors_are_fail_soft_error() -> None:
    snapshot = MarketMicrostructureAnalyzer().analyze(
        market=MARKET,
        observed_at=NOW,
        book=None,
        trades=None,
        errors=("KrakenTimeoutError", "KrakenRateLimitError"),
    )
    assert snapshot.status is MicrostructureStatus.ERROR
    assert snapshot.data_quality is MicrostructureDataQuality.TECHNICAL_ERROR
    assert snapshot.error_type == "KrakenTimeoutError"


def test_non_spot_market_is_explicitly_not_applicable() -> None:
    market = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.PERPETUAL)
    snapshot = MarketMicrostructureAnalyzer().analyze(
        market=market,
        observed_at=NOW,
        book=None,
        trades=None,
    )
    assert snapshot.status is MicrostructureStatus.NOT_APPLICABLE
    assert snapshot.data_quality is MicrostructureDataQuality.NOT_APPLICABLE
    assert snapshot.characteristics == ()
