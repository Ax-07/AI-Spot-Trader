import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from ai_spot_trader.control_plane import CampaignConfiguration
from ai_spot_trader.core.runtime import EngineRuntimeSnapshot
from ai_spot_trader.domain.enums import LLMModel, MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.discovery import MarketDiscoveryPolicy
from ai_spot_trader.persistence.control_plane import SqlAlchemyControlPlaneStore
from ai_spot_trader.persistence.db import Database
from ai_spot_trader.persistence.runs import PaperRunPage
from ai_spot_trader.sessions import SessionConflictError, SessionMarketMode, SessionService, SessionStatus


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 9, 25, 17, 0, tzinfo=UTC)


class EmptyPaperRunReader:
    async def list_runs(self, *, limit: int, offset: int, order) -> PaperRunPage:
        return PaperRunPage(items=(), total=0, limit=limit, offset=offset)

    async def latest_for_campaign(self, campaign_id: UUID):
        return None


class FakeRuntime:
    def __init__(self, store: SqlAlchemyControlPlaneStore) -> None:
        self.store = store
        self.active_campaign_id: UUID | None = None
        self.status = "UNAVAILABLE"
        self.resume_flags: list[bool] = []
        self.deactivated: list[UUID] = []
        self.cycles = 0

    def engine_snapshot(self) -> EngineRuntimeSnapshot:
        return EngineRuntimeSnapshot(
            configured=self.active_campaign_id is not None,
            status=self.status,
        )

    async def activate_campaign(self, campaign_id: UUID, *, resume: bool) -> EngineRuntimeSnapshot:
        assert await self.store.get_campaign(campaign_id) is not None
        self.active_campaign_id = campaign_id
        self.status = "STOPPED"
        self.resume_flags.append(resume)
        return self.engine_snapshot()

    async def start_engine(self) -> EngineRuntimeSnapshot:
        assert self.active_campaign_id is not None
        self.status = "RUNNING"
        return self.engine_snapshot()

    async def deactivate_campaign(self, campaign_id: UUID) -> EngineRuntimeSnapshot:
        assert self.active_campaign_id == campaign_id
        self.deactivated.append(campaign_id)
        self.active_campaign_id = None
        self.status = "UNAVAILABLE"
        return self.engine_snapshot()

    async def run_engine_cycle_once(self) -> EngineRuntimeSnapshot:
        assert self.active_campaign_id is not None
        self.cycles += 1
        self.status = "STOPPED"
        return self.engine_snapshot()


def _config(*, automatic: bool) -> CampaignConfiguration:
    market = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT)
    return CampaignConfiguration(
        llm_model=LLMModel.LUNA,
        aggressiveness=5,
        trading_cadence_seconds=30.0,
        paper_initial_capital=Decimal("1000"),
        paper_settlement_asset="USD",
        paper_executable_markets=(market,),
        market_discovery=(
            MarketDiscoveryPolicy(market_types=(MarketType.SPOT,)) if automatic else None
        ),
        paper_fee_rate=Decimal("0.001"),
        paper_spread_bps=Decimal("2"),
        paper_slippage_bps=Decimal("2"),
        risk_max_order_notional=Decimal("100"),
        risk_allowed_pairs=None if automatic else ("BTC/USD",),
        risk_allow_quantity_reduction=True,
        cycle_market_timeout_seconds=20.0,
        cycle_agent_timeout_seconds=35.0,
        cycle_broker_timeout_seconds=5.0,
    )


def test_session_projection_market_modes_and_running_edit_guard() -> None:
    async def scenario() -> None:
        database = Database("sqlite+aiosqlite:///:memory:")
        await database.create_schema_for_tests()
        store = SqlAlchemyControlPlaneStore(database.sessions, clock=FixedClock())
        runtime = FakeRuntime(store)
        service = SessionService(
            store=store,
            paper_run_reader=EmptyPaperRunReader(),
            runtime=runtime,  # type: ignore[arg-type]
        )
        try:
            automatic = await service.create_session(
                name="Auto",
                instructions="Cherche les opportunités.",
                configuration=_config(automatic=True),
                start_now=False,
            )
            manual = await service.create_session(
                name="Manuel",
                instructions="Travaille dans la liste autorisée.",
                configuration=_config(automatic=False),
                start_now=False,
            )
            assert automatic.status is SessionStatus.DRAFT
            assert automatic.market_mode is SessionMarketMode.AUTOMATIC_AI
            assert manual.market_mode is SessionMarketMode.MANUAL

            running = await service.start_session(automatic.session_id)
            assert running.status is SessionStatus.RUNNING
            assert runtime.resume_flags == [False]

            with pytest.raises(SessionConflictError, match="stop the running Session"):
                await service.update_session(
                    automatic.session_id,
                    name="Auto modifiée",
                    instructions=automatic.instructions,
                    configuration=automatic.configuration,
                )

            with pytest.raises(SessionConflictError, match="another Session is active"):
                await service.start_session(manual.session_id)
        finally:
            await database.close()

    asyncio.run(scenario())
