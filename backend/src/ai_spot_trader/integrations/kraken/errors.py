class KrakenMarketDataError(RuntimeError):
    """Base error raised by the public Kraken market-data integration."""


class KrakenConnectionError(KrakenMarketDataError):
    """Kraken public API connection or transport failure."""


class KrakenPayloadError(KrakenMarketDataError):
    """Kraken returned a payload that cannot be safely normalized."""


class UnknownKrakenSymbolError(KrakenMarketDataError):
    """Requested symbol is not present in the discovered Kraken Spot pairs."""


class StaleMarketDataError(KrakenMarketDataError):
    """Received market data is older than the configured technical freshness limit."""
