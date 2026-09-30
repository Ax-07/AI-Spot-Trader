from enum import StrEnum


class KrakenPayloadStage(StrEnum):
    """Bounded, payload-free stage identifier safe for aggregate diagnostics."""

    ASSET_PAIRS_PAYLOAD = "ASSET_PAIRS_PAYLOAD"
    ASSET_PAIRS_ENTRY = "ASSET_PAIRS_ENTRY"
    ASSET_PAIRS_SYMBOL = "ASSET_PAIRS_SYMBOL"
    OHLC_RESULT = "OHLC_RESULT"
    OHLC_SERIES = "OHLC_SERIES"
    OHLC_PAIR_KEY = "OHLC_PAIR_KEY"
    OHLC_ROW = "OHLC_ROW"
    OHLC_TIMESTAMP = "OHLC_TIMESTAMP"
    OHLC_NUMERIC = "OHLC_NUMERIC"


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
    """Retryable Kraken rate-limit/throttling response."""


class KrakenServerError(KrakenTransientError):
    """Retryable Kraken HTTP 5xx response."""


class KrakenHTTPError(KrakenConnectionError):
    """Permanent Kraken HTTP failure that must not be retried automatically."""


class KrakenPayloadError(KrakenMarketDataError):
    """Kraken returned a payload that cannot be safely normalized."""

    def __init__(
        self,
        message: str,
        *,
        stage: KrakenPayloadStage | None = None,
    ) -> None:
        super().__init__(message)
        if stage is None:
            self.stage: KrakenPayloadStage | None = None
        else:
            try:
                self.stage = stage if isinstance(stage, KrakenPayloadStage) else KrakenPayloadStage(stage)
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid Kraken payload diagnostic stage") from exc


class KrakenAPIError(KrakenPayloadError):
    """Kraken returned a valid public-API envelope containing a provider error."""


class UnknownKrakenSymbolError(KrakenMarketDataError):
    """Requested symbol is not present in the discovered Kraken Spot pairs."""


class StaleMarketDataError(KrakenMarketDataError):
    """Received market data is older than the configured technical freshness limit."""
