import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from ai_spot_trader.persistence.analytics import SqlAlchemyPaperAnalyticsQueryService
from ai_spot_trader.persistence.db import Database
from ai_spot_trader.persistence.models import (
    CycleRecord,
    DecisionRecord,
    ExecutionIntentRecord,
    FillRecord,
    RiskAssessmentRecord,
)
from ai_spot_trader.persistence.query import AuditSortOrder, SqlAlchemyCycleAuditQueryService
from ai_spot_trader.persistence.runs import (
    PaperRunDefinition,
    PaperRunSortOrder,
    SqlAlchemyPaperRunLifecycle,
    SqlAlchemyPaperRunQueryService,
)

BASE = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
RUN_A = UUID("aaaaaaaa-0000-0000-0000-000000000001")
RUN_B = UUID("bbbbbbbb-0000-0000-0000-000000000002")
LEGACY_CYCLE = UUID("cccccccc-0000-0000-0000-000000000099")


class FixedClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


def _portfolio(*, cash: str, btc: str = "0", offset: int) -> dict[str, object]:
    positions: list[dict[str, object]] = []
    if Decimal(btc) != 0:
        positions.append({"asset": "BTC", "quantity": btc, "available": btc})
    return {
        "portfolio_state_id": str(UUID(int=10_000 + offset)),
        "as_of": (BASE + timedelta(minutes=offset)).isoformat().replace("+00:00", "Z"),
        "mode": "PAPER",
        "balances": [{"asset": "EUR", "available": cash}],
        "positions": positions,
    }


def _agent_input(
    cycle_id: UUID,
    *,
    price: str,
    portfolio: dict[str, object],
    offset: int,
) -> dict[str, object]:
    at = BASE + timedelta(minutes=offset)
    return {
        "cycle_id": str(cycle_id),
        "created_at": at.isoformat().replace("+00:00", "Z"),
        "market_state": {
            "market_state_id": str(UUID(int=20_000 + offset)),
            "as_of": at.isoformat().replace("+00:00", "Z"),
            "symbol": "BTC/EUR",
            "last_price": price,
            "context": None,
        },
        "portfolio_state": portfolio,
        "aggressiveness": 5,
    }


def _decision(
    cycle_id: UUID, *, action: str, quantity: str | None, offset: int
) -> dict[str, object]:
    return {
        "decision_id": str(UUID(int=30_000 + offset)),
        "cycle_id": str(cycle_id),
        "created_at": (BASE + timedelta(minutes=offset)).isoformat().replace("+00:00", "Z"),
        "action": action,
        "symbol": "BTC/EUR",
        "proposed_quantity": quantity,
        "rationale": "run isolation test",
    }


def _risk(
    cycle_id: UUID,
    *,
    action: str,
    requested: str | None,
    authorized: str | None,
    offset: int,
) -> dict[str, object]:
    return {
        "risk_assessment_id": str(UUID(int=40_000 + offset)),
        "cycle_id": str(cycle_id),
        "decision_id": str(UUID(int=30_000 + offset)),
        "assessed_at": (BASE + timedelta(minutes=offset)).isoformat().replace("+00:00", "Z"),
        "status": "ALLOW",
        "requested_quantity": requested,
        "authorized_quantity": authorized,
        "evaluated_limits": [],
        "reasons": ["HOLD_NO_EXECUTION"] if action == "HOLD" else [],
    }


def _fill(*, offset: int) -> dict[str, object]:
    at = BASE + timedelta(minutes=offset)
    return {
        "fill_id": str(UUID(int=60_000 + offset)),
        "execution_id": str(UUID(int=50_000 + offset)),
        "market_state_id": str(UUID(int=20_000 + offset)),
        "filled_at": at.isoformat().replace("+00:00", "Z"),
        "pricing_as_of": at.isoformat().replace("+00:00", "Z"),
        "action": "BUY",
        "symbol": "BTC/EUR",
        "quantity": "1",
        "reference_price": "100",
        "price": "100",
        "notional": "100",
        "fee": "0",
        "spread_cost": "0",
        "slippage_cost": "0",
    }


async def _add_cycle(
    database: Database,
    *,
    paper_run_id: UUID | None,
    cycle_id: UUID,
    offset: int,
    price: str,
    before: dict[str, object],
    action: str,
    after: dict[str, object] | None = None,
) -> None:
    decision_id = UUID(int=30_000 + offset)
    risk_id = UUID(int=40_000 + offset)
    execution_id = UUID(int=50_000 + offset)
    fill_id = UUID(int=60_000 + offset)
    agent_payload = _agent_input(cycle_id, price=price, portfolio=before, offset=offset)
    decision_payload = _decision(
        cycle_id,
        action=action,
        quantity=None if action == "HOLD" else "1",
        offset=offset,
    )
    risk_payload = _risk(
        cycle_id,
        action=action,
        requested=None if action == "HOLD" else "1",
        authorized=None if action == "HOLD" else "1",
        offset=offset,
    )
    async with database.sessions() as session, session.begin():
        session.add(
            CycleRecord(
                cycle_id=cycle_id,
                paper_run_id=paper_run_id,
                status="COMPLETED",
                recorded_at=BASE + timedelta(minutes=offset),
                result_digest=f"{offset:064x}",
                failure_stage=None,
                failure_error_type=None,
                failure_timed_out=None,
                market_state_id=UUID(int=20_000 + offset),
                portfolio_state_before_id=UUID(str(before["portfolio_state_id"])),
                portfolio_state_after_id=(
                    None if after is None else UUID(str(after["portfolio_state_id"]))
                ),
                market_as_of=BASE + timedelta(minutes=offset),
                portfolio_before_as_of=BASE + timedelta(minutes=offset),
                portfolio_after_as_of=(
                    None if after is None else BASE + timedelta(minutes=offset)
                ),
                agent_input_payload=agent_payload,
                portfolio_after_payload=after,
            )
        )
        session.add(
            DecisionRecord(
                decision_id=decision_id,
                cycle_id=cycle_id,
                created_at=BASE + timedelta(minutes=offset),
                action=action,
                symbol="BTC/EUR",
                payload=decision_payload,
            )
        )
        session.add(
            RiskAssessmentRecord(
                risk_assessment_id=risk_id,
                cycle_id=cycle_id,
                decision_id=decision_id,
                assessed_at=BASE + timedelta(minutes=offset),
                status="ALLOW",
                payload=risk_payload,
            )
        )
        if action == "BUY":
            fill_payload = _fill(offset=offset)
            session.add(
                ExecutionIntentRecord(
                    execution_id=execution_id,
                    cycle_id=cycle_id,
                    decision_id=decision_id,
                    risk_assessment_id=risk_id,
                    created_at=BASE + timedelta(minutes=offset),
                    action="BUY",
                    symbol="BTC/EUR",
                    payload={
                        "execution_id": str(execution_id),
                        "cycle_id": str(cycle_id),
                        "decision_id": str(decision_id),
                        "risk_assessment_id": str(risk_id),
                        "created_at": (BASE + timedelta(minutes=offset))
                        .isoformat()
                        .replace("+00:00", "Z"),
                        "mode": "PAPER",
                        "action": "BUY",
                        "symbol": "BTC/EUR",
                        "quantity": "1",
                    },
                )
            )
            session.add(
                FillRecord(
                    fill_id=fill_id,
                    execution_id=execution_id,
                    market_state_id=UUID(int=20_000 + offset),
                    filled_at=BASE + timedelta(minutes=offset),
                    payload=fill_payload,
                )
            )


def test_two_runs_share_one_database_without_mixing_analytics_or_legacy() -> None:
    async def scenario() -> None:
        database = Database("sqlite+aiosqlite:///:memory:")
        await database.create_schema_for_tests()
        try:
            lifecycle_a = SqlAlchemyPaperRunLifecycle(
                database.sessions,
                definition=PaperRunDefinition(
                    paper_run_id=RUN_A,
                    started_at=BASE,
                    market_type="SPOT",
                    symbol="BTC/EUR",
                ),
                clock=FixedClock(BASE + timedelta(hours=1)),
            )
            lifecycle_b = SqlAlchemyPaperRunLifecycle(
                database.sessions,
                definition=PaperRunDefinition(
                    paper_run_id=RUN_B,
                    started_at=BASE + timedelta(seconds=1),
                    market_type="PERPETUAL",
                    symbol="BTC/USD",
                ),
                clock=FixedClock(BASE + timedelta(hours=1)),
            )
            await lifecycle_a.initialize()
            await lifecycle_b.initialize()

            p1000 = _portfolio(cash="1000", offset=1)
            p_after_buy = _portfolio(cash="900", btc="1", offset=2)
            await _add_cycle(
                database,
                paper_run_id=RUN_A,
                cycle_id=UUID(int=1),
                offset=1,
                price="100",
                before=p1000,
                action="HOLD",
            )
            await _add_cycle(
                database,
                paper_run_id=RUN_A,
                cycle_id=UUID(int=2),
                offset=2,
                price="100",
                before=p1000,
                action="BUY",
                after=p_after_buy,
            )
            await _add_cycle(
                database,
                paper_run_id=RUN_A,
                cycle_id=UUID(int=3),
                offset=3,
                price="80",
                before=p_after_buy,
                action="HOLD",
            )

            p2000 = _portfolio(cash="2000", offset=10)
            await _add_cycle(
                database,
                paper_run_id=RUN_B,
                cycle_id=UUID(int=10),
                offset=10,
                price="200",
                before=p2000,
                action="HOLD",
            )
            await _add_cycle(
                database,
                paper_run_id=RUN_B,
                cycle_id=UUID(int=11),
                offset=11,
                price="250",
                before=p2000,
                action="HOLD",
            )

            legacy = _portfolio(cash="9999", offset=99)
            await _add_cycle(
                database,
                paper_run_id=None,
                cycle_id=LEGACY_CYCLE,
                offset=99,
                price="999",
                before=legacy,
                action="HOLD",
            )

            analytics = SqlAlchemyPaperAnalyticsQueryService(database.sessions)
            run_a = await analytics.paper_analytics_for_run(RUN_A)
            run_b = await analytics.paper_analytics_for_run(RUN_B)

            assert run_a.summary.initial_equity == Decimal("1000")
            assert run_a.summary.ending_equity == Decimal("980")
            assert run_a.summary.trade_count == 1
            assert run_a.summary.hold_count == 2
            assert run_a.summary.max_drawdown_value == Decimal("20")

            assert run_b.summary.initial_equity == Decimal("2000")
            assert run_b.summary.ending_equity == Decimal("2000")
            assert run_b.summary.trade_count == 0
            assert run_b.summary.hold_count == 2
            assert run_b.summary.max_drawdown_value == Decimal("0")

            queries = SqlAlchemyCycleAuditQueryService(database.sessions)
            page_a = await queries.list_cycles_for_run(
                RUN_A, limit=20, offset=0, order=AuditSortOrder.ASC
            )
            page_b = await queries.list_cycles_for_run(
                RUN_B, limit=20, offset=0, order=AuditSortOrder.ASC
            )
            all_cycles = await queries.list_cycles(
                limit=20, offset=0, order=AuditSortOrder.ASC
            )
            assert page_a.total == 3
            assert page_b.total == 2
            assert all_cycles.total == 6
            assert LEGACY_CYCLE in {item.cycle_id for item in all_cycles.items}
            assert all(item.paper_run_id == RUN_A for item in page_a.items)
            assert all(item.paper_run_id == RUN_B for item in page_b.items)

            decisions_a = await queries.list_decisions_for_run(
                RUN_A, limit=20, offset=0, order=AuditSortOrder.ASC
            )
            decisions_b = await queries.list_decisions_for_run(
                RUN_B, limit=20, offset=0, order=AuditSortOrder.ASC
            )
            risk_a = await queries.list_risk_assessments_for_run(
                RUN_A, limit=20, offset=0, order=AuditSortOrder.ASC
            )
            risk_b = await queries.list_risk_assessments_for_run(
                RUN_B, limit=20, offset=0, order=AuditSortOrder.ASC
            )
            assert decisions_a.total == 3
            assert decisions_b.total == 2
            assert risk_a.total == 3
            assert risk_b.total == 2

            executions_a = await queries.list_executions_for_run(
                RUN_A, limit=20, offset=0, order=AuditSortOrder.ASC
            )
            executions_b = await queries.list_executions_for_run(
                RUN_B, limit=20, offset=0, order=AuditSortOrder.ASC
            )
            assert executions_a.total == 1
            assert len(executions_a.items[0].fills) == 1
            assert executions_b.total == 0

            run_reader = SqlAlchemyPaperRunQueryService(database.sessions)
            run_page = await run_reader.list_runs(
                limit=20, offset=0, order=PaperRunSortOrder.ASC
            )
            assert run_page.total == 2
            assert tuple(item.paper_run_id for item in run_page.items) == (RUN_A, RUN_B)
            assert tuple(item.market_type for item in run_page.items) == ("SPOT", "PERPETUAL")

            await lifecycle_a.close()
            closed_a = await run_reader.get_run(RUN_A)
            assert closed_a is not None and closed_a.ended_at is not None
        finally:
            await database.close()

    asyncio.run(scenario())


def test_backend_restart_creates_new_run_while_same_lifetime_is_idempotent() -> None:
    async def scenario() -> None:
        database = Database("sqlite+aiosqlite:///:memory:")
        await database.create_schema_for_tests()
        try:
            first = SqlAlchemyPaperRunLifecycle(
                database.sessions,
                market_type="SPOT",
                symbol="BTC/EUR",
                clock=FixedClock(BASE),
                run_id_factory=lambda: RUN_A,
            )
            created = await first.initialize()
            repeated = await first.initialize()
            assert created.paper_run_id == RUN_A
            assert repeated.paper_run_id == RUN_A
            assert first.current_run_id == RUN_A

            await first.close()
            assert first.current_run_id is None

            restarted = SqlAlchemyPaperRunLifecycle(
                database.sessions,
                market_type="SPOT",
                symbol="BTC/EUR",
                clock=FixedClock(BASE + timedelta(hours=2)),
                run_id_factory=lambda: RUN_B,
            )
            second = await restarted.initialize()
            assert second.paper_run_id == RUN_B
            assert restarted.current_run_id == RUN_B

            reader = SqlAlchemyPaperRunQueryService(database.sessions)
            page = await reader.list_runs(
                limit=10,
                offset=0,
                order=PaperRunSortOrder.ASC,
            )
            assert tuple(item.paper_run_id for item in page.items) == (RUN_A, RUN_B)
            assert page.items[0].ended_at is not None
            assert page.items[1].ended_at is None

            await restarted.close()
        finally:
            await database.close()

    asyncio.run(scenario())
