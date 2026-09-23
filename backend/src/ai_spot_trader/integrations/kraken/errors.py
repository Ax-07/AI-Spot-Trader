class KrakenMarketDataError(RuntimeError):
    """Base error raised by the public Kraken market-data integration."""


class KrakenConnectionError(KrakenMarketDataError):
    """Kraken public API connection or transport failure."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class KrakenTransientError(KrakenConnectionError):
    """Retryable public Kraken transport failure for a read-only operation."""


class KrakenTimeoutError(KrakenTransientError, TimeoutError):
    """Retryable Kraken timeout, including an HTTP 408 response."""


class KrakenNetworkError(KrakenTransientError):
    """Retryable Kraken DNS/connectivity/transport failure."""


class KrakenRateLimitError(KrakenTransientError):
    """Retryable Kraken HTTP 429 response."""


class KrakenServerError(KrakenTransientError):
    """Retryable Kraken HTTP 5xx response."""


class KrakenHTTPError(KrakenConnectionError):
    """Permanent Kraken HTTP failure that must not be retried automatically."""


class KrakenPayloadError(KrakenMarketDataError):
    """Kraken returned a payload that cannot be safely normalized."""


class UnknownKrakenSymbolError(KrakenMarketDataError):
    """Requested symbol is not present in the discovered Kraken Spot pairs."""


class StaleMarketDataError(KrakenMarketDataError):
    """Received market data is older than the configured technical freshness limit."""
