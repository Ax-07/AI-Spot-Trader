from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from ai_spot_trader.domain.enums import MarketType, PositionSide
from ai_spot_trader.domain.models import (
    DomainModel,
    MarketState,
    PortfolioState,
    UtcDateTime,
)
from ai_spot_trader.domain.symbols import parse_canonical_symbol

MAX_ACTIVE_STRATEGIC_POSITIONS = 20
MAX_SUPPORTING_FACTS = 6
MAX_INVALIDATION_CONDITIONS = 6

CompactText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]
ThesisSummaryText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1200),
]
ReviewSummaryText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=800),
]
HorizonText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=64),
]


class StrategicThesisStatus(StrEnum):
    NEW = "NEW"
    CONFIRMED = "CONFIRMED"
    WEAKENING = "WEAKENING"
    INVALIDATED = "INVALIDATED"
    COMPLETED = "COMPLETED"


class StrategicThesisOrigin(StrEnum):
    AGENT_OPENING = "AGENT_OPENING"
    LEGACY_ADOPTION = "LEGACY_ADOPTION"


class StrategicPositionMemoryState(StrEnum):
    ACTIVE = "ACTIVE"
    UNAVAILABLE_LEGACY = "UNAVAILABLE_LEGACY"


class StrategicThesisUpdate(DomainModel):
    """Bounded strategic thesis proposal/review emitted by the same trading Agent."""

    status: StrategicThesisStatus
    horizon: HorizonText
    thesis_summary: ThesisSummaryText
    supporting_facts: Annotated[
        tuple[CompactText, ...], Field(max_length=MAX_SUPPORTING_FACTS)
    ] = ()
    invalidation_conditions: Annotated[
        tuple[CompactText, ...], Field(max_length=MAX_INVALIDATION_CONDITIONS)
    ] = ()
    review_summary: ReviewSummaryText

    @model_validator(mode="after")
    def validate_bounded_lists(self) -> "StrategicThesisUpdate":
        if len(set(self.supporting_facts)) != len(self.supporting_facts):
            raise ValueError("supporting_facts must not contain duplicates")
        if len(set(self.invalidation_conditions)) != len(self.invalidation_conditions):
            raise ValueError("invalidation_conditions must not contain duplicates")
        return self


class StrategicThesisReview(DomainModel):
    reviewed_at: UtcDateTime
    status: StrategicThesisStatus
    summary: ReviewSummaryText


class ActiveStrategicThesis(DomainModel):
    """Current durable strategic memory for one actually open economic exposure."""

    thesis_id: UUID
    symbol: CompactText
    market_type: MarketType
    side: PositionSide
    origin: StrategicThesisOrigin
    created_at: UtcDateTime
    activated_at: UtcDateTime | None = None
    horizon: HorizonText
    thesis_summary: ThesisSummaryText
    supporting_facts: Annotated[
        tuple[CompactText, ...], Field(max_length=MAX_SUPPORTING_FACTS)
    ] = ()
    invalidation_conditions: Annotated[
        tuple[CompactText, ...], Field(max_length=MAX_INVALIDATION_CONDITIONS)
    ] = ()
    status: StrategicThesisStatus
    last_review: StrategicThesisReview
    updated_at: UtcDateTime

    @model_validator(mode="after")
    def validate_thesis_identity_and_time(self) -> "ActiveStrategicThesis":
        if self.market_type not in {MarketType.SPOT, MarketType.PERPETUAL}:
            raise ValueError("strategic thesis supports SPOT and PERPETUAL only")
        if self.market_type is MarketType.SPOT and self.side is not PositionSide.LONG:
            raise ValueError("SPOT strategic thesis must be LONG")
        if self.updated_at < self.created_at:
            raise ValueError("strategic thesis updated_at cannot precede created_at")
        if self.activated_at is not None and self.activated_at < self.created_at:
            raise ValueError("strategic thesis activated_at cannot precede created_at")
        if self.last_review.reviewed_at < self.created_at:
            raise ValueError("strategic thesis review cannot precede created_at")
        if self.last_review.reviewed_at > self.updated_at:
            raise ValueError("strategic thesis review cannot postdate updated_at")
        if self.last_review.status is not self.status:
            raise ValueError("strategic thesis last_review status must match current status")
        return self


class StrategicPositionContextEntry(DomainModel):
    symbol: CompactText
    market_type: MarketType
    side: PositionSide
    quantity: Annotated[Decimal, Field(gt=0)]
    memory_state: StrategicPositionMemoryState
    thesis: ActiveStrategicThesis | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def validate_memory_state(self) -> "StrategicPositionContextEntry":
        if self.market_type is MarketType.SPOT and self.side is not PositionSide.LONG:
            raise ValueError("SPOT strategic position context must be LONG")
        if self.memory_state is StrategicPositionMemoryState.ACTIVE:
            if self.thesis is None:
                raise ValueError("ACTIVE strategic position context requires a thesis")
            if (
                self.thesis.symbol != self.symbol
                or self.thesis.market_type is not self.market_type
                or self.thesis.side is not self.side
            ):
                raise ValueError("strategic thesis identity must match its position context")
        elif self.thesis is not None:
            raise ValueError("legacy unavailable position context cannot fabricate a thesis")
        return self


class StrategicPositionContext(DomainModel):
    """Compact causal thesis context for only the open positions visible to this cycle."""

    as_of: UtcDateTime
    positions: Annotated[
        tuple[StrategicPositionContextEntry, ...],
        Field(max_length=MAX_ACTIVE_STRATEGIC_POSITIONS),
    ] = ()

    @model_validator(mode="after")
    def validate_context(self) -> "StrategicPositionContext":
        expected = tuple(
            sorted(
                self.positions,
                key=lambda item: (item.market_type.value, item.symbol, item.side.value),
            )
        )
        if expected != self.positions:
            raise ValueError("strategic position context must use deterministic sorted order")
        keys = tuple(
            (item.symbol, item.market_type, item.side) for item in self.positions
        )
        if len(set(keys)) != len(keys):
            raise ValueError("strategic position context contains duplicate exposure identities")
        for item in self.positions:
            thesis = item.thesis
            if thesis is None:
                continue
            if thesis.created_at > self.as_of or thesis.updated_at > self.as_of:
                raise ValueError("strategic thesis cannot postdate its cycle context")
            if thesis.activated_at is not None and thesis.activated_at > self.as_of:
                raise ValueError("strategic thesis activation cannot postdate its cycle context")
            if thesis.last_review.reviewed_at > self.as_of:
                raise ValueError("strategic thesis review cannot postdate its cycle context")
        return self


def active_thesis_key(
    thesis: ActiveStrategicThesis,
) -> tuple[str, MarketType, PositionSide]:
    return thesis.symbol, thesis.market_type, thesis.side


def build_strategic_position_context(
    *,
    portfolio_state: PortfolioState,
    market_states: tuple[MarketState, ...],
    active_theses: tuple[ActiveStrategicThesis, ...],
    as_of: UtcDateTime,
) -> StrategicPositionContext:
    """Project durable thesis state onto current economic positions without inventing history."""

    if portfolio_state.as_of > as_of:
        raise ValueError("portfolio state cannot postdate strategic position context")
    thesis_by_key = {active_thesis_key(item): item for item in active_theses}
    if len(thesis_by_key) != len(active_theses):
        raise ValueError("active strategic thesis snapshot contains duplicate identities")

    entries: list[StrategicPositionContextEntry] = []
    for market in market_states:
        exposure = _exposure_for_market(portfolio_state, market)
        if exposure is None:
            continue
        side, quantity = exposure
        thesis = thesis_by_key.get((market.symbol, market.market_type, side))
        entries.append(
            StrategicPositionContextEntry(
                symbol=market.symbol,
                market_type=market.market_type,
                side=side,
                quantity=quantity,
                memory_state=(
                    StrategicPositionMemoryState.ACTIVE
                    if thesis is not None
                    else StrategicPositionMemoryState.UNAVAILABLE_LEGACY
                ),
                thesis=thesis,
            )
        )

    return StrategicPositionContext(
        as_of=as_of,
        positions=tuple(
            sorted(
                entries,
                key=lambda item: (item.market_type.value, item.symbol, item.side.value),
            )
        ),
    )


def _exposure_for_market(
    portfolio_state: PortfolioState,
    market_state: MarketState,
) -> tuple[PositionSide, Decimal] | None:
    if market_state.market_type is MarketType.SPOT:
        base_asset, _quote_asset = parse_canonical_symbol(market_state.symbol)
        position = next(
            (
                item
                for item in portfolio_state.positions
                if item.asset == base_asset and item.quantity > 0
            ),
            None,
        )
        if position is None:
            return None
        return PositionSide.LONG, position.quantity

    if market_state.market_type is MarketType.PERPETUAL:
        position = next(
            (
                item
                for item in portfolio_state.derivative_positions
                if item.symbol == market_state.symbol and item.quantity > 0
            ),
            None,
        )
        if position is None:
            return None
        return position.side, position.quantity

    return None


__all__ = [
    "ActiveStrategicThesis",
    "StrategicPositionContext",
    "StrategicPositionContextEntry",
    "StrategicPositionMemoryState",
    "StrategicThesisOrigin",
    "StrategicThesisReview",
    "StrategicThesisStatus",
    "StrategicThesisUpdate",
    "active_thesis_key",
    "build_strategic_position_context",
]
