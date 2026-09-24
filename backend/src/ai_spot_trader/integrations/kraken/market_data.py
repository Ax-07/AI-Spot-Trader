from datetime import datetime, timedelta
from typing import Protocol

from ai_spot_trader.core.clock import Clock, SystemClock
from ai_spot_trader.core.config import Settings
from ai_spot_trader.domain.models import MarketObservation, MarketState
from ai_spot_trader.integrations.kraken.errors import KrakenPayloadError, StaleMarketDataError
from ai_spot_trader.integrations.kraken.models import KrakenOhlcCandle, KrakenTicker
from ai_spot_trader.integrations.kraken.resilience import RetryingKrakenSpotRestSource
from ai_spot_trader.integrations.kraken.rest import KrakenPublicRestClient
from ai_spot_trader.integrations.kraken.symbols import KrakenPairRegistry
from ai_spot_trader.integrations.kraken.websocket import KrakenTickerWebSocketClient
from ai_spot_trader.market import DEFAULT_MARKET_HORIZONS, MarketStateBuilder

KRAKEN_HISTORY_INTERVAL_MINUTES = 1
_HISTORY_INTERVAL = timedelta(minutes=KRAKEN_HISTORY_INTERVAL_MINUTES)
_HISTORY_PADDING_INTERVALS = 2


class KrakenRestSource(Protocol):
    async def fetch_pair_registry(self) -> KrakenPairRegistry: ...

    async def fetch_ohlc_history(
        self,
        symbol: str,
        *,
        interval_minutes: int,
        since: datetime,
    ) -> tuple[KrakenOhlcCandle, ...]: ...

    async def aclose(self) -> None: ...


class TickerSource(Protocol):
    async def first_ticker(self, symbol: str) -> KrakenTicker: ...


class SpotMarketSink(Protocol):
    """Optional PAPER ledger hook for causal SPOT valuation after a valid snapshot."""

    def mark_spot_market(self, market_state: MarketState) -> None: ...


class KrakenMarketDataSource:
    """Kraken public Spot source exposing normalized observations and rich snapshots."""

    def __init__(
        self,
        rest_client: KrakenRestSource,
        websocket_client: TickerSource,
        *,
        clock: Clock | None = None,
        stale_after: timedelta | None = None,
        registry: KrakenPairRegistry | None = None,
        market_sink: SpotMarketSink | None = None,
    ) -> None:
        self._rest_client = rest_client
        self._websocket_client = websocket_client
        self._clock = clock or SystemClock()
        self._stale_after = stale_after
        self._registry = registry
        self._market_sink = market_sink
        self._builders: dict[str, MarketStateBuilder] = {}
        self._latest_current_observations: dict[str, MarketObservation] = {}

    async def observation(self, symbol: str) -> MarketObservation:
        registry = await self._pair_registry()
        canonical_symbol = registry.normalize(symbol)
        ticker = await self._websocket_client.first_ticker(canonical_symbol)
        normalized_ticker_symbol = registry.normalize(ticker.symbol)
        if normalized_ticker_symbol != canonical_symbol:
            raise KrakenPayloadError("Kraken ticker symbol did not match the requested market")
        if self.is_stale(ticker.timestamp):
            raise StaleMarketDataError(f"Kraken market data is stale for {canonical_symbol}")

        return MarketObservation(
            observed_at=ticker.timestamp,
            symbol=canonical_symbol,
            last_price=ticker.last_price,
        )

    async def snapshot(self, symbol: str) -> MarketState:
        observation = await self.observation(symbol)
        self._validate_current_sequence(observation)

        builder = self._builders.get(observation.symbol)
        if builder is None:
            builder = MarketStateBuilder(
                horizons=DEFAULT_MARKET_HORIZONS,
                stale_after=self._stale_after,
                clock=self._clock,
            )
            self._builders[observation.symbol] = builder

        history = await self._rest_client.fetch_ohlc_history(
            observation.symbol,
            interval_minutes=KRAKEN_HISTORY_INTERVAL_MINUTES,
            since=observation.observed_at
            - max(DEFAULT_MARKET_HORIZONS)
            - (_HISTORY_INTERVAL * _HISTORY_PADDING_INTERVALS),
        )

        snapshot_at = self._clock.now()
        if observation.observed_at > snapshot_at:
            raise KrakenPayloadError(
                "Kraken ticker timestamp is newer than the local snapshot clock"
            )
        if (
            self._stale_after is not None
            and snapshot_at - observation.observed_at > self._stale_after
        ):
            raise StaleMarketDataError(
                f"Kraken market data is stale for {observation.symbol}"
            )

        self._append_history(
            builder,
            symbol=observation.symbol,
            history=history,
            before=observation.observed_at,
        )
        retained = builder.retained_observations
        statistics_as_of = retained[-1].observed_at if retained else snapshot_at
        market_state = builder.build(
            as_of=snapshot_at,
            current_observation=observation,
            statistics_as_of=statistics_as_of,
        )
        self._latest_current_observations[observation.symbol] = observation
        if self._market_sink is not None:
            self._market_sink.mark_spot_market(market_state)
        return market_state

    def is_stale(self, as_of: datetime) -> bool:
        if self._stale_after is None:
            return False
        return self._clock.now() - as_of > self._stale_after

    async def refresh_pairs(self) -> KrakenPairRegistry:
        self._registry = await self._rest_client.fetch_pair_registry()
        return self._registry

    async def aclose(self) -> None:
        await self._rest_client.aclose()

    async def _pair_registry(self) -> KrakenPairRegistry:
        if self._registry is None:
            return await self.refresh_pairs()
        return self._registry

    def _append_history(
        self,
        builder: MarketStateBuilder,
        *,
        symbol: str,
        history: tuple[KrakenOhlcCandle, ...],
        before: datetime,
    ) -> None:
        for candle in history:
            if candle.closed_at >= before:
                continue
            latest = builder.retained_observations[-1] if builder.retained_observations else None
            if latest is not None and candle.closed_at <= latest.observed_at:
                continue
            builder.add_observation(
                MarketObservation(
                    observed_at=candle.closed_at,
                    symbol=symbol,
                    last_price=candle.close_price,
                )
            )

    def _validate_current_sequence(self, observation: MarketObservation) -> None:
        previous = self._latest_current_observations.get(observation.symbol)
        if previous is None:
            return
        if observation.observed_at < previous.observed_at:
            raise KrakenPayloadError("Kraken ticker timestamp moved backwards")
        if (
            observation.observed_at == previous.observed_at
            and observation.last_price != previous.last_price
        ):
            raise KrakenPayloadError("Kraken ticker conflicts with previous current observation")


def build_kraken_market_data_source(
    settings: Settings,
    *,
    clock: Clock | None = None,
    market_sink: SpotMarketSink | None = None,
) -> KrakenMarketDataSource:
    stale_after = (
        timedelta(seconds=settings.kraken_stale_after_seconds)
        if settings.kraken_stale_after_seconds is not None
        else None
    )
    return KrakenMarketDataSource(
        RetryingKrakenSpotRestSource(
            KrakenPublicRestClient(
                settings.kraken_rest_url,
                timeout_seconds=settings.kraken_rest_timeout_seconds,
            )
        ),
        KrakenTickerWebSocketClient(
            settings.kraken_ws_url,
            max_reconnect_attempts=settings.kraken_ws_max_reconnect_attempts,
            reconnect_delay_seconds=settings.kraken_ws_reconnect_delay_seconds,
            receive_timeout_seconds=settings.kraken_ws_receive_timeout_seconds,
        ),
        clock=clock,
        stale_after=stale_after,
        market_sink=market_sink,
    )
