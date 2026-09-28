from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict

from ai_spot_trader.market.attention import MarketAttentionOverview, RadarStatus

router = APIRouter(prefix="/api/v1/market-attention", tags=["market-attention"])


class MarketAttentionReader(Protocol):
    @property
    def latest(self) -> MarketAttentionOverview: ...

    def history(self, *, limit: int = 24) -> tuple[MarketAttentionOverview, ...]: ...


class MarketAttentionHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    items: tuple[MarketAttentionOverview, ...]


@router.get("", response_model=MarketAttentionOverview)
async def market_attention(request: Request) -> MarketAttentionOverview:
    service = _service(request)
    if service is None:
        return MarketAttentionOverview(
            observed_at=datetime.now(UTC),
            status=RadarStatus.NOT_CONFIGURED,
            informative_only=True,
        )
    return service.latest


@router.get("/history", response_model=MarketAttentionHistoryResponse)
async def market_attention_history(
    request: Request,
    limit: int = Query(default=24, ge=1, le=96),
) -> MarketAttentionHistoryResponse:
    service = _service(request)
    if service is None:
        return MarketAttentionHistoryResponse(items=())
    return MarketAttentionHistoryResponse(items=service.history(limit=limit))


def _service(request: Request) -> MarketAttentionReader | None:
    value = getattr(request.app.state, "market_attention", None)
    if value is None:
        return None
    if not hasattr(value, "latest") or not hasattr(value, "history"):
        raise RuntimeError("market attention reader is not configured")
    return value
