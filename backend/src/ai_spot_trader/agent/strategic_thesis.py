from __future__ import annotations

import logging
from typing import Protocol, cast
from uuid import UUID

from ai_spot_trader.agent.llm_audit import current_llm_audit_context, llm_audit_context
from ai_spot_trader.domain.models import AgentToolTrace
from ai_spot_trader.domain.planning import CycleDecisionPlan, CycleDecisionPlanInput
from ai_spot_trader.domain.ports import MultiMarketLLMProvider
from ai_spot_trader.domain.strategic_thesis import StrategicPositionContext

logger = logging.getLogger("ai_spot_trader.agent.planner")


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
        *,
        session_id: UUID | None = None,
    ) -> None:
        self._delegate = delegate
        self._context_source = context_source
        self._session_id = session_id

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
        with llm_audit_context(
            session_id=self._session_id,
            cycle_id=plan_input.cycle_id,
        ):
            plan = await self._delegate.generate_decision_plan(plan_input)
            _log_agent_plan_completed(plan)
            return plan


def _log_agent_plan_completed(plan: CycleDecisionPlan) -> None:
    """Emit safe post-validation action counts without influencing the Agent result."""

    try:
        context = current_llm_audit_context()
        actions = [str(getattr(item.action, "value", item.action)).upper() for item in plan.decisions]
        logger.info(
            "agent_plan_completed session_id=%s cycle_id=%s decisions=%d buy=%d sell=%d hold=%d",
            "-" if context.session_id is None else str(context.session_id),
            str(context.cycle_id or plan.cycle_id),
            len(actions),
            actions.count("BUY"),
            actions.count("SELL"),
            actions.count("HOLD"),
        )
    except Exception:
        # Live observability must never alter, reject or delay a validated strategic plan.
        pass


__all__ = [
    "StrategicPositionContextSource",
    "StrategicThesisContextDecisionProvider",
]
