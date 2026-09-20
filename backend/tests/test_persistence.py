import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_spot_trader.domain.enums import RiskDecision, RiskReason, TradingAction
from ai_spot_trader.domain.models import (
    AgentInput,
    AssetBalance,
    DecisionCandidate,
    ExecutionIntent,
    Fill,
    MarketState,
    PortfolioState,
    RiskAssessment,
)
from ai_spot_trader.persistence import Database, SqlAlchemyCycleAuditRepository
from ai_spot_trader.persistence.audit import AuditedTradingCycleRunner
from ai_spot_trader.persistence.models import (
    CycleRecord,
    DecisionRecord,
    ExecutionIntentRecord,
    FillRecord,
    RiskAssessmentRecord,
)
from ai_spot_trader.trading.engine import (
    TradingCycleFailure,
    TradingCycleResult,
    TradingCycleStage,
    TradingCycleStatus,
)

NOW = datetime(2026, 9, 20, 16, 0, tzinfo=UTC)
CYCLE_ID = UUID("10000000-0000-0000-0000-000000000001")
DECISION_ID = UUID("20000000-0000-0000-0000-000000000002")
MARKET_ID = UUID("30000000-0000-0000-0000-000000000003")
PORTFOLIO_ID = UUID("40000000-0000-0000-0000-000000000004")
PORTFOLIO_AFTER_ID = UUID("50000000-0000-0000-0000-000000000005")
RISK_ID = UUID("60000000-0000-0000-0000-000000000006")
EXECUTION_ID = UUID("70000000-0000-0000-0000-000000000007")
FILL_ID = UUID("80000000-0000-0000-0000-000000000008")


def agent_input() -> AgentInput:
    return AgentInput(
        cycle_id=CYCLE_ID,
        created_at=NOW,
        market_state=MarketState(
            market_state_id=MARKET_ID,
            as_of=NOW,
            symbol="BTC/EUR",
            last_price=Decimal("100"),
        ),
        portfolio_state=PortfolioState(
            portfolio_state_id=PORTFOLIO_ID,
            as_of=NOW,
            balances=(AssetBalance(asset="EUR", available=Decimal("1000")),),
        ),
        aggressiveness=5,
    )


def completed_result(
    *,
    action: TradingAction,
    risk_status: RiskDecision,
) -> TradingCycleResult:
    source = agent_input()
    quantity = None if action is TradingAction.HOLD else Decimal("1")
    decision = DecisionCandidate(
        decision_id=DECISION_ID,
        cycle_id=CYCLE_ID,
        created_at=NOW,
        action=action,
        symbol="BTC/EUR",
        proposed_quantity=quantity,
        rationale="audit test",
    )
    if action is TradingAction.HOLD:
        assessment = RiskAssessment(
            risk_assessment_id=RISK_ID,
            cycle_id=CYCLE_ID,
            decision_id=DECISION_ID,
            assessed_at=NOW,
            status=RiskDecision.ALLOW,
            reasons=(RiskReason.HOLD_NO_EXECUTION,),
        )
        return TradingCycleResult(
            cycle_id=CYCLE_ID,
            status=TradingCycleStatus.COMPLETED,
            agent_input=source,
            decision=decision,
            risk_assessment=assessment,
        )
    if risk_status is RiskDecision.REJECT:
        assessment = RiskAssessment(
            risk_assessment_id=RISK_ID,
            cycle_id=CYCLE_ID,
            decision_id=DECISION_ID,
            assessed_at=NOW,
            status=RiskDecision.REJECT,
            requested_quantity=Decimal("1"),
            reasons=(RiskReason.INSUFFICIENT_CASH,),
        )
        return TradingCycleResult(
            cycle_id=CYCLE_ID,
            status=TradingCycleStatus.COMPLETED,
            agent_input=source,
            decision=decision,
            risk_assessment=assessment,
        )

    authorized = Decimal("0.5") if risk_status is RiskDecision.MODIFY else Decimal("1")
    assessment = RiskAssessment(
        risk_assessment_id=RISK_ID,
        cycle_id=CYCLE_ID,
        decision_id=DECISION_ID,
        assessed_at=NOW,
        status=risk_status,
        requested_quantity=Decimal("1"),
        authorized_quantity=authorized,
        reasons=(RiskReason.BUY_CASH_LIMIT,) if risk_status is RiskDecision.MODIFY else (),
    )
    intent = ExecutionIntent(
        execution_id=EXECUTION_ID,
        cycle_id=CYCLE_ID,
        decision_id=DECISION_ID,
        risk_assessment_id=RISK_ID,
        created_at=NOW,
        action=action,
        symbol="BTC/EUR",
        quantity=authorized,
    )
    fill = Fill(
        fill_id=FILL_ID,
        execution_id=EXECUTION_ID,
        market_state_id=MARKET_ID,
        filled_at=NOW,
        pricing_as_of=NOW,
        action=action,
        symbol="BTC/EUR",
        quantity=authorized,
        reference_price=Decimal("100"),
        price=Decimal("100"),
        notional=Decimal("100") * authorized,
        fee=Decimal("0"),
        spread_cost=Decimal("0"),
        slippage_cost=Decimal("0"),
    )
    after = PortfolioState(
        portfolio_state_id=PORTFOLIO_AFTER_ID,
        as_of=NOW,
        balances=(AssetBalance(asset="EUR", available=Decimal("900")),),
    )
    return TradingCycleResult(
        cycle_id=CYCLE_ID,
        status=TradingCycleStatus.COMPLETED,
        agent_input=source,
        decision=decision,
        risk_assessment=assessment,
        execution_intent=intent,
        fills=(fill,),
        portfolio_state_after=after,
    )


async def make_repo() -> tuple[Database, SqlAlchemyCycleAuditRepository]:
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_schema_for_tests()
    return database, SqlAlchemyCycleAuditRepository(database.sessions)


async def counts(database: Database) -> tuple[int, int, int, int, int]:
    async with database.sessions() as session:
        tables = (
            CycleRecord,
            DecisionRecord,
            RiskAssessmentRecord,
            ExecutionIntentRecord,
            FillRecord,
        )
        values = []
        for table in tables:
            values.append(int(await session.scalar(select(func.count()).select_from(table)) or 0))
        return tuple(values)  # type: ignore[return-value]


def test_hold_and_reject_have_no_intent_or_fill() -> None:
    async def scenario() -> None:
        for result in (
            completed_result(action=TradingAction.HOLD, risk_status=RiskDecision.ALLOW),
            completed_result(action=TradingAction.BUY, risk_status=RiskDecision.REJECT),
        ):
            database, repo = await make_repo()
            try:
                assert await repo.record(result) is True
                assert await counts(database) == (1, 1, 1, 0, 0)
            finally:
                await database.close()

    asyncio.run(scenario())


def test_allow_and_modify_persist_full_relation_graph() -> None:
    async def scenario() -> None:
        for status in (RiskDecision.ALLOW, RiskDecision.MODIFY):
            database, repo = await make_repo()
            try:
                result = completed_result(action=TradingAction.BUY, risk_status=status)
                assert await repo.record(result) is True
                assert await counts(database) == (1, 1, 1, 1, 1)
                async with database.sessions() as session:
                    cycle = await session.get(CycleRecord, CYCLE_ID)
                    assert cycle is not None
                    assert cycle.market_state_id == MARKET_ID
                    assert cycle.portfolio_state_before_id == PORTFOLIO_ID
                    assert cycle.portfolio_state_after_id == PORTFOLIO_AFTER_ID
                    risk = await session.get(RiskAssessmentRecord, RISK_ID)
                    assert risk is not None and risk.status == status.value
            finally:
                await database.close()

    asyncio.run(scenario())


def test_failed_cycle_preserves_sanitized_technical_error() -> None:
    async def scenario() -> None:
        database, repo = await make_repo()
        try:
            result = TradingCycleResult(
                cycle_id=CYCLE_ID,
                status=TradingCycleStatus.FAILED,
                failure=TradingCycleFailure(
                    stage=TradingCycleStage.AGENT,
                    error_type="TimeoutError",
                    timed_out=True,
                ),
                agent_input=agent_input(),
            )
            await repo.record(result)
            async with database.sessions() as session:
                cycle = await session.get(CycleRecord, CYCLE_ID)
                assert cycle is not None
                assert cycle.failure_stage == TradingCycleStage.AGENT.value
                assert cycle.failure_error_type == "TimeoutError"
                assert cycle.failure_timed_out is True
                assert cycle.agent_input_payload is not None
        finally:
            await database.close()

    asyncio.run(scenario())


def test_exact_replay_is_idempotent() -> None:
    async def scenario() -> None:
        database, repo = await make_repo()
        try:
            result = completed_result(action=TradingAction.HOLD, risk_status=RiskDecision.ALLOW)
            assert await repo.record(result) is True
            assert await repo.record(result) is False
            assert await counts(database) == (1, 1, 1, 0, 0)
        finally:
            await database.close()

    asyncio.run(scenario())


def test_audited_runner_persists_returned_result() -> None:
    class FixedRunner:
        async def run_cycle(self) -> TradingCycleResult:
            return completed_result(action=TradingAction.HOLD, risk_status=RiskDecision.ALLOW)

    async def scenario() -> None:
        database, repo = await make_repo()
        try:
            runner = AuditedTradingCycleRunner(delegate=FixedRunner(), audit_writer=repo)
            result = await runner.run_cycle()
            assert result.cycle_id == CYCLE_ID
            assert await counts(database) == (1, 1, 1, 0, 0)
        finally:
            await database.close()

    asyncio.run(scenario())


def test_transaction_rolls_back_the_whole_graph_on_write_failure() -> None:
    class FailingRepository(SqlAlchemyCycleAuditRepository):
        def _add_graph(
            self,
            session: AsyncSession,
            *,
            result: TradingCycleResult,
            digest: str,
        ) -> None:
            super()._add_graph(session, result=result, digest=digest)
            raise RuntimeError("forced write failure")

    async def scenario() -> None:
        database, _ = await make_repo()
        repo = FailingRepository(database.sessions)
        try:
            result = completed_result(action=TradingAction.BUY, risk_status=RiskDecision.ALLOW)
            try:
                await repo.record(result)
            except RuntimeError as exc:
                assert str(exc) == "forced write failure"
            else:
                raise AssertionError("forced failure was not propagated")
            assert await counts(database) == (0, 0, 0, 0, 0)
        finally:
            await database.close()

    asyncio.run(scenario())
