import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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

    async def record(self, result: TradingCycleResult, *, paper_run_id: UUID | None = None) -> bool:
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

    async def record_for_run(self, paper_run_id: UUID, result: TradingCycleResult) -> bool:
        return await self.record(result, paper_run_id=paper_run_id)

    def _add_graph(
        self,
        session: AsyncSession,
        *,
        result: TradingCycleResult,
        digest: str,
        paper_run_id: UUID | None = None,
    ) -> None:
        agent_input = result.agent_input
        selection_input = result.market_selection_input
        portfolio_before = (
            agent_input.portfolio_state
            if agent_input is not None
            else selection_input.portfolio_state
            if selection_input is not None
            else None
        )
        portfolio_after = result.portfolio_state_after
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
                market_state_id=agent_input.market_state.market_state_id if agent_input else None,
                portfolio_state_before_id=(
                    portfolio_before.portfolio_state_id if portfolio_before is not None else None
                ),
                portfolio_state_after_id=(
                    portfolio_after.portfolio_state_id if portfolio_after is not None else None
                ),
                market_as_of=agent_input.market_state.as_of if agent_input else None,
                portfolio_before_as_of=(
                    portfolio_before.as_of if portfolio_before is not None else None
                ),
                portfolio_after_as_of=(
                    portfolio_after.as_of if portfolio_after is not None else None
                ),
                market_selection_input_payload=_model_payload(selection_input),
                market_selection_payload=_model_payload(result.market_selection),
                agent_input_payload=_model_payload(agent_input),
                agent_tool_traces_payload=_tool_trace_payload(result),
                portfolio_after_payload=_model_payload(portfolio_after),
            )
        )

        if result.decision is not None:
            decision = result.decision
            session.add(
                DecisionRecord(
                    decision_id=decision.decision_id,
                    cycle_id=decision.cycle_id,
                    created_at=decision.created_at,
                    action=decision.action.value,
                    symbol=decision.symbol,
                    payload=decision.model_dump(mode="json"),
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
            session.add(
                FillRecord(
                    fill_id=fill.fill_id,
                    execution_id=fill.execution_id,
                    market_state_id=fill.market_state_id,
                    filled_at=fill.filled_at,
                    payload=fill.model_dump(mode="json"),
                )
            )


def _committed_portfolio_payload(result: TradingCycleResult) -> dict[str, object] | None:
    if result.portfolio_state_after is not None:
        return _model_payload(result.portfolio_state_after)
    if result.agent_input is not None:
        return _model_payload(result.agent_input.portfolio_state)
    return None


def _model_payload(model: Any | None) -> dict[str, object] | None:
    if model is None:
        return None
    return dict(model.model_dump(mode="json"))


def _tool_trace_payload(result: TradingCycleResult) -> list[dict[str, object]]:
    return [dict(trace.model_dump(mode="json")) for trace in result.agent_tool_traces]


def _result_digest(result: TradingCycleResult, *, paper_run_id: UUID | None) -> str:
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
        "market_selection": _model_payload(result.market_selection),
        "agent_input": _model_payload(result.agent_input),
        "agent_tool_traces": _tool_trace_payload(result),
        "decision": _model_payload(result.decision),
        "risk_assessment": _model_payload(result.risk_assessment),
        "execution_intent": _model_payload(result.execution_intent),
        "fills": [_model_payload(fill) for fill in result.fills],
        "portfolio_state_after": _model_payload(result.portfolio_state_after),
    }
    if paper_run_id is not None:
        payload["paper_run_id"] = str(paper_run_id)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
