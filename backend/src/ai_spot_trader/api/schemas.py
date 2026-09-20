from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

JsonObject = dict[str, object]


class ApiModel(BaseModel):
    """Strict response contract owned by the HTTP boundary."""

    model_config = ConfigDict(extra="forbid")


class CycleFailureResponse(ApiModel):
    stage: str
    error_type: str
    timed_out: bool


class CycleSummaryResponse(ApiModel):
    cycle_id: UUID
    status: str
    recorded_at: datetime
    decision_action: str | None = None
    symbol: str | None = None
    risk_status: str | None = None
    execution_id: UUID | None = None
    fill_count: int = Field(ge=0)
    failure: CycleFailureResponse | None = None


class FillResponse(ApiModel):
    fill_id: UUID
    execution_id: UUID
    market_state_id: UUID
    filled_at: datetime
    payload: JsonObject


class CycleDetailResponse(ApiModel):
    cycle_id: UUID
    status: str
    recorded_at: datetime
    failure: CycleFailureResponse | None = None
    market_state_id: UUID | None = None
    portfolio_state_before_id: UUID | None = None
    portfolio_state_after_id: UUID | None = None
    market_as_of: datetime | None = None
    portfolio_before_as_of: datetime | None = None
    portfolio_after_as_of: datetime | None = None
    agent_input: JsonObject | None = None
    decision: JsonObject | None = None
    risk_assessment: JsonObject | None = None
    execution_intent: JsonObject | None = None
    fills: tuple[FillResponse, ...] = ()
    portfolio_state_after: JsonObject | None = None


class DecisionResponse(ApiModel):
    decision_id: UUID
    cycle_id: UUID
    created_at: datetime
    action: str
    symbol: str
    payload: JsonObject


class RiskAssessmentResponse(ApiModel):
    risk_assessment_id: UUID
    cycle_id: UUID
    decision_id: UUID
    assessed_at: datetime
    status: str
    payload: JsonObject


class ExecutionResponse(ApiModel):
    execution_id: UUID
    cycle_id: UUID
    decision_id: UUID
    risk_assessment_id: UUID
    created_at: datetime
    action: str
    symbol: str
    payload: JsonObject
    fills: tuple[FillResponse, ...] = ()


class CyclePageResponse(ApiModel):
    items: tuple[CycleSummaryResponse, ...]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class DecisionPageResponse(ApiModel):
    items: tuple[DecisionResponse, ...]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class RiskAssessmentPageResponse(ApiModel):
    items: tuple[RiskAssessmentResponse, ...]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class ExecutionPageResponse(ApiModel):
    items: tuple[ExecutionResponse, ...]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class LatestErrorResponse(ApiModel):
    cycle_id: UUID
    recorded_at: datetime
    failure: CycleFailureResponse


class MarketStateResponse(ApiModel):
    market_state_id: UUID
    as_of: datetime
    symbol: str
    last_price: Decimal = Field(gt=0)
    context: JsonObject | None = None


class AssetBalanceResponse(ApiModel):
    asset: str
    available: Decimal = Field(ge=0)


class AssetPositionResponse(ApiModel):
    asset: str
    quantity: Decimal = Field(ge=0)
    available: Decimal = Field(ge=0)


class PortfolioResponse(ApiModel):
    portfolio_state_id: UUID
    as_of: datetime
    mode: Literal["PAPER"] = "PAPER"
    balances: tuple[AssetBalanceResponse, ...] = ()
    positions: tuple[AssetPositionResponse, ...] = ()


class EngineStatusResponse(ApiModel):
    configured: bool
    status: Literal["RUNNING", "STOPPED", "UNAVAILABLE"]
    last_cycle_id: UUID | None = None
    last_cycle_status: str | None = None
    last_cycle_failure: CycleFailureResponse | None = None
    last_unexpected_error_type: str | None = None
