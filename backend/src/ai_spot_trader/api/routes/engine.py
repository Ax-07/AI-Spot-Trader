from typing import cast

from fastapi import APIRouter, HTTPException, Request, status

from ai_spot_trader.api.schemas import (
    CycleFailureResponse,
    EngineStatusResponse,
)
from ai_spot_trader.core.runtime import (
    AppRuntime,
    EngineRuntimeSnapshot,
    TradingEngineAlreadyRunningError,
    TradingEngineCycleFailedError,
    TradingEngineUnavailableError,
)

router = APIRouter(prefix="/api/v1/engine", tags=["engine"])


def _runtime(request: Request) -> AppRuntime:
    return cast(AppRuntime, request.app.state.runtime)


def _response(snapshot: EngineRuntimeSnapshot) -> EngineStatusResponse:
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


@router.get("", response_model=EngineStatusResponse)
async def engine_status(request: Request) -> EngineStatusResponse:
    return _response(_runtime(request).engine_snapshot())


@router.post("/start", response_model=EngineStatusResponse)
async def start_engine(request: Request) -> EngineStatusResponse:
    try:
        snapshot = await _runtime(request).start_engine()
    except TradingEngineUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="trading engine is not configured",
        ) from exc
    except TradingEngineAlreadyRunningError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="trading engine is already running",
        ) from exc
    return _response(snapshot)


@router.post("/stop", response_model=EngineStatusResponse)
async def stop_engine(request: Request) -> EngineStatusResponse:
    try:
        snapshot = await _runtime(request).stop_engine()
    except TradingEngineUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="trading engine is not configured",
        ) from exc
    return _response(snapshot)


@router.post("/run-cycle", response_model=EngineStatusResponse)
async def run_cycle_once(request: Request) -> EngineStatusResponse:
    """Request exactly one cycle from the configured canonical TradingEngine."""

    try:
        snapshot = await _runtime(request).run_engine_cycle_once()
    except TradingEngineUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="trading engine is not configured for single-cycle execution",
        ) from exc
    except TradingEngineAlreadyRunningError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="autonomous trading is already running",
        ) from exc
    except TradingEngineCycleFailedError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="trading cycle failed before durable canonical completion",
        ) from exc
    return _response(snapshot)
