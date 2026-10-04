from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from ai_spot_trader.domain.enums import DerivativeContractKind, MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.integrations.kraken.attention import (
    KrakenAttentionCatalogue,
    parse_kraken_derivatives_quote_volumes,
)
from ai_spot_trader.integrations.kraken.derivatives import KrakenDerivativesTickerSnapshot
from ai_spot_trader.integrations.kraken.errors import KrakenPayloadError
from ai_spot_trader.market.attention import MarketAttentionPolicy
from ai_spot_trader.market.attention_filters import (
    FilteredStructuredMarketAttentionRadar,
    MarketAttentionFilters,
    MarketMetadataSnapshot,
)
from ai_spot_trader.market.attention_scope_trend import MarketScope
from ai_spot_trader.market.candles import Candle, CandleKey, CandleTimeframe
from ai_spot_trader.market.microstructure import MicrostructurePolicy
from ai_spot_trader.market.structure import MarketStructurePolicy

NOW = datetime(2026, 10, 3, 8, 0, tzinfo=UTC)
PERP = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.PERPETUAL)


def _active_perpetual_history() -> tuple[Candle, ...]:
    count = 420
    rows: list[Candle] = []
    for index in range(count):
        open_time = NOW - CandleTimeframe.M5.duration * (count - index)
        close_time = open_time + CandleTimeframe.M5.duration
        volume = Decimal("10") if index >= count - 48 else Decimal("1")
        rows.append(
            Candle(
                symbol="BTC/USD",
                market_type=MarketType.PERPETUAL,
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


class Catalogue:
    def __init__(self, volume: Decimal | None = Decimal("150000")) -> None:
        self.volume = volume
        self.volume_calls = 0

    async def list_markets(self):
        return (PERP,)

    async def volume_24h_usd_by_market(self):
        self.volume_calls += 1
        return {} if self.volume is None else {PERP: self.volume}

    async def aclose(self) -> None:
        return None


class BrokenVolumeCatalogue(Catalogue):
    async def volume_24h_usd_by_market(self):
        self.volume_calls += 1
        raise RuntimeError("ticker unavailable")


class Cache:
    def __init__(self, rows: tuple[Candle, ...]) -> None:
        self.rows = rows

    def history_as_of(self, key: CandleKey, *, as_of: datetime, limit: int | None = None):
        del key
        rows = tuple(item for item in self.rows if item.close_time <= as_of)
        return rows if limit is None else rows[-limit:]


class Candles:
    def __init__(self) -> None:
        self.rows = _active_perpetual_history()
        self.cache = Cache(self.rows)
        self.activity_calls: list[CandleKey] = []

    async def history(self, key: CandleKey, *, limit: int = 1000):
        self.activity_calls.append(key)
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
        raise AssertionError("PERPETUAL scope must not request SPOT order book")

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


def _radar(catalogue: Catalogue):
    return FilteredStructuredMarketAttentionRadar(
        candle_service=Candles(),  # type: ignore[arg-type]
        catalogue=catalogue,  # type: ignore[arg-type]
        microstructure_provider=Microstructure(),  # type: ignore[arg-type]
        metadata_provider=Metadata(),
        policy=MarketAttentionPolicy(scan_limit=10, candle_limit=420, candidate_limit=10),
        microstructure_policy=MicrostructurePolicy(market_limit_per_refresh=10),
        structure_policy=MarketStructurePolicy(
            history_limit=40,
            min_history_candles=20,
            fetch_concurrency=4,
        ),
    )


class FakeSpotCatalogueClient:
    async def fetch_pair_registry(self):
        return SimpleNamespace(pairs=())

    async def aclose(self) -> None:
        return None


class FakeDerivativesCatalogueClient:
    def __init__(self) -> None:
        self.instrument = SimpleNamespace(
            symbol="BTC/USD",
            venue_symbol="PF_XBTUSD",
            market_type=MarketType.PERPETUAL,
            contract_kind=DerivativeContractKind.LINEAR,
            quote_asset="USD",
            contract_size=Decimal("1"),
        )
        self.ticker_calls = 0

    async def fetch_instruments(self):
        return (self.instrument,)

    async def fetch_tickers(self):
        self.ticker_calls += 1
        return (
            KrakenDerivativesTickerSnapshot(
                venue_symbol="PF_XBTUSD",
                observed_at=NOW,
                mark_price=Decimal("65000"),
                index_price=Decimal("64990"),
                volume_quote=Decimal("150000.25"),
                open_interest=Decimal("1000"),
                funding_rate_raw=Decimal("6.5"),
                funding_rate_prediction_raw=Decimal("7.0"),
                suspended=False,
                post_only=False,
            ),
        )

    async def aclose(self) -> None:
        return None


def test_kraken_catalogue_discovers_linear_perpetual_and_maps_bulk_quote_volume() -> None:
    async def scenario() -> None:
        catalogue = KrakenAttentionCatalogue.__new__(KrakenAttentionCatalogue)
        catalogue._spot = FakeSpotCatalogueClient()  # type: ignore[attr-defined]
        derivatives = FakeDerivativesCatalogueClient()
        catalogue._derivatives = derivatives  # type: ignore[attr-defined]
        catalogue._perpetual_instruments = {}  # type: ignore[attr-defined]

        markets = await catalogue.list_markets()
        assert markets == (PERP,)

        volumes = await catalogue.volume_24h_usd_by_market()
        assert volumes == {PERP: Decimal("150000.25")}
        assert derivatives.ticker_calls == 1

    asyncio.run(scenario())



def test_kraken_catalogue_maps_bulk_ticker_and_preserves_relative_funding_conversion() -> None:
    async def scenario() -> None:
        catalogue = KrakenAttentionCatalogue.__new__(KrakenAttentionCatalogue)
        catalogue._spot = FakeSpotCatalogueClient()  # type: ignore[attr-defined]
        derivatives = FakeDerivativesCatalogueClient()
        catalogue._derivatives = derivatives  # type: ignore[attr-defined]
        catalogue._perpetual_instruments = {}  # type: ignore[attr-defined]

        snapshots = await catalogue.perpetual_ticker_snapshot_by_market()

        assert derivatives.ticker_calls == 1
        ticker = snapshots[PERP]
        assert ticker.volume_quote == Decimal("150000.25")
        assert ticker.open_interest == Decimal("1000")
        assert ticker.funding_rate_raw == Decimal("6.5")
        assert ticker.funding_rate_prediction_raw == Decimal("7.0")
        assert ticker.funding_rate_relative == Decimal("0.0001")

    asyncio.run(scenario())

def test_bulk_ticker_quote_volume_parser_is_explicit_and_fail_closed() -> None:
    parsed = parse_kraken_derivatives_quote_volumes(
        {
            "result": "success",
            "serverTime": "2026-10-04T12:00:00Z",
            "tickers": [
                {"symbol": "PF_XBTUSD", "volumeQuote": "150000.25"},
                {"symbol": "PF_ETHUSD", "volumeQuote": "99999.5"},
                {"symbol": "PF_SOLUSD"},
                {"symbol": "PF_XRPUSD", "volumeQuote": "123", "suspended": True},
            ],
        }
    )
    assert parsed == {
        "PF_XBTUSD": Decimal("150000.25"),
        "PF_ETHUSD": Decimal("99999.5"),
    }

    with pytest.raises(KrakenPayloadError):
        parse_kraken_derivatives_quote_volumes(
            {"result": "success", "tickers": [{"symbol": "PF_XBTUSD", "volumeQuote": "-1"}]}
        )


def test_perpetual_volume_all_scans_and_keeps_active_candidate() -> None:
    async def scenario() -> None:
        catalogue = Catalogue()
        radar = _radar(catalogue)
        try:
            snapshot = await radar.set_filters(
                MarketAttentionFilters(
                    market_scope=MarketScope.PERPETUAL,
                    min_volume_24h_usd=None,
                ),
                observed_at=NOW,
            )
        finally:
            await radar.aclose()

        assert snapshot.catalogue_market_count > 0
        assert snapshot.scanned_market_count > 0
        assert snapshot.scanned_market_type_counts.PERPETUAL > 0
        assert snapshot.fresh_market_type_counts.PERPETUAL > 0
        assert snapshot.candidate_market_count > 0
        assert catalogue.volume_calls == 1

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("volume", "expected_candidates", "expected_available", "expected_below"),
    [
        (Decimal("150000"), 1, 1, 0),
        (Decimal("100000"), 1, 1, 0),
        (Decimal("99999.99"), 0, 0, 1),
    ],
)
def test_perpetual_volume_threshold_uses_kraken_quote_turnover(
    volume: Decimal,
    expected_candidates: int,
    expected_available: int,
    expected_below: int,
) -> None:
    async def scenario() -> None:
        radar = _radar(Catalogue(volume))
        try:
            snapshot = await radar.set_filters(
                MarketAttentionFilters(
                    market_scope=MarketScope.PERPETUAL,
                    min_volume_24h_usd=Decimal("100000"),
                ),
                observed_at=NOW,
            )
        finally:
            await radar.aclose()

        assert snapshot.candidate_market_count == expected_candidates
        assert snapshot.volume_24h_status_counts.AVAILABLE == expected_available
        assert snapshot.volume_24h_status_counts.BELOW_THRESHOLD == expected_below
        assert snapshot.volume_24h_status_counts.UNKNOWN_UNSUPPORTED_MARKET_TYPE == 0

    asyncio.run(scenario())


def test_perpetual_volume_provider_failure_is_explicit_unknown() -> None:
    async def scenario() -> None:
        radar = _radar(BrokenVolumeCatalogue())
        try:
            snapshot = await radar.set_filters(
                MarketAttentionFilters(
                    market_scope=MarketScope.PERPETUAL,
                    min_volume_24h_usd=Decimal("100000"),
                ),
                observed_at=NOW,
            )
        finally:
            await radar.aclose()

        assert snapshot.candidate_market_count == 0
        assert snapshot.volume_24h_status_counts.UNKNOWN_TECHNICAL_ERROR == 1
        assert snapshot.volume_24h_status_counts.UNKNOWN_UNSUPPORTED_MARKET_TYPE == 0

    asyncio.run(scenario())


def _mixed_active_history(
    market: ExecutableMarket,
    *,
    recent_volume: Decimal,
) -> tuple[Candle, ...]:
    count = 420
    rows: list[Candle] = []
    for index in range(count):
        open_time = NOW - CandleTimeframe.M5.duration * (count - index)
        close_time = open_time + CandleTimeframe.M5.duration
        volume = recent_volume if index >= count - 48 else Decimal("1")
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


class MixedCatalogue:
    SPOT = ExecutableMarket(symbol="ETH/USD", market_type=MarketType.SPOT)
    PERP_KNOWN = PERP
    PERP_UNKNOWN = ExecutableMarket(symbol="DOGE/USD", market_type=MarketType.PERPETUAL)
    markets = (SPOT, PERP_KNOWN, PERP_UNKNOWN)

    async def list_markets(self):
        return self.markets

    async def volume_24h_usd_by_market(self):
        return {self.PERP_KNOWN: Decimal("150000")}

    async def aclose(self) -> None:
        return None


class MixedCache:
    def __init__(self, histories: dict[CandleKey, tuple[Candle, ...]]) -> None:
        self.histories = histories

    def history_as_of(self, key: CandleKey, *, as_of: datetime, limit: int | None = None):
        rows = tuple(item for item in self.histories.get(key, ()) if item.close_time <= as_of)
        return rows if limit is None else rows[-limit:]


class MixedCandles:
    def __init__(self) -> None:
        self.histories = {
            CandleKey(
                symbol=MixedCatalogue.SPOT.symbol,
                market_type=MixedCatalogue.SPOT.market_type,
                timeframe=CandleTimeframe.M5,
            ): _mixed_active_history(MixedCatalogue.SPOT, recent_volume=Decimal("20")),
            CandleKey(
                symbol=MixedCatalogue.PERP_KNOWN.symbol,
                market_type=MixedCatalogue.PERP_KNOWN.market_type,
                timeframe=CandleTimeframe.M5,
            ): _mixed_active_history(MixedCatalogue.PERP_KNOWN, recent_volume=Decimal("10")),
            CandleKey(
                symbol=MixedCatalogue.PERP_UNKNOWN.symbol,
                market_type=MixedCatalogue.PERP_UNKNOWN.market_type,
                timeframe=CandleTimeframe.M5,
            ): _mixed_active_history(MixedCatalogue.PERP_UNKNOWN, recent_volume=Decimal("10")),
        }
        self.cache = MixedCache(self.histories)

    async def history(self, key: CandleKey, *, limit: int = 1000):
        return self.histories.get(key, ())[-limit:]

    async def history_as_of(
        self,
        key: CandleKey,
        *,
        as_of: datetime,
        limit: int = 1000,
    ):
        del key, as_of, limit
        return ()


class MixedMicrostructure:
    async def fetch_order_book(self, symbol: str, *, limit: int):
        del symbol, limit
        raise RuntimeError("test order book unavailable")

    async def fetch_recent_trades(self, symbol: str, *, limit: int):
        del symbol, limit
        raise RuntimeError("test trades unavailable")

    async def aclose(self) -> None:
        return None


def test_scope_all_mixes_spot_known_perpetual_known_and_perpetual_unknown() -> None:
    async def scenario() -> None:
        radar = FilteredStructuredMarketAttentionRadar(
            candle_service=MixedCandles(),  # type: ignore[arg-type]
            catalogue=MixedCatalogue(),  # type: ignore[arg-type]
            microstructure_provider=MixedMicrostructure(),  # type: ignore[arg-type]
            metadata_provider=Metadata(),
            policy=MarketAttentionPolicy(scan_limit=10, candle_limit=420, candidate_limit=10),
            microstructure_policy=MicrostructurePolicy(market_limit_per_refresh=10),
            structure_policy=MarketStructurePolicy(
                history_limit=40,
                min_history_candles=20,
                fetch_concurrency=4,
            ),
        )
        try:
            snapshot = await radar.set_filters(
                MarketAttentionFilters(
                    market_scope=MarketScope.ALL,
                    min_volume_24h_usd=Decimal("100000"),
                ),
                observed_at=NOW,
            )
        finally:
            await radar.aclose()

        assert snapshot.volume_24h_status_counts.AVAILABLE == 2
        assert snapshot.volume_24h_status_counts.UNKNOWN_MISSING_QUOTE_VOLUME == 1
        assert snapshot.volume_24h_status_counts.UNKNOWN_TECHNICAL_ERROR == 0
        assert snapshot.volume_24h_status_counts.UNKNOWN_UNSUPPORTED_MARKET_TYPE == 0
        assert snapshot.candidate_market_count == 2
        assert {item.market.market_type for item in snapshot.shortlist} == {
            MarketType.SPOT,
            MarketType.PERPETUAL,
        }

    asyncio.run(scenario())
