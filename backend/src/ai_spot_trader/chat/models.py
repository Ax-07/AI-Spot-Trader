from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
)

from ai_spot_trader.domain.enums import LLMModel


def _normalize_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


UtcDateTime = Annotated[AwareDatetime, AfterValidator(_normalize_utc)]
OperatorText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4000),
]
AgentText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=12000),
]


class ChatModel(BaseModel):
    """Strict base contract for the operator chat boundary."""

    model_config = ConfigDict(extra="forbid", strict=True)


class ChatRole(StrEnum):
    OPERATOR = "OPERATOR"
    AGENT = "AGENT"


class ChatMessage(ChatModel):
    message_id: UUID
    created_at: UtcDateTime
    role: ChatRole
    content: str


class SendChatMessageRequest(ChatModel):
    session_id: UUID | None = None
    message: OperatorText
    context_cycle_id: UUID | None = None


class ChatExchangeResponse(ChatModel):
    session_id: UUID
    model: LLMModel
    historical_cycle_id: UUID | None = None
    operator_message: ChatMessage
    agent_message: ChatMessage
    history_size: int = Field(ge=2)


class ChatHistoryResponse(ChatModel):
    session_id: UUID
    model: LLMModel
    messages: tuple[ChatMessage, ...] = ()
    max_messages: int = Field(ge=2)


class ChatContextSnapshot(ChatModel):
    """Read-only canonical facts exposed to one conversational request."""

    generated_at: UtcDateTime
    engine: dict[str, object]
    current_market: dict[str, object] | None = None
    current_portfolio: dict[str, object] | None = None
    recent_cycles: tuple[dict[str, object], ...] = ()
    historical_cycle: dict[str, object] | None = None
    historical_cycle_id: UUID | None = None
    analytics_summary: dict[str, object] | None = None
    audit_status: Literal["AVAILABLE", "UNCONFIGURED", "UNAVAILABLE", "INVALID"]
    analytics_status: Literal["AVAILABLE", "UNCONFIGURED", "UNAVAILABLE", "INVALID"]
