from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.attention import (
    ActivityHorizonSnapshot,
    LiquidityRegime,
    MarketActivitySnapshot,
    MarketActivityState,
    MarketAttentionPolicy,
    MarketAttentionRadar,
    RadarInterestLevel,
    RadarStatus,
    _liquidity_regime,
    _spot_usd_notional,
)
from ai_spot_trader.market.candles import Candle, CandleTimeframe

NOW = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)


def _candle(symbol: str, market_type: MarketType, volume: str = "2", close: str = "10") -> Candle:
    value = Decimal(close)
    return Candle(
        symbol=symbol, market_type=market_type, timeframe=CandleTimeframe.M5,
        open_time=NOW - timedelta(minutes=5), close_time=NOW, open=value, high=value, low=value, close=value,
        volume=Decimal(volume), is_final=True, updated_at=NOW,
    )


def test_direct_usd_spot_exposes_valid_notional() -> None:
    market = ExecutableMarket(symbol="QNT/USD", market_type=MarketType.SPOT)
    assert _spot_usd_notional((_candle("QNT/USD", MarketType.SPOT),), market=market) == Decimal("20")


def test_non_usd_spot_never_invents_usd_conversion() -> None:
    market = ExecutableMarket(symbol="QNT/EUR", market_type=MarketType.SPOT)
    assert _spot_usd_notional((_candle("QNT/EUR", MarketType.SPOT),), market=market) is None


def test_perpetual_notional_remains_unavailable_without_verified_contract_semantics() -> None:
    market = ExecutableMarket(symbol="QNT/USD", market_type=MarketType.PERPETUAL)
    assert _spot_usd_notional((_candle("QNT/USD", MarketType.PERPETUAL),), market=market) is None


def test_liquidity_regime_quantiles_are_deterministic() -> None:
    population = tuple(Decimal(str(v)) for v in (1, 2, 3, 4, 5))
    assert _liquidity_regime(Decimal("1"), population) is LiquidityRegime.MICRO
    assert _liquidity_regime(Decimal("3"), population) is LiquidityRegime.MEDIUM
    assert _liquidity_regime(Decimal("5"), population) is LiquidityRegime.VERY_HIGH


def _candidate(symbol: str, regime: LiquidityRegime, ratio: str) -> MarketActivitySnapshot:
    return MarketActivitySnapshot(
        market=ExecutableMarket(symbol=symbol, market_type=MarketType.SPOT),
        observed_at=NOW, status=RadarStatus.AVAILABLE,
        activity_state=MarketActivityState.ELEVATED,
        liquidity_regime=regime,
        horizons=(ActivityHorizonSnapshot(
            timeframe=CandleTimeframe.M5,
            volume_ratio=Decimal(ratio), volume_acceleration=Decimal("0.2"),
            observation_count=1, baseline_period_count=6, complete=True,
        ),),
        interest_level=RadarInterestLevel.MEDIUM,
    )


class DummyCatalogue:
    async def list_markets(self): return ()
    async def aclose(self): return None
class DummyCandles:
    async def history(self, key, *, limit: int = 1000): return ()


def test_micro_market_is_preserved_by_candidate_diversification() -> None:
    radar = MarketAttentionRadar(
        candle_service=DummyCandles(), catalogue=DummyCatalogue(),  # type: ignore[arg-type]
        policy=MarketAttentionPolicy(candidate_limit=2, candle_limit=160),
    )
    candidates = radar._candidates_from((
        _candidate("AAA/USD", LiquidityRegime.VERY_HIGH, "3"),
        _candidate("BBB/USD", LiquidityRegime.HIGH, "2.5"),
        _candidate("CCC/USD", LiquidityRegime.MICRO, "3.5"),
    ))
    assert any(item.liquidity_regime is LiquidityRegime.MICRO for item in candidates)
