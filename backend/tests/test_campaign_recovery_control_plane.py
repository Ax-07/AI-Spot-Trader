import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import (
    AssetBalance,
    AssetPosition,
    ExecutableMarket,
    PortfolioState,
)
from ai_spot_trader.persistence.campaign_runs import CampaignPaperRunLifecycle
from ai_spot_trader.persistence.db import Database
from ai_spot_trader.persistence.models import (
    CampaignRecord,
    PaperRunRecord,
    StrategyRecord,
    StrategyRevisionRecord,
)
from ai_spot_trader.persistence.runs import PAPER_LEDGER_RECOVERY_VERSION, PaperRunRecoveryError
from ai_spot_trader.portfolio.ledger import PaperPortfolioLedger

BASE = datetime(2026, 9, 23, 18, 0, tzinfo=UTC)
CAMPAIGN_A = UUID("189a0000-0000-0000-0000-000000000101")
CAMPAIGN_B = UUID("189a0000-0000-0000-0000-000000000102")
STRATEGY = UUID("189a0000-0000-0000-0000-000000000201")


class FixedClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


def _portfolio(at: datetime) -> PortfolioState:
    return PortfolioState(
        portfolio_state_id=UUID("189a0000-0000-0000-0000-000000000301"),
        as_of=at,
        balances=(AssetBalance(asset="USD", available=Decimal("1000")),),
    )


def _universe() -> tuple[ExecutableMarket, ...]:
    return (ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),)


async def _seed_campaign(database: Database, campaign_id: UUID) -> None:
    async with database.sessions() as session, session.begin():
        if await session.get(StrategyRecord, STRATEGY) is None:
            session.add(
                StrategyRecord(
                    strategy_id=STRATEGY,
                    strategy_name="test",
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
                campaign_id=campaign_id,
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


def test_same_campaign_resume_restores_ledger_and_links_run() -> None:
    async def scenario() -> None:
        database = Database("sqlite+aiosqlite:///:memory:")
        await database.create_schema_for_tests()
        await _seed_campaign(database, CAMPAIGN_A)
        try:
            first_ledger = PaperPortfolioLedger(
                initial_state=_portfolio(BASE), clock=FixedClock(BASE)
            )
            first = CampaignPaperRunLifecycle(
                database.sessions,
                campaign_id=CAMPAIGN_A,
                execution_universe=_universe(),
                initial_portfolio=_portfolio(BASE),
                portfolio_sink=first_ledger,
                resume=False,
                clock=FixedClock(BASE),
            )
            first_run = await first.initialize()
            assert first_run.campaign_id == CAMPAIGN_A
            assert first_run.recovery_version == PAPER_LEDGER_RECOVERY_VERSION

            durable = PortfolioState(
                portfolio_state_id=UUID("189a0000-0000-0000-0000-000000000302"),
                as_of=BASE + timedelta(minutes=1),
                balances=(AssetBalance(asset="USD", available=Decimal("900")),),
                positions=(
                    AssetPosition(asset="BTC", quantity=Decimal("1"), available=Decimal("1")),
                ),
            )
            async with database.sessions() as session, session.begin():
                row = await session.get(PaperRunRecord, first_run.paper_run_id)
                assert row is not None
                row.current_portfolio_payload = durable.model_dump(mode="json")
            await first.close()

            second_ledger = PaperPortfolioLedger(
                initial_state=_portfolio(BASE + timedelta(hours=1)),
                clock=FixedClock(BASE + timedelta(hours=1)),
            )
            second = CampaignPaperRunLifecycle(
                database.sessions,
                campaign_id=CAMPAIGN_A,
                execution_universe=_universe(),
                initial_portfolio=_portfolio(BASE + timedelta(hours=1)),
                portfolio_sink=second_ledger,
                resume=True,
                clock=FixedClock(BASE + timedelta(hours=1)),
            )
            resumed = await second.initialize()
            assert resumed.campaign_id == CAMPAIGN_A
            assert resumed.resumed_from_paper_run_id == first_run.paper_run_id
            assert second_ledger.snapshot().positions[0].asset == "BTC"
        finally:
            await database.close()

    asyncio.run(scenario())


def test_new_campaign_cannot_resume_another_campaign_run() -> None:
    async def scenario() -> None:
        database = Database("sqlite+aiosqlite:///:memory:")
        await database.create_schema_for_tests()
        await _seed_campaign(database, CAMPAIGN_A)
        await _seed_campaign(database, CAMPAIGN_B)
        try:
            ledger = PaperPortfolioLedger(initial_state=_portfolio(BASE), clock=FixedClock(BASE))
            first = CampaignPaperRunLifecycle(
                database.sessions,
                campaign_id=CAMPAIGN_A,
                execution_universe=_universe(),
                initial_portfolio=_portfolio(BASE),
                portfolio_sink=ledger,
                resume=False,
                clock=FixedClock(BASE),
            )
            await first.initialize()
            await first.close()

            second_ledger = PaperPortfolioLedger(
                initial_state=_portfolio(BASE + timedelta(hours=1)),
                clock=FixedClock(BASE + timedelta(hours=1)),
            )
            wrong_campaign = CampaignPaperRunLifecycle(
                database.sessions,
                campaign_id=CAMPAIGN_B,
                execution_universe=_universe(),
                initial_portfolio=_portfolio(BASE + timedelta(hours=1)),
                portfolio_sink=second_ledger,
                resume=True,
                clock=FixedClock(BASE + timedelta(hours=1)),
            )
            with pytest.raises(PaperRunRecoveryError, match="no PAPER run"):
                await wrong_campaign.initialize()
        finally:
            await database.close()

    asyncio.run(scenario())
