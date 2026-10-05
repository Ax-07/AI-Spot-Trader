from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from ai_spot_trader.api.schemas import ApiModel

StrategicThesisStatusValue = Literal[
    "NEW", "CONFIRMED", "WEAKENING", "INVALIDATED", "COMPLETED"
]
MarketTypeValue = Literal["SPOT", "PERPETUAL"]
PositionSideValue = Literal["LONG", "SHORT"]
MemoryStateValue = Literal["ACTIVE", "UNAVAILABLE_LEGACY"]
OriginValue = Literal["AGENT_OPENING", "LEGACY_ADOPTION"]
RevisionStateValue = Literal[
    "ACTIVE_COMMITTED",
    "RETIRED_COMMITTED",
    "PROPOSED_NOT_ACTIVATED",
    "FAILED_CYCLE",
    "UNAVAILABLE_LEGACY",
]


class StrategicThesisReviewResponse(ApiModel):
    reviewed_at: datetime
    status: StrategicThesisStatusValue
    summary: str


class StrategicThesisPositionResponse(ApiModel):
    thesis_id: UUID | None = None
    symbol: str
    market_type: MarketTypeValue
    side: PositionSideValue
    quantity: Decimal = Field(gt=0)
    memory_state: MemoryStateValue
    origin: OriginValue | None = None
    status: StrategicThesisStatusValue | None = None
    created_at: datetime | None = None
    activated_at: datetime | None = None
    updated_at: datetime | None = None
    horizon: str | None = None
    thesis_summary: str | None = None
    supporting_facts: tuple[str, ...] = ()
    invalidation_conditions: tuple[str, ...] = ()
    last_review: StrategicThesisReviewResponse | None = None


class StrategicThesisRevisionResponse(ApiModel):
    cycle_id: UUID
    paper_run_id: UUID | None = None
    decision_index: int = Field(ge=0)
    decision_id: UUID | None = None
    thesis_id: UUID | None = None
    reviewed_at: datetime
    symbol: str
    market_type: MarketTypeValue
    side: PositionSideValue | None = None
    status: StrategicThesisStatusValue
    horizon: str
    thesis_summary: str
    review_summary: str
    supporting_facts: tuple[str, ...] = ()
    invalidation_conditions: tuple[str, ...] = ()
    agent_action: Literal["BUY", "SELL", "HOLD"]
    risk_status: Literal["ALLOW", "MODIFY", "REJECT"] | None = None
    fill_count: int = Field(ge=0)
    cycle_status: str
    active_after_cycle: bool | None = None
    revision_state: RevisionStateValue


class StrategicThesisObservabilityResponse(ApiModel):
    paper_run_id: UUID
    lineage_paper_run_ids: tuple[UUID, ...]
    calculation_version: str
    timezone: Literal["UTC"]
    as_of: datetime | None = None
    positions: tuple[StrategicThesisPositionResponse, ...] = ()
    revisions: tuple[StrategicThesisRevisionResponse, ...] = ()
    total_revision_count: int = Field(ge=0)
    history_limit: int = Field(ge=0, le=200)


__all__ = [
    "StrategicThesisObservabilityResponse",
    "StrategicThesisPositionResponse",
    "StrategicThesisRevisionResponse",
    "StrategicThesisReviewResponse",
]
