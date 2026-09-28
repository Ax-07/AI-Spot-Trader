from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from ai_spot_trader.api.schemas import ApiModel, CycleSummaryResponse


class EconomicOperationResponse(ApiModel):
    paper_run_id: UUID | None = None
    cycle_id: UUID
    decision_index: int = Field(ge=0)
    execution_id: UUID
    filled_at: datetime
    symbol: str
    market_type: Literal["SPOT", "PERPETUAL", "FUTURE"]
    action: Literal["BUY", "SELL"]
    economic_effect: str
    quantity: Decimal = Field(gt=0)
    reference_price: Decimal = Field(gt=0)
    price: Decimal = Field(gt=0)
    notional: Decimal = Field(gt=0)
    fee: Decimal = Field(ge=0)
    spread_cost: Decimal = Field(ge=0)
    slippage_cost: Decimal = Field(ge=0)
    funding_pnl: Decimal
    execution_costs: Decimal = Field(ge=0)
    total_costs: Decimal
    realized_pnl: Decimal
    position_before: Decimal
    position_after: Decimal
    fill_count: int = Field(ge=1)
    fill_ids: tuple[UUID, ...]


class EconomicHistorySummaryResponse(ApiModel):
    initial_equity: Decimal | None = Field(default=None, ge=0)
    ending_equity: Decimal | None = Field(default=None, ge=0)
    gross_pnl: Decimal
    net_pnl: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal | None = None
    fees: Decimal = Field(ge=0)
    spread_cost: Decimal = Field(ge=0)
    slippage_cost: Decimal = Field(ge=0)
    funding_pnl: Decimal
    execution_costs: Decimal = Field(ge=0)
    total_costs: Decimal
    max_drawdown_value: Decimal = Field(ge=0)
    max_drawdown_fraction: Decimal | None = Field(default=None, ge=0)
    current_drawdown_value: Decimal = Field(ge=0)
    current_drawdown_fraction: Decimal | None = Field(default=None, ge=0)
    current_exposure_value: Decimal = Field(ge=0)
    current_exposure_fraction: Decimal | None = Field(default=None, ge=0)
    completed_cycle_count: int = Field(ge=0)
    failed_cycle_count: int = Field(ge=0)
    decision_count: int = Field(ge=0)
    buy_decision_count: int = Field(ge=0)
    sell_decision_count: int = Field(ge=0)
    hold_count: int = Field(ge=0)
    reject_count: int = Field(ge=0)
    modify_count: int = Field(ge=0)
    trade_count: int = Field(ge=0)
    buy_trade_count: int = Field(ge=0)
    sell_trade_count: int = Field(ge=0)
    fill_count: int = Field(ge=0)
    total_notional: Decimal = Field(ge=0)
    turnover_fraction: Decimal | None = Field(default=None, ge=0)
    costs_to_notional_fraction: Decimal | None = None
    costs_to_initial_equity_fraction: Decimal | None = None
    duration_hours: Decimal | None = Field(default=None, gt=0)
    fills_per_hour: Decimal | None = Field(default=None, ge=0)
    market_switch_count: int = Field(ge=0)
    market_switches_per_hour: Decimal | None = Field(default=None, ge=0)
    open_count: int = Field(ge=0)
    increase_count: int = Field(ge=0)
    reduce_count: int = Field(ge=0)
    close_count: int = Field(ge=0)
    flip_count: int = Field(ge=0)
    long_effect_count: int = Field(ge=0)
    short_effect_count: int = Field(ge=0)
    first_at: datetime | None = None
    last_at: datetime | None = None


class EconomicHistoryResponse(ApiModel):
    paper_run_id: UUID
    lineage_paper_run_ids: tuple[UUID, ...]
    calculation_version: str
    timezone: Literal["UTC"]
    source_digest: str = Field(min_length=64, max_length=64)
    summary: EconomicHistorySummaryResponse
    operations: tuple[EconomicOperationResponse, ...] = ()
    cycles: tuple[CycleSummaryResponse, ...] = ()
