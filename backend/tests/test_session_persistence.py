import asyncio
from datetime import UTC, datetime
from decimal import Decimal

from ai_spot_trader.control_plane import CampaignConfiguration
from ai_spot_trader.domain.enums import LLMModel, MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.discovery import MarketDiscoveryPolicy
from ai_spot_trader.persistence.control_plane import SqlAlchemyControlPlaneStore
from ai_spot_trader.persistence.db import Database


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 9, 25, 16, 0, tzinfo=UTC)


def _config(*, aggressiveness: int = 5, automatic: bool = False) -> CampaignConfiguration:
    market = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT)
    return CampaignConfiguration(
        llm_model=LLMModel.LUNA,
        aggressiveness=aggressiveness,
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


def test_session_bundle_create_and_versioned_update_preserve_history() -> None:
    async def scenario() -> None:
        database = Database("sqlite+aiosqlite:///:memory:")
        await database.create_schema_for_tests()
        store = SqlAlchemyControlPlaneStore(database.sessions, clock=FixedClock())
        try:
            created = await store.create_session_bundle(
                name="Session Alpha",
                strategy_prompt="Cherche les meilleures opportunités.",
                configuration=_config(automatic=True),
            )
            assert created.strategy.latest_revision == 1
            assert created.campaign.strategy_revision == 1
            assert created.campaign.configuration.market_discovery is not None

            rename_only = await store.update_session_bundle(
                created.strategy.strategy_id,
                name="Session Alpha renommée",
                strategy_prompt="Cherche les meilleures opportunités.",
                configuration=_config(automatic=True),
            )
            assert rename_only.strategy.latest_revision == 1
            assert rename_only.campaign.campaign_id == created.campaign.campaign_id

            prompt_update = await store.update_session_bundle(
                created.strategy.strategy_id,
                name="Session Alpha renommée",
                strategy_prompt="Cherche les meilleures opportunités et privilégie les signaux nets.",
                configuration=_config(automatic=True),
            )
            assert prompt_update.revision.strategy_revision == 2
            assert prompt_update.campaign.strategy_revision == 2
            assert prompt_update.campaign.campaign_id != created.campaign.campaign_id

            config_update = await store.update_session_bundle(
                created.strategy.strategy_id,
                name="Session Alpha renommée",
                strategy_prompt="Cherche les meilleures opportunités et privilégie les signaux nets.",
                configuration=_config(aggressiveness=7, automatic=True),
            )
            assert config_update.revision.strategy_revision == 2
            assert config_update.campaign.strategy_revision == 2
            assert config_update.campaign.campaign_id != prompt_update.campaign.campaign_id

            revision_one = await store.get_revision(created.strategy.strategy_id, 1)
            revision_two = await store.get_revision(created.strategy.strategy_id, 2)
            campaigns = [
                item
                for item in await store.list_campaigns()
                if item.strategy_id == created.strategy.strategy_id
            ]
            assert revision_one is not None
            assert revision_two is not None
            assert revision_one.strategy_prompt_digest != revision_two.strategy_prompt_digest
            assert len(campaigns) == 3
            assert {item.campaign_id for item in campaigns} == {
                created.campaign.campaign_id,
                prompt_update.campaign.campaign_id,
                config_update.campaign.campaign_id,
            }
            assert campaigns[0].campaign_id == config_update.campaign.campaign_id
        finally:
            await database.close()

    asyncio.run(scenario())
