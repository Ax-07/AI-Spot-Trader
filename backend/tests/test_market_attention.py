from __future__ import annotations

import asyncio
import inspect
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

import ai_spot_trader.market.attention as attention_module
from ai_spot_trader.api.routes.market_attention import router as market_attention_router
from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.attention import MarketActivityAnalyzer, MarketActivityState, MarketAttentionRadar, RadarStatus
from ai_spot_trader.market.candles import Candle, CandleKey, CandleTimeframe

NOW = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)


def _candle(index: int, *, symbol: str = "QNT/USD", volume: str = "1", final: bool = True) -> Candle:
    open_time = NOW - timedelta(minutes=5 * (404 - index))
    close_time = open_time + timedelta(minutes=5)
    return Candle(
        symbol=symbol, market_type=MarketType.SPOT, timeframe=CandleTimeframe.M5,
        open_time=open_time, close_time=close_time,
        open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"),
        volume=Decimal(volume), is_final=final, updated_at=close_time,
    )


def _history(*, current: str = "6") -> tuple[Candle, ...]:
    rows = []
    for index in range(404):
        volume = "1"
        if 404 - 96 <= index < 404 - 48:
            volume = "2"
        elif index >= 404 - 48:
            volume = current
        rows.append(_candle(index, volume=volume))
    return tuple(rows)


def test_market_activity_uses_relative_volume_and_detects_acceleration() -> None:
    analyzer = MarketActivityAnalyzer(baseline_periods=6, stale_after=timedelta(minutes=15))
    snapshot = analyzer.analyze(
        market=ExecutableMarket(symbol="QNT/USD", market_type=MarketType.SPOT),
        candles=_history(), observed_at=NOW,
    )
    assert snapshot.status is RadarStatus.AVAILABLE
    assert snapshot.activity_state in {MarketActivityState.ACCELERATING, MarketActivityState.VERY_HIGH}


def test_market_activity_reports_insufficient_data_without_fake_statistics() -> None:
    analyzer = MarketActivityAnalyzer(baseline_periods=6, stale_after=timedelta(minutes=15))
    snapshot = analyzer.analyze(
        market=ExecutableMarket(symbol="QNT/USD", market_type=MarketType.SPOT),
        candles=(), observed_at=NOW,
    )
    assert snapshot.status is RadarStatus.PARTIAL
    assert all(not horizon.complete for horizon in snapshot.horizons)


class Catalogue:
    async def list_markets(self):
        return (ExecutableMarket(symbol="QNT/USD", market_type=MarketType.SPOT),)
    async def aclose(self):
        return None


class Candles:
    async def history(self, key: CandleKey, *, limit: int = 1000):
        return _history()


def test_radar_refresh_is_deterministic_and_requires_no_external_researcher() -> None:
    async def scenario() -> None:
        radar = MarketAttentionRadar(candle_service=Candles(), catalogue=Catalogue())  # type: ignore[arg-type]
        overview = await radar.refresh_once(observed_at=NOW)
        assert overview.candidate_market_count >= 1
        dumped = overview.model_dump(mode="json")
        assert "public_attention" not in dumped
        assert "web_search_count" not in dumped
        await radar.aclose()
    asyncio.run(scenario())


def test_market_attention_api_is_read_only_and_exposes_latest_snapshot() -> None:
    app = FastAPI()
    app.state.market_attention = None
    app.include_router(market_attention_router)
    with TestClient(app) as client:
        response = client.get("/api/v1/market-attention")
        assert response.status_code == 200
        assert response.json()["informative_only"] is True
        assert response.json()["protocol_version"] == "market-attention-radar-v2"
        assert client.post("/api/v1/market-attention").status_code == 405


def test_radar_module_has_no_agent_risk_broker_discovery_openai_or_web_dependency() -> None:
    source = inspect.getsource(attention_module).lower()
    for token in ("ai_spot_trader.agent", "risk", "broker", "market.discovery", "openai", "web_search"):
        assert token not in source
