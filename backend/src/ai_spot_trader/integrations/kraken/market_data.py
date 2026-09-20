from datetime import datetime, timedelta
from typing import Protocol
from uuid import uuid4

from ai_spot_trader.core.clock import Clock, SystemClock
from ai_spot_trader.core.config import Settings
from ai_spot_trader.domain.models import MarketObservation, MarketState
from ai_spot_trader.integrations.kraken.errors import KrakenPayloadError, StaleMarketDataError
from ai_spot_trader.integrations.kraken.models import KrakenTicker
from ai_spot_trader.integrations.kraken.rest import KrakenPublicRestClient
from ai_spot_trader.integrations.kraken.symbols import KrakenPairRegistry
from ai_spot_trader.integrations.kraken.websocket import KrakenTickerWebSocketClient


class PairRegistrySource(Protocol):
    async def fetch_pair_registry(self) -> KrakenPairRegistry: ...

    async def aclose(self) -> None: ...


class TickerSource(Protocol):
    async def first_ticker(self, symbol: str) -> KrakenTicker: ...


class KrakenMarketDataSource:
    """Kraken public Spot source exposing normalized observations and snapshots."""

    def __init__(
        self,
        rest_client: PairRegistrySource,
        websocket_client: TickerSource,
        *,
        clock: Clock | None = None,
        stale_after: timedelta | None = None,
        registry: KrakenPairRegistry | None = None,
    ) -> None:
        self._rest_client = rest_client
        self._websocket_client = websocket_client
        self._clock = clock or SystemClock()
        self._stale_after = stale_after
        self._registry = registry

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
        return MarketState(
            market_state_id=uuid4(),
            as_of=observation.observed_at,
            symbol=observation.symbol,
            last_price=observation.last_price,
        )

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


def build_kraken_market_data_source(
    settings: Settings,
    *,
    clock: Clock | None = None,
) -> KrakenMarketDataSource:
    stale_after = (
        timedelta(seconds=settings.kraken_stale_after_seconds)
        if settings.kraken_stale_after_seconds is not None
        else None
    )
    return KrakenMarketDataSource(
        KrakenPublicRestClient(
            settings.kraken_rest_url,
            timeout_seconds=settings.kraken_rest_timeout_seconds,
        ),
        KrakenTickerWebSocketClient(
            settings.kraken_ws_url,
            max_reconnect_attempts=settings.kraken_ws_max_reconnect_attempts,
            reconnect_delay_seconds=settings.kraken_ws_reconnect_delay_seconds,
            receive_timeout_seconds=settings.kraken_ws_receive_timeout_seconds,
        ),
        clock=clock,
        stale_after=stale_after,
    )
