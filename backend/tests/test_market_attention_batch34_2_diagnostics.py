from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.integrations.kraken.errors import KrakenPayloadError, KrakenPayloadStage
from ai_spot_trader.market.attention import MarketAttentionRadar

NOW = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)
MARKET = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT)


class OneMarketCatalogue:
    async def list_markets(self): return (MARKET,)
    async def aclose(self): return None


class SequencedCandles:
    def __init__(self): self.calls = 0
    async def history(self, key, *, limit: int):
        self.calls += 1
        if self.calls == 1:
            raise KrakenPayloadError("PRIVATE KRAKEN PAYLOAD MUST NOT LEAK", stage=KrakenPayloadStage.ASSET_PAIRS_SYMBOL)
        return ()


def test_payload_stage_is_aggregated_without_exception_content_and_cleared_after_success() -> None:
    async def scenario() -> None:
        candles = SequencedCandles()
        radar = MarketAttentionRadar(candle_service=candles, catalogue=OneMarketCatalogue())  # type: ignore[arg-type]
        first = await radar.refresh_once(observed_at=NOW)
        assert first.activity_error_counts.KrakenPayloadError == 1
        assert first.activity_payload_stage_counts.ASSET_PAIRS_SYMBOL == 1
        assert "PRIVATE KRAKEN PAYLOAD MUST NOT LEAK" not in str(first.model_dump(mode="json"))
        second = await radar.refresh_once(observed_at=NOW)
        assert second.activity_error_counts.KrakenPayloadError == 0
        assert sum(second.activity_payload_stage_counts.model_dump().values()) == 0
        await radar.aclose()
    asyncio.run(scenario())


def test_non_allowlisted_payload_stage_is_not_exposed() -> None:
    class UnknownStageCandles:
        async def history(self, key, *, limit: int):
            exc = KrakenPayloadError("PRIVATE")
            exc.stage = "PROVIDER_KEY=SECRET"  # type: ignore[assignment]
            raise exc
    async def scenario() -> None:
        radar = MarketAttentionRadar(candle_service=UnknownStageCandles(), catalogue=OneMarketCatalogue())  # type: ignore[arg-type]
        overview = await radar.refresh_once(observed_at=NOW)
        assert overview.activity_error_counts.KrakenPayloadError == 1
        assert sum(overview.activity_payload_stage_counts.model_dump().values()) == 0
        await radar.aclose()
    asyncio.run(scenario())
