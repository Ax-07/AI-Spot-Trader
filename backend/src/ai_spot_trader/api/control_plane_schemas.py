from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ai_spot_trader.api.schemas import EngineStatusResponse
from ai_spot_trader.control_plane import CampaignConfiguration


class ControlApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StrategyCreateRequest(ControlApiModel):
    strategy_name: str = Field(min_length=1, max_length=120)
    strategy_prompt: str = Field(min_length=1)


class StrategyRenameRequest(ControlApiModel):
    strategy_name: str = Field(min_length=1, max_length=120)


class StrategyRevisionCreateRequest(ControlApiModel):
    strategy_prompt: str = Field(min_length=1)


class StrategyResponse(ControlApiModel):
    strategy_id: UUID
    strategy_name: str
    created_at: datetime
    archived_at: datetime | None = None
    latest_revision: int | None = None


class StrategyRevisionResponse(ControlApiModel):
    strategy_id: UUID
    strategy_revision: int
    strategy_prompt: str
    strategy_prompt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    base_agent_contract_version: str
    created_at: datetime


class StrategyCreateResponse(ControlApiModel):
    strategy: StrategyResponse
    revision: StrategyRevisionResponse


class StrategyRevisionComparisonResponse(ControlApiModel):
    strategy_id: UUID
    left_revision: int
    right_revision: int
    left_digest: str
    right_digest: str
    identical: bool
    unified_diff: str


class CampaignCreateRequest(ControlApiModel):
    strategy_id: UUID
    strategy_revision: int = Field(ge=1)
    configuration: CampaignConfiguration


class CampaignResponse(ControlApiModel):
    campaign_id: UUID
    created_at: datetime
    strategy_id: UUID
    strategy_revision: int
    strategy_prompt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    base_agent_contract_version: str
    configuration: CampaignConfiguration
    configuration_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    experiment_protocol_version: Literal["paper-experiment-v4"]
    experiment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class CampaignActivationResponse(ControlApiModel):
    campaign: CampaignResponse
    paper_run_id: UUID | None
    engine: EngineStatusResponse


class PromptPreviewRequest(ControlApiModel):
    strategy_id: UUID
    strategy_revision: int = Field(ge=1)
    aggressiveness: int = Field(ge=1, le=10)
    phase: Literal["MARKET_SELECTION", "FINAL_DECISION"]


class PromptPreviewResponse(ControlApiModel):
    strategy_id: UUID
    strategy_revision: int
    strategy_prompt_digest: str
    base_agent_contract_version: str
    aggressiveness: int
    phase: Literal["MARKET_SELECTION", "FINAL_DECISION"]
    instructions: str
    dynamic_input_model: Literal["MarketSelectionInput", "AgentInput"]
    dynamic_input: None = None
    note: str
