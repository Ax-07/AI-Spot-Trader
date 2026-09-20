class MarketStateError(ValueError):
    """Base error raised while constructing deterministic market state."""


class EmptyMarketHistoryError(MarketStateError):
    """No observation exists at or before the requested snapshot time."""


class OutOfOrderObservationError(MarketStateError):
    """An observation timestamp is older than the latest retained observation."""


class DuplicateObservationError(MarketStateError):
    """Two observations for one builder use the same timestamp."""


class SymbolMismatchError(MarketStateError):
    """An observation does not match the symbol already owned by a builder."""
