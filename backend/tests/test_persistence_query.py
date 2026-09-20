import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

from ai_spot_trader.persistence.db import Database
from ai_spot_trader.persistence.models import (
    CycleRecord,
    DecisionRecord,
    ExecutionIntentRecord,
    FillRecord,
    RiskAssessmentRecord,
)
from ai_spot_trader.persistence.query import (
    AuditSortOrder,
    SqlAlchemyCycleAuditQueryService,
)

NOW = datetime(2026, 9, 20, 18, 0, tzinfo=UTC)
HOLD_CYCLE = UUID("10000000-0000-0000-0000-000000000011")
MODIFY_CYCLE = UUID("10000000-0000-0000-0000-000000000012")
FAILED_CYCLE = UUID("10000000-0000-0000-0000-000000000013")


def _agent_input_payload(cycle_id: UUID, *, offset: int) -> dict[str, object]:
    as_of = NOW + timedelta(minutes=offset)
    return {
        "cycle_id": str(cycle_id),
        "created_at": as_of.isoformat().replace("+00:00", "Z"),
        "market_state": {
            "market_state_id": str(UUID(int=1000 + offset)),
            "as_of": as_of.isoformat().replace("+00:00", "Z"),
            "symbol": "BTC/EUR",
            "last_price": str(100 + offset),
            "context": None,
        },
        "portfolio_state": {
            "portfolio_state_id": str(UUID(int=2000 + offset)),
            "as_of": as_of.isoformat().replace("+00:00", "Z"),
            "mode": "PAPER",
            "balances": [{"asset": "EUR", "available": "1000"}],
            "positions": [],
        },
        "aggressiveness": 5,
    }


async def _seed(database: Database) -> None:
    hold_decision = UUID("20000000-0000-0000-0000-000000000011")
    hold_risk = UUID("30000000-0000-0000-0000-000000000011")
    modify_decision = UUID("20000000-0000-0000-0000-000000000012")
    modify_risk = UUID("30000000-0000-0000-0000-000000000012")
    execution_id = UUID("40000000-0000-0000-0000-000000000012")
    fill_id = UUID("50000000-0000-0000-0000-000000000012")

    async with database.sessions() as session, session.begin():
        session.add_all(
            [
                CycleRecord(
                    cycle_id=HOLD_CYCLE,
                    status="COMPLETED",
                    recorded_at=NOW + timedelta(minutes=1),
                    result_digest="1" * 64,
                    failure_stage=None,
                    failure_error_type=None,
                    failure_timed_out=None,
                    market_state_id=UUID(int=1001),
                    portfolio_state_before_id=UUID(int=2001),
                    portfolio_state_after_id=None,
                    market_as_of=NOW + timedelta(minutes=1),
                    portfolio_before_as_of=NOW + timedelta(minutes=1),
                    portfolio_after_as_of=None,
                    agent_input_payload=_agent_input_payload(HOLD_CYCLE, offset=1),
                    portfolio_after_payload=None,
                ),
                CycleRecord(
                    cycle_id=MODIFY_CYCLE,
                    status="COMPLETED",
                    recorded_at=NOW + timedelta(minutes=2),
                    result_digest="2" * 64,
                    failure_stage=None,
                    failure_error_type=None,
                    failure_timed_out=None,
                    market_state_id=UUID(int=1002),
                    portfolio_state_before_id=UUID(int=2002),
                    portfolio_state_after_id=UUID(int=3002),
                    market_as_of=NOW + timedelta(minutes=2),
                    portfolio_before_as_of=NOW + timedelta(minutes=2),
                    portfolio_after_as_of=NOW + timedelta(minutes=2),
                    agent_input_payload=_agent_input_payload(MODIFY_CYCLE, offset=2),
                    portfolio_after_payload={
                        "portfolio_state_id": str(UUID(int=3002)),
                        "as_of": (NOW + timedelta(minutes=2)).isoformat().replace(
                            "+00:00", "Z"
                        ),
                        "mode": "PAPER",
                        "balances": [{"asset": "EUR", "available": "950"}],
                        "positions": [{"asset": "BTC", "quantity": "0.5", "available": "0.5"}],
                    },
                ),
                CycleRecord(
                    cycle_id=FAILED_CYCLE,
                    status="FAILED",
                    recorded_at=NOW + timedelta(minutes=3),
                    result_digest="3" * 64,
                    failure_stage="AGENT",
                    failure_error_type="TimeoutError",
                    failure_timed_out=True,
                    market_state_id=None,
                    portfolio_state_before_id=None,
                    portfolio_state_after_id=None,
                    market_as_of=None,
                    portfolio_before_as_of=None,
                    portfolio_after_as_of=None,
                    agent_input_payload=None,
                    portfolio_after_payload=None,
                ),
                DecisionRecord(
                    decision_id=hold_decision,
                    cycle_id=HOLD_CYCLE,
                    created_at=NOW + timedelta(minutes=1),
                    action="HOLD",
                    symbol="BTC/EUR",
                    payload={
                        "decision_id": str(hold_decision),
                        "cycle_id": str(HOLD_CYCLE),
                        "created_at": (NOW + timedelta(minutes=1)).isoformat().replace(
                            "+00:00", "Z"
                        ),
                        "action": "HOLD",
                        "symbol": "BTC/EUR",
                        "proposed_quantity": None,
                        "rationale": "test",
                    },
                ),
                RiskAssessmentRecord(
                    risk_assessment_id=hold_risk,
                    cycle_id=HOLD_CYCLE,
                    decision_id=hold_decision,
                    assessed_at=NOW + timedelta(minutes=1),
                    status="ALLOW",
                    payload={
                        "risk_assessment_id": str(hold_risk),
                        "cycle_id": str(HOLD_CYCLE),
                        "decision_id": str(hold_decision),
                        "assessed_at": (NOW + timedelta(minutes=1)).isoformat().replace(
                            "+00:00", "Z"
                        ),
                        "status": "ALLOW",
                        "requested_quantity": None,
                        "authorized_quantity": None,
                        "evaluated_limits": [],
                        "reasons": ["HOLD_NO_EXECUTION"],
                    },
                ),
                DecisionRecord(
                    decision_id=modify_decision,
                    cycle_id=MODIFY_CYCLE,
                    created_at=NOW + timedelta(minutes=2),
                    action="BUY",
                    symbol="BTC/EUR",
                    payload={
                        "decision_id": str(modify_decision),
                        "cycle_id": str(MODIFY_CYCLE),
                        "created_at": (NOW + timedelta(minutes=2)).isoformat().replace(
                            "+00:00", "Z"
                        ),
                        "action": "BUY",
                        "symbol": "BTC/EUR",
                        "proposed_quantity": "1",
                        "rationale": "test",
                    },
                ),
                RiskAssessmentRecord(
                    risk_assessment_id=modify_risk,
                    cycle_id=MODIFY_CYCLE,
                    decision_id=modify_decision,
                    assessed_at=NOW + timedelta(minutes=2),
                    status="MODIFY",
                    payload={
                        "risk_assessment_id": str(modify_risk),
                        "cycle_id": str(MODIFY_CYCLE),
                        "decision_id": str(modify_decision),
                        "assessed_at": (NOW + timedelta(minutes=2)).isoformat().replace(
                            "+00:00", "Z"
                        ),
                        "status": "MODIFY",
                        "requested_quantity": "1",
                        "authorized_quantity": "0.5",
                        "evaluated_limits": [],
                        "reasons": ["BUY_CASH_LIMIT"],
                    },
                ),
                ExecutionIntentRecord(
                    execution_id=execution_id,
                    cycle_id=MODIFY_CYCLE,
                    decision_id=modify_decision,
                    risk_assessment_id=modify_risk,
                    created_at=NOW + timedelta(minutes=2),
                    action="BUY",
                    symbol="BTC/EUR",
                    payload={
                        "execution_id": str(execution_id),
                        "cycle_id": str(MODIFY_CYCLE),
                        "decision_id": str(modify_decision),
                        "risk_assessment_id": str(modify_risk),
                        "created_at": (NOW + timedelta(minutes=2)).isoformat().replace(
                            "+00:00", "Z"
                        ),
                        "mode": "PAPER",
                        "action": "BUY",
                        "symbol": "BTC/EUR",
                        "quantity": "0.5",
                    },
                ),
                FillRecord(
                    fill_id=fill_id,
                    execution_id=execution_id,
                    market_state_id=UUID(int=1002),
                    filled_at=NOW + timedelta(minutes=2),
                    payload={
                        "fill_id": str(fill_id),
                        "execution_id": str(execution_id),
                        "market_state_id": str(UUID(int=1002)),
                        "filled_at": (NOW + timedelta(minutes=2)).isoformat().replace(
                            "+00:00", "Z"
                        ),
                        "pricing_as_of": (NOW + timedelta(minutes=2)).isoformat().replace(
                            "+00:00", "Z"
                        ),
                        "action": "BUY",
                        "symbol": "BTC/EUR",
                        "quantity": "0.5",
                        "reference_price": "102",
                        "price": "102",
                        "notional": "51",
                        "fee": "0",
                        "spread_cost": "0",
                        "slippage_cost": "0",
                    },
                ),
            ]
        )


def test_sqlalchemy_audit_query_service_reads_durable_history() -> None:
    async def scenario() -> None:
        database = Database("sqlite+aiosqlite:///:memory:")
        await database.create_schema_for_tests()
        try:
            await _seed(database)
            queries = SqlAlchemyCycleAuditQueryService(database.sessions)

            page = await queries.list_cycles(
                limit=2,
                offset=0,
                order=AuditSortOrder.DESC,
            )
            assert page.total == 3
            assert tuple(item.cycle_id for item in page.items) == (
                FAILED_CYCLE,
                MODIFY_CYCLE,
            )

            filtered = await queries.list_cycles(
                limit=10,
                offset=0,
                order=AuditSortOrder.ASC,
                action="HOLD",
                risk_status="ALLOW",
            )
            assert filtered.total == 1
            assert filtered.items[0].cycle_id == HOLD_CYCLE
            assert filtered.items[0].execution_id is None

            detail = await queries.get_cycle(MODIFY_CYCLE)
            assert detail is not None
            assert detail.risk_assessment is not None
            assert detail.risk_assessment["status"] == "MODIFY"
            assert detail.execution_intent is not None
            assert len(detail.fills) == 1

            executions = await queries.list_executions(
                limit=10,
                offset=0,
                order=AuditSortOrder.DESC,
                action="BUY",
            )
            assert executions.total == 1
            assert len(executions.items[0].fills) == 1

            latest_error = await queries.latest_error()
            assert latest_error is not None
            assert latest_error.cycle_id == FAILED_CYCLE
            assert latest_error.failure.error_type == "TimeoutError"
            assert latest_error.failure.timed_out is True

            latest_market = await queries.latest_market_state()
            assert latest_market is not None
            assert latest_market["market_state_id"] == str(UUID(int=1002))
            assert latest_market["symbol"] == "BTC/EUR"
        finally:
            await database.close()

    asyncio.run(scenario())
