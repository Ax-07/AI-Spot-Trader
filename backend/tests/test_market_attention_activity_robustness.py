from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.integrations.kraken.errors import KrakenPayloadError, KrakenPayloadStage
from ai_spot_trader.market.attention import (
    ActivityDataQuality,
    MarketActivityAnalyzer,
    MarketActivityState,
    MarketAttentionRadar,
    RadarStatus,
    _activity_state,
)
from ai_spot_trader.market.candles import Candle, CandleTimeframe

NOW = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)


def _candles(symbol: str, *, count: int = 404, anchor: datetime = NOW, final: bool = True) -> tuple[Candle, ...]:
    rows = []
    for index in range(count):
        open_time = anchor - timedelta(minutes=5 * (count - index))
        close_time = open_time + timedelta(minutes=5)
        price = Decimal("100") + Decimal(index) / Decimal("1000")
        rows.append(Candle(
            symbol=symbol, market_type=MarketType.SPOT, timeframe=CandleTimeframe.M5,
            open_time=open_time, close_time=close_time,
            open=price, high=price + Decimal("1"), low=price - Decimal("1"), close=price + Decimal("0.1"),
            volume=Decimal("1"), is_final=final, updated_at=close_time,
        ))
    return tuple(rows)


def _analyzer() -> MarketActivityAnalyzer:
    return MarketActivityAnalyzer(baseline_periods=6, stale_after=timedelta(minutes=15))


def test_liquid_continuous_market_remains_available() -> None:
    snapshot = _analyzer().analyze(
        market=ExecutableMarket(symbol="AAA/USD", market_type=MarketType.SPOT),
        candles=_candles("AAA/USD"), observed_at=NOW,
    )
    assert snapshot.status is RadarStatus.AVAILABLE
    assert snapshot.data_quality in {ActivityDataQuality.COMPLETE, ActivityDataQuality.NO_TRADE_GAPS}


def test_complete_but_old_history_is_stale() -> None:
    snapshot = _analyzer().analyze(
        market=ExecutableMarket(symbol="AAA/USD", market_type=MarketType.SPOT),
        candles=_candles("AAA/USD", anchor=NOW - timedelta(hours=1)), observed_at=NOW,
    )
    assert snapshot.status is RadarStatus.STALE


def test_very_high_requires_ratio_and_acceleration_on_same_horizon() -> None:
    assert _activity_state((Decimal("2.6"), Decimal("1")), (Decimal("0.6"), Decimal("2"))) is MarketActivityState.VERY_HIGH
    assert _activity_state((Decimal("2.6"), Decimal("1")), (Decimal("0.1"), Decimal("0.6"))) is not MarketActivityState.VERY_HIGH


class Catalogue:
    async def list_markets(self): return (ExecutableMarket(symbol="AAA/USD", market_type=MarketType.SPOT),)
    async def aclose(self): return None
class BrokenCandles:
    async def history(self, key, *, limit: int = 1000):
        raise KrakenPayloadError("PRIVATE", stage=KrakenPayloadStage.OHLC_ROW)


def test_radar_counts_specific_kraken_payload_diagnostic_without_leaking_message() -> None:
    async def scenario() -> None:
        radar = MarketAttentionRadar(candle_service=BrokenCandles(), catalogue=Catalogue())  # type: ignore[arg-type]
        overview = await radar.refresh_once(observed_at=NOW)
        assert overview.activity_error_counts.KrakenPayloadError == 1
        assert overview.activity_payload_stage_counts.OHLC_ROW == 1
        assert "PRIVATE" not in str(overview.model_dump(mode="json"))
        await radar.aclose()
    asyncio.run(scenario())
