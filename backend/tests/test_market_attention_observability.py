from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_spot_trader.api.routes.market_attention import router as market_attention_router
from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.attention import (
    ActivityDataQuality,
    ActivityHorizonSnapshot,
    MarketActivitySnapshot,
    MarketActivityState,
    MarketAttentionRadar,
    RadarStatus,
    _activity_data_quality_counts,
    _activity_state_counts,
    _activity_status_counts,
)
from ai_spot_trader.market.candles import CandleKey, CandleTimeframe

NOW = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)


def _snapshot(symbol: str, status: RadarStatus, state: MarketActivityState, quality: ActivityDataQuality) -> MarketActivitySnapshot:
    return MarketActivitySnapshot(
        market=ExecutableMarket(symbol=symbol, market_type=MarketType.SPOT),
        observed_at=NOW,
        status=status,
        activity_state=state,
        freshness_seconds=Decimal("0"),
        horizons=(ActivityHorizonSnapshot(timeframe=CandleTimeframe.M5, observation_count=0, baseline_period_count=0, complete=False),),
        data_quality=quality,
    )


def test_overview_count_helpers_cover_status_state_and_quality() -> None:
    rows = (
        _snapshot("AAA/USD", RadarStatus.AVAILABLE, MarketActivityState.NORMAL, ActivityDataQuality.COMPLETE),
        _snapshot("BBB/USD", RadarStatus.PARTIAL, MarketActivityState.UNKNOWN, ActivityDataQuality.INSUFFICIENT_HISTORY),
        _snapshot("CCC/USD", RadarStatus.ERROR, MarketActivityState.UNKNOWN, ActivityDataQuality.TECHNICAL_ERROR),
    )
    assert _activity_status_counts(rows).model_dump() == {"AVAILABLE": 1, "PARTIAL": 1, "STALE": 0, "ERROR": 1}
    assert _activity_state_counts(rows).NORMAL == 1
    assert _activity_state_counts(rows).UNKNOWN == 2
    assert _activity_data_quality_counts(rows).TECHNICAL_ERROR == 1


class Catalogue:
    async def list_markets(self):
        return (ExecutableMarket(symbol="AAA/USD", market_type=MarketType.SPOT),)
    async def aclose(self):
        return None


class BrokenCandles:
    async def history(self, key: CandleKey, *, limit: int = 1000):
        raise TimeoutError("private details")


def test_kraken_failure_is_fail_soft_and_bounded() -> None:
    async def scenario() -> None:
        radar = MarketAttentionRadar(candle_service=BrokenCandles(), catalogue=Catalogue())  # type: ignore[arg-type]
        overview = await radar.refresh_once(observed_at=NOW)
        assert overview.activity_status_counts.ERROR == 1
        assert overview.activity_error_counts.Other == 1
        assert "private details" not in str(overview.model_dump(mode="json"))
        await radar.aclose()
    asyncio.run(scenario())


def test_read_only_api_exposes_deterministic_observability_fields_only() -> None:
    app = FastAPI()
    app.state.market_attention = None
    app.include_router(market_attention_router)
    with TestClient(app) as client:
        payload = client.get("/api/v1/market-attention").json()
    assert payload["protocol_version"] == "market-attention-radar-v2"
    assert "activity_error_counts" in payload
    assert "activity_payload_stage_counts" in payload
    assert not any("web" in key or "public_research" in key for key in payload)
