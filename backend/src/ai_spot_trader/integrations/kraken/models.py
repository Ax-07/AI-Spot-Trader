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


@dataclass(frozen=True, slots=True)
class KrakenOhlcvCandle:
    """Full Kraken Spot OHLCV candle used by the cockpit candle pipeline."""

    started_at: datetime
    closed_at: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal
    is_final: bool
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class KrakenOhlcUpdate:
    """Full Kraken Spot WebSocket v2 OHLC update for the current/finalized candle."""

    symbol: str
    interval_minutes: int
    started_at: datetime
    closed_at: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal
    is_final: bool
    updated_at: datetime
