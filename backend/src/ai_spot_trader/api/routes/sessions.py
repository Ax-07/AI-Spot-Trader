from __future__ import annotations

from typing import cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status

from ai_spot_trader.api.schemas import CycleFailureResponse, EngineStatusResponse
from ai_spot_trader.api.session_schemas import (
    SessionCreateRequest,
    SessionDuplicateRequest,
    SessionPaperRunSummary,
    SessionResponse,
    SessionUpdateRequest,
)
from ai_spot_trader.core.control_plane_runtime import (
    CampaignActivationConflictError,
    CampaignActivationError,
    CampaignRuntimeManager,
)
from ai_spot_trader.core.runtime import (
    EngineRuntimeSnapshot,
    TradingEngineAlreadyRunningError,
    TradingEngineCycleFailedError,
    TradingEngineUnavailableError,
)
from ai_spot_trader.persistence.control_plane import (
    ControlPlaneConflictError,
    ControlPlaneNotFoundError,
    ControlPlaneStore,
    ControlPlaneUnavailableError,
)
from ai_spot_trader.persistence.runs import PaperRunRecoveryError, PaperRunStoreUnavailableError
from ai_spot_trader.sessions import SessionConflictError, SessionService, SessionView

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


def _service(request: Request) -> SessionService:
    runtime = request.app.state.runtime
    store = getattr(request.app.state, "control_plane_store", None)
    if not isinstance(runtime, CampaignRuntimeManager) or store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Session control is not configured",
        )
    return SessionService(
        store=cast(ControlPlaneStore, store),
        paper_run_reader=runtime.paper_run_reader,
        runtime=runtime,
    )


def _engine(snapshot: EngineRuntimeSnapshot | None) -> EngineStatusResponse | None:
    if snapshot is None:
        return None
    failure = snapshot.last_cycle_failure
    return EngineStatusResponse(
        configured=snapshot.configured,
        status=snapshot.status,
        last_cycle_id=snapshot.last_cycle_id,
        last_cycle_status=snapshot.last_cycle_status,
        last_cycle_failure=(
            CycleFailureResponse(
                stage=failure.stage,
                error_type=failure.error_type,
                timed_out=failure.timed_out,
            )
            if failure is not None
            else None
        ),
        last_unexpected_error_type=snapshot.last_unexpected_error_type,
    )


def _response(value: SessionView) -> SessionResponse:
    run = value.latest_paper_run
    return SessionResponse(
        session_id=value.session_id,
        name=value.name,
        created_at=value.created_at,
        last_activity_at=value.last_activity_at,
        archived_at=value.archived_at,
        status=value.status,
        market_mode=value.market_mode,
        instructions=value.instructions,
        configuration=value.configuration,
        current_campaign_id=value.current_campaign_id,
        current_campaign_created_at=value.current_campaign_created_at,
        current_strategy_revision=value.current_strategy_revision,
        has_history=value.has_history,
        current_campaign_has_history=value.current_campaign_has_history,
        latest_paper_run=(
            SessionPaperRunSummary(
                paper_run_id=run.paper_run_id,
                started_at=run.started_at,
                ended_at=run.ended_at,
                resumed_from_paper_run_id=run.resumed_from_paper_run_id,
            )
            if run is not None
            else None
        ),
        engine=_engine(value.engine),
    )


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, ControlPlaneNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(
        exc,
        (
            SessionConflictError,
            ControlPlaneConflictError,
            CampaignActivationConflictError,
            PaperRunRecoveryError,
            TradingEngineAlreadyRunningError,
        ),
    ):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, TradingEngineCycleFailedError):
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    if isinstance(
        exc,
        (
            ControlPlaneUnavailableError,
            CampaignActivationError,
            PaperRunStoreUnavailableError,
            TradingEngineUnavailableError,
        ),
    ):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Session operation is unavailable",
        )
    if isinstance(exc, ValueError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Session operation failed",
    )


def _sync_chat(request: Request) -> None:
    runtime = request.app.state.runtime
    if isinstance(runtime, CampaignRuntimeManager):
        request.app.state.chat_service = runtime.active_chat_service


async def _call(request: Request, operation) -> SessionResponse:
    try:
        value = await operation()
    except Exception as exc:
        if isinstance(
            exc,
            (
                SessionConflictError,
                ControlPlaneNotFoundError,
                ControlPlaneConflictError,
                ControlPlaneUnavailableError,
                CampaignActivationConflictError,
                CampaignActivationError,
                PaperRunRecoveryError,
                PaperRunStoreUnavailableError,
                TradingEngineUnavailableError,
                TradingEngineAlreadyRunningError,
                TradingEngineCycleFailedError,
                ValueError,
            ),
        ):
            raise _translate(exc) from exc
        raise
    finally:
        _sync_chat(request)
    return _response(value)


@router.get("", response_model=tuple[SessionResponse, ...])
async def list_sessions(
    request: Request,
    include_archived: bool = Query(default=False),
) -> tuple[SessionResponse, ...]:
    try:
        values = await _service(request).list_sessions(include_archived=include_archived)
    except Exception as exc:
        if isinstance(
            exc,
            (
                ControlPlaneNotFoundError,
                ControlPlaneUnavailableError,
                PaperRunStoreUnavailableError,
            ),
        ):
            raise _translate(exc) from exc
        raise
    return tuple(_response(value) for value in values)


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(payload: SessionCreateRequest, request: Request) -> SessionResponse:
    service = _service(request)
    return await _call(
        request,
        lambda: service.create_session(
            name=payload.name,
            instructions=payload.instructions,
            configuration=payload.configuration,
            start_now=payload.start_now,
        ),
    )


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: UUID, request: Request) -> SessionResponse:
    return await _call(request, lambda: _service(request).get_session(session_id))


@router.put("/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: UUID,
    payload: SessionUpdateRequest,
    request: Request,
) -> SessionResponse:
    service = _service(request)
    return await _call(
        request,
        lambda: service.update_session(
            session_id,
            name=payload.name,
            instructions=payload.instructions,
            configuration=payload.configuration,
        ),
    )


@router.post("/{session_id}/duplicate", response_model=SessionResponse, status_code=201)
async def duplicate_session(
    session_id: UUID,
    payload: SessionDuplicateRequest,
    request: Request,
) -> SessionResponse:
    service = _service(request)
    return await _call(
        request,
        lambda: service.duplicate_session(session_id, name=payload.name),
    )


@router.delete("/{session_id}", response_model=SessionResponse)
async def archive_session(session_id: UUID, request: Request) -> SessionResponse:
    return await _call(request, lambda: _service(request).archive_session(session_id))


@router.post("/{session_id}/start", response_model=SessionResponse)
async def start_session(session_id: UUID, request: Request) -> SessionResponse:
    return await _call(request, lambda: _service(request).start_session(session_id))


@router.post("/{session_id}/stop", response_model=SessionResponse)
async def stop_session(session_id: UUID, request: Request) -> SessionResponse:
    return await _call(request, lambda: _service(request).stop_session(session_id))


@router.post("/{session_id}/resume", response_model=SessionResponse)
async def resume_session(session_id: UUID, request: Request) -> SessionResponse:
    return await _call(request, lambda: _service(request).resume_session(session_id))


@router.post("/{session_id}/run-cycle", response_model=SessionResponse)
async def run_session_cycle(session_id: UUID, request: Request) -> SessionResponse:
    return await _call(request, lambda: _service(request).run_cycle(session_id))
