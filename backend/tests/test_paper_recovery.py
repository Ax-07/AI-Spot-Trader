import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import func, select

from ai_spot_trader.domain.enums import (
    MarketType,
    PositionSide,
    RiskDecision,
    RiskReason,
    TradingAction,
)
from ai_spot_trader.domain.models import (
    AgentInput,
    AssetBalance,
    AssetPosition,
    DecisionCandidate,
    DerivativePosition,
    ExecutableMarket,
    MarketState,
    PortfolioState,
    RiskAssessment,
)
from ai_spot_trader.persistence.analytics import SqlAlchemyPaperAnalyticsQueryService
from ai_spot_trader.persistence.audit import AuditedTradingCycleRunner
from ai_spot_trader.persistence.db import Database
from ai_spot_trader.persistence.models import (
    CycleRecord,
    DecisionRecord,
    ExecutionIntentRecord,
    FillRecord,
    PaperRunRecord,
    RiskAssessmentRecord,
)
from ai_spot_trader.persistence.repository import SqlAlchemyCycleAuditRepository
from ai_spot_trader.persistence.runs import (
    PAPER_LEDGER_RECOVERY_VERSION,
    PaperRunDefinition,
    PaperRunRecoveryError,
    SqlAlchemyPaperRunLifecycle,
)
from ai_spot_trader.portfolio.ledger import PaperPortfolioLedger
from ai_spot_trader.trading.engine import (
    TradingCycleFailure,
    TradingCycleResult,
    TradingCycleStage,
    TradingCycleStatus,
)

BASE = datetime(2026, 9, 23, 7, 0, tzinfo=UTC)
RUN_A = UUID("18060000-0000-0000-0000-000000000001")
RUN_B = UUID("18060000-0000-0000-0000-000000000002")
RUN_C = UUID("18060000-0000-0000-0000-000000000003")
CYCLE_A = UUID("18060000-0000-0000-0000-000000000101")
DECISION_A = UUID("18060000-0000-0000-0000-000000000201")
RISK_A = UUID("18060000-0000-0000-0000-000000000301")
EXECUTION_A = UUID("18060000-0000-0000-0000-000000000401")
FILL_A = UUID("18060000-0000-0000-0000-000000000501")
MARKET_A = UUID("18060000-0000-0000-0000-000000000601")


@dataclass
class FixedClock:
    value: datetime

    def now(self) -> datetime:
        return self.value


def bootstrap(*, at: datetime = BASE) -> PortfolioState:
    return PortfolioState(
        portfolio_state_id=UUID("18060000-0000-0000-0000-000000000701"),
        as_of=at,
        balances=(AssetBalance(asset="EUR", available=Decimal("1000")),),
    )


def universe() -> tuple[ExecutableMarket, ...]:
    return (
        ExecutableMarket(symbol="BTC/EUR", market_type=MarketType.SPOT),
        ExecutableMarket(symbol="ETH/EUR", market_type=MarketType.PERPETUAL),
    )


async def add_completed_snapshot(
    database: Database,
    *,
    run_id: UUID,
    state: PortfolioState,
    cycle_id: UUID = CYCLE_A,
    at: datetime = BASE + timedelta(minutes=1),
    with_execution_graph: bool = False,
) -> None:
    async with database.sessions() as session, session.begin():
        run = await session.get(PaperRunRecord, run_id)
        assert run is not None
        run.current_portfolio_payload = state.model_dump(mode="json")
        session.add(
            CycleRecord(
                cycle_id=cycle_id,
                paper_run_id=run_id,
                status="COMPLETED",
                recorded_at=at,
                result_digest="a" * 64,
                portfolio_state_after_id=state.portfolio_state_id,
                portfolio_after_as_of=state.as_of,
                portfolio_after_payload=state.model_dump(mode="json"),
            )
        )
        if with_execution_graph:
            session.add(
                DecisionRecord(
                    decision_id=DECISION_A,
                    cycle_id=cycle_id,
                    created_at=at,
                    action="BUY",
                    symbol="BTC/EUR",
                    payload={},
                )
            )
            session.add(
                RiskAssessmentRecord(
                    risk_assessment_id=RISK_A,
                    cycle_id=cycle_id,
                    decision_id=DECISION_A,
                    assessed_at=at,
                    status="ALLOW",
                    payload={},
                )
            )
            session.add(
                ExecutionIntentRecord(
                    execution_id=EXECUTION_A,
                    cycle_id=cycle_id,
                    decision_id=DECISION_A,
                    risk_assessment_id=RISK_A,
                    created_at=at,
                    action="BUY",
                    symbol="BTC/EUR",
                    payload={},
                )
            )
            session.add(
                FillRecord(
                    fill_id=FILL_A,
                    execution_id=EXECUTION_A,
                    market_state_id=MARKET_A,
                    filled_at=at,
                    payload={},
                )
            )


def test_restart_restores_spot_inventory_and_links_new_run_without_replay() -> None:
    async def scenario() -> None:
        database = Database("sqlite+aiosqlite:///:memory:")
        await database.create_schema_for_tests()
        first_ledger = PaperPortfolioLedger(
            initial_state=bootstrap(),
            clock=FixedClock(BASE),
        )
        first = SqlAlchemyPaperRunLifecycle(
            database.sessions,
            execution_universe=universe(),
            initial_portfolio=bootstrap(),
            portfolio_sink=first_ledger,
            clock=FixedClock(BASE),
            run_id_factory=lambda: RUN_A,
        )
        try:
            created = await first.initialize()
            assert created.paper_run_id == RUN_A
            assert created.resumed_from_paper_run_id is None
            assert created.recovery_version == PAPER_LEDGER_RECOVERY_VERSION

            durable = PortfolioState(
                portfolio_state_id=UUID("18060000-0000-0000-0000-000000000702"),
                as_of=BASE + timedelta(minutes=1),
                balances=(AssetBalance(asset="EUR", available=Decimal("900")),),
                positions=(
                    AssetPosition(
                        asset="BTC",
                        quantity=Decimal("1"),
                        available=Decimal("1"),
                    ),
                ),
            )
            await add_completed_snapshot(
                database,
                run_id=RUN_A,
                state=durable,
                with_execution_graph=True,
            )
            await first.close()

            second_ledger = PaperPortfolioLedger(
                initial_state=bootstrap(at=BASE + timedelta(hours=1)),
                clock=FixedClock(BASE + timedelta(hours=1)),
            )
            second = SqlAlchemyPaperRunLifecycle(
                database.sessions,
                execution_universe=universe(),
                initial_portfolio=bootstrap(at=BASE + timedelta(hours=1)),
                portfolio_sink=second_ledger,
                clock=FixedClock(BASE + timedelta(hours=1)),
                run_id_factory=lambda: RUN_B,
            )
            recovered = await second.initialize()
            assert recovered.paper_run_id == RUN_B
            assert recovered.resumed_from_paper_run_id == RUN_A
            restored = second_ledger.snapshot()
            assert tuple((item.asset, item.available) for item in restored.balances) == (
                ("EUR", Decimal("900")),
            )
            assert tuple((item.asset, item.quantity) for item in restored.positions) == (
                ("BTC", Decimal("1")),
            )

            async with database.sessions() as session:
                intent_count = int(
                    await session.scalar(
                        select(func.count()).select_from(ExecutionIntentRecord)
                    )
                    or 0
                )
                fill_count = int(
                    await session.scalar(select(func.count()).select_from(FillRecord)) or 0
                )
                assert intent_count == 1
                assert fill_count == 1

            # A second restart before any new cycle is still deterministic because RUN_B carries
            # its own durable initial snapshot; no decision or fill is regenerated.
            await second.close()
            third_ledger = PaperPortfolioLedger(
                initial_state=bootstrap(at=BASE + timedelta(hours=2)),
                clock=FixedClock(BASE + timedelta(hours=2)),
            )
            third = SqlAlchemyPaperRunLifecycle(
                database.sessions,
                execution_universe=universe(),
                initial_portfolio=bootstrap(at=BASE + timedelta(hours=2)),
                portfolio_sink=third_ledger,
                clock=FixedClock(BASE + timedelta(hours=2)),
                run_id_factory=lambda: RUN_C,
            )
            repeated = await third.initialize()
            assert repeated.resumed_from_paper_run_id == RUN_B
            assert third_ledger.snapshot().positions[0].quantity == Decimal("1")
        finally:
            await database.close()

    asyncio.run(scenario())


def test_restart_restores_open_perpetual_position_funding_margin_and_pnl() -> None:
    async def scenario() -> None:
        database = Database("sqlite+aiosqlite:///:memory:")
        await database.create_schema_for_tests()
        ledger = PaperPortfolioLedger(initial_state=bootstrap(), clock=FixedClock(BASE))
        first = SqlAlchemyPaperRunLifecycle(
            database.sessions,
            execution_universe=universe(),
            initial_portfolio=bootstrap(),
            portfolio_sink=ledger,
            clock=FixedClock(BASE),
            run_id_factory=lambda: RUN_A,
        )
        try:
            await first.initialize()
            position = DerivativePosition(
                symbol="ETH/EUR",
                side=PositionSide.LONG,
                quantity=Decimal("2"),
                average_entry_price=Decimal("100"),
                mark_price=Decimal("110"),
                contract_size=Decimal("1"),
                notional=Decimal("220"),
                realized_pnl=Decimal("7"),
                unrealized_pnl=Decimal("20"),
                leverage=Decimal("2"),
                margin_used=Decimal("100"),
                initial_margin_rate=Decimal("0.10"),
                maintenance_margin_rate=Decimal("0.05"),
                maintenance_margin=Decimal("11"),
                cumulative_funding=Decimal("-1.25"),
                liquidation_price=Decimal("52"),
                funding_updated_at=BASE + timedelta(minutes=1),
            )
            durable = PortfolioState(
                portfolio_state_id=UUID("18060000-0000-0000-0000-000000000703"),
                as_of=BASE + timedelta(minutes=1),
                balances=(AssetBalance(asset="EUR", available=Decimal("890")),),
                derivative_positions=(position,),
            )
            await add_completed_snapshot(database, run_id=RUN_A, state=durable)
            await first.close()

            recovered_ledger = PaperPortfolioLedger(
                initial_state=bootstrap(at=BASE + timedelta(hours=1)),
                clock=FixedClock(BASE + timedelta(hours=1)),
            )
            restarted = SqlAlchemyPaperRunLifecycle(
                database.sessions,
                execution_universe=universe(),
                initial_portfolio=bootstrap(at=BASE + timedelta(hours=1)),
                portfolio_sink=recovered_ledger,
                clock=FixedClock(BASE + timedelta(hours=1)),
                run_id_factory=lambda: RUN_B,
            )
            await restarted.initialize()
            restored = recovered_ledger.snapshot().derivative_positions[0]
            assert restored.side is PositionSide.LONG
            assert restored.quantity == Decimal("2")
            assert restored.average_entry_price == Decimal("100")
            assert restored.margin_used == Decimal("100")
            assert restored.realized_pnl == Decimal("7")
            assert restored.unrealized_pnl == Decimal("20")
            assert restored.cumulative_funding == Decimal("-1.25")
            assert restored.funding_updated_at == BASE + timedelta(minutes=1)
        finally:
            await database.close()

    asyncio.run(scenario())



def test_recovery_analytics_replays_parent_chain_without_regenerating_cycles() -> None:
    async def scenario() -> None:
        database = Database("sqlite+aiosqlite:///:memory:")
        await database.create_schema_for_tests()
        first_ledger = PaperPortfolioLedger(initial_state=bootstrap(), clock=FixedClock(BASE))
        first = SqlAlchemyPaperRunLifecycle(
            database.sessions,
            execution_universe=universe(),
            initial_portfolio=bootstrap(),
            portfolio_sink=first_ledger,
            clock=FixedClock(BASE),
            run_id_factory=lambda: RUN_A,
        )
        try:
            await first.initialize()
            repository = SqlAlchemyCycleAuditRepository(database.sessions)
            assert await repository.record_for_run(RUN_A, hold_result(bootstrap())) is True
            await first.close()

            second_ledger = PaperPortfolioLedger(
                initial_state=bootstrap(at=BASE + timedelta(hours=1)),
                clock=FixedClock(BASE + timedelta(hours=1)),
            )
            second = SqlAlchemyPaperRunLifecycle(
                database.sessions,
                execution_universe=universe(),
                initial_portfolio=bootstrap(at=BASE + timedelta(hours=1)),
                portfolio_sink=second_ledger,
                clock=FixedClock(BASE + timedelta(hours=1)),
                run_id_factory=lambda: RUN_B,
            )
            await second.initialize()

            report = await SqlAlchemyPaperAnalyticsQueryService(
                database.sessions
            ).paper_analytics_for_run(RUN_B)
            assert report.summary.completed_cycle_count == 1
            assert report.summary.hold_count == 1
            assert report.summary.initial_equity == Decimal("1000")
            assert report.summary.ending_equity == Decimal("1000")

            async with database.sessions() as session:
                assert int(
                    await session.scalar(select(func.count()).select_from(CycleRecord)) or 0
                ) == 1
        finally:
            await database.close()

    asyncio.run(scenario())

def test_fresh_empty_state_is_durable_and_recoverable_before_first_cycle() -> None:
    async def scenario() -> None:
        database = Database("sqlite+aiosqlite:///:memory:")
        await database.create_schema_for_tests()
        first_ledger = PaperPortfolioLedger(initial_state=bootstrap(), clock=FixedClock(BASE))
        spot_only = (
            ExecutableMarket(symbol="BTC/EUR", market_type=MarketType.SPOT),
        )
        first = SqlAlchemyPaperRunLifecycle(
            database.sessions,
            execution_universe=spot_only,
            initial_portfolio=bootstrap(),
            portfolio_sink=first_ledger,
            clock=FixedClock(BASE),
            run_id_factory=lambda: RUN_A,
        )
        try:
            await first.initialize()
            await first.close()
            second_ledger = PaperPortfolioLedger(
                initial_state=bootstrap(at=BASE + timedelta(hours=1)),
                clock=FixedClock(BASE + timedelta(hours=1)),
            )
            second = SqlAlchemyPaperRunLifecycle(
                database.sessions,
                execution_universe=spot_only,
                initial_portfolio=bootstrap(at=BASE + timedelta(hours=1)),
                portfolio_sink=second_ledger,
                clock=FixedClock(BASE + timedelta(hours=1)),
                run_id_factory=lambda: RUN_B,
            )
            view = await second.initialize()
            assert view.resumed_from_paper_run_id == RUN_A
            assert second_ledger.snapshot().positions == ()
            assert second_ledger.snapshot().derivative_positions == ()
            assert second_ledger.snapshot().balances[0].available == Decimal("1000")
        finally:
            await database.close()

    asyncio.run(scenario())


def test_legacy_run_ending_in_failed_cycle_fails_closed() -> None:
    async def scenario() -> None:
        database = Database("sqlite+aiosqlite:///:memory:")
        await database.create_schema_for_tests()
        legacy = SqlAlchemyPaperRunLifecycle(
            database.sessions,
            definition=PaperRunDefinition(
                paper_run_id=RUN_A,
                started_at=BASE,
                execution_universe=universe(),
            ),
            clock=FixedClock(BASE),
        )
        try:
            await legacy.initialize()
            async with database.sessions() as session, session.begin():
                session.add(
                    CycleRecord(
                        cycle_id=CYCLE_A,
                        paper_run_id=RUN_A,
                        status="FAILED",
                        recorded_at=BASE + timedelta(minutes=1),
                        result_digest="b" * 64,
                        failure_stage="AGENT",
                        failure_error_type="TimeoutError",
                        failure_timed_out=True,
                    )
                )

            target = PaperPortfolioLedger(
                initial_state=bootstrap(at=BASE + timedelta(hours=1)),
                clock=FixedClock(BASE + timedelta(hours=1)),
            )
            restarted = SqlAlchemyPaperRunLifecycle(
                database.sessions,
                execution_universe=universe(),
                initial_portfolio=bootstrap(at=BASE + timedelta(hours=1)),
                portfolio_sink=target,
                clock=FixedClock(BASE + timedelta(hours=1)),
                run_id_factory=lambda: RUN_B,
            )
            with pytest.raises(PaperRunRecoveryError, match="ambiguous"):
                await restarted.initialize()
            assert restarted.current_run_id is None
            async with database.sessions() as session:
                assert int(
                    await session.scalar(select(func.count()).select_from(PaperRunRecord)) or 0
                ) == 1
        finally:
            await database.close()

    asyncio.run(scenario())


def test_recovery_refuses_execution_universe_change() -> None:
    async def scenario() -> None:
        database = Database("sqlite+aiosqlite:///:memory:")
        await database.create_schema_for_tests()
        first_ledger = PaperPortfolioLedger(initial_state=bootstrap(), clock=FixedClock(BASE))
        first = SqlAlchemyPaperRunLifecycle(
            database.sessions,
            execution_universe=universe(),
            initial_portfolio=bootstrap(),
            portfolio_sink=first_ledger,
            clock=FixedClock(BASE),
            run_id_factory=lambda: RUN_A,
        )
        try:
            await first.initialize()
            await first.close()
            target = PaperPortfolioLedger(
                initial_state=bootstrap(at=BASE + timedelta(hours=1)),
                clock=FixedClock(BASE + timedelta(hours=1)),
            )
            restarted = SqlAlchemyPaperRunLifecycle(
                database.sessions,
                execution_universe=(
                    ExecutableMarket(symbol="BTC/EUR", market_type=MarketType.SPOT),
                ),
                initial_portfolio=bootstrap(at=BASE + timedelta(hours=1)),
                portfolio_sink=target,
                clock=FixedClock(BASE + timedelta(hours=1)),
                run_id_factory=lambda: RUN_B,
            )
            with pytest.raises(PaperRunRecoveryError, match="universe"):
                await restarted.initialize()
        finally:
            await database.close()

    asyncio.run(scenario())


def hold_result(state: PortfolioState) -> TradingCycleResult:
    decision = DecisionCandidate(
        decision_id=DECISION_A,
        cycle_id=CYCLE_A,
        created_at=BASE,
        action=TradingAction.HOLD,
        symbol="BTC/EUR",
        proposed_quantity=None,
    )
    risk = RiskAssessment(
        risk_assessment_id=RISK_A,
        cycle_id=CYCLE_A,
        decision_id=DECISION_A,
        assessed_at=BASE,
        status=RiskDecision.ALLOW,
        reasons=(RiskReason.HOLD_NO_EXECUTION,),
    )
    return TradingCycleResult(
        cycle_id=CYCLE_A,
        status=TradingCycleStatus.COMPLETED,
        agent_input=AgentInput(
            cycle_id=CYCLE_A,
            created_at=BASE,
            market_state=MarketState(
                market_state_id=MARKET_A,
                as_of=BASE,
                symbol="BTC/EUR",
                last_price=Decimal("100"),
            ),
            portfolio_state=state,
            aggressiveness=5,
        ),
        decision=decision,
        risk_assessment=risk,
    )


def test_audited_runner_rolls_back_failed_or_non_durable_ledger_mutations() -> None:
    class Writer:
        def __init__(self, *, result: bool = True, error: Exception | None = None) -> None:
            self.result = result
            self.error = error

        async def ensure_available(self) -> None:
            return None

        async def record(self, result: TradingCycleResult) -> bool:
            if self.error is not None:
                raise self.error
            return self.result

    class MutatingDelegate:
        def __init__(
            self,
            ledger: PaperPortfolioLedger,
            result: TradingCycleResult,
        ) -> None:
            self.ledger = ledger
            self.result = result
            self.calls = 0

        async def run_cycle(self) -> TradingCycleResult:
            self.calls += 1
            self.ledger.apply_buy(
                base_asset="BTC",
                quote_asset="EUR",
                quantity=Decimal("1"),
                quote_debit=Decimal("100"),
            )
            return self.result

    async def scenario() -> None:
        for result, writer, raises in (
            (
                TradingCycleResult(
                    cycle_id=CYCLE_A,
                    status=TradingCycleStatus.FAILED,
                    failure=TradingCycleFailure(
                        stage=TradingCycleStage.AGENT,
                        error_type="TimeoutError",
                    ),
                ),
                Writer(),
                False,
            ),
            (hold_result(bootstrap()), Writer(result=False), False),
            (hold_result(bootstrap()), Writer(error=RuntimeError("audit down")), True),
        ):
            ledger = PaperPortfolioLedger(initial_state=bootstrap(), clock=FixedClock(BASE))
            runner = AuditedTradingCycleRunner(
                delegate=MutatingDelegate(ledger, result),
                audit_writer=writer,
                portfolio=ledger,
            )
            if raises:
                with pytest.raises(RuntimeError, match="audit down"):
                    await runner.run_cycle()
            else:
                await runner.run_cycle()
            snapshot = ledger.snapshot()
            assert snapshot.positions == ()
            assert snapshot.balances[0].available == Decimal("1000")

    asyncio.run(scenario())


def test_completed_cycle_advances_durable_current_portfolio_but_failed_cycle_does_not() -> None:
    async def scenario() -> None:
        database = Database("sqlite+aiosqlite:///:memory:")
        await database.create_schema_for_tests()
        ledger = PaperPortfolioLedger(initial_state=bootstrap(), clock=FixedClock(BASE))
        lifecycle = SqlAlchemyPaperRunLifecycle(
            database.sessions,
            execution_universe=universe(),
            initial_portfolio=bootstrap(),
            portfolio_sink=ledger,
            clock=FixedClock(BASE),
            run_id_factory=lambda: RUN_A,
        )
        try:
            await lifecycle.initialize()
            committed = PortfolioState(
                portfolio_state_id=UUID("18060000-0000-0000-0000-000000000799"),
                as_of=BASE,
                balances=(AssetBalance(asset="EUR", available=Decimal("900")),),
                positions=(
                    AssetPosition(
                        asset="BTC", quantity=Decimal("1"), available=Decimal("1")
                    ),
                ),
            )
            repository = SqlAlchemyCycleAuditRepository(database.sessions)
            assert await repository.record_for_run(RUN_A, hold_result(committed)) is True

            async with database.sessions() as session:
                run = await session.get(PaperRunRecord, RUN_A)
                assert run is not None and run.current_portfolio_payload is not None
                before_failure = dict(run.current_portfolio_payload)

            failed = TradingCycleResult(
                cycle_id=UUID("18060000-0000-0000-0000-000000000102"),
                status=TradingCycleStatus.FAILED,
                failure=TradingCycleFailure(
                    stage=TradingCycleStage.AGENT,
                    error_type="TimeoutError",
                ),
            )
            assert await repository.record_for_run(RUN_A, failed) is True
            async with database.sessions() as session:
                run = await session.get(PaperRunRecord, RUN_A)
                assert run is not None
                assert run.current_portfolio_payload == before_failure
        finally:
            await database.close()

    asyncio.run(scenario())
