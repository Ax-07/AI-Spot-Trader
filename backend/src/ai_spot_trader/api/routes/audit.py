from collections.abc import Awaitable
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status

from ai_spot_trader.api.explainability import build_cycle_explainability
from ai_spot_trader.api.schemas import (
    CycleDetailResponse,
    CycleFailureResponse,
    CyclePageResponse,
    CycleSummaryResponse,
    DecisionPageResponse,
    DecisionResponse,
    ExecutionPageResponse,
    ExecutionResponse,
    FillResponse,
    LatestErrorResponse,
    MarketStateResponse,
    RiskAssessmentPageResponse,
    RiskAssessmentResponse,
)
from ai_spot_trader.core.runtime import AppRuntime
from ai_spot_trader.persistence.query import (
    AuditDataIntegrityError,
    AuditSortOrder,
    AuditStoreUnavailableError,
    CycleAuditDetail,
    CycleAuditReader,
    CycleAuditSummary,
    CycleFailureView,
    DecisionAuditItem,
    ExecutionAuditItem,
    FillAuditItem,
    LatestErrorView,
    RiskAssessmentAuditItem,
    RunScopedCycleAuditReader,
)

router = APIRouter(prefix="/api/v1", tags=["audit"])
CycleStatusFilter = Literal["COMPLETED", "FAILED"]
ActionFilter = Literal["BUY", "SELL", "HOLD"]
RiskStatusFilter = Literal["ALLOW", "MODIFY", "REJECT"]
CycleMarketType = Literal["SPOT", "PERPETUAL", "FUTURE"]


def _reader(request: Request) -> CycleAuditReader:
    runtime = cast(AppRuntime, request.app.state.runtime)
    reader = runtime.audit_reader
    if reader is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="audit store is not configured",
        )
    return reader


def _resolved_run_id(
    request: Request,
    paper_run_id: UUID | None,
) -> UUID | None:
    if paper_run_id is not None:
        return paper_run_id
    runtime = cast(AppRuntime, request.app.state.runtime)
    return runtime.current_paper_run_id


def _scoped_reader(request: Request) -> RunScopedCycleAuditReader:
    reader = _reader(request)
    if not isinstance(reader, RunScopedCycleAuditReader):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="audit reader does not support PAPER run selection",
        )
    return reader


async def _audit_call[T](operation: Awaitable[T]) -> T:
    try:
        return await operation
    except AuditStoreUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="audit store is unavailable",
        ) from exc
    except AuditDataIntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="audit data is unavailable",
        ) from exc


def _failure(value: CycleFailureView | None) -> CycleFailureResponse | None:
    if value is None:
        return None
    return CycleFailureResponse(
        stage=value.stage,
        error_type=value.error_type,
        timed_out=value.timed_out,
    )


def _fill(value: FillAuditItem) -> FillResponse:
    return FillResponse(
        fill_id=value.fill_id,
        execution_id=value.execution_id,
        market_state_id=value.market_state_id,
        filled_at=value.filled_at,
        payload=value.payload,
    )


def _cycle_summary(value: CycleAuditSummary) -> CycleSummaryResponse:
    return CycleSummaryResponse(
        cycle_id=value.cycle_id,
        paper_run_id=value.paper_run_id,
        status=value.status,
        recorded_at=value.recorded_at,
        decision_action=value.decision_action,
        symbol=value.symbol,
        market_type=cast(CycleMarketType | None, value.market_type),
        risk_status=value.risk_status,
        execution_id=value.execution_id,
        fill_count=value.fill_count,
        failure=_failure(value.failure),
    )


def _cycle_detail(value: CycleAuditDetail) -> CycleDetailResponse:
    return CycleDetailResponse(
        cycle_id=value.cycle_id,
        paper_run_id=value.paper_run_id,
        status=value.status,
        recorded_at=value.recorded_at,
        failure=_failure(value.failure),
        market_state_id=value.market_state_id,
        portfolio_state_before_id=value.portfolio_state_before_id,
        portfolio_state_after_id=value.portfolio_state_after_id,
        market_as_of=value.market_as_of,
        portfolio_before_as_of=value.portfolio_before_as_of,
        portfolio_after_as_of=value.portfolio_after_as_of,
        market_selection_input=value.market_selection_input,
        market_selection=value.market_selection,
        agent_input=value.agent_input,
        agent_tool_traces=value.agent_tool_traces,
        decision=value.decision,
        risk_assessment=value.risk_assessment,
        execution_intent=value.execution_intent,
        fills=tuple(_fill(item) for item in value.fills),
        portfolio_state_after=value.portfolio_state_after,
        explainability=build_cycle_explainability(value),
    )


def _decision(value: DecisionAuditItem) -> DecisionResponse:
    return DecisionResponse(
        decision_id=value.decision_id,
        cycle_id=value.cycle_id,
        created_at=value.created_at,
        action=value.action,
        symbol=value.symbol,
        payload=value.payload,
    )


def _risk(value: RiskAssessmentAuditItem) -> RiskAssessmentResponse:
    return RiskAssessmentResponse(
        risk_assessment_id=value.risk_assessment_id,
        cycle_id=value.cycle_id,
        decision_id=value.decision_id,
        assessed_at=value.assessed_at,
        status=value.status,
        payload=value.payload,
    )


def _execution(value: ExecutionAuditItem) -> ExecutionResponse:
    return ExecutionResponse(
        execution_id=value.execution_id,
        cycle_id=value.cycle_id,
        decision_id=value.decision_id,
        risk_assessment_id=value.risk_assessment_id,
        created_at=value.created_at,
        action=value.action,
        symbol=value.symbol,
        payload=value.payload,
        fills=tuple(_fill(item) for item in value.fills),
    )


def _latest_error(value: LatestErrorView) -> LatestErrorResponse:
    failure = _failure(value.failure)
    assert failure is not None
    return LatestErrorResponse(
        cycle_id=value.cycle_id,
        paper_run_id=value.paper_run_id,
        recorded_at=value.recorded_at,
        failure=failure,
    )


@router.get("/cycles", response_model=CyclePageResponse)
async def list_cycles(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    order: AuditSortOrder = AuditSortOrder.DESC,
    status_filter: Annotated[
        CycleStatusFilter | None,
        Query(alias="status"),
    ] = None,
    action: ActionFilter | None = None,
    risk_status: RiskStatusFilter | None = None,
    paper_run_id: UUID | None = None,
) -> CyclePageResponse:
    resolved_run_id = _resolved_run_id(request, paper_run_id)
    if resolved_run_id is None:
        operation = _reader(request).list_cycles(
            limit=limit,
            offset=offset,
            order=order,
            status=status_filter,
            action=action,
            risk_status=risk_status,
        )
    else:
        operation = _scoped_reader(request).list_cycles_for_run(
            resolved_run_id,
            limit=limit,
            offset=offset,
            order=order,
            status=status_filter,
            action=action,
            risk_status=risk_status,
        )
    page = await _audit_call(operation)
    return CyclePageResponse(
        items=tuple(_cycle_summary(item) for item in page.items),
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/cycles/latest", response_model=CycleDetailResponse)
async def latest_cycle(
    request: Request,
    paper_run_id: UUID | None = None,
) -> CycleDetailResponse:
    resolved_run_id = _resolved_run_id(request, paper_run_id)
    operation = (
        _reader(request).latest_cycle()
        if resolved_run_id is None
        else _scoped_reader(request).latest_cycle_for_run(resolved_run_id)
    )
    item = await _audit_call(operation)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="cycle not found",
        )
    return _cycle_detail(item)


@router.get("/cycles/{cycle_id}", response_model=CycleDetailResponse)
async def get_cycle(
    cycle_id: UUID,
    request: Request,
) -> CycleDetailResponse:
    item = await _audit_call(_reader(request).get_cycle(cycle_id))
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="cycle not found",
        )
    return _cycle_detail(item)


@router.get("/decisions", response_model=DecisionPageResponse)
async def list_decisions(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    order: AuditSortOrder = AuditSortOrder.DESC,
    action: ActionFilter | None = None,
    symbol: Annotated[
        str | None,
        Query(min_length=1, max_length=64),
    ] = None,
    paper_run_id: UUID | None = None,
) -> DecisionPageResponse:
    resolved_run_id = _resolved_run_id(request, paper_run_id)
    if resolved_run_id is None:
        operation = _reader(request).list_decisions(
            limit=limit,
            offset=offset,
            order=order,
            action=action,
            symbol=symbol,
        )
    else:
        operation = _scoped_reader(request).list_decisions_for_run(
            resolved_run_id,
            limit=limit,
            offset=offset,
            order=order,
            action=action,
            symbol=symbol,
        )
    page = await _audit_call(operation)
    return DecisionPageResponse(
        items=tuple(_decision(item) for item in page.items),
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/risk-assessments", response_model=RiskAssessmentPageResponse)
async def list_risk_assessments(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    order: AuditSortOrder = AuditSortOrder.DESC,
    status_filter: Annotated[
        RiskStatusFilter | None,
        Query(alias="status"),
    ] = None,
    paper_run_id: UUID | None = None,
) -> RiskAssessmentPageResponse:
    resolved_run_id = _resolved_run_id(request, paper_run_id)
    if resolved_run_id is None:
        operation = _reader(request).list_risk_assessments(
            limit=limit,
            offset=offset,
            order=order,
            status=status_filter,
        )
    else:
        operation = _scoped_reader(request).list_risk_assessments_for_run(
            resolved_run_id,
            limit=limit,
            offset=offset,
            order=order,
            status=status_filter,
        )
    page = await _audit_call(operation)
    return RiskAssessmentPageResponse(
        items=tuple(_risk(item) for item in page.items),
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/executions", response_model=ExecutionPageResponse)
async def list_executions(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    order: AuditSortOrder = AuditSortOrder.DESC,
    action: Annotated[
        Literal["BUY", "SELL"] | None,
        Query(),
    ] = None,
    symbol: Annotated[
        str | None,
        Query(min_length=1, max_length=64),
    ] = None,
    paper_run_id: UUID | None = None,
) -> ExecutionPageResponse:
    resolved_run_id = _resolved_run_id(request, paper_run_id)
    if resolved_run_id is None:
        operation = _reader(request).list_executions(
            limit=limit,
            offset=offset,
            order=order,
            action=action,
            symbol=symbol,
        )
    else:
        operation = _scoped_reader(request).list_executions_for_run(
            resolved_run_id,
            limit=limit,
            offset=offset,
            order=order,
            action=action,
            symbol=symbol,
        )
    page = await _audit_call(operation)
    return ExecutionPageResponse(
        items=tuple(_execution(item) for item in page.items),
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/errors/latest", response_model=LatestErrorResponse)
async def latest_error(
    request: Request,
    paper_run_id: UUID | None = None,
) -> LatestErrorResponse:
    resolved_run_id = _resolved_run_id(request, paper_run_id)
    operation = (
        _reader(request).latest_error()
        if resolved_run_id is None
        else _scoped_reader(request).latest_error_for_run(resolved_run_id)
    )
    item = await _audit_call(operation)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="error not found",
        )
    return _latest_error(item)


@router.get("/market/latest", response_model=MarketStateResponse)
async def latest_market_state(
    request: Request,
    paper_run_id: UUID | None = None,
) -> MarketStateResponse:
    resolved_run_id = _resolved_run_id(request, paper_run_id)
    operation = (
        _reader(request).latest_market_state()
        if resolved_run_id is None
        else _scoped_reader(request).latest_market_state_for_run(resolved_run_id)
    )
    payload = await _audit_call(operation)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="market state not found",
        )
    try:
        return MarketStateResponse.model_validate(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="audit data is unavailable",
        ) from exc
