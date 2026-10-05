from __future__ import annotations

from typing import cast

from ai_spot_trader.domain.models import AgentToolTrace
from ai_spot_trader.domain.planning import CycleDecisionPlan, CycleDecisionPlanInput
from ai_spot_trader.domain.ports import MultiMarketLLMProvider
from ai_spot_trader.domain.radar_context import (
    RadarAnalyticsStrategicContext,
    restrict_radar_analytics_context,
)


class FrozenRadarContextDecisionProvider:
    """Attach one immutable Radar snapshot to the existing single strategic Agent call."""

    def __init__(
        self,
        delegate: MultiMarketLLMProvider,
        context: RadarAnalyticsStrategicContext,
    ) -> None:
        self._delegate = delegate
        self._context = context

    @property
    def last_tool_traces(self) -> tuple[AgentToolTrace, ...]:
        return cast(
            tuple[AgentToolTrace, ...],
            getattr(self._delegate, "last_tool_traces", ()),
        )

    async def generate_decision_plan(
        self,
        plan_input: CycleDecisionPlanInput,
    ) -> CycleDecisionPlan:
        plan_input.radar_analytics_context = restrict_radar_analytics_context(
            self._context,
            markets=tuple(
                (market.symbol, market.market_type) for market in plan_input.market_states
            ),
        )
        CycleDecisionPlanInput.model_validate(plan_input.model_dump(mode="python"))
        return await self._delegate.generate_decision_plan(plan_input)


__all__ = ["FrozenRadarContextDecisionProvider"]
