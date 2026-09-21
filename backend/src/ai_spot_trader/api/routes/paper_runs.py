from collections.abc import Awaitable
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status

from ai_spot_trader.api.schemas import PaperRunPageResponse, PaperRunResponse
from ai_spot_trader.core.runtime import AppRuntime
from ai_spot_trader.persistence.runs import (
    PaperRunReader,
    PaperRunSortOrder,
    PaperRunStoreUnavailableError,
    PaperRunView,
)

router = APIRouter(prefix="/api/v1/paper-runs", tags=["paper-runs"])


def _runtime(request: Request) -> AppRuntime:
    return cast(AppRuntime, request.app.state.runtime)


def _reader(request: Request) -> PaperRunReader:
    reader = _runtime(request).paper_run_reader
    if reader is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PAPER run store is not configured",
        )
    return reader


async def _run_call[T](operation: Awaitable[T]) -> T:
    try:
        return await operation
    except PaperRunStoreUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PAPER run store is unavailable",
        ) from exc


def _response(value: PaperRunView, *, current_run_id: UUID | None) -> PaperRunResponse:
    return PaperRunResponse(
        paper_run_id=value.paper_run_id,
        started_at=value.started_at,
        ended_at=value.ended_at,
        market_type=value.market_type,
        symbol=value.symbol,
        is_current=value.paper_run_id == current_run_id,
    )


@router.get("", response_model=PaperRunPageResponse)
async def list_paper_runs(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    order: PaperRunSortOrder = PaperRunSortOrder.DESC,
) -> PaperRunPageResponse:
    page = await _run_call(
        _reader(request).list_runs(limit=limit, offset=offset, order=order)
    )
    current_run_id = _runtime(request).current_paper_run_id
    return PaperRunPageResponse(
        items=tuple(_response(item, current_run_id=current_run_id) for item in page.items),
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/current", response_model=PaperRunResponse)
async def current_paper_run(request: Request) -> PaperRunResponse:
    current_run_id = _runtime(request).current_paper_run_id
    if current_run_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="current PAPER run is not configured",
        )
    item = await _run_call(_reader(request).get_run(current_run_id))
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PAPER run not found")
    return _response(item, current_run_id=current_run_id)


@router.get("/{paper_run_id}", response_model=PaperRunResponse)
async def get_paper_run(paper_run_id: UUID, request: Request) -> PaperRunResponse:
    item = await _run_call(_reader(request).get_run(paper_run_id))
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PAPER run not found")
    return _response(item, current_run_id=_runtime(request).current_paper_run_id)
