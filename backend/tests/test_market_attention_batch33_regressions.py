from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import ai_spot_trader.market.attention as attention_module
from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.attention import _scan_allocations, _spot_usd_notional
from ai_spot_trader.market.candles import Candle, CandleTimeframe

NOW = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)


def test_batch32_rotation_allocation_remains_100_spot_20_perpetual() -> None:
    assert _scan_allocations({MarketType.SPOT: 100, MarketType.PERPETUAL: 20}, limit=120) == {MarketType.SPOT: 100, MarketType.PERPETUAL: 20}


def test_batch31_notional_semantics_remain_spot_usd_only() -> None:
    candle = Candle(
        symbol="BTC/USD", market_type=MarketType.SPOT, timeframe=CandleTimeframe.M5,
        open_time=NOW - timedelta(minutes=5), close_time=NOW, open=Decimal("100"), high=Decimal("100"), low=Decimal("100"), close=Decimal("100"), volume=Decimal("2"), is_final=True, updated_at=NOW,
    )
    assert _spot_usd_notional((candle,), market=ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT)) == Decimal("200")
    assert _spot_usd_notional((candle,), market=ExecutableMarket(symbol="BTC/USD", market_type=MarketType.PERPETUAL)) is None


def test_market_attention_module_keeps_execution_and_external_research_dependencies_absent() -> None:
    source = inspect.getsource(attention_module).lower()
    for token in ("agent.", "risk", "broker", "discovery", "openai", "web_search"):
        assert token not in source
