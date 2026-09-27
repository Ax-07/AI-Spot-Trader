from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_spot_trader.domain.models import AgentInput
from ai_spot_trader.persistence.models import (
    CycleRecord,
    DecisionRecord,
    ExecutionIntentRecord,
    FillRecord,
    PaperRunRecord,
    RiskAssessmentRecord,
)
from ai_spot_trader.persistence.runs import PaperRunClosedError, PaperRunNotFoundError
from ai_spot_trader.trading.engine import TradingCycleResult, TradingCycleStatus
from ai_spot_trader.trading.multi_market import (
    DecisionExecutionResult,
    MultiMarketTradingCycleResult,
)

CycleResult = TradingCycleResult | MultiMarketTradingCycleResult


class CycleAuditConflictError(RuntimeError):
    """Raised when one cycle_id is reused for different canonical facts."""


class SqlAlchemyCycleAuditRepository:
    """Atomically persist one immutable audit graph per business cycle identity."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def ensure_available(self) -> None:
        async with self._sessions() as session:
            await session.execute(select(CycleRecord.cycle_id).limit(1))

    async def ensure_run_available(self, paper_run_id: UUID) -> None:
        async with self._sessions() as session:
            run = await session.get(PaperRunRecord, paper_run_id)
            if run is None:
                raise PaperRunNotFoundError(f"paper run {paper_run_id} does not exist")
            if run.ended_at is not None:
                raise PaperRunClosedError(f"paper run {paper_run_id} is closed")
            await session.execute(select(CycleRecord.cycle_id).limit(1))

    async def ensure_available_for_run(self, paper_run_id: UUID) -> None:
        await self.ensure_run_available(paper_run_id)

    async def record(self, result: CycleResult, *, paper_run_id: UUID | None = None) -> bool:
        digest = _result_digest(result, paper_run_id=paper_run_id)
        async with self._sessions() as session, session.begin():
            run: PaperRunRecord | None = None
            if paper_run_id is not None:
                run = await session.get(PaperRunRecord, paper_run_id)
                if run is None:
                    raise PaperRunNotFoundError(f"paper run {paper_run_id} does not exist")
                if run.ended_at is not None:
                    raise PaperRunClosedError(f"paper run {paper_run_id} is closed")
            existing = await session.get(CycleRecord, result.cycle_id)
            if existing is not None:
                if existing.paper_run_id == paper_run_id and existing.result_digest == digest:
                    return False
                raise CycleAuditConflictError(
                    f"cycle_id {result.cycle_id} already exists with different content"
                )
            self._add_graph(session, result=result, digest=digest, paper_run_id=paper_run_id)
            if run is not None and result.status is TradingCycleStatus.COMPLETED:
                committed = _committed_portfolio_payload(result)
                if committed is None:
                    raise CycleAuditConflictError(
                        "completed cycle has no durable committed portfolio snapshot"
                    )
                run.current_portfolio_payload = committed
        return True

    async def record_for_run(self, paper_run_id: UUID, result: CycleResult) -> bool:
        return await self.record(result, paper_run_id=paper_run_id)

    def _add_graph(
        self,
        session: AsyncSession,
        *,
        result: CycleResult,
        digest: str,
        paper_run_id: UUID | None = None,
    ) -> None:
        trajectories = _decision_trajectories(result)
        multi = isinstance(result, MultiMarketTradingCycleResult)
        singleton = trajectories[0] if len(trajectories) == 1 else None

        if multi:
            plan_input = result.decision_plan_input
            portfolio_before = plan_input.portfolio_state if plan_input is not None else None
            portfolio_after = result.final_portfolio_state
            singleton_agent_payload = (
                _analytics_agent_input_payload(result, singleton)
                if singleton is not None
                else None
            )
            singleton_market = singleton.market_state if singleton is not None else None
        else:
            agent_input = result.agent_input
            portfolio_before = (
                agent_input.portfolio_state
                if agent_input is not None
                else result.market_selection_input.portfolio_state
                if result.market_selection_input is not None
                else None
            )
            portfolio_after = result.portfolio_state_after
            singleton_agent_payload = _model_payload(agent_input)
            singleton_market = agent_input.market_state if agent_input is not None else None

        session.add(
            CycleRecord(
                cycle_id=result.cycle_id,
                paper_run_id=paper_run_id,
                status=result.status.value,
                recorded_at=datetime.now(UTC),
                result_digest=digest,
                failure_stage=result.failure.stage.value if result.failure else None,
                failure_error_type=result.failure.error_type if result.failure else None,
                failure_timed_out=result.failure.timed_out if result.failure else None,
                market_state_id=(
                    singleton_market.market_state_id if singleton_market is not None else None
                ),
                portfolio_state_before_id=(
                    portfolio_before.portfolio_state_id if portfolio_before is not None else None
                ),
                portfolio_state_after_id=(
                    portfolio_after.portfolio_state_id if portfolio_after is not None else None
                ),
                market_as_of=singleton_market.as_of if singleton_market is not None else None,
                portfolio_before_as_of=(
                    portfolio_before.as_of if portfolio_before is not None else None
                ),
                portfolio_after_as_of=(
                    portfolio_after.as_of if portfolio_after is not None else None
                ),
                market_selection_input_payload=_selection_input_payload(result),
                market_selection_payload=(
                    None if multi else _model_payload(result.market_selection)
                ),
                agent_input_payload=singleton_agent_payload,
                agent_tool_traces_payload=_tool_trace_payload(result),
                portfolio_after_payload=_model_payload(portfolio_after),
                decision_plan_input_payload=(
                    _model_payload(result.decision_plan_input) if multi else None
                ),
                decision_plan_payload=(
                    _model_payload(result.decision_plan) if multi else None
                ),
            )
        )

        if multi:
            for trajectory in trajectories:
                self._add_trajectory(session, result=result, trajectory=trajectory)
            return

        if result.decision is not None:
            decision = result.decision
            session.add(
                DecisionRecord(
                    decision_id=decision.decision_id,
                    cycle_id=decision.cycle_id,
                    decision_index=0,
                    created_at=decision.created_at,
                    action=decision.action.value,
                    symbol=decision.symbol,
                    payload=decision.model_dump(mode="json"),
                    agent_input_payload=_model_payload(result.agent_input),
                    portfolio_after_payload=_model_payload(result.portfolio_state_after),
                )
            )
        if result.risk_assessment is not None:
            assessment = result.risk_assessment
            session.add(
                RiskAssessmentRecord(
                    risk_assessment_id=assessment.risk_assessment_id,
                    cycle_id=assessment.cycle_id,
                    decision_id=assessment.decision_id,
                    assessed_at=assessment.assessed_at,
                    status=assessment.status.value,
                    payload=assessment.model_dump(mode="json"),
                )
            )
        if result.execution_intent is not None:
            intent = result.execution_intent
            session.add(
                ExecutionIntentRecord(
                    execution_id=intent.execution_id,
                    cycle_id=intent.cycle_id,
                    decision_id=intent.decision_id,
                    risk_assessment_id=intent.risk_assessment_id,
                    created_at=intent.created_at,
                    action=intent.action.value,
                    symbol=intent.symbol,
                    payload=intent.model_dump(mode="json"),
                )
            )
        for fill in result.fills:
            session.add(_fill_record(fill))

    def _add_trajectory(
        self,
        session: AsyncSession,
        *,
        result: MultiMarketTradingCycleResult,
        trajectory: DecisionExecutionResult,
    ) -> None:
        decision = trajectory.decision
        session.add(
            DecisionRecord(
                decision_id=decision.decision_id,
                cycle_id=decision.cycle_id,
                decision_index=trajectory.decision_index,
                created_at=decision.created_at,
                action=decision.action.value,
                symbol=decision.symbol,
                payload=decision.model_dump(mode="json"),
                agent_input_payload=_analytics_agent_input_payload(result, trajectory),
                portfolio_after_payload=_model_payload(trajectory.portfolio_state_after),
            )
        )
        assessment = trajectory.risk_assessment
        if assessment is not None:
            session.add(
                RiskAssessmentRecord(
                    risk_assessment_id=assessment.risk_assessment_id,
                    cycle_id=assessment.cycle_id,
                    decision_id=assessment.decision_id,
                    assessed_at=assessment.assessed_at,
                    status=assessment.status.value,
                    payload=assessment.model_dump(mode="json"),
                )
            )
        intent = trajectory.execution_intent
        if intent is not None:
            session.add(
                ExecutionIntentRecord(
                    execution_id=intent.execution_id,
                    cycle_id=intent.cycle_id,
                    decision_id=intent.decision_id,
                    risk_assessment_id=intent.risk_assessment_id,
                    created_at=intent.created_at,
                    action=intent.action.value,
                    symbol=intent.symbol,
                    payload=intent.model_dump(mode="json"),
                )
            )
        for fill in trajectory.fills:
            session.add(_fill_record(fill))


def _fill_record(fill: Any) -> FillRecord:
    return FillRecord(
        fill_id=fill.fill_id,
        execution_id=fill.execution_id,
        market_state_id=fill.market_state_id,
        filled_at=fill.filled_at,
        payload=fill.model_dump(mode="json"),
    )


def _decision_trajectories(result: CycleResult) -> tuple[DecisionExecutionResult, ...]:
    if isinstance(result, MultiMarketTradingCycleResult):
        return result.decision_results
    return ()


def _analytics_agent_input_payload(
    result: MultiMarketTradingCycleResult,
    trajectory: DecisionExecutionResult,
) -> dict[str, object] | None:
    plan_input = result.decision_plan_input
    if plan_input is None:
        return None
    created_at = max(
        plan_input.created_at,
        trajectory.market_state.as_of,
        trajectory.portfolio_state_before.as_of,
    )
    value = AgentInput(
        cycle_id=result.cycle_id,
        created_at=created_at,
        market_state=trajectory.market_state,
        portfolio_state=trajectory.portfolio_state_before,
        aggressiveness=plan_input.aggressiveness,
        aggressiveness_context=plan_input.aggressiveness_context,
        trading_style_context=plan_input.trading_style_context,
        execution_cost_context=plan_input.execution_cost_context,
    )
    return _model_payload(value)


def _committed_portfolio_payload(result: CycleResult) -> dict[str, object] | None:
    if isinstance(result, MultiMarketTradingCycleResult):
        return _model_payload(result.final_portfolio_state)
    if result.portfolio_state_after is not None:
        return _model_payload(result.portfolio_state_after)
    if result.agent_input is not None:
        return _model_payload(result.agent_input.portfolio_state)
    return None


def _model_payload(model: Any | None) -> dict[str, object] | None:
    if model is None:
        return None
    return dict(model.model_dump(mode="json"))


def _capacity_payload(result: CycleResult) -> dict[str, object] | None:
    assessment = result.capacity_assessment
    return None if assessment is None else assessment.to_payload()


def _selection_input_payload(result: CycleResult) -> dict[str, object] | None:
    payload = _model_payload(result.market_selection_input)
    capacity = _capacity_payload(result)
    if payload is None and capacity is None:
        return None
    merged = {} if payload is None else payload
    assessment = result.capacity_assessment
    if assessment is not None:
        merged["capacity_context"] = assessment.to_payload()
        if assessment.mode == "MANAGEMENT" and payload is not None:
            merged["executable_markets"] = [
                market.model_dump(mode="json")
                for market in assessment.management_markets
            ]
    return merged


def _tool_trace_payload(result: CycleResult) -> list[dict[str, object]]:
    return [dict(trace.model_dump(mode="json")) for trace in result.agent_tool_traces]


def _result_digest(result: CycleResult, *, paper_run_id: UUID | None) -> str:
    payload: dict[str, object] = {
        "cycle_id": str(result.cycle_id),
        "status": result.status.value,
        "failure": (
            {
                "stage": result.failure.stage.value,
                "error_type": result.failure.error_type,
                "timed_out": result.failure.timed_out,
            }
            if result.failure is not None
            else None
        ),
        "market_selection_input": _model_payload(result.market_selection_input),
        "agent_tool_traces": _tool_trace_payload(result),
    }
    if isinstance(result, MultiMarketTradingCycleResult):
        payload.update(
            {
                "decision_plan_input": _model_payload(result.decision_plan_input),
                "decision_plan": _model_payload(result.decision_plan),
                "decision_results": [
                    {
                        "decision_index": item.decision_index,
                        "decision": _model_payload(item.decision),
                        "market_state": _model_payload(item.market_state),
                        "portfolio_state_before": _model_payload(item.portfolio_state_before),
                        "risk_assessment": _model_payload(item.risk_assessment),
                        "execution_intent": _model_payload(item.execution_intent),
                        "fills": [_model_payload(fill) for fill in item.fills],
                        "portfolio_state_after": _model_payload(item.portfolio_state_after),
                    }
                    for item in result.decision_results
                ],
                "final_portfolio_state": _model_payload(result.final_portfolio_state),
            }
        )
    else:
        payload.update(
            {
                "market_selection": _model_payload(result.market_selection),
                "agent_input": _model_payload(result.agent_input),
                "decision": _model_payload(result.decision),
                "risk_assessment": _model_payload(result.risk_assessment),
                "execution_intent": _model_payload(result.execution_intent),
                "fills": [_model_payload(fill) for fill in result.fills],
                "portfolio_state_after": _model_payload(result.portfolio_state_after),
            }
        )
    capacity = _capacity_payload(result)
    if capacity is not None:
        payload["capacity_assessment"] = capacity
    if paper_run_id is not None:
        payload["paper_run_id"] = str(paper_run_id)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
