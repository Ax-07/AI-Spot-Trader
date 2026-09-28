from __future__ import annotations

import asyncio
import inspect
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import ai_spot_trader.market.attention as attention_module
from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.attention import (
    LiquidityRegime,
    MarketActivityAnalyzer,
    MarketActivityState,
    MarketAttentionPolicy,
    MarketAttentionRadar,
    RadarStatus,
    _activity_state,
    _liquidity_regime,
)
from ai_spot_trader.market.candles import Candle, CandleKey, CandleTimeframe

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


def candle(
    index: int,
    *,
    symbol: str = "QNT/USD",
    market_type: MarketType = MarketType.SPOT,
    volume: str = "1",
    close: str = "100",
) -> Candle:
    open_time = NOW - timedelta(minutes=5 * (404 - index))
    close_time = open_time + timedelta(minutes=5)
    price = Decimal(close)
    return Candle(
        symbol=symbol,
        market_type=market_type,
        timeframe=CandleTimeframe.M5,
        open_time=open_time,
        close_time=close_time,
        open=price,
        high=price * Decimal("1.01"),
        low=price * Decimal("0.99"),
        close=price,
        volume=Decimal(volume),
        is_final=True,
        updated_at=close_time,
    )


def history(
    *,
    symbol: str = "QNT/USD",
    market_type: MarketType = MarketType.SPOT,
    baseline: str = "1",
    previous: str = "2",
    current: str = "6",
    close: str = "100",
) -> tuple[Candle, ...]:
    rows: list[Candle] = []
    for index in range(404):
        volume = baseline
        if index >= 404 - 96 and index < 404 - 48:
            volume = previous
        elif index >= 404 - 48:
            volume = current
        rows.append(
            candle(
                index,
                symbol=symbol,
                market_type=market_type,
                volume=volume,
                close=close,
            )
        )
    return tuple(rows)


def analyzer() -> MarketActivityAnalyzer:
    return MarketActivityAnalyzer(baseline_periods=6, stale_after=timedelta(minutes=15))


def test_direct_usd_spot_exposes_current_baseline_and_delta_notional() -> None:
    market = ExecutableMarket(symbol="QNT/USD", market_type=MarketType.SPOT)
    snapshot = analyzer().analyze(market=market, candles=history(), observed_at=NOW)
    h4 = snapshot.horizon(CandleTimeframe.H4)

    assert h4 is not None and h4.complete is True
    assert h4.current_notional_usd == Decimal("28800")
    assert h4.baseline_notional_usd == Decimal("4800")
    assert h4.notional_delta_usd == Decimal("24000")
    assert h4.notional_method == "SPOT_BASE_VOLUME_X_5M_CLOSE_ESTIMATE"


def test_low_volume_spot_keeps_small_but_valid_usd_notional() -> None:
    market = ExecutableMarket(symbol="TINY/USD", market_type=MarketType.SPOT)
    snapshot = analyzer().analyze(
        market=market,
        candles=history(
            symbol="TINY/USD",
            baseline="0.001",
            previous="0.002",
            current="0.008",
            close="0.25",
        ),
        observed_at=NOW,
    )
    h4 = snapshot.horizon(CandleTimeframe.H4)

    assert h4 is not None and h4.volume_ratio == Decimal("8")
    assert h4.current_notional_usd == Decimal("0.09600")
    assert h4.baseline_notional_usd == Decimal("0.01200")
    assert h4.notional_delta_usd == Decimal("0.08400")


def test_non_usd_spot_never_invents_usd_conversion() -> None:
    market = ExecutableMarket(symbol="QNT/EUR", market_type=MarketType.SPOT)
    snapshot = analyzer().analyze(
        market=market,
        candles=history(symbol="QNT/EUR"),
        observed_at=NOW,
    )
    h4 = snapshot.horizon(CandleTimeframe.H4)

    assert h4 is not None and h4.volume_ratio == Decimal("6")
    assert h4.current_notional_usd is None
    assert h4.baseline_notional_usd is None
    assert h4.notional_delta_usd is None
    assert h4.notional_method is None


def test_perpetual_notional_remains_unavailable_without_verified_contract_volume_semantics() -> None:
    market = ExecutableMarket(symbol="QNT/USD", market_type=MarketType.PERPETUAL)
    snapshot = analyzer().analyze(
        market=market,
        candles=history(market_type=MarketType.PERPETUAL),
        observed_at=NOW,
    )
    h4 = snapshot.horizon(CandleTimeframe.H4)

    assert h4 is not None and h4.volume_ratio == Decimal("6")
    assert h4.current_notional_usd is None
    assert h4.baseline_notional_usd is None
    assert h4.notional_delta_usd is None


def test_relative_activity_thresholds_are_unchanged() -> None:
    assert _activity_state((Decimal("1.3999"),), (Decimal("5"),)) is MarketActivityState.NORMAL
    assert _activity_state((Decimal("1.40"),), (Decimal("0"),)) is MarketActivityState.ELEVATED
    assert _activity_state((Decimal("1.75"),), (Decimal("0.25"),)) is MarketActivityState.ACCELERATING
    assert _activity_state((Decimal("2.50"),), (Decimal("0.50"),)) is MarketActivityState.VERY_HIGH


def test_liquidity_regime_quantiles_are_deterministic() -> None:
    population = tuple(Decimal(value) for value in ("100", "200", "300", "400", "500"))
    assert _liquidity_regime(Decimal("100"), population) is LiquidityRegime.MICRO
    assert _liquidity_regime(Decimal("200"), population) is LiquidityRegime.LOW
    assert _liquidity_regime(Decimal("300"), population) is LiquidityRegime.MEDIUM
    assert _liquidity_regime(Decimal("400"), population) is LiquidityRegime.HIGH
    assert _liquidity_regime(Decimal("500"), population) is LiquidityRegime.VERY_HIGH
    assert _liquidity_regime(None, population) is LiquidityRegime.UNKNOWN


class LiquidityCandleService:
    async def history(self, key: CandleKey, *, limit: int = 1000) -> tuple[Candle, ...]:
        params = {
            "MICRO/USD": ("0.05", "0.05", "0.40", "1"),
            "MID/USD": ("10", "10", "30", "10"),
            "BIG/USD": ("1000", "1000", "2000", "100"),
        }
        baseline, previous, current, close = params[key.symbol]
        return history(
            symbol=key.symbol,
            market_type=key.market_type,
            baseline=baseline,
            previous=previous,
            current=current,
            close=close,
        )[-limit:]


class FakeCatalogue:
    def __init__(self, markets: tuple[ExecutableMarket, ...]) -> None:
        self.markets = markets

    async def list_markets(self) -> tuple[ExecutableMarket, ...]:
        return self.markets

    async def aclose(self) -> None:
        return None


def test_small_liquidity_market_remains_candidate_and_shortlist_is_regime_diversified() -> None:
    async def scenario() -> None:
        markets = tuple(
            ExecutableMarket(symbol=symbol, market_type=MarketType.SPOT)
            for symbol in ("MICRO/USD", "MID/USD", "BIG/USD")
        )
        radar = MarketAttentionRadar(
            candle_service=LiquidityCandleService(),  # type: ignore[arg-type]
            catalogue=FakeCatalogue(markets),
            researcher=None,
            policy=MarketAttentionPolicy(
                scan_limit=10,
                candidate_limit=2,
                max_web_searches_per_refresh=0,
                candle_limit=404,
            ),
        )
        overview = await radar.refresh_once(observed_at=NOW)
        candidates = {item.market_activity.market.symbol for item in overview.shortlist}

        assert overview.candidate_market_count == 2
        assert "MICRO/USD" in candidates
        assert len({item.market_activity.liquidity_regime for item in overview.shortlist}) == 2
        assert overview.web_search_count == 0
        await radar.aclose()

    asyncio.run(scenario())


def test_liquidity_context_does_not_add_trading_dependencies() -> None:
    source = inspect.getsource(attention_module)
    assert "ai_spot_trader.agent" not in source
    assert "ai_spot_trader.risk" not in source
    assert "ai_spot_trader.broker" not in source
    assert "ai_spot_trader.market.discovery" not in source
