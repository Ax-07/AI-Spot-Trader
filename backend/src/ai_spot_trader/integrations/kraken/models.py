from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class KrakenPairMetadata:
    """Provider-local representation of the pair identifiers needed for normalization."""

    symbol: str
    altname: str | None
    wsname: str | None
    status: str | None


@dataclass(frozen=True, slots=True)
class KrakenTicker:
    """Normalized subset of a Kraken WebSocket v2 ticker message."""

    symbol: str
    last_price: Decimal
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class KrakenOhlcCandle:
    """Committed Kraken Spot OHLC close with explicit causal availability time."""

    started_at: datetime
    closed_at: datetime
    close_price: Decimal
