import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ai_spot_trader.core.config import Settings
from ai_spot_trader.core.control_plane_runtime import (
    CampaignActivationConflictError,
    CampaignRuntimeManager,
)


class NeverStore:
    async def get_campaign(self, campaign_id: object) -> object:
        raise AssertionError("RUNNING conflict must be rejected before reading campaign")


class NullDatabase:
    async def close(self) -> None:
        return None


def test_activation_is_refused_while_canonical_engine_is_running() -> None:
    manager = CampaignRuntimeManager(
        settings=Settings(_env_file=None, environment="test"),
        control_plane_store=NeverStore(),  # type: ignore[arg-type]
        database=NullDatabase(),  # type: ignore[arg-type]
        paper_run_reader=SimpleNamespace(),  # type: ignore[arg-type]
        audit_reader=SimpleNamespace(),  # type: ignore[arg-type]
        analytics_reader=SimpleNamespace(),  # type: ignore[arg-type]
    )
    manager._active = SimpleNamespace(  # type: ignore[assignment]
        trading_engine=SimpleNamespace(is_running=True)
    )

    async def scenario() -> None:
        with pytest.raises(CampaignActivationConflictError, match="RUNNING"):
            await manager.activate_campaign(uuid4(), resume=False)

    asyncio.run(scenario())
