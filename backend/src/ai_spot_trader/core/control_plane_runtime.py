from __future__ import annotations

import asyncio
from uuid import UUID

from ai_spot_trader.campaign_composition import CampaignRuntimeComposition, build_campaign_runtime
from ai_spot_trader.core.config import Settings
from ai_spot_trader.core.runtime import (
    EngineRuntimeSnapshot,
    TradingEngineAlreadyRunningError,
    TradingEngineCycleFailedError,
    TradingEngineUnavailableError,
)
from ai_spot_trader.persistence.analytics import PaperAnalyticsReader
from ai_spot_trader.persistence.campaign_runs import CampaignPaperRunQueryService
from ai_spot_trader.persistence.control_plane import (
    ControlPlaneNotFoundError,
    ControlPlaneStore,
)
from ai_spot_trader.persistence.db import Database
from ai_spot_trader.persistence.query import CycleAuditReader
from ai_spot_trader.persistence.runs import PaperRunRecoveryError


class CampaignActivationError(RuntimeError):
    pass


class CampaignActivationConflictError(CampaignActivationError):
    pass


class CampaignRuntimeManager:
    """Keep backend infrastructure alive while owning at most one active PAPER runtime."""

    def __init__(
        self,
        *,
        settings: Settings,
        control_plane_store: ControlPlaneStore,
        database: Database,
        paper_run_reader: CampaignPaperRunQueryService,
        audit_reader: CycleAuditReader,
        analytics_reader: PaperAnalyticsReader,
    ) -> None:
        self._settings = settings
        self.control_plane_store = control_plane_store
        self._database = database
        self.paper_run_reader = paper_run_reader
        self.audit_reader = audit_reader
        self.analytics_reader = analytics_reader
        self._active: CampaignRuntimeComposition | None = None
        self._active_campaign_id: UUID | None = None
        self._command_lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Start the Control Plane without implicitly activating any campaign."""

        return None

    @property
    def active_campaign_id(self) -> UUID | None:
        return self._active_campaign_id

    @property
    def active_chat_service(self) -> object | None:
        return None if self._active is None else self._active.chat_service

    @property
    def portfolio(self) -> object | None:
        return None if self._active is None else self._active.runtime.portfolio

    @property
    def paper_run_lifecycle(self) -> object | None:
        return None if self._active is None else self._active.runtime.paper_run_lifecycle

    @property
    def current_paper_run_id(self) -> UUID | None:
        return None if self._active is None else self._active.runtime.current_paper_run_id

    def engine_snapshot(self) -> EngineRuntimeSnapshot:
        if self._active is None:
            return EngineRuntimeSnapshot(configured=False, status="UNAVAILABLE")
        return self._active.runtime.engine_snapshot()

    async def start_engine(self) -> EngineRuntimeSnapshot:
        return await self._require_active().runtime.start_engine()

    async def stop_engine(self) -> EngineRuntimeSnapshot:
        return await self._require_active().runtime.stop_engine()

    async def run_engine_cycle_once(self) -> EngineRuntimeSnapshot:
        return await self._require_active().runtime.run_engine_cycle_once()

    async def activate_campaign(
        self,
        campaign_id: UUID,
        *,
        resume: bool,
    ) -> EngineRuntimeSnapshot:
        async with self._command_lock:
            if self._active is not None and self._active.trading_engine.is_running:
                raise CampaignActivationConflictError(
                    "cannot activate or resume a campaign while the engine is RUNNING"
                )

            campaign = await self.control_plane_store.get_campaign(campaign_id)
            if campaign is None:
                raise ControlPlaneNotFoundError("campaign not found")
            revision = await self.control_plane_store.get_revision(
                campaign.strategy_id,
                campaign.strategy_revision,
            )
            if revision is None:
                raise CampaignActivationError("campaign strategy revision is unavailable")
            if revision.strategy_prompt_digest != campaign.strategy_prompt_digest:
                raise CampaignActivationError("campaign strategy digest mismatch")
            if revision.base_agent_contract_version != campaign.base_agent_contract_version:
                raise CampaignActivationError("campaign Agent contract version mismatch")

            latest = await self.paper_run_reader.latest_for_campaign(campaign_id)
            if resume and latest is None:
                raise CampaignActivationConflictError("campaign has no PAPER run to resume")
            if not resume and latest is not None:
                raise CampaignActivationConflictError(
                    "campaign has already run; explicit resume is required"
                )

            if self._active is not None:
                await self._active.runtime.close()
                self._active = None
                self._active_campaign_id = None

            try:
                composition = build_campaign_runtime(
                    self._settings,
                    campaign=campaign,
                    revision=revision,
                    resume=resume,
                )
            except Exception as exc:
                raise CampaignActivationError(
                    "campaign runtime composition failed"
                ) from exc

            try:
                await composition.runtime.initialize()
            except PaperRunRecoveryError:
                await composition.runtime.close()
                raise
            except Exception as exc:
                await composition.runtime.close()
                raise CampaignActivationError(
                    "campaign runtime initialization failed"
                ) from exc

            self._active = composition
            self._active_campaign_id = campaign_id
            return composition.runtime.engine_snapshot()

    async def close(self) -> None:
        async with self._command_lock:
            try:
                if self._active is not None:
                    await self._active.runtime.close()
                    self._active = None
                    self._active_campaign_id = None
            finally:
                await self._database.close()

    def _require_active(self) -> CampaignRuntimeComposition:
        if self._active is None:
            raise TradingEngineUnavailableError("trading engine is not configured")
        return self._active


__all__ = [
    "CampaignActivationConflictError",
    "CampaignActivationError",
    "CampaignRuntimeManager",
    "TradingEngineAlreadyRunningError",
    "TradingEngineCycleFailedError",
    "TradingEngineUnavailableError",
]
