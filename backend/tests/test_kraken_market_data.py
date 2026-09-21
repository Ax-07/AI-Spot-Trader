import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai_spot_trader.domain.models import MarketObservation, MarketState
from ai_spot_trader.domain.ports import MarketDataSource, MarketObservationSource
from ai_spot_trader.integrations.kraken.errors import (
    KrakenConnectionError,
    KrakenPayloadError,
    StaleMarketDataError,
    UnknownKrakenSymbolError,
)
from ai_spot_trader.integrations.kraken.market_data import KrakenMarketDataSource
from ai_spot_trader.integrations.kraken.models import (
    KrakenOhlcCandle,
    KrakenPairMetadata,
    KrakenTicker,
)
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


def candle(closed_minutes: int, price: str) -> KrakenOhlcCandle:
    closed_at = NOW + timedelta(minutes=closed_minutes)
    return KrakenOhlcCandle(
        started_at=closed_at - timedelta(minutes=1),
        closed_at=closed_at,
        close_price=Decimal(price),
    )


HISTORY = tuple(candle(offset, str(50000 + offset)) for offset in range(-31, 0))


@dataclass
class FixedClock:
    current: datetime

    def now(self) -> datetime:
        return self.current


class SequenceClock:
    def __init__(self, values: list[datetime]) -> None:
        self._values = values

    def now(self) -> datetime:
        if len(self._values) > 1:
            return self._values.pop(0)
        return self._values[0]


class FakeRestClient:
    def __init__(
        self,
        *,
        history: tuple[KrakenOhlcCandle, ...] = HISTORY,
        history_error: Exception | None = None,
    ) -> None:
        self.fetch_count = 0
        self.closed = False
        self.history = history
        self.history_error = history_error
        self.history_calls: list[tuple[str, int, datetime]] = []

    async def fetch_pair_registry(self) -> KrakenPairRegistry:
        self.fetch_count += 1
        return REGISTRY

    async def fetch_ohlc_history(
        self,
        symbol: str,
        *,
        interval_minutes: int,
        since: datetime,
    ) -> tuple[KrakenOhlcCandle, ...]:
        self.history_calls.append((symbol, interval_minutes, since))
        if self.history_error is not None:
            raise self.history_error
        return self.history

    async def aclose(self) -> None:
        self.closed = True


class FakeTickerClient:
    def __init__(self, ticker: KrakenTicker) -> None:
        self.ticker = ticker
        self.requested: list[str] = []

    async def first_ticker(self, symbol: str) -> KrakenTicker:
        self.requested.append(symbol)
        return self.ticker


class SequenceTickerClient:
    def __init__(self, tickers: list[KrakenTicker]) -> None:
        self.tickers = tickers
        self.requested: list[str] = []

    async def first_ticker(self, symbol: str) -> KrakenTicker:
        self.requested.append(symbol)
        return self.tickers.pop(0)


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
    assert rest.history_calls == []


def test_snapshot_builds_canonical_multi_horizon_context_from_history_and_ticker() -> None:
    rest = FakeRestClient()
    source = KrakenMarketDataSource(
        rest,
        FakeTickerClient(KrakenTicker("BTC/EUR", Decimal("50000.10"), NOW)),
        clock=FixedClock(NOW),
        stale_after=timedelta(seconds=10),
        registry=REGISTRY,
    )

    market_state = asyncio.run(source.snapshot("BTC/EUR"))

    assert isinstance(market_state, MarketState)
    assert market_state.symbol == "BTC/EUR"
    assert market_state.last_price == Decimal("50000.10")
    assert market_state.as_of == NOW
    assert market_state.context is not None
    assert market_state.context.last_observed_at == NOW
    assert market_state.context.data_age_seconds == Decimal("0")
    assert market_state.context.stale_after_seconds == Decimal("10")
    assert market_state.context.is_stale is False
    assert [window.horizon_seconds for window in market_state.context.windows] == [
        Decimal("300"),
        Decimal("1800"),
    ]
    assert [window.observation_count for window in market_state.context.windows] == [6, 31]
    assert all(window.is_complete for window in market_state.context.windows)
    assert rest.history_calls == [("BTC/EUR", 1, NOW - timedelta(minutes=32))]


def test_snapshot_with_no_committed_history_has_explicit_partial_context() -> None:
    source = KrakenMarketDataSource(
        FakeRestClient(history=()),
        FakeTickerClient(KrakenTicker("BTC/EUR", Decimal("50000.10"), NOW)),
        clock=FixedClock(NOW),
        registry=REGISTRY,
    )

    market_state = asyncio.run(source.snapshot("BTC/EUR"))

    assert market_state.context is not None
    assert [window.observation_count for window in market_state.context.windows] == [1, 1]
    assert not any(window.is_complete for window in market_state.context.windows)
    assert all(window.return_fraction is None for window in market_state.context.windows)


def test_snapshot_excludes_history_not_strictly_before_current_ticker() -> None:
    history = (
        candle(-2, "49990"),
        candle(0, "99999"),
        candle(1, "100000"),
    )
    source = KrakenMarketDataSource(
        FakeRestClient(history=history),
        FakeTickerClient(KrakenTicker("BTC/EUR", Decimal("50000"), NOW)),
        clock=FixedClock(NOW),
        registry=REGISTRY,
    )

    market_state = asyncio.run(source.snapshot("BTC/EUR"))

    assert market_state.last_price == Decimal("50000")
    assert market_state.context is not None
    five_minute = market_state.context.windows[0]
    assert five_minute.observation_count == 2
    assert five_minute.max_price == Decimal("50000")
    assert five_minute.last_observed_at == NOW


def test_repeated_same_ticker_does_not_create_duplicate_observations() -> None:
    rest = FakeRestClient()
    ticker_client = FakeTickerClient(KrakenTicker("BTC/EUR", Decimal("50000"), NOW))
    source = KrakenMarketDataSource(
        rest,
        ticker_client,
        clock=FixedClock(NOW),
        registry=REGISTRY,
    )

    first = asyncio.run(source.snapshot("BTC/EUR"))
    second = asyncio.run(source.snapshot("BTC/EUR"))

    assert first.context is not None and second.context is not None
    assert [window.observation_count for window in second.context.windows] == [6, 31]
    assert len(rest.history_calls) == 2


def test_ticker_timestamp_cannot_move_backwards_across_snapshots() -> None:
    ticker_client = SequenceTickerClient(
        [
            KrakenTicker("BTC/EUR", Decimal("50000"), NOW),
            KrakenTicker("BTC/EUR", Decimal("49900"), NOW - timedelta(seconds=1)),
        ]
    )
    source = KrakenMarketDataSource(
        FakeRestClient(),
        ticker_client,
        clock=FixedClock(NOW),
        registry=REGISTRY,
    )

    asyncio.run(source.snapshot("BTC/EUR"))
    with pytest.raises(KrakenPayloadError, match="moved backwards"):
        asyncio.run(source.snapshot("BTC/EUR"))


def test_history_provider_error_is_not_downgraded_to_context_none() -> None:
    source = KrakenMarketDataSource(
        FakeRestClient(history_error=KrakenConnectionError("history unavailable")),
        FakeTickerClient(KrakenTicker("BTC/EUR", Decimal("50000"), NOW)),
        clock=FixedClock(NOW),
        registry=REGISTRY,
    )

    with pytest.raises(KrakenConnectionError, match="history unavailable"):
        asyncio.run(source.snapshot("BTC/EUR"))


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


def test_snapshot_rechecks_freshness_after_history_fetch() -> None:
    source = KrakenMarketDataSource(
        FakeRestClient(),
        FakeTickerClient(KrakenTicker("BTC/EUR", Decimal("50000"), NOW)),
        clock=SequenceClock([NOW, NOW + timedelta(seconds=11)]),
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


def test_future_ticker_is_rejected_before_market_state_build() -> None:
    source = KrakenMarketDataSource(
        FakeRestClient(),
        FakeTickerClient(KrakenTicker("BTC/EUR", Decimal("50000"), NOW + timedelta(seconds=1))),
        clock=FixedClock(NOW),
        registry=REGISTRY,
    )

    with pytest.raises(KrakenPayloadError, match="newer than the local snapshot clock"):
        asyncio.run(source.snapshot("BTC/EUR"))


def test_source_close_closes_owned_rest_boundary() -> None:
    rest = FakeRestClient()
    source = KrakenMarketDataSource(
        rest,
        FakeTickerClient(KrakenTicker("BTC/EUR", Decimal("50000"), NOW)),
        registry=REGISTRY,
    )

    asyncio.run(source.aclose())

    assert rest.closed
