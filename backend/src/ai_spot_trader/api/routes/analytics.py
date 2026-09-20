from typing import cast

from fastapi import APIRouter, HTTPException, Request, status

from ai_spot_trader.api.schemas import PaperAnalyticsResponse
from ai_spot_trader.core.runtime import AppRuntime
from ai_spot_trader.persistence.analytics import PaperAnalyticsReader
from ai_spot_trader.persistence.query import AuditDataIntegrityError, AuditStoreUnavailableError

router = APIRouter(prefix="/api/v1", tags=["analytics"])


def _reader(request: Request) -> PaperAnalyticsReader:
    runtime = cast(AppRuntime, request.app.state.runtime)
    reader = runtime.analytics_reader
    if reader is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="analytics store is not configured",
        )
    return reader


@router.get("/analytics", response_model=PaperAnalyticsResponse)
async def paper_analytics(request: Request) -> PaperAnalyticsResponse:
    try:
        report = await _reader(request).paper_analytics()
    except AuditStoreUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="analytics store is unavailable",
        ) from exc
    except AuditDataIntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="analytics data is unavailable",
        ) from exc
    return PaperAnalyticsResponse.model_validate(report, from_attributes=True)
