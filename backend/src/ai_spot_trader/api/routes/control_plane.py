from __future__ import annotations

from typing import cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status

from ai_spot_trader.agent.prompt import compose_agent_instructions
from ai_spot_trader.api.control_plane_schemas import (
    CampaignActivationResponse,
    CampaignCreateRequest,
    CampaignResponse,
    PromptPreviewRequest,
    PromptPreviewResponse,
    StrategyCreateRequest,
    StrategyCreateResponse,
    StrategyRenameRequest,
    StrategyResponse,
    StrategyRevisionComparisonResponse,
    StrategyRevisionCreateRequest,
    StrategyRevisionResponse,
)
from ai_spot_trader.api.schemas import CycleFailureResponse, EngineStatusResponse
from ai_spot_trader.core.control_plane_runtime import (
    CampaignActivationConflictError,
    CampaignActivationError,
    CampaignRuntimeManager,
)
from ai_spot_trader.domain.experiments import aggressiveness_context
from ai_spot_trader.persistence.control_plane import (
    CampaignView,
    ControlPlaneConflictError,
    ControlPlaneNotFoundError,
    ControlPlaneStore,
    ControlPlaneUnavailableError,
    StrategyRevisionComparison,
    StrategyRevisionView,
    StrategyView,
)
from ai_spot_trader.persistence.runs import PaperRunRecoveryError, PaperRunStoreUnavailableError

router = APIRouter(prefix="/api/v1", tags=["control-plane"])


def _store(request: Request) -> ControlPlaneStore:
    value = getattr(request.app.state, "control_plane_store", None)
    if value is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="control plane persistence is not configured",
        )
    return cast(ControlPlaneStore, value)


def _manager(request: Request) -> CampaignRuntimeManager:
    runtime = request.app.state.runtime
    if not isinstance(runtime, CampaignRuntimeManager):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="campaign runtime control is not configured",
        )
    return runtime


def _strategy(value: StrategyView) -> StrategyResponse:
    return StrategyResponse(
        strategy_id=value.strategy_id,
        strategy_name=value.strategy_name,
        created_at=value.created_at,
        archived_at=value.archived_at,
        latest_revision=value.latest_revision,
    )


def _revision(value: StrategyRevisionView) -> StrategyRevisionResponse:
    return StrategyRevisionResponse(
        strategy_id=value.strategy_id,
        strategy_revision=value.strategy_revision,
        strategy_prompt=value.strategy_prompt,
        strategy_prompt_digest=value.strategy_prompt_digest,
        base_agent_contract_version=value.base_agent_contract_version,
        created_at=value.created_at,
    )


def _comparison(value: StrategyRevisionComparison) -> StrategyRevisionComparisonResponse:
    return StrategyRevisionComparisonResponse(
        strategy_id=value.strategy_id,
        left_revision=value.left_revision,
        right_revision=value.right_revision,
        left_digest=value.left_digest,
        right_digest=value.right_digest,
        identical=value.identical,
        unified_diff=value.unified_diff,
    )


def _campaign(value: CampaignView) -> CampaignResponse:
    return CampaignResponse(
        campaign_id=value.campaign_id,
        created_at=value.created_at,
        strategy_id=value.strategy_id,
        strategy_revision=value.strategy_revision,
        strategy_prompt_digest=value.strategy_prompt_digest,
        base_agent_contract_version=value.base_agent_contract_version,
        configuration=value.configuration,
        configuration_digest=value.configuration_digest,
        experiment_protocol_version="paper-experiment-v4",
        experiment_digest=value.experiment_digest,
    )


def _engine(manager: CampaignRuntimeManager) -> EngineStatusResponse:
    snapshot = manager.engine_snapshot()
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


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, ControlPlaneNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(
        exc,
        (
            ControlPlaneConflictError,
            CampaignActivationConflictError,
            PaperRunRecoveryError,
        ),
    ):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(
        exc,
        (
            ControlPlaneUnavailableError,
            PaperRunStoreUnavailableError,
            CampaignActivationError,
        ),
    ):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="control plane operation is unavailable",
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="control plane operation failed",
    )


@router.post("/strategies", response_model=StrategyCreateResponse, status_code=201)
async def create_strategy(
    payload: StrategyCreateRequest,
    request: Request,
) -> StrategyCreateResponse:
    try:
        strategy, revision = await _store(request).create_strategy(
            name=payload.strategy_name,
            strategy_prompt=payload.strategy_prompt,
        )
    except (ValueError, ControlPlaneConflictError, ControlPlaneUnavailableError) as exc:
        if isinstance(exc, ValueError):
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        raise _translate(exc) from exc
    return StrategyCreateResponse(strategy=_strategy(strategy), revision=_revision(revision))


@router.get("/strategies", response_model=tuple[StrategyResponse, ...])
async def list_strategies(request: Request) -> tuple[StrategyResponse, ...]:
    try:
        return tuple(_strategy(item) for item in await _store(request).list_strategies())
    except ControlPlaneUnavailableError as exc:
        raise _translate(exc) from exc


@router.get("/strategies/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(strategy_id: UUID, request: Request) -> StrategyResponse:
    try:
        item = await _store(request).get_strategy(strategy_id)
    except ControlPlaneUnavailableError as exc:
        raise _translate(exc) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="strategy not found")
    return _strategy(item)


@router.patch("/strategies/{strategy_id}", response_model=StrategyResponse)
async def rename_strategy(
    strategy_id: UUID,
    payload: StrategyRenameRequest,
    request: Request,
) -> StrategyResponse:
    try:
        return _strategy(
            await _store(request).rename_strategy(
                strategy_id,
                name=payload.strategy_name,
            )
        )
    except (ValueError, ControlPlaneNotFoundError, ControlPlaneUnavailableError) as exc:
        if isinstance(exc, ValueError):
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        raise _translate(exc) from exc


@router.post("/strategies/{strategy_id}/archive", response_model=StrategyResponse)
async def archive_strategy(strategy_id: UUID, request: Request) -> StrategyResponse:
    try:
        return _strategy(await _store(request).archive_strategy(strategy_id))
    except (ControlPlaneNotFoundError, ControlPlaneUnavailableError) as exc:
        raise _translate(exc) from exc


@router.post(
    "/strategies/{strategy_id}/revisions",
    response_model=StrategyRevisionResponse,
    status_code=201,
)
async def create_strategy_revision(
    strategy_id: UUID,
    payload: StrategyRevisionCreateRequest,
    request: Request,
) -> StrategyRevisionResponse:
    try:
        value = await _store(request).create_revision(
            strategy_id,
            strategy_prompt=payload.strategy_prompt,
        )
        return _revision(value)
    except (
        ValueError,
        ControlPlaneNotFoundError,
        ControlPlaneConflictError,
        ControlPlaneUnavailableError,
    ) as exc:
        if isinstance(exc, ValueError):
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        raise _translate(exc) from exc


@router.get(
    "/strategies/{strategy_id}/revisions/{revision}",
    response_model=StrategyRevisionResponse,
)
async def get_strategy_revision(
    strategy_id: UUID,
    revision: int,
    request: Request,
) -> StrategyRevisionResponse:
    try:
        item = await _store(request).get_revision(strategy_id, revision)
    except ControlPlaneUnavailableError as exc:
        raise _translate(exc) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="strategy revision not found")
    return _revision(item)


@router.get(
    "/strategies/{strategy_id}/compare",
    response_model=StrategyRevisionComparisonResponse,
)
async def compare_strategy_revisions(
    strategy_id: UUID,
    request: Request,
    left: int = Query(ge=1),
    right: int = Query(ge=1),
) -> StrategyRevisionComparisonResponse:
    try:
        return _comparison(await _store(request).compare_revisions(strategy_id, left, right))
    except (ControlPlaneNotFoundError, ControlPlaneUnavailableError) as exc:
        raise _translate(exc) from exc


@router.post("/campaigns", response_model=CampaignResponse, status_code=201)
async def create_campaign(
    payload: CampaignCreateRequest,
    request: Request,
) -> CampaignResponse:
    try:
        return _campaign(
            await _store(request).create_campaign(
                strategy_id=payload.strategy_id,
                strategy_revision=payload.strategy_revision,
                configuration=payload.configuration,
            )
        )
    except (
        ControlPlaneNotFoundError,
        ControlPlaneConflictError,
        ControlPlaneUnavailableError,
    ) as exc:
        raise _translate(exc) from exc


@router.get("/campaigns", response_model=tuple[CampaignResponse, ...])
async def list_campaigns(request: Request) -> tuple[CampaignResponse, ...]:
    try:
        return tuple(_campaign(item) for item in await _store(request).list_campaigns())
    except ControlPlaneUnavailableError as exc:
        raise _translate(exc) from exc


@router.get("/campaigns/active", response_model=CampaignActivationResponse)
async def active_campaign(request: Request) -> CampaignActivationResponse:
    manager = _manager(request)
    campaign_id = manager.active_campaign_id
    if campaign_id is None:
        raise HTTPException(status_code=404, detail="no campaign is active")
    try:
        campaign = await _store(request).get_campaign(campaign_id)
    except ControlPlaneUnavailableError as exc:
        raise _translate(exc) from exc
    if campaign is None:
        raise HTTPException(status_code=404, detail="active campaign not found")
    return CampaignActivationResponse(
        campaign=_campaign(campaign),
        paper_run_id=manager.current_paper_run_id,
        engine=_engine(manager),
    )


@router.get("/campaigns/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(campaign_id: UUID, request: Request) -> CampaignResponse:
    try:
        item = await _store(request).get_campaign(campaign_id)
    except ControlPlaneUnavailableError as exc:
        raise _translate(exc) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="campaign not found")
    return _campaign(item)


async def _activate(
    campaign_id: UUID,
    request: Request,
    *,
    resume: bool,
) -> CampaignActivationResponse:
    manager = _manager(request)
    try:
        await manager.activate_campaign(campaign_id, resume=resume)
        campaign = await _store(request).get_campaign(campaign_id)
    except Exception as exc:
        request.app.state.chat_service = manager.active_chat_service
        if isinstance(
            exc,
            (
                ControlPlaneNotFoundError,
                ControlPlaneUnavailableError,
                ControlPlaneConflictError,
                CampaignActivationError,
                PaperRunRecoveryError,
                PaperRunStoreUnavailableError,
            ),
        ):
            raise _translate(exc) from exc
        raise
    assert campaign is not None
    request.app.state.chat_service = manager.active_chat_service
    return CampaignActivationResponse(
        campaign=_campaign(campaign),
        paper_run_id=manager.current_paper_run_id,
        engine=_engine(manager),
    )


@router.post("/campaigns/{campaign_id}/activate", response_model=CampaignActivationResponse)
async def activate_campaign(
    campaign_id: UUID,
    request: Request,
) -> CampaignActivationResponse:
    return await _activate(campaign_id, request, resume=False)


@router.post("/campaigns/{campaign_id}/resume", response_model=CampaignActivationResponse)
async def resume_campaign(
    campaign_id: UUID,
    request: Request,
) -> CampaignActivationResponse:
    return await _activate(campaign_id, request, resume=True)


@router.post("/prompt-preview", response_model=PromptPreviewResponse)
async def preview_prompt(
    payload: PromptPreviewRequest,
    request: Request,
) -> PromptPreviewResponse:
    try:
        revision = await _store(request).get_revision(
            payload.strategy_id,
            payload.strategy_revision,
        )
    except ControlPlaneUnavailableError as exc:
        raise _translate(exc) from exc
    if revision is None:
        raise HTTPException(status_code=404, detail="strategy revision not found")
    context = aggressiveness_context(payload.aggressiveness)
    composition = compose_agent_instructions(
        strategy_prompt=revision.strategy_prompt,
        aggressiveness_context=context,
    )
    dynamic_model = (
        "MarketSelectionInput" if payload.phase == "MARKET_SELECTION" else "AgentInput"
    )
    return PromptPreviewResponse(
        strategy_id=revision.strategy_id,
        strategy_revision=revision.strategy_revision,
        strategy_prompt_digest=composition.strategy_prompt_digest,
        base_agent_contract_version=composition.base_agent_contract_version,
        aggressiveness=payload.aggressiveness,
        phase=payload.phase,
        instructions=composition.instructions,
        dynamic_input_model=dynamic_model,
        dynamic_input=None,
        note=(
            "Les instructions statiques sont exactes. L'input structuré dynamique n'est pas "
            "inventé avant le cycle et sera fourni par le pipeline canonique au moment causal."
        ),
    )
