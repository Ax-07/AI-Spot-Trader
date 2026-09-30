from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.integrations.kraken.errors import KrakenPayloadError, KrakenPayloadStage
from ai_spot_trader.market.attention import MarketAttentionRadar, RadarStatus

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
MARKET = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT)
PERPETUAL_MARKET = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.PERPETUAL)


class OneMarketCatalogue:
    async def list_markets(self) -> tuple[ExecutableMarket, ...]:
        return (MARKET,)

    async def aclose(self) -> None:
        return None


class SequencedCandles:
    def __init__(self) -> None:
        self.calls = 0

    async def history(self, key, *, limit: int):
        self.calls += 1
        if self.calls == 1:
            raise KrakenPayloadError(
                "PRIVATE KRAKEN PAYLOAD MUST NOT LEAK",
                stage=KrakenPayloadStage.ASSET_PAIRS_SYMBOL,
            )
        return ()


def test_payload_stage_is_aggregated_without_exception_content_and_cleared_after_success() -> None:
    async def scenario() -> None:
        candles = SequencedCandles()
        radar = MarketAttentionRadar(
            candle_service=candles,  # type: ignore[arg-type]
            catalogue=OneMarketCatalogue(),
            researcher=None,
        )

        first = await radar.refresh_once(observed_at=NOW)
        first_dump = first.model_dump(mode="json")
        assert first.activity_error_counts.KrakenPayloadError == 1
        assert first.activity_payload_stage_counts.ASSET_PAIRS_SYMBOL == 1
        assert sum(first.activity_payload_stage_counts.model_dump().values()) == 1
        assert "PRIVATE KRAKEN PAYLOAD MUST NOT LEAK" not in str(first_dump)
        assert "ASSET_PAIRS_SYMBOL" in str(first_dump)

        second = await radar.refresh_once(observed_at=NOW)
        assert second.status in {RadarStatus.PARTIAL, RadarStatus.AVAILABLE}
        assert second.activity_error_counts.KrakenPayloadError == 0
        assert sum(second.activity_payload_stage_counts.model_dump().values()) == 0

    asyncio.run(scenario())


def test_non_allowlisted_payload_stage_is_not_exposed() -> None:
    class UnknownStageCandles:
        async def history(self, key, *, limit: int):
            exc = KrakenPayloadError("PRIVATE")
            # Defense-in-depth: simulate a corrupted/mutated exception instance.
            exc.stage = "PROVIDER_KEY=SECRET"  # type: ignore[assignment]
            raise exc

    async def scenario() -> None:
        radar = MarketAttentionRadar(
            candle_service=UnknownStageCandles(),  # type: ignore[arg-type]
            catalogue=OneMarketCatalogue(),
            researcher=None,
        )
        overview = await radar.refresh_once(observed_at=NOW)
        dumped = overview.model_dump(mode="json")
        assert overview.activity_error_counts.KrakenPayloadError == 1
        assert sum(overview.activity_payload_stage_counts.model_dump().values()) == 0
        assert "PROVIDER_KEY" not in str(dumped)
        assert "SECRET" not in str(dumped)

    asyncio.run(scenario())


def test_perpetual_activity_without_payload_error_does_not_create_payload_stage() -> None:
    class PerpetualCatalogue:
        async def list_markets(self) -> tuple[ExecutableMarket, ...]:
            return (PERPETUAL_MARKET,)

        async def aclose(self) -> None:
            return None

    class EmptyCandles:
        async def history(self, key, *, limit: int):
            return ()

    async def scenario() -> None:
        radar = MarketAttentionRadar(
            candle_service=EmptyCandles(),  # type: ignore[arg-type]
            catalogue=PerpetualCatalogue(),
            researcher=None,
        )
        overview = await radar.refresh_once(observed_at=NOW)
        assert overview.activity_error_counts.KrakenPayloadError == 0
        assert sum(overview.activity_payload_stage_counts.model_dump().values()) == 0
        assert overview.activity_market_type_status_counts.PERPETUAL.ERROR == 0

    asyncio.run(scenario())
