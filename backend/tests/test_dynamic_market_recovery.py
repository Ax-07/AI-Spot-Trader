import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import (
    AssetBalance,
    AssetPosition,
    ExecutableMarket,
    PortfolioState,
)
from ai_spot_trader.persistence.db import Database
from ai_spot_trader.persistence.dynamic_campaign_runs import DynamicCampaignPaperRunLifecycle
from ai_spot_trader.persistence.models import (
    CampaignRecord,
    PaperRunRecord,
    StrategyRecord,
    StrategyRevisionRecord,
)
from ai_spot_trader.portfolio.ledger import PaperPortfolioLedger

BASE = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
CAMPAIGN = UUID("289a0000-0000-0000-0000-000000000101")
STRATEGY = UUID("289a0000-0000-0000-0000-000000000201")
BTC = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT)
ETH = ExecutableMarket(symbol="ETH/USD", market_type=MarketType.SPOT)


class FixedClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


def portfolio(at: datetime, *, cash: str = "1000", eth: bool = False) -> PortfolioState:
    cash_value = Decimal(cash)
    positions = (
        (AssetPosition(asset="ETH", quantity=Decimal("1"), available=Decimal("1")),)
        if eth
        else ()
    )
    return PortfolioState(
        portfolio_state_id=UUID(int=301 if not eth else 302),
        as_of=at,
        settlement_asset="USD",
        balances=(AssetBalance(asset="USD", available=cash_value),),
        positions=positions,
        cash_available=cash_value,
        valuation_complete=False,
    )


async def seed_campaign(database: Database) -> None:
    async with database.sessions() as session, session.begin():
        session.add(
            StrategyRecord(
                strategy_id=STRATEGY,
                strategy_name="dynamic recovery",
                created_at=BASE,
                archived_at=None,
            )
        )
        session.add(
            StrategyRevisionRecord(
                strategy_id=STRATEGY,
                strategy_revision=1,
                strategy_prompt="test",
                strategy_prompt_digest="a" * 64,
                base_agent_contract_version="agent-contract-v1",
                created_at=BASE,
            )
        )
        session.add(
            CampaignRecord(
                campaign_id=CAMPAIGN,
                created_at=BASE,
                strategy_id=STRATEGY,
                strategy_revision=1,
                strategy_prompt_digest="a" * 64,
                base_agent_contract_version="agent-contract-v1",
                configuration_payload={},
                configuration_digest="b" * 64,
                experiment_protocol_version="paper-experiment-v4",
                experiment_digest="c" * 64,
            )
        )


def test_resume_reinjects_dynamic_held_market_outside_bootstrap() -> None:
    async def scenario() -> None:
        database = Database("sqlite+aiosqlite:///:memory:")
        await database.create_schema_for_tests()
        await seed_campaign(database)
        try:
            first_ledger = PaperPortfolioLedger(
                initial_state=portfolio(BASE),
                clock=FixedClock(BASE),
                settlement_asset="USD",
            )
            first = DynamicCampaignPaperRunLifecycle(
                database.sessions,
                campaign_id=CAMPAIGN,
                execution_universe=(BTC,),
                initial_portfolio=portfolio(BASE),
                portfolio_sink=first_ledger,
                resume=False,
                clock=FixedClock(BASE),
                settlement_asset="USD",
                dynamic_market_types=(MarketType.SPOT,),
            )
            first_run = await first.initialize()

            durable = portfolio(BASE + timedelta(minutes=1), cash="900", eth=True)
            async with database.sessions() as session, session.begin():
                row = await session.get(PaperRunRecord, first_run.paper_run_id)
                assert row is not None
                row.current_portfolio_payload = durable.model_dump(mode="json")
            await first.close()

            second_ledger = PaperPortfolioLedger(
                initial_state=portfolio(BASE + timedelta(hours=1)),
                clock=FixedClock(BASE + timedelta(hours=1)),
                settlement_asset="USD",
            )
            second = DynamicCampaignPaperRunLifecycle(
                database.sessions,
                campaign_id=CAMPAIGN,
                execution_universe=(BTC,),
                initial_portfolio=portfolio(BASE + timedelta(hours=1)),
                portfolio_sink=second_ledger,
                resume=True,
                clock=FixedClock(BASE + timedelta(hours=1)),
                settlement_asset="USD",
                dynamic_market_types=(MarketType.SPOT,),
            )
            resumed = await second.initialize()

            assert resumed.resumed_from_paper_run_id == first_run.paper_run_id
            assert resumed.execution_universe == (BTC, ETH)
            assert second_ledger.snapshot().positions[0].asset == "ETH"
        finally:
            await database.close()

    asyncio.run(scenario())
