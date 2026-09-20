import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai_spot_trader.domain.models import MarketState
from ai_spot_trader.domain.ports import MarketDataSource
from ai_spot_trader.integrations.kraken.errors import StaleMarketDataError, UnknownKrakenSymbolError
from ai_spot_trader.integrations.kraken.market_data import KrakenMarketDataSource
from ai_spot_trader.integrations.kraken.models import KrakenPairMetadata, KrakenTicker
from ai_spot_trader.integrations.kraken.symbols import KrakenPairRegistry

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
REGISTRY = KrakenPairRegistry(
    (
        KrakenPairMetadata(
            symbol="BTC/EUR",
            altname="XBTEUR",
            wsname="XBT/EUR",
            status="ONLINE",
        ),
    )
)


@dataclass
class FixedClock:
    current: datetime

    def now(self) -> datetime:
        return self.current


class FakeRestClient:
    def __init__(self) -> None:
        self.fetch_count = 0
        self.closed = False

    async def fetch_pair_registry(self) -> KrakenPairRegistry:
        self.fetch_count += 1
        return REGISTRY

    async def aclose(self) -> None:
        self.closed = True


class FakeTickerClient:
    def __init__(self, ticker: KrakenTicker) -> None:
        self.ticker = ticker
        self.requested: list[str] = []

    async def first_ticker(self, symbol: str) -> KrakenTicker:
        self.requested.append(symbol)
        return self.ticker


def test_kraken_source_structurally_implements_market_data_port() -> None:
    source = KrakenMarketDataSource(
        FakeRestClient(),
        FakeTickerClient(KrakenTicker("BTC/EUR", Decimal("50000"), NOW)),
        registry=REGISTRY,
    )
    port: MarketDataSource = source
    assert port is source


def test_snapshot_normalizes_symbol_and_produces_minimal_market_state() -> None:
    rest = FakeRestClient()
    ticker_client = FakeTickerClient(
        KrakenTicker("BTC/EUR", Decimal("50000.10"), NOW - timedelta(seconds=2))
    )
    source = KrakenMarketDataSource(
        rest,
        ticker_client,
        clock=FixedClock(NOW),
        stale_after=timedelta(seconds=5),
    )

    market_state = asyncio.run(source.snapshot("XBT/EUR"))

    assert isinstance(market_state, MarketState)
    assert market_state.symbol == "BTC/EUR"
    assert market_state.last_price == Decimal("50000.10")
    assert market_state.as_of == NOW - timedelta(seconds=2)
    assert market_state.as_of.tzinfo is UTC
    assert ticker_client.requested == ["BTC/EUR"]
    assert rest.fetch_count == 1


def test_pair_registry_is_cached_after_first_snapshot() -> None:
    rest = FakeRestClient()
    ticker_client = FakeTickerClient(KrakenTicker("BTC/EUR", Decimal("50000"), NOW))
    source = KrakenMarketDataSource(rest, ticker_client)

    asyncio.run(source.snapshot("BTC/EUR"))
    asyncio.run(source.snapshot("XBTEUR"))

    assert rest.fetch_count == 1


def test_unknown_symbol_is_rejected_before_websocket_subscription() -> None:
    ticker_client = FakeTickerClient(KrakenTicker("BTC/EUR", Decimal("50000"), NOW))
    source = KrakenMarketDataSource(FakeRestClient(), ticker_client, registry=REGISTRY)

    with pytest.raises(UnknownKrakenSymbolError):
        asyncio.run(source.snapshot("DOGE/NOPE"))
    assert ticker_client.requested == []


def test_stale_ticker_is_rejected_with_injectable_clock() -> None:
    source = KrakenMarketDataSource(
        FakeRestClient(),
        FakeTickerClient(KrakenTicker("BTC/EUR", Decimal("50000"), NOW - timedelta(seconds=11))),
        clock=FixedClock(NOW),
        stale_after=timedelta(seconds=10),
        registry=REGISTRY,
    )

    with pytest.raises(StaleMarketDataError):
        asyncio.run(source.snapshot("BTC/EUR"))


def test_freshness_guard_can_remain_unconfigured() -> None:
    source = KrakenMarketDataSource(
        FakeRestClient(),
        FakeTickerClient(KrakenTicker("BTC/EUR", Decimal("50000"), NOW - timedelta(days=1))),
        clock=FixedClock(NOW),
        stale_after=None,
        registry=REGISTRY,
    )

    assert not source.is_stale(NOW - timedelta(days=1))


def test_source_close_closes_owned_rest_boundary() -> None:
    rest = FakeRestClient()
    source = KrakenMarketDataSource(
        rest,
        FakeTickerClient(KrakenTicker("BTC/EUR", Decimal("50000"), NOW)),
        registry=REGISTRY,
    )

    asyncio.run(source.aclose())

    assert rest.closed
