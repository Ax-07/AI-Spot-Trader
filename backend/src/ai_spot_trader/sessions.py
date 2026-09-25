from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from ai_spot_trader.control_plane import CampaignConfiguration
from ai_spot_trader.core.control_plane_runtime import (
    CampaignActivationConflictError,
    CampaignRuntimeManager,
)
from ai_spot_trader.core.runtime import EngineRuntimeSnapshot
from ai_spot_trader.persistence.campaign_runs import (
    CampaignPaperRunQueryService,
    CampaignPaperRunView,
)
from ai_spot_trader.persistence.control_plane import (
    CampaignView,
    ControlPlaneConflictError,
    ControlPlaneNotFoundError,
    ControlPlaneStore,
    StrategyRevisionView,
    StrategyView,
)


class SessionStatus(StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    RESUMABLE = "RESUMABLE"
    ARCHIVED = "ARCHIVED"


class SessionMarketMode(StrEnum):
    AUTOMATIC_AI = "AUTOMATIC_AI"
    MANUAL = "MANUAL"


class SessionConflictError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SessionView:
    session_id: UUID
    name: str
    created_at: datetime
    last_activity_at: datetime
    archived_at: datetime | None
    status: SessionStatus
    market_mode: SessionMarketMode
    instructions: str
    configuration: CampaignConfiguration
    current_campaign_id: UUID
    current_campaign_created_at: datetime
    current_strategy_revision: int
    has_history: bool
    current_campaign_has_history: bool
    latest_paper_run: CampaignPaperRunView | None
    engine: EngineRuntimeSnapshot | None


class SessionService:
    """User-facing façade over Strategy/Revision/Campaign/PAPER-run canonical facts."""

    def __init__(
        self,
        *,
        store: ControlPlaneStore,
        paper_run_reader: CampaignPaperRunQueryService,
        runtime: CampaignRuntimeManager,
    ) -> None:
        self._store = store
        self._paper_run_reader = paper_run_reader
        self._runtime = runtime

    async def list_sessions(self, *, include_archived: bool = False) -> tuple[SessionView, ...]:
        strategies = await self._store.list_strategies()
        campaigns = await self._store.list_campaigns()
        revisions: dict[tuple[UUID, int], StrategyRevisionView] = {}
        campaigns_by_strategy: dict[UUID, list[CampaignView]] = {}
        for campaign in campaigns:
            campaigns_by_strategy.setdefault(campaign.strategy_id, []).append(campaign)
        latest_runs_by_campaign: dict[UUID, CampaignPaperRunView] = {}
        for campaign in campaigns:
            latest_run = await self._paper_run_reader.latest_for_campaign(campaign.campaign_id)
            if latest_run is not None:
                latest_runs_by_campaign[campaign.campaign_id] = latest_run
        active_campaign = await self._active_campaign()

        result: list[SessionView] = []
        for strategy in strategies:
            if strategy.archived_at is not None and not include_archived:
                continue
            strategy_campaigns = campaigns_by_strategy.get(strategy.strategy_id, [])
            if not strategy_campaigns:
                # A legacy partial Strategy is a technical fact, not a complete user Session.
                continue
            current_campaign = strategy_campaigns[0]
            key = (strategy.strategy_id, current_campaign.strategy_revision)
            revision = revisions.get(key)
            if revision is None:
                revision = await self._store.get_revision(*key)
                if revision is None:
                    raise ControlPlaneNotFoundError("session strategy revision not found")
                revisions[key] = revision
            strategy_runs = tuple(
                latest_runs_by_campaign[item.campaign_id]
                for item in strategy_campaigns
                if item.campaign_id in latest_runs_by_campaign
            )
            result.append(
                self._project(
                    strategy=strategy,
                    campaigns=tuple(strategy_campaigns),
                    current_campaign=current_campaign,
                    revision=revision,
                    all_runs=strategy_runs,
                    active_campaign=active_campaign,
                )
            )
        return tuple(
            sorted(
                result,
                key=lambda item: (item.last_activity_at, item.created_at, str(item.session_id)),
                reverse=True,
            )
        )

    async def get_session(self, session_id: UUID, *, include_archived: bool = True) -> SessionView:
        strategy = await self._store.get_strategy(session_id)
        if strategy is None:
            raise ControlPlaneNotFoundError("session not found")
        if strategy.archived_at is not None and not include_archived:
            raise ControlPlaneNotFoundError("session not found")
        campaigns = tuple(
            item
            for item in await self._store.list_campaigns()
            if item.strategy_id == session_id
        )
        if not campaigns:
            raise ControlPlaneNotFoundError("session campaign not found")
        current_campaign = campaigns[0]
        revision = await self._store.get_revision(session_id, current_campaign.strategy_revision)
        if revision is None:
            raise ControlPlaneNotFoundError("session strategy revision not found")
        runs_list: list[CampaignPaperRunView] = []
        for campaign in campaigns:
            run = await self._paper_run_reader.latest_for_campaign(campaign.campaign_id)
            if run is not None:
                runs_list.append(run)
        runs = tuple(runs_list)
        return self._project(
            strategy=strategy,
            campaigns=campaigns,
            current_campaign=current_campaign,
            revision=revision,
            all_runs=runs,
            active_campaign=await self._active_campaign(),
        )

    async def create_session(
        self,
        *,
        name: str,
        instructions: str,
        configuration: CampaignConfiguration,
        start_now: bool,
    ) -> SessionView:
        if start_now and self._runtime.active_campaign_id is not None:
            raise SessionConflictError(
                "another Session is active; stop it before creating and starting a new Session"
            )
        bundle = await self._store.create_session_bundle(
            name=name,
            strategy_prompt=instructions,
            configuration=configuration,
        )
        if start_now:
            await self._runtime.activate_campaign(bundle.campaign.campaign_id, resume=False)
            await self._runtime.start_engine()
        return await self.get_session(bundle.strategy.strategy_id)

    async def update_session(
        self,
        session_id: UUID,
        *,
        name: str,
        instructions: str,
        configuration: CampaignConfiguration,
    ) -> SessionView:
        await self._prepare_mutation(session_id)
        await self._store.update_session_bundle(
            session_id,
            name=name,
            strategy_prompt=instructions,
            configuration=configuration,
        )
        return await self.get_session(session_id)

    async def duplicate_session(
        self,
        session_id: UUID,
        *,
        name: str | None = None,
    ) -> SessionView:
        source = await self.get_session(session_id)
        if source.archived_at is not None:
            raise SessionConflictError("archived Session cannot be duplicated from the normal UX")
        bundle = await self._store.create_session_bundle(
            name=name.strip() if name is not None and name.strip() else f"{source.name} - copie",
            strategy_prompt=source.instructions,
            configuration=source.configuration,
        )
        return await self.get_session(bundle.strategy.strategy_id)

    async def archive_session(self, session_id: UUID) -> SessionView:
        await self._prepare_mutation(session_id)
        await self._store.archive_strategy(session_id)
        return await self.get_session(session_id)

    async def start_session(self, session_id: UUID) -> SessionView:
        session = await self.get_session(session_id)
        self._ensure_not_archived(session)
        active = await self._active_campaign()
        if active is not None:
            if active.strategy_id != session_id:
                raise SessionConflictError("another Session is active")
            if active.campaign_id != session.current_campaign_id:
                raise SessionConflictError("an older Campaign version is active")
            snapshot = self._runtime.engine_snapshot()
            if snapshot.status == "RUNNING":
                raise SessionConflictError("Session is already running")
            await self._runtime.start_engine()
            return await self.get_session(session_id)

        if session.current_campaign_has_history:
            raise SessionConflictError(
                "Session Campaign has already run; explicit resume is required"
            )
        await self._runtime.activate_campaign(session.current_campaign_id, resume=False)
        await self._runtime.start_engine()
        return await self.get_session(session_id)

    async def resume_session(self, session_id: UUID) -> SessionView:
        session = await self.get_session(session_id)
        self._ensure_not_archived(session)
        active = await self._active_campaign()
        if active is not None:
            if active.strategy_id != session_id:
                raise SessionConflictError("another Session is active")
            if active.campaign_id != session.current_campaign_id:
                raise SessionConflictError("an older Campaign version is active")
            snapshot = self._runtime.engine_snapshot()
            if snapshot.status == "RUNNING":
                raise SessionConflictError("Session is already running")
            await self._runtime.start_engine()
            return await self.get_session(session_id)

        if not session.current_campaign_has_history:
            raise SessionConflictError("Session has no PAPER run to resume")
        await self._runtime.activate_campaign(session.current_campaign_id, resume=True)
        await self._runtime.start_engine()
        return await self.get_session(session_id)

    async def stop_session(self, session_id: UUID) -> SessionView:
        session = await self.get_session(session_id)
        self._ensure_not_archived(session)
        active = await self._active_campaign()
        if active is None or active.strategy_id != session_id:
            raise SessionConflictError("Session is not active")
        await self._runtime.deactivate_campaign(active.campaign_id)
        return await self.get_session(session_id)

    async def run_cycle(self, session_id: UUID) -> SessionView:
        session = await self.get_session(session_id)
        self._ensure_not_archived(session)
        active = await self._active_campaign()
        if active is not None:
            if active.strategy_id != session_id:
                raise SessionConflictError("another Session is active")
            if active.campaign_id != session.current_campaign_id:
                raise SessionConflictError("an older Campaign version is active")
        else:
            await self._runtime.activate_campaign(
                session.current_campaign_id,
                resume=session.current_campaign_has_history,
            )
        await self._runtime.run_engine_cycle_once()
        return await self.get_session(session_id)

    async def _prepare_mutation(self, session_id: UUID) -> None:
        session = await self.get_session(session_id)
        self._ensure_not_archived(session)
        active = await self._active_campaign()
        if active is None or active.strategy_id != session_id:
            return
        snapshot = self._runtime.engine_snapshot()
        if snapshot.status == "RUNNING":
            raise SessionConflictError(
                "stop the running Session before modifying or archiving it"
            )
        await self._runtime.deactivate_campaign(active.campaign_id)

    async def _active_campaign(self) -> CampaignView | None:
        campaign_id = self._runtime.active_campaign_id
        if campaign_id is None:
            return None
        return await self._store.get_campaign(campaign_id)

    @staticmethod
    def _ensure_not_archived(session: SessionView) -> None:
        if session.archived_at is not None:
            raise SessionConflictError("archived Session cannot be operated")

    def _project(
        self,
        *,
        strategy: StrategyView,
        campaigns: tuple[CampaignView, ...],
        current_campaign: CampaignView,
        revision: StrategyRevisionView,
        all_runs: tuple[CampaignPaperRunView, ...],
        active_campaign: CampaignView | None,
    ) -> SessionView:
        campaign_ids = {item.campaign_id for item in campaigns}
        session_runs = tuple(
            run for run in all_runs if run.campaign_id in campaign_ids
        )
        current_runs = tuple(
            run for run in session_runs if run.campaign_id == current_campaign.campaign_id
        )
        latest_run = session_runs[0] if session_runs else None
        latest_current_run = current_runs[0] if current_runs else None
        active_for_session = (
            active_campaign is not None and active_campaign.strategy_id == strategy.strategy_id
        )
        engine = self._runtime.engine_snapshot() if active_for_session else None

        if strategy.archived_at is not None:
            status = SessionStatus.ARCHIVED
        elif active_for_session and engine is not None and engine.status == "RUNNING":
            status = SessionStatus.RUNNING
        elif active_for_session:
            status = SessionStatus.READY
        elif latest_current_run is not None and latest_current_run.ended_at is None:
            status = SessionStatus.RESUMABLE
        elif session_runs:
            status = SessionStatus.STOPPED
        else:
            status = SessionStatus.DRAFT

        activity_candidates = [strategy.created_at, current_campaign.created_at]
        for run in session_runs:
            activity_candidates.append(run.started_at)
            if run.ended_at is not None:
                activity_candidates.append(run.ended_at)
        if strategy.archived_at is not None:
            activity_candidates.append(strategy.archived_at)

        return SessionView(
            session_id=strategy.strategy_id,
            name=strategy.strategy_name,
            created_at=strategy.created_at,
            last_activity_at=max(activity_candidates),
            archived_at=strategy.archived_at,
            status=status,
            market_mode=(
                SessionMarketMode.AUTOMATIC_AI
                if current_campaign.configuration.market_discovery is not None
                else SessionMarketMode.MANUAL
            ),
            instructions=revision.strategy_prompt,
            configuration=current_campaign.configuration,
            current_campaign_id=current_campaign.campaign_id,
            current_campaign_created_at=current_campaign.created_at,
            current_strategy_revision=current_campaign.strategy_revision,
            has_history=bool(session_runs),
            current_campaign_has_history=bool(current_runs),
            latest_paper_run=latest_run,
            engine=engine,
        )


__all__ = [
    "SessionConflictError",
    "SessionMarketMode",
    "SessionService",
    "SessionStatus",
    "SessionView",
]
