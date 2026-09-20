import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_spot_trader.persistence.models import (
    CycleRecord,
    DecisionRecord,
    ExecutionIntentRecord,
    FillRecord,
    RiskAssessmentRecord,
)
from ai_spot_trader.trading.engine import TradingCycleResult


class CycleAuditConflictError(RuntimeError):
    """Raised when one cycle_id is reused for different canonical facts."""


class SqlAlchemyCycleAuditRepository:
    """Atomically persist one immutable audit graph per business cycle identity."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def record(self, result: TradingCycleResult) -> bool:
        """Persist a cycle once; return False for an exact idempotent replay."""

        digest = _result_digest(result)
        async with self._sessions() as session, session.begin():
            existing = await session.get(CycleRecord, result.cycle_id)
            if existing is not None:
                if existing.result_digest == digest:
                    return False
                raise CycleAuditConflictError(
                    f"cycle_id {result.cycle_id} already exists with different content"
                )
            self._add_graph(session, result=result, digest=digest)
        return True

    def _add_graph(
        self,
        session: AsyncSession,
        *,
        result: TradingCycleResult,
        digest: str,
    ) -> None:
        agent_input = result.agent_input
        portfolio_after = result.portfolio_state_after
        session.add(
            CycleRecord(
                cycle_id=result.cycle_id,
                status=result.status.value,
                recorded_at=datetime.now(UTC),
                result_digest=digest,
                failure_stage=result.failure.stage.value if result.failure else None,
                failure_error_type=result.failure.error_type if result.failure else None,
                failure_timed_out=result.failure.timed_out if result.failure else None,
                market_state_id=(
                    agent_input.market_state.market_state_id if agent_input is not None else None
                ),
                portfolio_state_before_id=(
                    agent_input.portfolio_state.portfolio_state_id
                    if agent_input is not None
                    else None
                ),
                portfolio_state_after_id=(
                    portfolio_after.portfolio_state_id if portfolio_after is not None else None
                ),
                market_as_of=(
                    agent_input.market_state.as_of if agent_input is not None else None
                ),
                portfolio_before_as_of=(
                    agent_input.portfolio_state.as_of if agent_input is not None else None
                ),
                portfolio_after_as_of=(
                    portfolio_after.as_of if portfolio_after is not None else None
                ),
                agent_input_payload=_model_payload(agent_input),
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


def _model_payload(model: Any | None) -> dict[str, object] | None:
    if model is None:
        return None
    return dict(model.model_dump(mode="json"))


def _result_digest(result: TradingCycleResult) -> str:
    payload = {
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
        "agent_input": _model_payload(result.agent_input),
        "decision": _model_payload(result.decision),
        "risk_assessment": _model_payload(result.risk_assessment),
        "execution_intent": _model_payload(result.execution_intent),
        "fills": [_model_payload(fill) for fill in result.fills],
        "portfolio_state_after": _model_payload(result.portfolio_state_after),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
