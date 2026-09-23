import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from ai_spot_trader.control_plane import CampaignConfiguration
from ai_spot_trader.domain.enums import LLMModel, MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.persistence.control_plane import (
    ControlPlaneConflictError,
    SqlAlchemyControlPlaneStore,
)
from ai_spot_trader.persistence.db import Database


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 9, 23, 18, 0, tzinfo=UTC)


def _config() -> CampaignConfiguration:
    return CampaignConfiguration(
        llm_model=LLMModel.LUNA,
        aggressiveness=5,
        trading_cadence_seconds=30.0,
        paper_initial_capital=Decimal("1000"),
        paper_settlement_asset="USD",
        paper_executable_markets=(
            ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),
        ),
        paper_fee_rate=Decimal("0.0026"),
        paper_spread_bps=Decimal("5"),
        paper_slippage_bps=Decimal("3"),
        risk_max_order_notional=Decimal("100"),
        risk_allowed_pairs=("BTC/USD",),
        risk_allow_quantity_reduction=True,
        cycle_market_timeout_seconds=20.0,
        cycle_agent_timeout_seconds=35.0,
        cycle_broker_timeout_seconds=5.0,
    )


def test_strategy_revisions_are_immutable_and_campaign_snapshots_revision() -> None:
    async def scenario() -> None:
        database = Database("sqlite+aiosqlite:///:memory:")
        await database.create_schema_for_tests()
        store = SqlAlchemyControlPlaneStore(database.sessions, clock=FixedClock())
        try:
            strategy, first = await store.create_strategy(
                name="Momentum",
                strategy_prompt="Cherche une tendance claire.",
            )
            first_digest = first.strategy_prompt_digest
            renamed = await store.rename_strategy(strategy.strategy_id, name="Momentum v2")
            assert renamed.strategy_name == "Momentum v2"
            renamed_revision = await store.get_revision(strategy.strategy_id, 1)
            assert renamed_revision is not None
            assert renamed_revision.strategy_prompt_digest == first_digest

            second = await store.create_revision(
                strategy.strategy_id,
                strategy_prompt="Cherche une tendance claire et confirme la liquidite.",
            )
            assert second.strategy_revision == 2
            assert second.strategy_prompt_digest != first_digest
            unchanged = await store.get_revision(strategy.strategy_id, 1)
            assert unchanged is not None
            assert unchanged.strategy_prompt_digest == first_digest

            campaign = await store.create_campaign(
                strategy_id=strategy.strategy_id,
                strategy_revision=1,
                configuration=_config(),
            )
            assert campaign.strategy_prompt_digest == first_digest
            assert campaign.configuration_digest == _config().digest
            assert campaign.experiment_protocol_version == "paper-experiment-v4"

            archived = await store.archive_strategy(strategy.strategy_id)
            assert archived.archived_at is not None
            with pytest.raises(ControlPlaneConflictError):
                await store.create_revision(
                    strategy.strategy_id,
                    strategy_prompt="Nouvelle revision interdite.",
                )
            with pytest.raises(ControlPlaneConflictError):
                await store.create_campaign(
                    strategy_id=strategy.strategy_id,
                    strategy_revision=2,
                    configuration=_config(),
                )
        finally:
            await database.close()

    asyncio.run(scenario())
