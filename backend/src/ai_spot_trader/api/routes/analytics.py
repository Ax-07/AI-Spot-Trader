from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from ai_spot_trader.api.economic_history_schemas import EconomicHistoryResponse
from ai_spot_trader.api.schemas import PaperAnalyticsResponse
from ai_spot_trader.core.runtime import AppRuntime
from ai_spot_trader.economic_history import (
    EconomicHistoryDataError,
    project_economic_history,
)
from ai_spot_trader.persistence.analytics import (
    PaperAnalyticsReader,
    RunScopedPaperAnalyticsReader,
)
from ai_spot_trader.persistence.query import (
    AuditDataIntegrityError,
    AuditSortOrder,
    AuditStoreUnavailableError,
    RunScopedCycleAuditReader,
)
from ai_spot_trader.persistence.runs import (
    PaperRunNotFoundError,
    PaperRunStoreUnavailableError,
    PaperRunView,
)

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


def _resolved_run_id(request: Request, paper_run_id: UUID | None) -> UUID:
    runtime = _runtime(request)
    resolved_run_id = paper_run_id or runtime.current_paper_run_id
    if resolved_run_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="paper_run_id is required when no current PAPER run is configured",
        )
    return resolved_run_id


async def _analytics_report(request: Request, paper_run_id: UUID):
    reader = _reader(request)
    if not isinstance(reader, RunScopedPaperAnalyticsReader):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="analytics reader does not support PAPER run selection",
        )
    return await reader.paper_analytics_for_run(paper_run_id)


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


@router.get("/economic-history", response_model=EconomicHistoryResponse)
async def economic_history(
    request: Request,
    paper_run_id: Annotated[UUID | None, Query()] = None,
) -> EconomicHistoryResponse:
    resolved_run_id = _resolved_run_id(request, paper_run_id)
    try:
        return await _economic_history_response(request, resolved_run_id)
    except PaperRunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PAPER run not found",
        ) from exc
    except (AuditStoreUnavailableError, PaperRunStoreUnavailableError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="economic history store is unavailable",
        ) from exc
    except (AuditDataIntegrityError, EconomicHistoryDataError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="economic history data is unavailable",
        ) from exc


@router.get("/economic-history/export")
async def export_economic_history(
    request: Request,
    paper_run_id: Annotated[UUID | None, Query()] = None,
) -> Response:
    response = await economic_history(request=request, paper_run_id=paper_run_id)
    filename = f"paper_run_{response.paper_run_id}_economic_history.json"
    return Response(
        content=response.model_dump_json(indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _economic_history_response(
    request: Request,
    paper_run_id: UUID,
) -> EconomicHistoryResponse:
    runtime = _runtime(request)
    audit_reader = runtime.audit_reader
    paper_run_reader = runtime.paper_run_reader
    if audit_reader is None or not isinstance(audit_reader, RunScopedCycleAuditReader):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="audit reader does not support PAPER run selection",
        )
    if paper_run_reader is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PAPER run store is not configured",
        )

    analytics = await _analytics_report(request, paper_run_id)
    lineage = await _paper_run_lineage(paper_run_reader, paper_run_id)

    summaries = []
    details = []
    for run in lineage:
        offset = 0
        while True:
            page = await audit_reader.list_cycles_for_run(
                run.paper_run_id,
                limit=100,
                offset=offset,
                order=AuditSortOrder.ASC,
            )
            summaries.extend(page.items)
            for item in page.items:
                detail = await audit_reader.get_cycle(item.cycle_id)
                if detail is None:
                    raise AuditDataIntegrityError(
                        "PAPER run references a missing cycle detail"
                    )
                details.append(detail)
            offset += len(page.items)
            if offset >= page.total or not page.items:
                break

    report = project_economic_history(
        paper_run_id=paper_run_id,
        analytics=analytics,
        cycles=tuple(details),
        cycle_summaries=tuple(summaries),
        lineage=lineage,
    )
    return EconomicHistoryResponse.model_validate(report, from_attributes=True)


async def _paper_run_lineage(
    reader,
    paper_run_id: UUID,
) -> tuple[PaperRunView, ...]:
    reverse: list[PaperRunView] = []
    seen: set[UUID] = set()
    current_id: UUID | None = paper_run_id
    while current_id is not None:
        if current_id in seen:
            raise AuditDataIntegrityError("PAPER run recovery lineage contains a cycle")
        seen.add(current_id)
        current = await reader.get_run(current_id)
        if current is None:
            if current_id == paper_run_id:
                raise PaperRunNotFoundError(f"paper run {paper_run_id} does not exist")
            raise AuditDataIntegrityError(
                "PAPER run recovery lineage references a missing parent"
            )
        reverse.append(current)
        current_id = current.resumed_from_paper_run_id
    return tuple(reversed(reverse))
