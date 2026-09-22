from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_spot_trader.core.clock import Clock, SystemClock
from ai_spot_trader.domain.enums import DerivativeContractKind, MarketType
from ai_spot_trader.domain.models import (
    DerivativeMarketContext,
    MarketContext,
    MarketState,
    UtcDateTime,
)
from ai_spot_trader.domain.symbols import parse_canonical_symbol


class MarketResearchError(RuntimeError):
    """Base error for provider-agnostic read-only market research."""


class MarketResearchValidationError(MarketResearchError):
    """Raised when a research request violates the bounded public contract."""


class MarketResearchDataError(MarketResearchError):
    """Raised when a provider result cannot satisfy the normalized contract."""


class _ResearchModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class MarketResearchMarket(_ResearchModel):
    """Factual provider-normalized market metadata with no strategic score or ranking."""

    symbol: str = Field(min_length=1, max_length=64)
    market_type: MarketType
    venue_symbol: str = Field(min_length=1, max_length=128)
    status: str | None = Field(default=None, max_length=64)
    contract_kind: DerivativeContractKind | None = None
    underlying_asset: str | None = Field(default=None, max_length=64)
    quote_asset: str | None = Field(default=None, max_length=64)
    expires_at: UtcDateTime | None = None

    @model_validator(mode="after")
    def validate_market_metadata(self) -> "MarketResearchMarket":
        base_asset, quote_asset = parse_canonical_symbol(self.symbol)
        if self.market_type is MarketType.SPOT:
            if self.contract_kind is not None or self.expires_at is not None:
                raise ValueError("SPOT market metadata cannot carry derivative contract fields")
            if self.underlying_asset not in (None, base_asset):
                raise ValueError("SPOT underlying_asset must match the canonical base asset")
            if self.quote_asset not in (None, quote_asset):
                raise ValueError("SPOT quote_asset must match the canonical quote asset")
        return self


class MarketResearchPage(_ResearchModel):
    """Deterministically sorted and paginated factual market catalogue."""

    as_of: UtcDateTime
    cursor: int = Field(ge=0)
    limit: int = Field(gt=0)
    total_available: int = Field(ge=0)
    next_cursor: int | None = Field(default=None, ge=0)
    markets: tuple[MarketResearchMarket, ...] = ()


class MarketResearchSnapshot(_ResearchModel):
    """Compact normalized market facts visible to the strategic Agent."""

    symbol: str = Field(min_length=1, max_length=64)
    market_type: MarketType
    as_of: UtcDateTime
    last_price: Decimal = Field(gt=0)
    context: MarketContext | None = None
    derivative: DerivativeMarketContext | None = None

    @model_validator(mode="after")
    def validate_snapshot(self) -> "MarketResearchSnapshot":
        parse_canonical_symbol(self.symbol)
        if self.context is not None and self.context.last_observed_at > self.as_of:
            raise ValueError("market research context cannot be newer than the snapshot")
        if self.market_type is MarketType.SPOT:
            if self.derivative is not None:
                raise ValueError("SPOT research snapshots cannot carry derivative context")
            return self
        if self.derivative is None:
            raise ValueError("derivative research snapshots require derivative context")
        if self.derivative.observed_at > self.as_of:
            raise ValueError("derivative research observation cannot be newer than snapshot")
        return self


class MarketResearchBackend(Protocol):
    """Provider-specific public-data adapter hidden behind the Agent/chat boundary."""

    async def list_markets(
        self,
        market_type: MarketType | None,
    ) -> tuple[MarketResearchMarket, ...]: ...

    async def snapshot(self, symbol: str, market_type: MarketType) -> MarketState: ...


class MarketResearchService:
    """Canonical bounded read-only market research service."""

    def __init__(
        self,
        backend: MarketResearchBackend,
        *,
        max_list_limit: int,
        clock: Clock | None = None,
    ) -> None:
        if isinstance(max_list_limit, bool) or max_list_limit <= 0:
            raise ValueError("max_list_limit must be a positive integer")
        self._backend = backend
        self._max_list_limit = max_list_limit
        self._clock = clock or SystemClock()

    @property
    def max_list_limit(self) -> int:
        return self._max_list_limit

    async def list_markets(
        self,
        *,
        market_type: MarketType | None,
        cursor: int,
        limit: int,
    ) -> MarketResearchPage:
        if isinstance(cursor, bool) or cursor < 0:
            raise MarketResearchValidationError("cursor must be a non-negative integer")
        if isinstance(limit, bool) or limit <= 0 or limit > self._max_list_limit:
            raise MarketResearchValidationError(
                f"limit must be between 1 and {self._max_list_limit}"
            )

        discovered = await self._backend.list_markets(market_type)
        ordered = tuple(
            sorted(
                discovered,
                key=lambda item: (
                    item.market_type.value,
                    item.symbol,
                    item.venue_symbol,
                ),
            )
        )
        page = ordered[cursor : cursor + limit]
        next_cursor_value = cursor + len(page)
        next_cursor = next_cursor_value if next_cursor_value < len(ordered) else None
        return MarketResearchPage(
            as_of=self._now(),
            cursor=cursor,
            limit=limit,
            total_available=len(ordered),
            next_cursor=next_cursor,
            markets=page,
        )

    async def get_market_snapshot(
        self,
        *,
        symbol: str,
        market_type: MarketType,
    ) -> MarketResearchSnapshot:
        try:
            parse_canonical_symbol(symbol)
        except ValueError as exc:
            raise MarketResearchValidationError("symbol must use canonical BASE/QUOTE") from exc

        state = await self._backend.snapshot(symbol, market_type)
        if state.symbol != symbol:
            raise MarketResearchDataError("provider snapshot symbol mismatch")
        if state.market_type is not market_type:
            raise MarketResearchDataError("provider snapshot market_type mismatch")
        if state.as_of > self._now():
            raise MarketResearchDataError("provider snapshot cannot be newer than local clock")
        return MarketResearchSnapshot(
            symbol=state.symbol,
            market_type=state.market_type,
            as_of=state.as_of,
            last_price=state.last_price,
            context=state.context,
            derivative=state.derivative,
        )

    def _now(self) -> datetime:
        value = self._clock.now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise MarketResearchDataError("market research clock must be timezone-aware")
        return value.astimezone(UTC)
