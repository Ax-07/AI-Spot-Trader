"""Provider-agnostic deterministic market-state construction and execution routing."""

from ai_spot_trader.market.errors import (
    DuplicateObservationError,
    EmptyMarketHistoryError,
    MarketStateError,
    OutOfOrderObservationError,
    SymbolMismatchError,
)
from ai_spot_trader.market.execution import (
    ExecutableMarketError,
    ExecutableMarketSnapshotMismatchError,
    MarketOutsideExecutableUniverseError,
    RoutedExecutableMarketDataSource,
    UnsupportedExecutableMarketError,
)
from ai_spot_trader.market.state import (
    DEFAULT_MARKET_HORIZONS,
    DEFAULT_MAX_OBSERVATIONS,
    MarketStateBuilder,
)

__all__ = [
    "DEFAULT_MARKET_HORIZONS",
    "DEFAULT_MAX_OBSERVATIONS",
    "DuplicateObservationError",
    "EmptyMarketHistoryError",
    "ExecutableMarketError",
    "ExecutableMarketSnapshotMismatchError",
    "MarketOutsideExecutableUniverseError",
    "MarketStateBuilder",
    "MarketStateError",
    "OutOfOrderObservationError",
    "RoutedExecutableMarketDataSource",
    "SymbolMismatchError",
    "UnsupportedExecutableMarketError",
]
