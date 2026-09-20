"""Public Kraken Spot market-data integration."""

from ai_spot_trader.integrations.kraken.errors import (
    KrakenConnectionError,
    KrakenMarketDataError,
    KrakenPayloadError,
    StaleMarketDataError,
    UnknownKrakenSymbolError,
)
from ai_spot_trader.integrations.kraken.market_data import (
    KrakenMarketDataSource,
    build_kraken_market_data_source,
)

__all__ = [
    "KrakenConnectionError",
    "KrakenMarketDataError",
    "KrakenMarketDataSource",
    "KrakenPayloadError",
    "StaleMarketDataError",
    "UnknownKrakenSymbolError",
    "build_kraken_market_data_source",
]
