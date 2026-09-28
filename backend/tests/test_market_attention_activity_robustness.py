from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.integrations.kraken.errors import (
    KrakenConnectionError,
    KrakenPayloadError,
    UnknownKrakenSymbolError,
)
from ai_spot_trader.market.attention import (
    ActivityDataQuality,
    MarketActivityAnalyzer,
    MarketActivityState,
    MarketAttentionPolicy,
    MarketAttentionRadar,
    RadarStatus,
    _activity_state,
)
from ai_spot_trader.market.candles import Candle, CandleKey, CandleTimeframe, CandleValidationError

NOW = datetime(2026, 9, 28, 14, 0, tzinfo=UTC)


def _market(symbol: str, market_type: MarketType = MarketType.SPOT) -> ExecutableMarket:
    return ExecutableMarket(symbol=symbol, market_type=market_type)


def _candles(
    symbol: str,
    *,
    market_type: MarketType = MarketType.SPOT,
    count: int = 404,
    anchor: datetime = NOW,
    current_hour_volume: str = "1",
) -> tuple[Candle, ...]:
    rows: list[Candle] = []
    for index in range(count):
        open_time = anchor - timedelta(minutes=5 * (count - index))
        close_time = open_time + timedelta(minutes=5)
        in_current_hour = index >= count - 12
        volume = Decimal(current_hour_volume if in_current_hour else "1")
        price = Decimal("100") + Decimal(index) / Decimal("1000")
        rows.append(
            Candle(
                symbol=symbol,
                market_type=market_type,
                timeframe=CandleTimeframe.M5,
                open_time=open_time,
                close_time=close_time,
                open=price,
                high=price + Decimal("1"),
                low=price - Decimal("1"),
                close=price + Decimal("0.1"),
                volume=volume,
                is_final=True,
                updated_at=close_time,
            )
        )
    return tuple(rows)


def _analyzer() -> MarketActivityAnalyzer:
    return MarketActivityAnalyzer(baseline_periods=6, stale_after=timedelta(minutes=15))


def test_liquid_continuous_market_remains_available() -> None:
    snapshot = _analyzer().analyze(
        market=_market("AAA/USD"),
        candles=_candles("AAA/USD"),
        observed_at=NOW,
    )

    assert snapshot.status is RadarStatus.AVAILABLE
    assert snapshot.data_quality is ActivityDataQuality.COMPLETE
    assert snapshot.activity_state is MarketActivityState.NORMAL
    assert all(item.complete for item in snapshot.horizons)


def test_spot_known_no_trade_gap_zero_fills_volume_only_without_fake_ohlc() -> None:
    rows = list(_candles("AAA/USD", current_hour_volume="2"))
    del rows[-6]

    snapshot = _analyzer().analyze(
        market=_market("AAA/USD"),
        candles=tuple(rows),
        observed_at=NOW,
        missing_intervals_mean_no_trades=True,
    )
    h1 = snapshot.horizon(CandleTimeframe.H1)

    assert snapshot.status is RadarStatus.AVAILABLE
    assert snapshot.data_quality is ActivityDataQuality.NO_TRADE_GAPS
    assert h1 is not None and h1.complete is True
    assert h1.data_quality is ActivityDataQuality.NO_TRADE_GAPS
    assert h1.current_volume == Decimal("22")
    assert h1.previous_comparable_volume == Decimal("12")
    assert h1.baseline_volume == Decimal("12")
    assert h1.volume_ratio == Decimal("22") / Decimal("12")
    assert h1.observation_count == 11
    assert h1.no_trade_interval_count == 1
    assert h1.unexplained_gap_count == 0
    assert h1.price_return is not None
    assert h1.price_range is not None
    assert h1.realized_volatility is not None


def test_spot_truncated_history_is_not_silently_zero_filled() -> None:
    rows = _candles("AAA/USD", count=200)
    snapshot = _analyzer().analyze(
        market=_market("AAA/USD"),
        candles=rows,
        observed_at=NOW,
        missing_intervals_mean_no_trades=True,
    )

    h4 = snapshot.horizon(CandleTimeframe.H4)
    assert snapshot.status is RadarStatus.PARTIAL
    assert snapshot.data_quality is ActivityDataQuality.INSUFFICIENT_HISTORY
    assert h4 is not None and h4.complete is False
    assert h4.data_quality is ActivityDataQuality.INSUFFICIENT_HISTORY
    assert h4.volume_ratio is None


def test_strict_perpetual_gap_remains_discontinuous_partial() -> None:
    rows = list(_candles("AAA/USD", market_type=MarketType.PERPETUAL))
    del rows[-200]

    snapshot = _analyzer().analyze(
        market=_market("AAA/USD", MarketType.PERPETUAL),
        candles=tuple(rows),
        observed_at=NOW,
    )

    h4 = snapshot.horizon(CandleTimeframe.H4)
    assert snapshot.status is RadarStatus.PARTIAL
    assert snapshot.data_quality is ActivityDataQuality.DISCONTINUOUS_HISTORY
    assert h4 is not None and h4.complete is False
    assert h4.unexplained_gap_count == 1


def test_valid_perpetual_history_is_exploitable() -> None:
    snapshot = _analyzer().analyze(
        market=_market("AAA/USD", MarketType.PERPETUAL),
        candles=_candles("AAA/USD", market_type=MarketType.PERPETUAL),
        observed_at=NOW,
    )

    assert snapshot.status is RadarStatus.AVAILABLE
    assert snapshot.data_quality is ActivityDataQuality.COMPLETE
    assert snapshot.horizon(CandleTimeframe.H4).volume_ratio is not None  # type: ignore[union-attr]


def test_complete_but_old_history_is_stale() -> None:
    snapshot = _analyzer().analyze(
        market=_market("AAA/USD"),
        candles=_candles("AAA/USD"),
        observed_at=NOW + timedelta(hours=2),
    )

    assert snapshot.status is RadarStatus.STALE
    assert snapshot.data_quality is ActivityDataQuality.COMPLETE


class Catalogue:
    def __init__(self, markets: tuple[ExecutableMarket, ...]) -> None:
        self.markets = markets

    async def list_markets(self) -> tuple[ExecutableMarket, ...]:
        return self.markets

    async def aclose(self) -> None:
        return None


class CandleService:
    def __init__(
        self,
        values: dict[tuple[MarketType, str], tuple[Candle, ...] | Exception],
    ) -> None:
        self.values = values

    async def history(self, key: CandleKey, *, limit: int = 1000) -> tuple[Candle, ...]:
        value = self.values[(key.market_type, key.symbol)]
        if isinstance(value, Exception):
            raise value
        return value[-limit:]


class Researcher:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def research(self, *, asset: str, symbols: tuple[str, ...], observed_at: datetime):
        self.calls.append(asset)
        raise AssertionError("diagnostic-only rows must never reach public research")

    async def aclose(self) -> None:
        return None


def _policy() -> MarketAttentionPolicy:
    return MarketAttentionPolicy(
        scan_limit=10,
        candidate_limit=10,
        diagnostic_market_limit=10,
        max_web_searches_per_refresh=10,
        candle_limit=404,
    )


def test_radar_exposes_bounded_error_types_and_market_type_status_counts() -> None:
    async def scenario() -> None:
        spot_ok = _market("AAA/USD")
        spot_partial = _market("BBB/USD")
        perp_connection = _market("CCC/USD", MarketType.PERPETUAL)
        perp_mapping = _market("DDD/USD", MarketType.PERPETUAL)
        perp_payload = _market("EEE/USD", MarketType.PERPETUAL)
        spot_validation = _market("FFF/USD")
        spot_other = _market("GGG/USD")
        markets = (
            spot_ok,
            spot_partial,
            perp_connection,
            perp_mapping,
            perp_payload,
            spot_validation,
            spot_other,
        )
        researcher = Researcher()
        radar = MarketAttentionRadar(
            candle_service=CandleService(
                {
                    (MarketType.SPOT, "AAA/USD"): _candles("AAA/USD"),
                    (MarketType.SPOT, "BBB/USD"): _candles("BBB/USD", count=20),
                    (MarketType.PERPETUAL, "CCC/USD"): KrakenConnectionError("network"),
                    (MarketType.PERPETUAL, "DDD/USD"): UnknownKrakenSymbolError("mapping"),
                    (MarketType.PERPETUAL, "EEE/USD"): KrakenPayloadError("payload"),
                    (MarketType.SPOT, "FFF/USD"): CandleValidationError("validation"),
                    (MarketType.SPOT, "GGG/USD"): RuntimeError("other"),
                }
            ),  # type: ignore[arg-type]
            catalogue=Catalogue(markets),
            researcher=researcher,  # type: ignore[arg-type]
            policy=_policy(),
        )

        overview = await radar.refresh_once(observed_at=NOW)

        assert overview.activity_market_type_status_counts.SPOT.model_dump() == {
            "AVAILABLE": 1,
            "PARTIAL": 1,
            "STALE": 0,
            "ERROR": 2,
        }
        assert overview.activity_market_type_status_counts.PERPETUAL.model_dump() == {
            "AVAILABLE": 0,
            "PARTIAL": 0,
            "STALE": 0,
            "ERROR": 3,
        }
        assert overview.activity_error_counts.model_dump() == {
            "KrakenConnectionError": 1,
            "KrakenPayloadError": 1,
            "UnknownKrakenSymbolError": 1,
            "CandleValidationError": 1,
            "Other": 1,
        }
        assert overview.activity_data_quality_counts.TECHNICAL_ERROR == 5
        assert overview.activity_data_quality_counts.INSUFFICIENT_HISTORY == 1
        assert overview.candidate_market_count == 0
        assert overview.web_search_count == 0
        assert researcher.calls == []
        await radar.aclose()

    asyncio.run(scenario())


def test_activity_thresholds_are_unchanged() -> None:
    assert _activity_state((Decimal("1.39"),), ()) is MarketActivityState.NORMAL
    assert _activity_state((Decimal("1.40"),), ()) is MarketActivityState.ELEVATED
    assert _activity_state((Decimal("1.75"),), (Decimal("0.25"),)) is MarketActivityState.ACCELERATING
    assert _activity_state((Decimal("2.50"),), (Decimal("0.50"),)) is MarketActivityState.VERY_HIGH
