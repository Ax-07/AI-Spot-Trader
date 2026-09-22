import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import (
    AssetBalance,
    ExecutableMarket,
    MarketSelection,
    MarketSelectionInput,
    PortfolioState,
    market_selection_digest,
)
from ai_spot_trader.persistence.db import Database
from ai_spot_trader.persistence.query import SqlAlchemyCycleAuditQueryService
from ai_spot_trader.persistence.repository import (
    SqlAlchemyCycleAuditRepository,
    _result_digest,
)
from ai_spot_trader.persistence.runs import (
    SqlAlchemyPaperRunLifecycle,
    SqlAlchemyPaperRunQueryService,
)
from ai_spot_trader.trading.engine import (
    TradingCycleFailure,
    TradingCycleResult,
    TradingCycleStage,
    TradingCycleStatus,
)

NOW = datetime(2026, 9, 22, 15, 0, tzinfo=UTC)
RUN = UUID("10000000-0000-0000-0000-000000000001")
CYCLE = UUID("20000000-0000-0000-0000-000000000002")
SELECTION = UUID("30000000-0000-0000-0000-000000000003")


def universe() -> tuple[ExecutableMarket, ...]:
    return (
        ExecutableMarket(
            symbol="ETH/USD",
            market_type=MarketType.PERPETUAL,
        ),
        ExecutableMarket(
            symbol="BTC/USD",
            market_type=MarketType.SPOT,
        ),
    )


def selection_input() -> MarketSelectionInput:
    return MarketSelectionInput(
        cycle_id=CYCLE,
        created_at=NOW,
        portfolio_state=PortfolioState(
            portfolio_state_id=UUID(int=99),
            as_of=NOW,
            balances=(
                AssetBalance(
                    asset="USD",
                    available=Decimal("1000"),
                ),
            ),
        ),
        executable_markets=universe(),
        aggressiveness=5,
    )


def selection(symbol: str, market_type: MarketType) -> MarketSelection:
    digest = market_selection_digest(
        selection_id=SELECTION,
        cycle_id=CYCLE,
        selected_at=NOW,
        symbol=symbol,
        market_type=market_type,
        tool_traces=(),
    )
    return MarketSelection(
        selection_id=SELECTION,
        cycle_id=CYCLE,
        selected_at=NOW,
        symbol=symbol,
        market_type=market_type,
        selection_digest=digest,
    )


def failed_result(selected: MarketSelection) -> TradingCycleResult:
    return TradingCycleResult(
        cycle_id=CYCLE,
        status=TradingCycleStatus.FAILED,
        failure=TradingCycleFailure(
            stage=TradingCycleStage.MARKET,
            error_type="KrakenConnectionError",
        ),
        market_selection_input=selection_input(),
        market_selection=selected,
    )


def test_cycle_digest_changes_when_market_selection_changes() -> None:
    spot = failed_result(selection("BTC/USD", MarketType.SPOT))
    perpetual = failed_result(selection("ETH/USD", MarketType.PERPETUAL))

    assert _result_digest(spot, paper_run_id=RUN) != _result_digest(
        perpetual,
        paper_run_id=RUN,
    )


def test_failed_cycle_after_selection_persists_selection_and_run_universe() -> None:
    async def scenario() -> None:
        database = Database("sqlite+aiosqlite:///:memory:")
        await database.create_schema_for_tests()
        lifecycle = SqlAlchemyPaperRunLifecycle(
            database.sessions,
            execution_universe=universe(),
            run_id_factory=lambda: RUN,
        )
        try:
            run = await lifecycle.initialize()
            assert run.market_type is None
            assert run.symbol is None
            assert run.execution_universe == universe()

            repository = SqlAlchemyCycleAuditRepository(database.sessions)
            await repository.record_for_run(
                RUN,
                failed_result(selection("ETH/USD", MarketType.PERPETUAL)),
            )
            detail = await SqlAlchemyCycleAuditQueryService(
                database.sessions
            ).get_cycle(CYCLE)
            assert detail is not None
            assert detail.market_selection is not None
            assert detail.market_selection["symbol"] == "ETH/USD"
            assert detail.market_selection["market_type"] == "PERPETUAL"
            assert detail.agent_input is None

            reread = await SqlAlchemyPaperRunQueryService(
                database.sessions
            ).get_run(RUN)
            assert reread is not None
            assert reread.market_type is None
            assert reread.symbol is None
            assert reread.execution_universe == universe()
        finally:
            await database.close()

    asyncio.run(scenario())
