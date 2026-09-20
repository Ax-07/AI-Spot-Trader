from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from ai_spot_trader.domain.enums import ExecutionMode, RiskDecision, TradingAction

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PositiveDecimal = Annotated[Decimal, Field(gt=0)]
NonNegativeDecimal = Annotated[Decimal, Field(ge=0)]


def _normalize_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


UtcDateTime = Annotated[AwareDatetime, AfterValidator(_normalize_utc)]


class DomainModel(BaseModel):
    """Base configuration shared by domain boundary contracts."""

    model_config = ConfigDict(extra="forbid", strict=True)


class AssetBalance(DomainModel):
    """Available amount for one portfolio asset."""

    asset: NonEmptyText
    available: NonNegativeDecimal


class AssetPosition(DomainModel):
    """Held and currently available quantity for one asset."""

    asset: NonEmptyText
    quantity: NonNegativeDecimal
    available: NonNegativeDecimal

    @model_validator(mode="after")
    def available_cannot_exceed_quantity(self) -> "AssetPosition":
        if self.available > self.quantity:
            raise ValueError("available quantity cannot exceed held quantity")
        return self


class MarketState(DomainModel):
    """Minimal deterministic market snapshot exposed to downstream components."""

    market_state_id: UUID
    as_of: UtcDateTime
    symbol: NonEmptyText
    last_price: PositiveDecimal


class PortfolioState(DomainModel):
    """Minimal canonical PAPER portfolio snapshot."""

    portfolio_state_id: UUID
    as_of: UtcDateTime
    mode: ExecutionMode = ExecutionMode.PAPER
    balances: tuple[AssetBalance, ...] = ()
    positions: tuple[AssetPosition, ...] = ()


class AgentInput(DomainModel):
    """Structured input boundary for the single strategic trading agent."""

    cycle_id: UUID
    created_at: UtcDateTime
    market_state: MarketState
    portfolio_state: PortfolioState
    aggressiveness: Annotated[int, Field(ge=1, le=10)]


class DecisionCandidate(DomainModel):
    """Validated strategic decision candidate before deterministic risk review."""

    decision_id: UUID
    cycle_id: UUID
    created_at: UtcDateTime
    action: TradingAction
    symbol: NonEmptyText
    rationale: str | None = None


class RiskAssessment(DomainModel):
    """Auditable outcome produced by the deterministic Risk Engine."""

    risk_assessment_id: UUID
    cycle_id: UUID
    decision_id: UUID
    assessed_at: UtcDateTime
    status: RiskDecision
    reasons: tuple[str, ...] = ()


class ExecutionIntent(DomainModel):
    """Risk-approved PAPER execution request for BUY or SELL only."""

    execution_id: UUID
    cycle_id: UUID
    decision_id: UUID
    risk_assessment_id: UUID
    created_at: UtcDateTime
    mode: ExecutionMode = ExecutionMode.PAPER
    action: TradingAction
    symbol: NonEmptyText
    quantity: PositiveDecimal

    @model_validator(mode="after")
    def hold_is_not_executable(self) -> "ExecutionIntent":
        if self.action is TradingAction.HOLD:
            raise ValueError("HOLD does not create an execution intent")
        return self


class Fill(DomainModel):
    """Minimal fact describing a simulated PAPER fill."""

    fill_id: UUID
    execution_id: UUID
    filled_at: UtcDateTime
    action: TradingAction
    symbol: NonEmptyText
    quantity: PositiveDecimal
    price: PositiveDecimal

    @model_validator(mode="after")
    def hold_cannot_fill(self) -> "Fill":
        if self.action is TradingAction.HOLD:
            raise ValueError("HOLD cannot produce a fill")
        return self
