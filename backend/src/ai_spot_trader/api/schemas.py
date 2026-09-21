from datetime import date, datetime
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
    market_type: Literal["SPOT", "PERPETUAL", "FUTURE"] = "SPOT"
    context: JsonObject | None = None
    derivative: JsonObject | None = None


class AssetBalanceResponse(ApiModel):
    asset: str
    available: Decimal = Field(ge=0)


class AssetPositionResponse(ApiModel):
    asset: str
    quantity: Decimal = Field(ge=0)
    available: Decimal = Field(ge=0)


class DerivativePositionResponse(ApiModel):
    symbol: str
    side: Literal["LONG", "SHORT"]
    quantity: Decimal = Field(gt=0)
    average_entry_price: Decimal = Field(gt=0)
    mark_price: Decimal = Field(gt=0)
    contract_size: Decimal = Field(gt=0)
    notional: Decimal = Field(gt=0)
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    leverage: Decimal = Field(ge=1)
    margin_used: Decimal = Field(gt=0)
    initial_margin_rate: Decimal = Field(gt=0, le=1)
    maintenance_margin_rate: Decimal = Field(gt=0, le=1)
    maintenance_margin: Decimal = Field(ge=0)
    cumulative_funding: Decimal
    liquidation_price: Decimal | None = Field(default=None, gt=0)
    margin_mode: Literal["ISOLATED", "CROSS"]
    funding_updated_at: datetime | None = None


class PortfolioResponse(ApiModel):
    portfolio_state_id: UUID
    as_of: datetime
    mode: Literal["PAPER"] = "PAPER"
    balances: tuple[AssetBalanceResponse, ...] = ()
    positions: tuple[AssetPositionResponse, ...] = ()
    derivative_positions: tuple[DerivativePositionResponse, ...] = ()


class EngineStatusResponse(ApiModel):
    configured: bool
    status: Literal["RUNNING", "STOPPED", "UNAVAILABLE"]
    last_cycle_id: UUID | None = None
    last_cycle_status: str | None = None
    last_cycle_failure: CycleFailureResponse | None = None
    last_unexpected_error_type: str | None = None


class PaperAnalyticsPointResponse(ApiModel):
    cycle_id: UUID
    at: datetime
    status: str
    action: str | None = None
    risk_status: str | None = None
    symbol: str
    reference_price: Decimal = Field(gt=0)
    equity: Decimal = Field(ge=0)
    gross_pnl: Decimal
    net_pnl: Decimal
    cumulative_fees: Decimal = Field(ge=0)
    cumulative_spread_cost: Decimal = Field(ge=0)
    cumulative_slippage_cost: Decimal = Field(ge=0)
    cumulative_funding_pnl: Decimal
    exposure_value: Decimal = Field(ge=0)
    exposure_fraction: Decimal | None = Field(default=None, ge=0)
    cumulative_return_fraction: Decimal | None = None
    drawdown_value: Decimal = Field(ge=0)
    drawdown_fraction: Decimal | None = Field(default=None, ge=0)
    trade_count: int = Field(ge=0)


class PaperDailyPerformanceResponse(ApiModel):
    day: date
    closing_at: datetime
    closing_equity: Decimal = Field(ge=0)
    gross_pnl: Decimal
    net_pnl: Decimal
    daily_net_pnl: Decimal
    daily_return_fraction: Decimal | None = None
    cumulative_return_fraction: Decimal | None = None
    fees: Decimal = Field(ge=0)
    spread_cost: Decimal = Field(ge=0)
    slippage_cost: Decimal = Field(ge=0)
    funding_pnl: Decimal
    trade_count: int = Field(ge=0)


class PaperAnalyticsSummaryResponse(ApiModel):
    initial_equity: Decimal | None = Field(default=None, ge=0)
    ending_equity: Decimal | None = Field(default=None, ge=0)
    gross_pnl: Decimal
    net_pnl: Decimal
    fees: Decimal = Field(ge=0)
    spread_cost: Decimal = Field(ge=0)
    slippage_cost: Decimal = Field(ge=0)
    funding_pnl: Decimal
    max_drawdown_value: Decimal = Field(ge=0)
    max_drawdown_fraction: Decimal | None = Field(default=None, ge=0)
    current_drawdown_value: Decimal = Field(ge=0)
    current_drawdown_fraction: Decimal | None = Field(default=None, ge=0)
    current_exposure_value: Decimal = Field(ge=0)
    current_exposure_fraction: Decimal | None = Field(default=None, ge=0)
    trade_count: int = Field(ge=0)
    buy_trade_count: int = Field(ge=0)
    sell_trade_count: int = Field(ge=0)
    hold_count: int = Field(ge=0)
    reject_count: int = Field(ge=0)
    modify_count: int = Field(ge=0)
    completed_cycle_count: int = Field(ge=0)
    failed_cycle_count: int = Field(ge=0)
    valued_cycle_count: int = Field(ge=0)
    first_at: datetime | None = None
    last_at: datetime | None = None


class PaperAnalyticsResponse(ApiModel):
    calculation_version: str
    timezone: Literal["UTC"]
    source_digest: str = Field(min_length=64, max_length=64)
    summary: PaperAnalyticsSummaryResponse
    points: tuple[PaperAnalyticsPointResponse, ...] = ()
    daily: tuple[PaperDailyPerformanceResponse, ...] = ()
