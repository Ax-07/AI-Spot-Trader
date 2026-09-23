"""Public Kraken Spot and Derivatives market-data integrations."""

from ai_spot_trader.integrations.kraken.derivatives import (
    KrakenDerivativesMarketDataSource,
    KrakenDerivativesPublicClient,
    parse_kraken_derivatives_instruments,
    parse_kraken_derivatives_ticker,
)
from ai_spot_trader.integrations.kraken.errors import (
    KrakenConnectionError,
    KrakenHTTPError,
    KrakenMarketDataError,
    KrakenNetworkError,
    KrakenPayloadError,
    KrakenRateLimitError,
    KrakenServerError,
    KrakenTimeoutError,
    KrakenTransientError,
    StaleMarketDataError,
    UnknownKrakenSymbolError,
)
from ai_spot_trader.integrations.kraken.market_data import (
    KrakenMarketDataSource,
    build_kraken_market_data_source,
)
from ai_spot_trader.integrations.kraken.resilience import (
    RetryingKrakenDerivativesRestSource,
    RetryingKrakenSpotRestSource,
)

__all__ = [
    "KrakenConnectionError",
    "KrakenDerivativesMarketDataSource",
    "KrakenDerivativesPublicClient",
    "KrakenHTTPError",
    "KrakenMarketDataError",
    "KrakenMarketDataSource",
    "KrakenNetworkError",
    "KrakenPayloadError",
    "KrakenRateLimitError",
    "KrakenServerError",
    "KrakenTimeoutError",
    "KrakenTransientError",
    "RetryingKrakenDerivativesRestSource",
    "RetryingKrakenSpotRestSource",
    "StaleMarketDataError",
    "UnknownKrakenSymbolError",
    "build_kraken_market_data_source",
    "parse_kraken_derivatives_instruments",
    "parse_kraken_derivatives_ticker",
]
