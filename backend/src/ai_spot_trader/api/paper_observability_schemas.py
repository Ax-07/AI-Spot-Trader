from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field

from ai_spot_trader.api.schemas import ApiModel


class PaperObservabilityBreakdownResponse(ApiModel):
    scope: Literal["TOTAL", "SPOT", "PERPETUAL"]
    gross_pnl: Decimal | None = None
    net_pnl: Decimal | None = None
    realized_pnl: Decimal
    unrealized_pnl: Decimal | None = None
    fees: Decimal = Field(ge=0)
    spread_cost: Decimal = Field(ge=0)
    slippage_cost: Decimal = Field(ge=0)
    funding_pnl: Decimal
    execution_costs: Decimal = Field(ge=0)
    total_costs: Decimal
    total_notional: Decimal = Field(ge=0)
    trade_count: int = Field(ge=0)
    fill_count: int = Field(ge=0)
    current_exposure_value: Decimal | None = Field(default=None, ge=0)
    current_exposure_fraction: Decimal | None = Field(default=None, ge=0)


class PaperDecisionFunnelResponse(ApiModel):
    decision_count: int = Field(ge=0)
    buy_count: int = Field(ge=0)
    sell_count: int = Field(ge=0)
    hold_count: int = Field(ge=0)
    risk_allow_count: int = Field(ge=0)
    risk_modify_count: int = Field(ge=0)
    risk_reject_count: int = Field(ge=0)
    execution_intent_count: int = Field(ge=0)
    decisions_with_fill: int = Field(ge=0)
    decisions_without_fill: int = Field(ge=0)
    fill_count: int = Field(ge=0)
    economic_trade_count: int = Field(ge=0)


class PaperMarketObservabilityResponse(ApiModel):
    symbol: str
    market_type: Literal["SPOT", "PERPETUAL", "FUTURE"]
    decision_count: int = Field(ge=0)
    buy_count: int = Field(ge=0)
    sell_count: int = Field(ge=0)
    hold_count: int = Field(ge=0)
    risk_allow_count: int = Field(ge=0)
    risk_modify_count: int = Field(ge=0)
    risk_reject_count: int = Field(ge=0)
    decisions_with_fill: int = Field(ge=0)
    decisions_without_fill: int = Field(ge=0)
    trade_count: int = Field(ge=0)
    fill_count: int = Field(ge=0)
    total_notional: Decimal = Field(ge=0)
    fees: Decimal = Field(ge=0)
    spread_cost: Decimal = Field(ge=0)
    slippage_cost: Decimal = Field(ge=0)
    funding_pnl: Decimal | None = None
    execution_costs: Decimal = Field(ge=0)
    total_costs: Decimal | None = None
    realized_pnl: Decimal
    current_exposure_value: Decimal | None = Field(default=None, ge=0)
    current_exposure_fraction: Decimal | None = Field(default=None, ge=0)
    unrealized_pnl: Decimal | None = None


class PaperObservabilityResponse(ApiModel):
    calculation_version: str
    timezone: Literal["UTC"]
    source_digest: str = Field(min_length=64, max_length=64)
    breakdowns: tuple[PaperObservabilityBreakdownResponse, ...]
    funnel: PaperDecisionFunnelResponse
    markets: tuple[PaperMarketObservabilityResponse, ...]
    unavailable_metrics: tuple[str, ...] = ()
