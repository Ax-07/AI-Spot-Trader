from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from ai_spot_trader.domain.enums import MarketType, PositionSide
from ai_spot_trader.domain.models import PortfolioState
from ai_spot_trader.domain.strategic_thesis import (
    ActiveStrategicThesis,
    StrategicPositionMemoryState,
    StrategicThesisOrigin,
    StrategicThesisReview,
    StrategicThesisStatus,
    StrategicThesisUpdate,
    active_thesis_key,
)
from ai_spot_trader.domain.symbols import parse_canonical_symbol

STRATEGIC_THESIS_OBSERVABILITY_VERSION = "strategic-thesis-observability-v1"


class StrategicThesisObservabilityDataError(ValueError):
    """Raised when persisted thesis facts cannot be projected without guessing."""


class StrategicThesisRevisionState(StrEnum):
    ACTIVE_COMMITTED = "ACTIVE_COMMITTED"
    RETIRED_COMMITTED = "RETIRED_COMMITTED"
    PROPOSED_NOT_ACTIVATED = "PROPOSED_NOT_ACTIVATED"
    FAILED_CYCLE = "FAILED_CYCLE"
    UNAVAILABLE_LEGACY = "UNAVAILABLE_LEGACY"


class _ExecutionUniverseItemLike(Protocol):
    symbol: str
    market_type: object


class _PaperRunLike(Protocol):
    paper_run_id: UUID
    execution_universe: tuple[_ExecutionUniverseItemLike, ...]


class _DecisionExecutionLike(Protocol):
    decision_index: int
    agent_input: dict[str, object] | None
    decision: dict[str, object]
    risk_assessment: dict[str, object] | None
    fills: tuple[object, ...]
    portfolio_state_after: dict[str, object] | None


class _CycleLike(Protocol):
    cycle_id: UUID
    paper_run_id: UUID | None
    status: str
    recorded_at: datetime
    decision_plan: dict[str, object] | None
    decision_results: tuple[_DecisionExecutionLike, ...]
    agent_input: dict[str, object] | None
    portfolio_state_after: dict[str, object] | None
    strategic_thesis_state: tuple[dict[str, object], ...] | None


@dataclass(frozen=True, slots=True)
class StrategicThesisPositionObservation:
    thesis_id: UUID | None
    symbol: str
    market_type: MarketType
    side: PositionSide
    quantity: Decimal
    memory_state: StrategicPositionMemoryState
    origin: StrategicThesisOrigin | None = None
    status: StrategicThesisStatus | None = None
    created_at: datetime | None = None
    activated_at: datetime | None = None
    updated_at: datetime | None = None
    horizon: str | None = None
    thesis_summary: str | None = None
    supporting_facts: tuple[str, ...] = ()
    invalidation_conditions: tuple[str, ...] = ()
    last_review: StrategicThesisReview | None = None


@dataclass(frozen=True, slots=True)
class StrategicThesisRevisionObservation:
    cycle_id: UUID
    paper_run_id: UUID | None
    decision_index: int
    decision_id: UUID | None
    thesis_id: UUID | None
    reviewed_at: datetime
    symbol: str
    market_type: MarketType
    side: PositionSide | None
    status: StrategicThesisStatus
    horizon: str
    thesis_summary: str
    review_summary: str
    supporting_facts: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]
    agent_action: str
    risk_status: str | None
    fill_count: int
    cycle_status: str
    active_after_cycle: bool | None
    revision_state: StrategicThesisRevisionState


@dataclass(frozen=True, slots=True)
class StrategicThesisObservabilityReport:
    paper_run_id: UUID
    lineage_paper_run_ids: tuple[UUID, ...]
    calculation_version: str
    timezone: str
    as_of: datetime | None
    positions: tuple[StrategicThesisPositionObservation, ...]
    revisions: tuple[StrategicThesisRevisionObservation, ...]
    total_revision_count: int
    history_limit: int


def project_strategic_thesis_observability(
    *,
    paper_run_id: UUID,
    cycles: tuple[_CycleLike, ...],
    lineage: tuple[_PaperRunLike, ...],
    history_limit: int = 100,
) -> StrategicThesisObservabilityReport:
    """Project the 50.1 durable thesis facts into a read-only operator view.

    This function never creates strategic state. Active memory comes only from the
    committed ``strategic_thesis_state_payload`` of completed cycles. Revision history
    comes only from persisted ``decision_plan_payload.thesis_updates`` and is evaluated
    against the previous and same-cycle committed snapshots, never a future snapshot.
    """

    if history_limit < 0:
        raise ValueError("history_limit cannot be negative")
    if not lineage:
        raise StrategicThesisObservabilityDataError(
            "strategic thesis observability requires a PAPER run lineage"
        )
    if lineage[-1].paper_run_id != paper_run_id:
        raise StrategicThesisObservabilityDataError(
            "PAPER run lineage does not end at the requested run"
        )

    ordered_cycles = tuple(
        sorted(cycles, key=lambda item: (item.recorded_at, str(item.cycle_id)))
    )
    latest_snapshot, _snapshot_known = _latest_committed_snapshot(ordered_cycles)
    portfolio = _last_committed_portfolio(ordered_cycles)
    positions = _position_observations(
        portfolio=portfolio,
        active_theses=latest_snapshot,
        lineage=lineage,
    )
    revisions = _revision_observations(ordered_cycles)
    total_revision_count = len(revisions)
    if history_limit == 0:
        bounded_revisions: tuple[StrategicThesisRevisionObservation, ...] = ()
    else:
        bounded_revisions = revisions[-history_limit:]

    as_of = portfolio.as_of if portfolio is not None else _last_completed_at(ordered_cycles)
    return StrategicThesisObservabilityReport(
        paper_run_id=paper_run_id,
        lineage_paper_run_ids=tuple(item.paper_run_id for item in lineage),
        calculation_version=STRATEGIC_THESIS_OBSERVABILITY_VERSION,
        timezone="UTC",
        as_of=as_of,
        positions=positions,
        revisions=bounded_revisions,
        total_revision_count=total_revision_count,
        history_limit=history_limit,
    )


def _latest_committed_snapshot(
    cycles: tuple[_CycleLike, ...],
) -> tuple[tuple[ActiveStrategicThesis, ...], bool]:
    snapshot: tuple[ActiveStrategicThesis, ...] = ()
    known = False
    for cycle in cycles:
        if cycle.status != "COMPLETED":
            continue
        raw = cycle.strategic_thesis_state
        if raw is None:
            snapshot = ()
            known = False
        else:
            snapshot = _parse_snapshot(raw)
            known = True
    return snapshot, known


def _parse_snapshot(
    payload: tuple[dict[str, object], ...],
) -> tuple[ActiveStrategicThesis, ...]:
    try:
        theses = tuple(
            ActiveStrategicThesis.model_validate_json(
                json.dumps(item, ensure_ascii=False, sort_keys=True)
            )
            for item in payload
        )
    except (TypeError, ValueError) as exc:
        raise StrategicThesisObservabilityDataError(
            "invalid persisted strategic thesis snapshot"
        ) from exc

    keys = tuple(active_thesis_key(item) for item in theses)
    if len(set(keys)) != len(keys):
        raise StrategicThesisObservabilityDataError(
            "persisted strategic thesis snapshot contains duplicate identities"
        )
    expected = tuple(
        sorted(
            theses,
            key=lambda item: (item.market_type.value, item.symbol, item.side.value),
        )
    )
    if expected != theses:
        raise StrategicThesisObservabilityDataError(
            "persisted strategic thesis snapshot is not deterministically ordered"
        )
    return theses


def _last_committed_portfolio(cycles: tuple[_CycleLike, ...]) -> PortfolioState | None:
    candidate: PortfolioState | None = None
    for cycle in cycles:
        if cycle.status != "COMPLETED":
            continue
        for item in cycle.decision_results:
            after = _portfolio_from_payload(item.portfolio_state_after)
            if after is not None:
                candidate = after
                continue
            before = _portfolio_from_agent_input(item.agent_input)
            if before is not None:
                candidate = before
        after_cycle = _portfolio_from_payload(cycle.portfolio_state_after)
        if after_cycle is not None:
            candidate = after_cycle
        elif not cycle.decision_results:
            before_cycle = _portfolio_from_agent_input(cycle.agent_input)
            if before_cycle is not None:
                candidate = before_cycle
    return candidate


def _portfolio_from_agent_input(payload: dict[str, object] | None) -> PortfolioState | None:
    if payload is None:
        return None
    value = payload.get("portfolio_state")
    if value is None:
        return None
    if not isinstance(value, dict):
        raise StrategicThesisObservabilityDataError(
            "AgentInput has an invalid durable portfolio_state"
        )
    return _portfolio_from_payload(value)


def _portfolio_from_payload(payload: dict[str, object] | None) -> PortfolioState | None:
    if payload is None:
        return None
    try:
        return PortfolioState.model_validate_json(json.dumps(payload))
    except (TypeError, ValueError) as exc:
        raise StrategicThesisObservabilityDataError(
            "invalid durable PortfolioState payload"
        ) from exc


def _position_observations(
    *,
    portfolio: PortfolioState | None,
    active_theses: tuple[ActiveStrategicThesis, ...],
    lineage: tuple[_PaperRunLike, ...],
) -> tuple[StrategicThesisPositionObservation, ...]:
    if portfolio is None:
        return ()

    by_key = {active_thesis_key(item): item for item in active_theses}
    universe = _execution_universe(lineage)
    observations: list[StrategicThesisPositionObservation] = []

    for position in portfolio.positions:
        if position.quantity <= 0:
            continue
        symbol = _spot_symbol_for_asset(
            asset=position.asset,
            active_theses=active_theses,
            universe=universe,
        )
        key = (symbol, MarketType.SPOT, PositionSide.LONG)
        observations.append(
            _position_observation(
                symbol=symbol,
                market_type=MarketType.SPOT,
                side=PositionSide.LONG,
                quantity=position.quantity,
                thesis=by_key.get(key),
            )
        )

    for position in portfolio.derivative_positions:
        key = (position.symbol, MarketType.PERPETUAL, position.side)
        observations.append(
            _position_observation(
                symbol=position.symbol,
                market_type=MarketType.PERPETUAL,
                side=position.side,
                quantity=position.quantity,
                thesis=by_key.get(key),
            )
        )

    return tuple(
        sorted(
            observations,
            key=lambda item: (item.market_type.value, item.symbol, item.side.value),
        )
    )


def _position_observation(
    *,
    symbol: str,
    market_type: MarketType,
    side: PositionSide,
    quantity: Decimal,
    thesis: ActiveStrategicThesis | None,
) -> StrategicThesisPositionObservation:
    if thesis is None:
        return StrategicThesisPositionObservation(
            thesis_id=None,
            symbol=symbol,
            market_type=market_type,
            side=side,
            quantity=quantity,
            memory_state=StrategicPositionMemoryState.UNAVAILABLE_LEGACY,
        )
    return StrategicThesisPositionObservation(
        thesis_id=thesis.thesis_id,
        symbol=symbol,
        market_type=market_type,
        side=side,
        quantity=quantity,
        memory_state=StrategicPositionMemoryState.ACTIVE,
        origin=thesis.origin,
        status=thesis.status,
        created_at=thesis.created_at,
        activated_at=thesis.activated_at,
        updated_at=thesis.updated_at,
        horizon=thesis.horizon,
        thesis_summary=thesis.thesis_summary,
        supporting_facts=thesis.supporting_facts,
        invalidation_conditions=thesis.invalidation_conditions,
        last_review=thesis.last_review,
    )


def _execution_universe(
    lineage: tuple[_PaperRunLike, ...],
) -> tuple[tuple[str, MarketType], ...]:
    values: dict[tuple[str, MarketType], None] = {}
    for run in lineage:
        for item in run.execution_universe:
            market_type = _market_type(item.market_type)
            if market_type in {MarketType.SPOT, MarketType.PERPETUAL}:
                values[(item.symbol, market_type)] = None
    return tuple(sorted(values, key=lambda item: (item[1].value, item[0])))


def _spot_symbol_for_asset(
    *,
    asset: str,
    active_theses: tuple[ActiveStrategicThesis, ...],
    universe: tuple[tuple[str, MarketType], ...],
) -> str:
    active_candidates = {
        item.symbol
        for item in active_theses
        if item.market_type is MarketType.SPOT
        and parse_canonical_symbol(item.symbol)[0] == asset
    }
    if len(active_candidates) == 1:
        return next(iter(active_candidates))
    if len(active_candidates) > 1:
        raise StrategicThesisObservabilityDataError(
            f"multiple active SPOT thesis symbols map to asset {asset}"
        )

    candidates = {
        symbol
        for symbol, market_type in universe
        if market_type is MarketType.SPOT and parse_canonical_symbol(symbol)[0] == asset
    }
    if len(candidates) != 1:
        raise StrategicThesisObservabilityDataError(
            f"cannot map SPOT asset {asset} to one canonical execution-universe symbol"
        )
    return next(iter(candidates))


def _revision_observations(
    cycles: tuple[_CycleLike, ...],
) -> tuple[StrategicThesisRevisionObservation, ...]:
    revisions: list[StrategicThesisRevisionObservation] = []
    previous_snapshot: tuple[ActiveStrategicThesis, ...] = ()
    previous_snapshot_known = False

    for cycle in cycles:
        current_snapshot: tuple[ActiveStrategicThesis, ...] = previous_snapshot
        current_snapshot_known = previous_snapshot_known
        if cycle.status == "COMPLETED":
            if cycle.strategic_thesis_state is None:
                current_snapshot = ()
                current_snapshot_known = False
            else:
                current_snapshot = _parse_snapshot(cycle.strategic_thesis_state)
                current_snapshot_known = True

        revisions.extend(
            _cycle_revisions(
                cycle=cycle,
                previous_snapshot=previous_snapshot,
                previous_snapshot_known=previous_snapshot_known,
                current_snapshot=current_snapshot,
                current_snapshot_known=current_snapshot_known,
            )
        )
        if cycle.status == "COMPLETED":
            previous_snapshot = current_snapshot
            previous_snapshot_known = current_snapshot_known

    return tuple(
        sorted(
            revisions,
            key=lambda item: (
                item.reviewed_at,
                str(item.cycle_id),
                item.decision_index,
            ),
        )
    )


def _cycle_revisions(
    *,
    cycle: _CycleLike,
    previous_snapshot: tuple[ActiveStrategicThesis, ...],
    previous_snapshot_known: bool,
    current_snapshot: tuple[ActiveStrategicThesis, ...],
    current_snapshot_known: bool,
) -> tuple[StrategicThesisRevisionObservation, ...]:
    plan = cycle.decision_plan
    if plan is None:
        return ()
    decisions = plan.get("decisions")
    updates = plan.get("thesis_updates")
    if not isinstance(decisions, list) or not isinstance(updates, list):
        return ()
    if len(updates) not in {0, len(decisions)}:
        raise StrategicThesisObservabilityDataError(
            "persisted decision plan has misaligned thesis_updates"
        )
    if not updates:
        return ()

    results = {item.decision_index: item for item in cycle.decision_results}
    observations: list[StrategicThesisRevisionObservation] = []
    for index, raw_update in enumerate(updates):
        if raw_update is None:
            continue
        if index >= len(decisions) or not isinstance(decisions[index], dict):
            raise StrategicThesisObservabilityDataError(
                "persisted thesis update has no aligned decision"
            )
        if not isinstance(raw_update, dict):
            raise StrategicThesisObservabilityDataError(
                "persisted thesis update is not an object"
            )
        decision = decisions[index]
        update = _parse_update(raw_update)
        symbol = _required_text(decision, "symbol")
        market_type = _market_type(_required_text(decision, "market_type"))
        action = _required_text(decision, "action")
        reviewed_at = _datetime_value(decision.get("created_at"), field="created_at")
        result = results.get(index)
        side = _revision_side(
            symbol=symbol,
            market_type=market_type,
            action=action,
            previous_snapshot=previous_snapshot,
            current_snapshot=current_snapshot,
        )
        previous = _snapshot_match(previous_snapshot, symbol, market_type, side)
        current = _snapshot_match(current_snapshot, symbol, market_type, side)
        active_after: bool | None = None
        if cycle.status == "COMPLETED" and current_snapshot_known:
            active_after = current is not None

        if cycle.status == "FAILED":
            revision_state = StrategicThesisRevisionState.FAILED_CYCLE
        elif not current_snapshot_known:
            revision_state = StrategicThesisRevisionState.UNAVAILABLE_LEGACY
        elif current is not None:
            revision_state = StrategicThesisRevisionState.ACTIVE_COMMITTED
        elif previous is not None and previous_snapshot_known:
            revision_state = StrategicThesisRevisionState.RETIRED_COMMITTED
        else:
            revision_state = StrategicThesisRevisionState.PROPOSED_NOT_ACTIVATED

        risk_status = None
        fill_count = 0
        if result is not None:
            risk = result.risk_assessment
            if isinstance(risk, dict):
                raw_risk = risk.get("status")
                if isinstance(raw_risk, str):
                    risk_status = raw_risk
            fill_count = len(result.fills)

        decision_id = _uuid_value(decision.get("decision_id"), field="decision_id")
        observations.append(
            StrategicThesisRevisionObservation(
                cycle_id=cycle.cycle_id,
                paper_run_id=cycle.paper_run_id,
                decision_index=index,
                decision_id=decision_id,
                thesis_id=(current or previous).thesis_id if (current or previous) else None,
                reviewed_at=reviewed_at,
                symbol=symbol,
                market_type=market_type,
                side=side,
                status=update.status,
                horizon=update.horizon,
                thesis_summary=update.thesis_summary,
                review_summary=update.review_summary,
                supporting_facts=update.supporting_facts,
                invalidation_conditions=update.invalidation_conditions,
                agent_action=action,
                risk_status=risk_status,
                fill_count=fill_count,
                cycle_status=cycle.status,
                active_after_cycle=active_after,
                revision_state=revision_state,
            )
        )
    return tuple(observations)


def _parse_update(payload: dict[str, object]) -> StrategicThesisUpdate:
    try:
        return StrategicThesisUpdate.model_validate_json(json.dumps(payload))
    except (TypeError, ValueError) as exc:
        raise StrategicThesisObservabilityDataError(
            "invalid persisted strategic thesis update"
        ) from exc


def _revision_side(
    *,
    symbol: str,
    market_type: MarketType,
    action: str,
    previous_snapshot: tuple[ActiveStrategicThesis, ...],
    current_snapshot: tuple[ActiveStrategicThesis, ...],
) -> PositionSide | None:
    if market_type is MarketType.SPOT:
        return PositionSide.LONG

    current = _snapshot_market_matches(current_snapshot, symbol, market_type)
    if len(current) == 1:
        return current[0].side
    previous = _snapshot_market_matches(previous_snapshot, symbol, market_type)
    if len(previous) == 1:
        return previous[0].side
    if action == "BUY":
        return PositionSide.LONG
    if action == "SELL":
        return PositionSide.SHORT
    return None


def _snapshot_market_matches(
    snapshot: tuple[ActiveStrategicThesis, ...],
    symbol: str,
    market_type: MarketType,
) -> tuple[ActiveStrategicThesis, ...]:
    return tuple(
        item
        for item in snapshot
        if item.symbol == symbol and item.market_type is market_type
    )


def _snapshot_match(
    snapshot: tuple[ActiveStrategicThesis, ...],
    symbol: str,
    market_type: MarketType,
    side: PositionSide | None,
) -> ActiveStrategicThesis | None:
    if side is None:
        matches = _snapshot_market_matches(snapshot, symbol, market_type)
        return matches[0] if len(matches) == 1 else None
    return next(
        (
            item
            for item in snapshot
            if item.symbol == symbol
            and item.market_type is market_type
            and item.side is side
        ),
        None,
    )


def _market_type(value: object) -> MarketType:
    raw = value.value if isinstance(value, StrEnum) else value
    try:
        market_type = MarketType(str(raw))
    except ValueError as exc:
        raise StrategicThesisObservabilityDataError(
            f"unsupported strategic thesis market type: {raw!r}"
        ) from exc
    if market_type not in {MarketType.SPOT, MarketType.PERPETUAL}:
        raise StrategicThesisObservabilityDataError(
            f"unsupported strategic thesis market type: {market_type.value}"
        )
    return market_type


def _required_text(payload: dict[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise StrategicThesisObservabilityDataError(
            f"persisted decision has no valid {field}"
        )
    return value


def _datetime_value(value: object, *, field: str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise StrategicThesisObservabilityDataError(
                f"persisted decision has invalid {field}"
            ) from exc
    raise StrategicThesisObservabilityDataError(
        f"persisted decision has no valid {field}"
    )


def _uuid_value(value: object, *, field: str) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError as exc:
            raise StrategicThesisObservabilityDataError(
                f"persisted decision has invalid {field}"
            ) from exc
    raise StrategicThesisObservabilityDataError(
        f"persisted decision has invalid {field}"
    )


def _last_completed_at(cycles: tuple[_CycleLike, ...]) -> datetime | None:
    values = [item.recorded_at for item in cycles if item.status == "COMPLETED"]
    return values[-1] if values else None


__all__ = [
    "STRATEGIC_THESIS_OBSERVABILITY_VERSION",
    "StrategicThesisObservabilityDataError",
    "StrategicThesisObservabilityReport",
    "StrategicThesisPositionObservation",
    "StrategicThesisRevisionObservation",
    "StrategicThesisRevisionState",
    "project_strategic_thesis_observability",
]
