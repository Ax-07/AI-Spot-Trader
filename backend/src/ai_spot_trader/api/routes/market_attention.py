from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, cast

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

from ai_spot_trader.market.attention import MarketAttentionOverview, RadarStatus
from ai_spot_trader.market.attention_filters import MarketAttentionOverviewV6
from ai_spot_trader.market.attention_microstructure import MarketAttentionOverviewV3
from ai_spot_trader.market.attention_perpetual_analytics import (
    MarketAttentionOverviewV6Analytics,
)
from ai_spot_trader.market.attention_scope_trend import (
    MarketAttentionOverviewV4,
    MarketScope,
)
from ai_spot_trader.market.attention_structure import MarketAttentionOverviewV5
from ai_spot_trader.market.attention_structure_prefilter import (
    MarketAttentionOverviewV6Structure,
    StructureAwareMarketAttentionFilters,
)

router = APIRouter(prefix="/api/v1/market-attention", tags=["market-attention"])

MarketAttentionPublicOverview = (
    MarketAttentionOverviewV6Analytics
    | MarketAttentionOverviewV6Structure
    | MarketAttentionOverviewV6
    | MarketAttentionOverviewV5
    | MarketAttentionOverviewV4
)


class MarketAttentionReader(Protocol):
    @property
    def latest(
        self,
    ) -> MarketAttentionOverview | MarketAttentionOverviewV3 | MarketAttentionPublicOverview: ...

    def history(
        self, *, limit: int = 24
    ) -> tuple[
        MarketAttentionOverview | MarketAttentionOverviewV3 | MarketAttentionPublicOverview, ...
    ]: ...


class MarketAttentionScopeWriter(Protocol):
    async def set_market_scope(
        self,
        market_scope: MarketScope,
        *,
        observed_at: datetime | None = None,
    ) -> MarketAttentionPublicOverview: ...


class MarketAttentionFilterWriter(Protocol):
    @property
    def filters(self) -> StructureAwareMarketAttentionFilters: ...

    async def set_filters(
        self,
        filters: StructureAwareMarketAttentionFilters,
        *,
        observed_at: datetime | None = None,
    ) -> MarketAttentionPublicOverview: ...


class MarketAttentionHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    items: tuple[MarketAttentionPublicOverview, ...]


class MarketAttentionScopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market_scope: MarketScope


@router.get("", response_model=MarketAttentionPublicOverview)
async def market_attention(request: Request) -> MarketAttentionPublicOverview:
    service = _service(request)
    if service is None:
        # Preserve the Batch 41 v4 fallback contract when no radar is configured.
        return MarketAttentionOverviewV4(
            observed_at=datetime.now(UTC),
            status=RadarStatus.NOT_CONFIGURED,
            informative_only=True,
            market_scope=MarketScope.ALL,
        )
    return _as_public(service.latest)


@router.put("/scope", response_model=MarketAttentionPublicOverview)
async def market_attention_scope(
    payload: MarketAttentionScopeRequest,
    request: Request,
) -> MarketAttentionPublicOverview:
    service = _service(request)
    if service is None or not hasattr(service, "set_market_scope"):
        raise HTTPException(status_code=503, detail="market attention scope control unavailable")
    writer = cast(MarketAttentionScopeWriter, service)
    result = await writer.set_market_scope(payload.market_scope)
    return _as_public(result)


@router.get("/filters", response_model=StructureAwareMarketAttentionFilters)
async def market_attention_filters(request: Request) -> StructureAwareMarketAttentionFilters:
    service = _service(request)
    if service is None or not hasattr(service, "filters"):
        return StructureAwareMarketAttentionFilters()
    writer = cast(MarketAttentionFilterWriter, service)
    return writer.filters


@router.put("/filters", response_model=MarketAttentionPublicOverview)
async def market_attention_set_filters(
    payload: StructureAwareMarketAttentionFilters,
    request: Request,
) -> MarketAttentionPublicOverview:
    service = _service(request)
    if service is None or not hasattr(service, "set_filters"):
        raise HTTPException(status_code=503, detail="market attention filter control unavailable")
    writer = cast(MarketAttentionFilterWriter, service)
    result = await writer.set_filters(payload)
    return _as_public(result)


@router.get("/history", response_model=MarketAttentionHistoryResponse)
async def market_attention_history(
    request: Request,
    limit: int = Query(default=24, ge=1, le=96),
) -> MarketAttentionHistoryResponse:
    service = _service(request)
    if service is None:
        return MarketAttentionHistoryResponse(items=())
    return MarketAttentionHistoryResponse(
        items=tuple(_as_public(item) for item in service.history(limit=limit))
    )


def _as_public(
    value: MarketAttentionOverview
    | MarketAttentionOverviewV3
    | MarketAttentionOverviewV4
    | MarketAttentionOverviewV5
    | MarketAttentionOverviewV6
    | MarketAttentionOverviewV6Structure
    | MarketAttentionOverviewV6Analytics,
) -> MarketAttentionPublicOverview:
    if isinstance(value, MarketAttentionOverviewV6Analytics):
        return value
    if isinstance(value, MarketAttentionOverviewV6Structure):
        return value
    if isinstance(value, MarketAttentionOverviewV6):
        return value
    if isinstance(value, MarketAttentionOverviewV5):
        return value
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
