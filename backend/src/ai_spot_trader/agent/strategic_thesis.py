from __future__ import annotations

from typing import Protocol, cast

from ai_spot_trader.domain.models import AgentToolTrace
from ai_spot_trader.domain.planning import CycleDecisionPlan, CycleDecisionPlanInput
from ai_spot_trader.domain.ports import MultiMarketLLMProvider
from ai_spot_trader.domain.strategic_thesis import StrategicPositionContext


class StrategicPositionContextSource(Protocol):
    async def build_context(
        self,
        plan_input: CycleDecisionPlanInput,
    ) -> StrategicPositionContext: ...


class StrategicThesisContextDecisionProvider:
    """Attach durable position-thesis memory to the existing single strategic Agent call."""

    def __init__(
        self,
        delegate: MultiMarketLLMProvider,
        context_source: StrategicPositionContextSource,
    ) -> None:
        self._delegate = delegate
        self._context_source = context_source

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
        plan_input.strategic_position_context = await self._context_source.build_context(
            plan_input
        )
        CycleDecisionPlanInput.model_validate(plan_input.model_dump(mode="python"))
        return await self._delegate.generate_decision_plan(plan_input)


__all__ = [
    "StrategicPositionContextSource",
    "StrategicThesisContextDecisionProvider",
]
