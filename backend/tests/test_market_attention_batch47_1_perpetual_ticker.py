from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.attention import MarketAttentionPolicy
from ai_spot_trader.market.attention_filters import (
    MarketMetadataSnapshot,
    PerpetualTickerContext,
    PerpetualTickerStatus,
    Volume24hStatus,
)
from ai_spot_trader.market.attention_scope_trend import MarketScope
from ai_spot_trader.market.attention_structure_prefilter import (
    MarketStructureScanPolicy,
    StructureAwareFilteredMarketAttentionRadar,
    StructureAwareMarketAttentionFilters,
    _structured_candidate_sort_key,
)
from ai_spot_trader.market.candles import Candle, CandleKey, CandleTimeframe
from ai_spot_trader.market.microstructure import MicrostructurePolicy
from ai_spot_trader.market.structure import MarketStructurePolicy

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
PERP = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.PERPETUAL)
SPOT = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT)


def _active_history(market: ExecutableMarket) -> tuple[Candle, ...]:
    count = 420
    rows: list[Candle] = []
    for index in range(count):
        open_time = NOW - CandleTimeframe.M5.duration * (count - index)
        close_time = open_time + CandleTimeframe.M5.duration
        volume = Decimal("10") if index >= count - 48 else Decimal("1")
        rows.append(
            Candle(
                symbol=market.symbol,
                market_type=market.market_type,
                timeframe=CandleTimeframe.M5,
                open_time=open_time,
                close_time=close_time,
                open=Decimal("100"),
                high=Decimal("101"),
                low=Decimal("99"),
                close=Decimal("100"),
                volume=volume,
                is_final=True,
                updated_at=close_time,
            )
        )
    return tuple(rows)


class Cache:
    def __init__(self, rows: tuple[Candle, ...]) -> None:
        self.rows = rows

    def history_as_of(self, key: CandleKey, *, as_of: datetime, limit: int | None = None):
        del key
        rows = tuple(item for item in self.rows if item.close_time <= as_of)
        return rows if limit is None else rows[-limit:]


class Candles:
    def __init__(self) -> None:
        self.rows = _active_history(PERP)
        self.cache = Cache(self.rows)

    async def history(self, key: CandleKey, *, limit: int = 1000):
        del key
        return self.rows[-limit:]

    async def history_as_of(
        self,
        key: CandleKey,
        *,
        as_of: datetime,
        limit: int = 1000,
    ):
        del key, as_of, limit
        return ()


class Microstructure:
    async def fetch_order_book(self, symbol: str, *, limit: int):
        del symbol, limit
        raise AssertionError("PERPETUAL scope must not request the SPOT order book")

    async def fetch_recent_trades(self, symbol: str, *, limit: int):
        del symbol, limit
        raise AssertionError("PERPETUAL scope must not request SPOT trades")

    async def aclose(self) -> None:
        return None


class Metadata:
    async def metadata_by_symbol(self):
        return {
            "BTC": MarketMetadataSnapshot(
                asset_symbol="BTC",
                market_cap_usd=Decimal("1000000000000"),
                market_cap_rank=1,
                circulating_supply=Decimal("20000000"),
                observed_at=NOW,
                provider="TEST",
            )
        }

    async def aclose(self) -> None:
        return None


class TickerCatalogue:
    def __init__(self, *, broken: bool = False, prediction: Decimal | None = Decimal("7.25")):
        self.broken = broken
        self.prediction = prediction
        self.ticker_calls = 0

    async def list_markets(self):
        return (PERP,)

    async def perpetual_ticker_snapshot_by_market(self):
        self.ticker_calls += 1
        if self.broken:
            raise RuntimeError("bulk ticker unavailable")
        return {
            PERP: SimpleNamespace(
                venue_symbol="PF_XBTUSD",
                observed_at=NOW,
                mark_price=Decimal("65000"),
                index_price=Decimal("64990"),
                volume_quote=Decimal("150000"),
                open_interest=Decimal("12345.75"),
                funding_rate_raw=Decimal("6.5"),
                funding_rate_prediction_raw=self.prediction,
                suspended=False,
            )
        }

    async def aclose(self) -> None:
        return None


class LegacyVolumeCatalogue:
    def __init__(self) -> None:
        self.volume_calls = 0

    async def list_markets(self):
        return (PERP,)

    async def volume_24h_usd_by_market(self):
        self.volume_calls += 1
        return {PERP: Decimal("150000")}

    async def aclose(self) -> None:
        return None


def _radar(catalogue):
    return StructureAwareFilteredMarketAttentionRadar(
        candle_service=Candles(),  # type: ignore[arg-type]
        catalogue=catalogue,  # type: ignore[arg-type]
        microstructure_provider=Microstructure(),  # type: ignore[arg-type]
        metadata_provider=Metadata(),
        policy=MarketAttentionPolicy(scan_limit=10, candle_limit=420, candidate_limit=1),
        microstructure_policy=MicrostructurePolicy(market_limit_per_refresh=10),
        structure_policy=MarketStructurePolicy(
            history_limit=40,
            min_history_candles=20,
            fetch_concurrency=4,
        ),
        structure_scan_policy=MarketStructureScanPolicy(
            market_limit_per_refresh=10,
            cache_ttl_seconds=3600,
        ),
    )


def test_spot_context_is_explicitly_not_applicable() -> None:
    radar = _radar(LegacyVolumeCatalogue())
    context = radar._perpetual_ticker_context(SPOT)  # noqa: SLF001
    assert context.status is PerpetualTickerStatus.NOT_APPLICABLE


def test_one_bulk_snapshot_feeds_volume_liquidity_oi_and_funding_without_ranking_changes() -> None:
    async def scenario() -> None:
        catalogue = TickerCatalogue()
        radar = _radar(catalogue)
        legacy = _radar(LegacyVolumeCatalogue())
        try:
            snapshot = await radar.set_filters(
                StructureAwareMarketAttentionFilters(
                    market_scope=MarketScope.PERPETUAL,
                    min_volume_24h_usd=Decimal("100000"),
                ),
                observed_at=NOW,
            )
            baseline = await legacy.set_filters(
                StructureAwareMarketAttentionFilters(
                    market_scope=MarketScope.PERPETUAL,
                    min_volume_24h_usd=Decimal("100000"),
                ),
                observed_at=NOW,
            )
        finally:
            await radar.aclose()
            await legacy.aclose()

        assert catalogue.ticker_calls == 1
        assert snapshot.candidate_market_count == 1
        assert len(snapshot.shortlist) == 1
        candidate = snapshot.shortlist[0]
        futures = candidate.perpetual_ticker
        assert futures is not None
        assert futures.status is PerpetualTickerStatus.AVAILABLE
        assert futures.open_interest == Decimal("12345.75")
        assert futures.open_interest_unit is None
        assert futures.funding_rate_raw == Decimal("6.5")
        assert futures.funding_rate_prediction_raw == Decimal("7.25")
        assert futures.funding_rate_relative is None
        assert futures.mark_price == Decimal("65000")
        assert futures.index_price == Decimal("64990")
        assert candidate.volume_24h_usd == Decimal("150000")
        assert candidate.market_activity.liquidity_reference_usd == Decimal("150000")

        # Batch 47.1 is descriptive only: canonical interest and adaptive OHLCV facts remain equal.
        legacy_candidate = baseline.shortlist[0]
        assert candidate.interest_level == legacy_candidate.interest_level
        assert candidate.interest_reasons == legacy_candidate.interest_reasons
        assert (
            candidate.market_activity.activity_state
            == legacy_candidate.market_activity.activity_state
        )
        assert [h.volume_anomaly_score for h in candidate.market_activity.horizons] == [
            h.volume_anomaly_score for h in legacy_candidate.market_activity.horizons
        ]
        assert candidate.market_structure == legacy_candidate.market_structure
        assert _structured_candidate_sort_key(candidate) == _structured_candidate_sort_key(
            candidate.model_copy(
                update={
                    "perpetual_ticker": PerpetualTickerContext(
                        status=PerpetualTickerStatus.AVAILABLE,
                        venue_symbol="PF_XBTUSD",
                        observed_at=NOW,
                        open_interest=Decimal("999999999"),
                        funding_rate_raw=Decimal("-12345"),
                        funding_rate_prediction_raw=Decimal("54321"),
                    )
                }
            )
        )
        assert snapshot.candidate_market_count == baseline.candidate_market_count == 1

    asyncio.run(scenario())


def test_missing_prediction_is_partial_and_never_conflated_with_current_funding() -> None:
    async def scenario() -> None:
        radar = _radar(TickerCatalogue(prediction=None))
        try:
            snapshot = await radar.set_filters(
                StructureAwareMarketAttentionFilters(market_scope=MarketScope.PERPETUAL),
                observed_at=NOW,
            )
        finally:
            await radar.aclose()

        futures = snapshot.shortlist[0].perpetual_ticker
        assert futures is not None
        assert futures.status is PerpetualTickerStatus.PARTIAL
        assert futures.funding_rate_raw == Decimal("6.5")
        assert futures.funding_rate_prediction_raw is None

    asyncio.run(scenario())


def test_bulk_failure_is_fail_soft_without_volume_filter_and_fail_closed_with_filter() -> None:
    async def scenario() -> None:
        fail_soft = _radar(TickerCatalogue(broken=True))
        fail_closed = _radar(TickerCatalogue(broken=True))
        try:
            soft = await fail_soft.set_filters(
                StructureAwareMarketAttentionFilters(market_scope=MarketScope.PERPETUAL),
                observed_at=NOW,
            )
            closed = await fail_closed.set_filters(
                StructureAwareMarketAttentionFilters(
                    market_scope=MarketScope.PERPETUAL,
                    min_volume_24h_usd=Decimal("100000"),
                ),
                observed_at=NOW,
            )
        finally:
            await fail_soft.aclose()
            await fail_closed.aclose()

        assert soft.candidate_market_count == 1
        futures = soft.shortlist[0].perpetual_ticker
        assert futures is not None
        assert futures.status is PerpetualTickerStatus.TECHNICAL_ERROR
        assert closed.candidate_market_count == 0
        assert closed.volume_24h_status_counts.UNKNOWN_TECHNICAL_ERROR == 1

    asyncio.run(scenario())


def test_legacy_volume_provider_keeps_batch43_2_behavior_and_partial_futures_context() -> None:
    async def scenario() -> None:
        catalogue = LegacyVolumeCatalogue()
        radar = _radar(catalogue)
        try:
            await radar._catalogue_if_due(NOW)  # noqa: SLF001
            measurement = radar._volume_24h_measurement(PERP, as_of=NOW)  # noqa: SLF001
            context = radar._perpetual_ticker_context(PERP)  # noqa: SLF001
        finally:
            await radar.aclose()

        assert catalogue.volume_calls == 1
        assert measurement.status is Volume24hStatus.AVAILABLE
        assert measurement.value_usd == Decimal("150000")
        assert context.status is PerpetualTickerStatus.PARTIAL

    asyncio.run(scenario())
