from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, cast

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

from ai_spot_trader.market.attention import MarketAttentionOverview, RadarStatus
from ai_spot_trader.market.attention_microstructure import (
    MarketAttentionOverviewV3,
)
from ai_spot_trader.market.attention_scope_trend import (
    MarketAttentionOverviewV4,
    MarketScope,
)

router = APIRouter(prefix="/api/v1/market-attention", tags=["market-attention"])


class MarketAttentionReader(Protocol):
    @property
    def latest(
        self,
    ) -> MarketAttentionOverview | MarketAttentionOverviewV3 | MarketAttentionOverviewV4: ...

    def history(
        self, *, limit: int = 24
    ) -> tuple[
        MarketAttentionOverview | MarketAttentionOverviewV3 | MarketAttentionOverviewV4, ...
    ]: ...


class MarketAttentionScopeWriter(Protocol):
    async def set_market_scope(
        self,
        market_scope: MarketScope,
        *,
        observed_at: datetime | None = None,
    ) -> MarketAttentionOverviewV4: ...


class MarketAttentionHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    items: tuple[MarketAttentionOverviewV4, ...]


class MarketAttentionScopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market_scope: MarketScope


@router.get("", response_model=MarketAttentionOverviewV4)
async def market_attention(request: Request) -> MarketAttentionOverviewV4:
    service = _service(request)
    if service is None:
        return MarketAttentionOverviewV4(
            observed_at=datetime.now(UTC),
            status=RadarStatus.NOT_CONFIGURED,
            informative_only=True,
            market_scope=MarketScope.ALL,
        )
    return _as_v4(service.latest)


@router.put("/scope", response_model=MarketAttentionOverviewV4)
async def market_attention_scope(
    payload: MarketAttentionScopeRequest,
    request: Request,
) -> MarketAttentionOverviewV4:
    service = _service(request)
    if service is None or not hasattr(service, "set_market_scope"):
        raise HTTPException(status_code=503, detail="market attention scope control unavailable")
    writer = cast(MarketAttentionScopeWriter, service)
    result = await writer.set_market_scope(payload.market_scope)
    return _as_v4(result)


@router.get("/history", response_model=MarketAttentionHistoryResponse)
async def market_attention_history(
    request: Request,
    limit: int = Query(default=24, ge=1, le=96),
) -> MarketAttentionHistoryResponse:
    service = _service(request)
    if service is None:
        return MarketAttentionHistoryResponse(items=())
    return MarketAttentionHistoryResponse(
        items=tuple(_as_v4(item) for item in service.history(limit=limit))
    )


def _as_v4(
    value: MarketAttentionOverview | MarketAttentionOverviewV3 | MarketAttentionOverviewV4,
) -> MarketAttentionOverviewV4:
    if isinstance(value, MarketAttentionOverviewV4):
        return value
    if isinstance(value, MarketAttentionOverviewV3):
        return MarketAttentionOverviewV4.from_v3(value)
    return MarketAttentionOverviewV4.from_v3(MarketAttentionOverviewV3.from_base(value))


def _service(request: Request) -> MarketAttentionReader | None:
    value = getattr(request.app.state, "market_attention", None)
    if value is None:
        return None
    if not hasattr(value, "latest") or not hasattr(value, "history"):
        raise RuntimeError("market attention reader is not configured")
    return value
