from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import Field, model_validator

from ai_spot_trader.domain.models import (
    AgentToolTrace,
    AggressivenessContext,
    DecisionCandidate,
    DomainModel,
    ExecutionCostContext,
    MarketState,
    PortfolioState,
    StrategicMultiTimeframeContext,
    TradingStyleContext,
    UtcDateTime,
)
from ai_spot_trader.domain.radar_context import RadarAnalyticsStrategicContext
from ai_spot_trader.domain.strategic_thesis import (
    StrategicPositionContext,
    StrategicThesisUpdate,
)

MAX_DECISIONS_PER_CYCLE_HARD_LIMIT = 20
DEFAULT_MAX_DECISIONS_PER_CYCLE = 6


class CycleDecisionPlanInput(DomainModel):
    """Causal multi-market boundary shown once to the single strategic Agent."""

    cycle_id: UUID
    created_at: UtcDateTime
    portfolio_state: PortfolioState
    market_states: Annotated[tuple[MarketState, ...], Field(min_length=1)]
    aggressiveness: Annotated[int, Field(ge=1, le=10)]
    aggressiveness_context: AggressivenessContext | None = None
    trading_style_context: TradingStyleContext | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    execution_cost_context: ExecutionCostContext | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    multi_timeframe_context: StrategicMultiTimeframeContext | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    radar_analytics_context: RadarAnalyticsStrategicContext | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    strategic_position_context: StrategicPositionContext | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    max_decisions_per_cycle: Annotated[
        int, Field(ge=1, le=MAX_DECISIONS_PER_CYCLE_HARD_LIMIT)
    ] = DEFAULT_MAX_DECISIONS_PER_CYCLE
    management_mode: bool = False
    capacity_reason: str | None = None

    @model_validator(mode="after")
    def validate_causal_context(self) -> "CycleDecisionPlanInput":
        if self.portfolio_state.as_of > self.created_at:
            raise ValueError("PortfolioState cannot be newer than CycleDecisionPlanInput")
        ordered = tuple(
            sorted(
                self.market_states,
                key=lambda item: (item.market_type.value, item.symbol),
            )
        )
        if ordered != self.market_states:
            raise ValueError("market_states must use deterministic sorted order")
        keys = tuple((item.symbol, item.market_type) for item in self.market_states)
        if len(set(keys)) != len(keys):
            raise ValueError("market_states must be unique by symbol + market_type")
        if any(item.as_of > self.created_at for item in self.market_states):
            raise ValueError("MarketState cannot be newer than CycleDecisionPlanInput")
        if (
            self.aggressiveness_context is not None
            and self.aggressiveness_context.level != self.aggressiveness
        ):
            raise ValueError("aggressiveness_context level must match aggressiveness")
        if (self.trading_style_context is None) != (self.execution_cost_context is None):
            raise ValueError(
                "trading_style_context and execution_cost_context must be supplied together"
            )
        if self.management_mode and not self.capacity_reason:
            raise ValueError("management_mode requires capacity_reason")
        if not self.management_mode and self.capacity_reason is not None:
            raise ValueError("capacity_reason is reserved for management_mode")
        self._validate_multi_timeframe_context()
        self._validate_radar_analytics_context()
        self._validate_strategic_position_context()
        return self

    def _validate_multi_timeframe_context(self) -> None:
        context = self.multi_timeframe_context
        style = self.trading_style_context
        if context is None:
            return
        if style is None:
            raise ValueError("multi_timeframe_context requires trading_style_context")
        if context.as_of != self.created_at:
            raise ValueError("multi_timeframe_context as_of must match plan input created_at")
        if (
            context.style is not style.style
            or context.style_mapping_version != style.mapping_version
        ):
            raise ValueError("multi_timeframe_context trading style identity mismatch")
        expected = tuple((item.symbol, item.market_type) for item in self.market_states)
        actual = tuple((item.symbol, item.market_type) for item in context.markets)
        if actual != expected:
            raise ValueError("multi_timeframe_context markets must match market_states")
        for market in context.markets:
            if tuple(item.timeframe for item in market.timeframes) != style.preferred_timeframes:
                raise ValueError("multi_timeframe_context timeframes must match trading style")

    def _validate_radar_analytics_context(self) -> None:
        context = self.radar_analytics_context
        if context is None:
            return
        if context.observed_at > self.created_at:
            raise ValueError("radar_analytics_context cannot postdate the plan input")
        allowed = {(item.symbol, item.market_type) for item in self.market_states}
        actual = {(item.symbol, item.market_type) for item in context.markets}
        if not actual.issubset(allowed):
            raise ValueError("radar_analytics_context must remain inside market_states")

    def _validate_strategic_position_context(self) -> None:
        context = self.strategic_position_context
        if context is None:
            return
        if context.as_of > self.created_at:
            raise ValueError("strategic_position_context cannot postdate the plan input")
        allowed = {(item.symbol, item.market_type) for item in self.market_states}
        actual = {(item.symbol, item.market_type) for item in context.positions}
        if not actual.issubset(allowed):
            raise ValueError("strategic_position_context must remain inside market_states")


class CycleDecisionPlan(DomainModel):
    """Ordered strategic plan emitted once by the single Agent for one cycle."""

    cycle_id: UUID
    created_at: UtcDateTime
    decisions: Annotated[tuple[DecisionCandidate, ...], Field(min_length=1)]
    thesis_updates: tuple[StrategicThesisUpdate | None, ...] = ()
    rationale: str | None = None
    tool_traces: tuple[AgentToolTrace, ...] = ()

    @model_validator(mode="after")
    def validate_plan(self) -> "CycleDecisionPlan":
        if len(self.decisions) > MAX_DECISIONS_PER_CYCLE_HARD_LIMIT:
            raise ValueError("decision plan exceeds the hard cycle decision limit")
        if self.thesis_updates and len(self.thesis_updates) != len(self.decisions):
            raise ValueError("thesis_updates must be empty or aligned one-to-one with decisions")
        keys: list[tuple[str, object]] = []
        for decision in self.decisions:
            if decision.cycle_id != self.cycle_id:
                raise ValueError("DecisionCandidate cycle_id must match CycleDecisionPlan")
            if decision.created_at != self.created_at:
                raise ValueError("all plan decisions must share the plan creation timestamp")
            if decision.tool_traces != self.tool_traces:
                raise ValueError("all plan decisions must preserve plan tool traces")
            keys.append((decision.symbol, decision.market_type))
        if len(set(keys)) != len(keys):
            raise ValueError("decision plan cannot contain duplicate symbol + market_type entries")
        call_ids = tuple(trace.call_id for trace in self.tool_traces)
        if len(set(call_ids)) != len(call_ids):
            raise ValueError("decision plan tool traces must have unique call_id values")
        if any(trace.completed_at > self.created_at for trace in self.tool_traces):
            raise ValueError("tool trace data cannot be newer than the decision plan")
        return self


__all__ = [
    "CycleDecisionPlan",
    "CycleDecisionPlanInput",
    "DEFAULT_MAX_DECISIONS_PER_CYCLE",
    "MAX_DECISIONS_PER_CYCLE_HARD_LIMIT",
]
