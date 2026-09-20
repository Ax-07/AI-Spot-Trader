import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai_spot_trader.domain.models import MarketObservation, MarketState
from ai_spot_trader.domain.ports import MarketDataSource, MarketObservationSource
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


def test_kraken_source_structurally_implements_market_ports() -> None:
    source = KrakenMarketDataSource(
        FakeRestClient(),
        FakeTickerClient(KrakenTicker("BTC/EUR", Decimal("50000"), NOW)),
        registry=REGISTRY,
    )
    state_port: MarketDataSource = source
    observation_port: MarketObservationSource = source
    assert state_port is source
    assert observation_port is source


def test_observation_normalizes_symbol_before_market_layer() -> None:
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

    observation = asyncio.run(source.observation("XBT/EUR"))

    assert isinstance(observation, MarketObservation)
    assert observation.symbol == "BTC/EUR"
    assert observation.last_price == Decimal("50000.10")
    assert observation.observed_at == NOW - timedelta(seconds=2)
    assert ticker_client.requested == ["BTC/EUR"]
    assert rest.fetch_count == 1


def test_snapshot_preserves_compatible_minimal_market_state() -> None:
    source = KrakenMarketDataSource(
        FakeRestClient(),
        FakeTickerClient(KrakenTicker("BTC/EUR", Decimal("50000.10"), NOW)),
        registry=REGISTRY,
    )

    market_state = asyncio.run(source.snapshot("BTC/EUR"))

    assert isinstance(market_state, MarketState)
    assert market_state.symbol == "BTC/EUR"
    assert market_state.last_price == Decimal("50000.10")
    assert market_state.as_of == NOW
    assert market_state.context is None


def test_pair_registry_is_cached_after_first_observation() -> None:
    rest = FakeRestClient()
    ticker_client = FakeTickerClient(KrakenTicker("BTC/EUR", Decimal("50000"), NOW))
    source = KrakenMarketDataSource(rest, ticker_client)

    asyncio.run(source.observation("BTC/EUR"))
    asyncio.run(source.observation("XBTEUR"))

    assert rest.fetch_count == 1


def test_unknown_symbol_is_rejected_before_websocket_subscription() -> None:
    ticker_client = FakeTickerClient(KrakenTicker("BTC/EUR", Decimal("50000"), NOW))
    source = KrakenMarketDataSource(FakeRestClient(), ticker_client, registry=REGISTRY)

    with pytest.raises(UnknownKrakenSymbolError):
        asyncio.run(source.observation("DOGE/NOPE"))
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
        asyncio.run(source.observation("BTC/EUR"))


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
