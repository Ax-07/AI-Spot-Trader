from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status

from ai_spot_trader.api.schemas import PaperAnalyticsResponse
from ai_spot_trader.core.runtime import AppRuntime
from ai_spot_trader.persistence.analytics import (
    PaperAnalyticsReader,
    RunScopedPaperAnalyticsReader,
)
from ai_spot_trader.persistence.query import AuditDataIntegrityError, AuditStoreUnavailableError
from ai_spot_trader.persistence.runs import PaperRunNotFoundError

router = APIRouter(prefix="/api/v1", tags=["analytics"])


def _runtime(request: Request) -> AppRuntime:
    return cast(AppRuntime, request.app.state.runtime)


def _reader(request: Request) -> PaperAnalyticsReader:
    reader = _runtime(request).analytics_reader
    if reader is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="analytics store is not configured",
        )
    return reader


@router.get("/analytics", response_model=PaperAnalyticsResponse)
async def paper_analytics(
    request: Request,
    paper_run_id: Annotated[UUID | None, Query()] = None,
) -> PaperAnalyticsResponse:
    runtime = _runtime(request)
    reader = _reader(request)
    resolved_run_id = paper_run_id or runtime.current_paper_run_id

    if resolved_run_id is None and runtime.paper_run_reader is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="paper_run_id is required when no current PAPER run is configured",
        )

    try:
        if resolved_run_id is not None:
            if not isinstance(reader, RunScopedPaperAnalyticsReader):
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="analytics reader does not support PAPER run selection",
                )
            report = await reader.paper_analytics_for_run(resolved_run_id)
        else:
            # Compatibility for explicitly injected legacy/test readers only.
            report = await reader.paper_analytics()
    except PaperRunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PAPER run not found",
        ) from exc
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
    response = PaperAnalyticsResponse.model_validate(report, from_attributes=True)
    return response.model_copy(update={"paper_run_id": resolved_run_id})
