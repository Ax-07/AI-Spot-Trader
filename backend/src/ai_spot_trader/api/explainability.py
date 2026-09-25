from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from ai_spot_trader.api.schemas import (
    CycleExplainabilityResponse,
    ExplainabilityAgentResponse,
    ExplainabilityContextResponse,
    ExplainabilityCorrelationResponse,
    ExplainabilityDiscoveryResponse,
    ExplainabilityExecutionResponse,
    ExplainabilityFillResponse,
    ExplainabilityMarketResponse,
    ExplainabilityMarketSelectionResponse,
    ExplainabilityRiskResponse,
    ExplainabilityWatchlistEntryResponse,
)


class FillAuditView(Protocol):
    @property
    def fill_id(self) -> UUID: ...

    @property
    def execution_id(self) -> UUID: ...

    @property
    def filled_at(self) -> datetime: ...

    @property
    def payload(self) -> Mapping[str, object]: ...


class FailureView(Protocol):
    @property
    def stage(self) -> str: ...

    @property
    def error_type(self) -> str: ...

    @property
    def timed_out(self) -> bool: ...


class CycleAuditDetailView(Protocol):
    @property
    def cycle_id(self) -> UUID: ...

    @property
    def status(self) -> str: ...

    @property
    def failure(self) -> FailureView | None: ...

    @property
    def market_selection_input(self) -> Mapping[str, object] | None: ...

    @property
    def market_selection(self) -> Mapping[str, object] | None: ...

    @property
    def decision(self) -> Mapping[str, object] | None: ...

    @property
    def risk_assessment(self) -> Mapping[str, object] | None: ...

    @property
    def execution_intent(self) -> Mapping[str, object] | None: ...

    @property
    def fills(self) -> tuple[FillAuditView, ...]: ...


def build_cycle_explainability(
    value: CycleAuditDetailView,
) -> CycleExplainabilityResponse | None:
    """Build a defensive presentation-only view from already persisted canonical facts."""

    selection_input = _mapping(value.market_selection_input)
    capacity = _mapping(selection_input.get("capacity_context"))
    discovery = _mapping(selection_input.get("market_discovery"))
    market_selection = _mapping(value.market_selection)
    decision = _mapping(value.decision)
    risk = _mapping(value.risk_assessment)
    execution = _mapping(value.execution_intent)

    if not any(
        (
            capacity,
            discovery,
            market_selection,
            decision,
            risk,
            execution,
            value.fills,
            value.failure,
        )
    ):
        return None

    agent = _agent(decision)
    risk_view = _risk(risk)
    execution_view = _execution(
        cycle_status=value.status,
        failure_present=value.failure is not None,
        decision=agent,
        risk=risk_view,
        execution=execution,
        fills=value.fills,
    )

    return CycleExplainabilityResponse(
        context=_context(capacity),
        discovery=_discovery(discovery),
        market_selection=_market_selection(market_selection),
        agent=agent,
        risk=risk_view,
        execution=execution_view,
        correlation=ExplainabilityCorrelationResponse(
            cycle_id=value.cycle_id,
            decision_id=_uuid(decision.get("decision_id")),
            risk_assessment_id=_uuid(risk.get("risk_assessment_id")),
            execution_id=_uuid(execution.get("execution_id")),
            fill_ids=tuple(fill.fill_id for fill in value.fills),
        ),
    )


def _context(payload: Mapping[str, Any]) -> ExplainabilityContextResponse | None:
    if not payload:
        return None
    return ExplainabilityContextResponse(
        mode=_text(payload.get("mode")),
        reason=_text(payload.get("reason")),
        spot_opening_capacity=_text(payload.get("spot_opening_capacity")),
        perpetual_opening_capacity=_text(payload.get("perpetual_opening_capacity")),
        new_opening_research_skipped=_bool(payload.get("new_opening_research_skipped")),
    )


def _discovery(payload: Mapping[str, Any]) -> ExplainabilityDiscoveryResponse | None:
    if not payload:
        return None
    status = _text(payload.get("status"))
    if status is None:
        return None
    return ExplainabilityDiscoveryResponse(
        status=status,
        discovery_id=_uuid(payload.get("discovery_id")),
        observed_at=_datetime(payload.get("observed_at")),
        selection_rationale=_text(payload.get("selection_rationale")),
        selection_entries=_watchlist_entries(payload.get("selection_entries")),
        previous_watchlist=_markets(payload.get("previous_watchlist")),
        effective_watchlist=_markets(payload.get("effective_watchlist")),
        added_markets=_markets(payload.get("added_markets")),
        maintained_markets=_markets(payload.get("maintained_markets")),
        removed_markets=_markets(payload.get("removed_markets")),
        error_type=_text(payload.get("error_type")),
        next_refresh_at=_datetime(payload.get("next_refresh_at")),
    )


def _market_selection(
    payload: Mapping[str, Any],
) -> ExplainabilityMarketSelectionResponse | None:
    if not payload:
        return None
    symbol = _text(payload.get("symbol"))
    if symbol is None:
        return None
    return ExplainabilityMarketSelectionResponse(
        selection_id=_uuid(payload.get("selection_id")),
        symbol=symbol,
        market_type=_text(payload.get("market_type")),
        rationale=_text(payload.get("rationale")),
    )


def _agent(payload: Mapping[str, Any]) -> ExplainabilityAgentResponse | None:
    if not payload:
        return None
    action = _text(payload.get("action"))
    symbol = _text(payload.get("symbol"))
    if action is None or symbol is None:
        return None
    return ExplainabilityAgentResponse(
        decision_id=_uuid(payload.get("decision_id")),
        action=action,
        symbol=symbol,
        market_type=_text(payload.get("market_type")),
        proposed_quantity=_number_text(payload.get("proposed_quantity")),
        rationale=_text(payload.get("rationale")),
    )


def _risk(payload: Mapping[str, Any]) -> ExplainabilityRiskResponse | None:
    if not payload:
        return None
    status = _text(payload.get("status"))
    if status is None:
        return None
    return ExplainabilityRiskResponse(
        risk_assessment_id=_uuid(payload.get("risk_assessment_id")),
        status=status,
        requested_quantity=_number_text(payload.get("requested_quantity")),
        authorized_quantity=_number_text(payload.get("authorized_quantity")),
        reasons=_text_tuple(payload.get("reasons")),
        evaluated_limits=_text_tuple(payload.get("evaluated_limits")),
    )


def _execution(
    *,
    cycle_status: str,
    failure_present: bool,
    decision: ExplainabilityAgentResponse | None,
    risk: ExplainabilityRiskResponse | None,
    execution: Mapping[str, Any],
    fills: tuple[FillAuditView, ...],
) -> ExplainabilityExecutionResponse:
    projected_fills = tuple(_fill(fill) for fill in fills)
    if projected_fills:
        outcome = "FILLED"
    elif execution:
        outcome = "INTENT_CREATED_NO_FILL"
    elif decision is not None and decision.action == "HOLD":
        outcome = "NOT_CREATED_HOLD"
    elif risk is not None and risk.status == "REJECT":
        outcome = "NOT_CREATED_RISK_REJECT"
    elif cycle_status == "FAILED" or failure_present:
        outcome = "NOT_CREATED_FAILURE"
    else:
        outcome = "NOT_CREATED"

    return ExplainabilityExecutionResponse(
        outcome=outcome,
        execution_id=_uuid(execution.get("execution_id")),
        action=_text(execution.get("action")),
        symbol=_text(execution.get("symbol")),
        market_type=_text(execution.get("market_type")),
        quantity=_number_text(execution.get("quantity")),
        fill_count=len(projected_fills),
        fills=projected_fills,
    )


def _fill(value: FillAuditView) -> ExplainabilityFillResponse:
    payload = _mapping(value.payload)
    return ExplainabilityFillResponse(
        fill_id=value.fill_id,
        execution_id=value.execution_id,
        filled_at=value.filled_at,
        action=_text(payload.get("action")),
        symbol=_text(payload.get("symbol")),
        market_type=_text(payload.get("market_type")),
        quantity=_number_text(payload.get("quantity")),
        reference_price=_number_text(payload.get("reference_price")),
        price=_number_text(payload.get("price")),
        notional=_number_text(payload.get("notional")),
        fee=_number_text(payload.get("fee")),
        spread_cost=_number_text(payload.get("spread_cost")),
        slippage_cost=_number_text(payload.get("slippage_cost")),
    )


def _watchlist_entries(value: Any) -> tuple[ExplainabilityWatchlistEntryResponse, ...]:
    items = _sequence(value)
    result: list[ExplainabilityWatchlistEntryResponse] = []
    for item in items:
        payload = _mapping(item)
        market = _market(payload.get("market"))
        if market is None:
            continue
        result.append(
            ExplainabilityWatchlistEntryResponse(
                market=market,
                rationale=_text(payload.get("rationale")),
            )
        )
    return tuple(result)


def _markets(value: Any) -> tuple[ExplainabilityMarketResponse, ...]:
    result: list[ExplainabilityMarketResponse] = []
    for item in _sequence(value):
        market = _market(item)
        if market is not None:
            result.append(market)
    return tuple(result)


def _market(value: Any) -> ExplainabilityMarketResponse | None:
    payload = _mapping(value)
    symbol = _text(payload.get("symbol"))
    if symbol is None:
        return None
    return ExplainabilityMarketResponse(
        symbol=symbol,
        market_type=_text(payload.get("market_type")),
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _number_text(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (str, int, float, Decimal)):
        text = str(value).strip()
        return text or None
    return None


def _text_tuple(value: Any) -> tuple[str, ...]:
    result: list[str] = []
    for item in _sequence(value):
        text = _text(item)
        if text is not None:
            result.append(text)
    return tuple(result)


def _uuid(value: Any) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if not isinstance(value, str):
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def _datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None
