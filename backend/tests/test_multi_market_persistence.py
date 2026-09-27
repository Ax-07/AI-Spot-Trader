import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select

from ai_spot_trader.api.explainability import build_cycle_explainability
from ai_spot_trader.api.routes.audit import _cycle_detail as api_cycle_detail
from ai_spot_trader.domain.enums import MarketType, RiskDecision, TradingAction
from ai_spot_trader.domain.models import (
    AgentInput,
    AssetBalance,
    AssetPosition,
    DecisionCandidate,
    ExecutionIntent,
    Fill,
    MarketState,
    PortfolioState,
    RiskAssessment,
)
from ai_spot_trader.domain.planning import CycleDecisionPlan, CycleDecisionPlanInput
from ai_spot_trader.persistence import Database
from ai_spot_trader.persistence.models import (
    CycleRecord,
    DecisionRecord,
    ExecutionIntentRecord,
    PaperRunRecord,
    RiskAssessmentRecord,
)
from ai_spot_trader.persistence.analytics import SqlAlchemyPaperAnalyticsQueryService
from ai_spot_trader.persistence.query import AuditSortOrder, SqlAlchemyCycleAuditQueryService
from ai_spot_trader.persistence.repository import SqlAlchemyCycleAuditRepository
from ai_spot_trader.trading.engine import TradingCycleStatus
from ai_spot_trader.trading.multi_market import (
    DecisionExecutionResult,
    MultiMarketTradingCycleResult,
)

NOW = datetime(2026, 9, 27, 0, 30, tzinfo=UTC)


def state(symbol: str, price: str = "100") -> MarketState:
    return MarketState(
        market_state_id=uuid4(),
        as_of=NOW,
        symbol=symbol,
        last_price=Decimal(price),
        market_type=MarketType.SPOT,
    )


def portfolio(cash: str, positions: tuple[tuple[str, str], ...] = ()) -> PortfolioState:
    return PortfolioState(
        portfolio_state_id=uuid4(),
        as_of=NOW,
        settlement_asset="USD",
        balances=(AssetBalance(asset="USD", available=Decimal(cash)),),
        positions=tuple(
            AssetPosition(asset=asset, quantity=Decimal(qty), available=Decimal(qty))
            for asset, qty in positions
        ),
    )


def multi_result() -> MultiMarketTradingCycleResult:
    cycle_id = uuid4()
    btc = state("BTC/USD")
    eth = state("ETH/USD")
    before = portfolio("300")
    after_btc = portfolio("200", (("BTC", "1"),))
    after_eth = portfolio("100", (("BTC", "1"), ("ETH", "1")))
    plan_input = CycleDecisionPlanInput(
        cycle_id=cycle_id,
        created_at=NOW,
        portfolio_state=before,
        market_states=(btc, eth),
        aggressiveness=5,
        max_decisions_per_cycle=6,
    )
    decisions = tuple(
        DecisionCandidate(
            decision_id=uuid4(),
            cycle_id=cycle_id,
            created_at=NOW,
            action=TradingAction.BUY,
            symbol=market.symbol,
            market_type=MarketType.SPOT,
            proposed_quantity=Decimal("1"),
            rationale="persistence test",
        )
        for market in (btc, eth)
    )
    plan = CycleDecisionPlan(
        cycle_id=cycle_id,
        created_at=NOW,
        decisions=decisions,
        rationale="ordered",
    )
    trajectories = []
    for index, (decision, market, p_before, p_after) in enumerate(
        (
            (decisions[0], btc, before, after_btc),
            (decisions[1], eth, after_btc, after_eth),
        )
    ):
        assessment = RiskAssessment(
            risk_assessment_id=uuid4(),
            cycle_id=cycle_id,
            decision_id=decision.decision_id,
            assessed_at=NOW,
            status=RiskDecision.ALLOW,
            requested_quantity=Decimal("1"),
            authorized_quantity=Decimal("1"),
        )
        intent = ExecutionIntent(
            execution_id=uuid4(),
            cycle_id=cycle_id,
            decision_id=decision.decision_id,
            risk_assessment_id=assessment.risk_assessment_id,
            created_at=NOW,
            action=TradingAction.BUY,
            symbol=market.symbol,
            quantity=Decimal("1"),
            market_type=MarketType.SPOT,
        )
        fill = Fill(
            fill_id=uuid4(),
            execution_id=intent.execution_id,
            market_state_id=market.market_state_id,
            filled_at=NOW,
            pricing_as_of=NOW,
            action=TradingAction.BUY,
            symbol=market.symbol,
            quantity=Decimal("1"),
            reference_price=Decimal("100"),
            price=Decimal("100"),
            notional=Decimal("100"),
            fee=Decimal("0"),
            spread_cost=Decimal("0"),
            slippage_cost=Decimal("0"),
            market_type=MarketType.SPOT,
        )
        trajectories.append(
            DecisionExecutionResult(
                decision_index=index,
                decision=decision,
                market_state=market,
                portfolio_state_before=p_before,
                risk_assessment=assessment,
                execution_intent=intent,
                fills=(fill,),
                portfolio_state_after=p_after,
            )
        )
    return MultiMarketTradingCycleResult(
        cycle_id=cycle_id,
        status=TradingCycleStatus.COMPLETED,
        decision_plan_input=plan_input,
        decision_plan=plan,
        decision_results=tuple(trajectories),
        final_portfolio_state=after_eth,
        portfolio_state_after=after_eth,
    )


def test_repository_persists_ordered_one_to_many_graph_and_query_does_not_fake_singleton() -> None:
    async def scenario() -> None:
        database = Database("sqlite+aiosqlite:///:memory:")
        await database.create_schema_for_tests()
        try:
            repository = SqlAlchemyCycleAuditRepository(database.sessions)
            reader = SqlAlchemyCycleAuditQueryService(database.sessions)
            result = multi_result()
            assert await repository.record(result) is True

            async with database.sessions() as session:
                cycle = await session.get(CycleRecord, result.cycle_id)
                assert cycle is not None
                assert cycle.market_state_id is None
                assert cycle.agent_input_payload is None
                assert cycle.decision_plan_payload is not None
                assert int(await session.scalar(select(func.count()).select_from(DecisionRecord)) or 0) == 2
                assert int(await session.scalar(select(func.count()).select_from(RiskAssessmentRecord)) or 0) == 2
                assert int(await session.scalar(select(func.count()).select_from(ExecutionIntentRecord)) or 0) == 2

            detail = await reader.get_cycle(result.cycle_id)
            assert detail is not None
            assert detail.decision is None
            assert detail.risk_assessment is None
            assert detail.execution_intent is None
            assert [item.decision_index for item in detail.decision_results] == [0, 1]
            assert [item.decision["symbol"] for item in detail.decision_results] == ["BTC/USD", "ETH/USD"]

            explanation = build_cycle_explainability(detail)
            assert explanation is not None
            assert explanation.plan_rationale == "ordered"
            assert [item.decision_index for item in explanation.decisions] == [0, 1]
            assert [item.agent.symbol for item in explanation.decisions] == ["BTC/USD", "ETH/USD"]

            response = api_cycle_detail(detail)
            assert response.decision is None
            assert response.risk_assessment is None
            assert response.execution_intent is None
            assert [item.decision_index for item in response.decision_results] == [0, 1]

            page = await reader.list_cycles(limit=10, offset=0, order=AuditSortOrder.DESC)
            summary = page.items[0]
            assert summary.decision_action is None and summary.symbol is None
            assert summary.decision_count == 2
            assert summary.buy_count == 2
            assert summary.execution_count == 2
            assert summary.fill_count == 2
        finally:
            await database.close()

    asyncio.run(scenario())


def test_multi_decision_analytics_counts_trades_not_cycles() -> None:
    async def scenario() -> None:
        database = Database("sqlite+aiosqlite:///:memory:")
        await database.create_schema_for_tests()
        try:
            repository = SqlAlchemyCycleAuditRepository(database.sessions)
            analytics = SqlAlchemyPaperAnalyticsQueryService(database.sessions)
            result = multi_result()
            assert result.decision_plan_input is not None
            run_id = uuid4()
            initial_payload = result.decision_plan_input.portfolio_state.model_dump(mode="json")
            async with database.sessions() as session, session.begin():
                session.add(
                    PaperRunRecord(
                        paper_run_id=run_id,
                        campaign_id=None,
                        started_at=NOW,
                        ended_at=None,
                        market_type=None,
                        symbol=None,
                        execution_universe_payload=[
                            {"symbol": "BTC/USD", "market_type": "SPOT"},
                            {"symbol": "ETH/USD", "market_type": "SPOT"},
                        ],
                        resumed_from_paper_run_id=None,
                        recovery_version=None,
                        initial_portfolio_payload=initial_payload,
                        current_portfolio_payload=initial_payload,
                    )
                )

            assert await repository.record_for_run(run_id, result) is True
            report = await analytics.paper_analytics_for_run(run_id)

            assert report.summary.completed_cycle_count == 1
            assert report.summary.trade_count == 2
            assert report.summary.buy_trade_count == 2
            assert report.summary.sell_trade_count == 0
            assert len(report.points) == 2
        finally:
            await database.close()

    asyncio.run(scenario())


def test_legacy_singleton_cycle_uses_cycle_level_payload_fallbacks() -> None:
    async def scenario() -> None:
        database = Database("sqlite+aiosqlite:///:memory:")
        await database.create_schema_for_tests()
        try:
            cycle_id = uuid4()
            market_state = state("BTC/USD")
            before = portfolio("100")
            after = portfolio("100")
            agent_input = AgentInput(
                cycle_id=cycle_id,
                created_at=NOW,
                market_state=market_state,
                portfolio_state=before,
                aggressiveness=5,
            )
            decision = DecisionCandidate(
                decision_id=uuid4(),
                cycle_id=cycle_id,
                created_at=NOW,
                action=TradingAction.HOLD,
                symbol="BTC/USD",
                market_type=MarketType.SPOT,
                rationale="legacy singleton",
            )
            async with database.sessions() as session, session.begin():
                session.add(
                    CycleRecord(
                        cycle_id=cycle_id,
                        paper_run_id=None,
                        status="COMPLETED",
                        recorded_at=NOW,
                        result_digest="a" * 64,
                        failure_stage=None,
                        failure_error_type=None,
                        failure_timed_out=None,
                        market_state_id=market_state.market_state_id,
                        portfolio_state_before_id=before.portfolio_state_id,
                        portfolio_state_after_id=after.portfolio_state_id,
                        market_as_of=market_state.as_of,
                        portfolio_before_as_of=before.as_of,
                        portfolio_after_as_of=after.as_of,
                        market_selection_input_payload=None,
                        market_selection_payload=None,
                        agent_input_payload=agent_input.model_dump(mode="json"),
                        agent_tool_traces_payload=[],
                        portfolio_after_payload=after.model_dump(mode="json"),
                        decision_plan_input_payload=None,
                        decision_plan_payload=None,
                    )
                )
                session.add(
                    DecisionRecord(
                        decision_id=decision.decision_id,
                        cycle_id=cycle_id,
                        decision_index=0,
                        created_at=NOW,
                        action="HOLD",
                        symbol="BTC/USD",
                        payload=decision.model_dump(mode="json"),
                        agent_input_payload=None,
                        portfolio_after_payload=None,
                    )
                )

            reader = SqlAlchemyCycleAuditQueryService(database.sessions)
            detail = await reader.get_cycle(cycle_id)
            assert detail is not None
            assert detail.agent_input == agent_input.model_dump(mode="json")
            assert detail.portfolio_state_after == after.model_dump(mode="json")
            assert len(detail.decision_results) == 1
            assert detail.decision_results[0].agent_input == agent_input.model_dump(mode="json")
            assert (
                detail.decision_results[0].portfolio_state_after
                == after.model_dump(mode="json")
            )
        finally:
            await database.close()

    asyncio.run(scenario())
