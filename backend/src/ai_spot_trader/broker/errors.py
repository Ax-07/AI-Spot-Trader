class PaperBrokerError(Exception):
    """Base PAPER broker error."""


class InvalidPaperCostModelError(PaperBrokerError, ValueError):
    """Raised when execution-cost configuration is invalid."""


class InvalidCanonicalSymbolError(PaperBrokerError, ValueError):
    """Raised when a canonical BASE/QUOTE symbol cannot be parsed."""


class PricingContextError(PaperBrokerError):
    """Raised when the supplied canonical pricing context is unusable."""


class PricingSymbolMismatchError(PricingContextError):
    """Raised when the intent and MarketState refer to different symbols."""


class FuturePricingContextError(PricingContextError):
    """Raised when pricing would use information newer than the execution intent."""


class InvalidExecutionTimeError(PaperBrokerError):
    """Raised when the execution clock precedes the already-created intent."""
