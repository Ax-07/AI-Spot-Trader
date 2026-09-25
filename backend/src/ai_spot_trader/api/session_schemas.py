from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ai_spot_trader.api.schemas import EngineStatusResponse
from ai_spot_trader.control_plane import CampaignConfiguration
from ai_spot_trader.sessions import SessionMarketMode, SessionStatus


class SessionApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionCreateRequest(SessionApiModel):
    name: str = Field(min_length=1, max_length=120)
    instructions: str = Field(min_length=1)
    configuration: CampaignConfiguration
    start_now: bool = False


class SessionUpdateRequest(SessionApiModel):
    name: str = Field(min_length=1, max_length=120)
    instructions: str = Field(min_length=1)
    configuration: CampaignConfiguration


class SessionDuplicateRequest(SessionApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)


class SessionPaperRunSummary(SessionApiModel):
    paper_run_id: UUID
    started_at: datetime
    ended_at: datetime | None
    resumed_from_paper_run_id: UUID | None


class SessionResponse(SessionApiModel):
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
    current_strategy_revision: int = Field(ge=1)
    has_history: bool
    current_campaign_has_history: bool
    latest_paper_run: SessionPaperRunSummary | None
    engine: EngineStatusResponse | None
