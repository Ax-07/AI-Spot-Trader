from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from ai_spot_trader.agent.llm_audit import GLOBAL_LLM_AUDIT_STORE, LLMAuditRecord

router = APIRouter(prefix="/api/v1/llm-audit", tags=["llm-audit"])
Category = Literal[
    "MARKET_DISCOVERY",
    "STRATEGIC_MULTI_MARKET_PLAN",
    "STRATEGIC_SINGLETON",
    "OPERATOR_CHAT",
    "UNKNOWN",
]


class LLMAuditRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_id: UUID
    recorded_at: str
    sequence: int = Field(ge=1)
    category: Category
    provider: Literal["OPENAI", "OLLAMA"]
    model: str
    status: Literal["SUCCESS", "ERROR"]
    error_type: str | None = None
    latency_ms: float | None = Field(default=None, ge=0)
    session_id: UUID | None = None
    cycle_id: UUID | None = None
    discovery_id: UUID | None = None
    request: dict[str, object]
    response_output: tuple[dict[str, object], ...]
    response_text: str | None = None


class LLMAuditPageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: tuple[LLMAuditRecordResponse, ...]
    retention_max_records: int
    retention_max_record_bytes: int
    persistence: Literal["PROCESS_MEMORY"] = "PROCESS_MEMORY"


def _response(value: LLMAuditRecord) -> LLMAuditRecordResponse:
    return LLMAuditRecordResponse(
        audit_id=value.audit_id,
        recorded_at=value.recorded_at.isoformat().replace("+00:00", "Z"),
        sequence=value.sequence,
        category=value.category,
        provider=value.provider,
        model=value.model,
        status=value.status,
        error_type=value.error_type,
        latency_ms=value.latency_ms,
        session_id=value.session_id,
        cycle_id=value.cycle_id,
        discovery_id=value.discovery_id,
        request=value.request,
        response_output=value.response_output,
        response_text=value.response_text,
    )


@router.get("", response_model=LLMAuditPageResponse)
async def list_llm_audit(
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    category: Category | None = None,
    cycle_id: UUID | None = None,
    session_id: UUID | None = None,
    discovery_id: UUID | None = None,
) -> LLMAuditPageResponse:
    items = GLOBAL_LLM_AUDIT_STORE.list_records(
        limit=limit,
        category=category,
        cycle_id=cycle_id,
        session_id=session_id,
        discovery_id=discovery_id,
    )
    return LLMAuditPageResponse(
        items=tuple(_response(item) for item in items),
        retention_max_records=200,
        retention_max_record_bytes=512_000,
    )
