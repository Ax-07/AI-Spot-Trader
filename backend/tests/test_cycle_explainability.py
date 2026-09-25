from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from ai_spot_trader.api.explainability import build_cycle_explainability


@dataclass(frozen=True)
class CycleFailureView:
    stage: str
    error_type: str
    timed_out: bool


@dataclass(frozen=True)
class FillAuditItem:
    fill_id: UUID
    execution_id: UUID
    market_state_id: UUID
    filled_at: datetime
    payload: dict[str, object]


@dataclass(frozen=True)
class CycleAuditDetail:
    cycle_id: UUID
    status: str
    recorded_at: datetime
    failure: CycleFailureView | None
    market_state_id: UUID | None
    portfolio_state_before_id: UUID | None
    portfolio_state_after_id: UUID | None
    market_as_of: datetime | None
    portfolio_before_as_of: datetime | None
    portfolio_after_as_of: datetime | None
    agent_input: dict[str, object] | None
    decision: dict[str, object] | None
    risk_assessment: dict[str, object] | None
    execution_intent: dict[str, object] | None
    fills: tuple[FillAuditItem, ...]
    portfolio_state_after: dict[str, object] | None
    market_selection_input: dict[str, object] | None = None
    market_selection: dict[str, object] | None = None

NOW = datetime(2026, 9, 25, 9, 30, tzinfo=UTC)
CYCLE = UUID("10000000-0000-0000-0000-000000000001")
DECISION = UUID("20000000-0000-0000-0000-000000000001")
RISK = UUID("30000000-0000-0000-0000-000000000001")
EXECUTION = UUID("40000000-0000-0000-0000-000000000001")
FILL = UUID("50000000-0000-0000-0000-000000000001")
MARKET = UUID("60000000-0000-0000-0000-000000000001")
DISCOVERY = UUID("70000000-0000-0000-0000-000000000001")
SELECTION = UUID("80000000-0000-0000-0000-000000000001")


def _detail(
    *,
    status: str = "COMPLETED",
    failure: CycleFailureView | None = None,
    market_selection_input: dict[str, object] | None = None,
    market_selection: dict[str, object] | None = None,
    decision: dict[str, object] | None = None,
    risk: dict[str, object] | None = None,
    execution: dict[str, object] | None = None,
    fills: tuple[FillAuditItem, ...] = (),
) -> CycleAuditDetail:
    return CycleAuditDetail(
        cycle_id=CYCLE,
        status=status,
        recorded_at=NOW,
        failure=failure,
        market_state_id=None,
        portfolio_state_before_id=None,
        portfolio_state_after_id=None,
        market_as_of=None,
        portfolio_before_as_of=None,
        portfolio_after_as_of=None,
        agent_input=None,
        decision=decision,
        risk_assessment=risk,
        execution_intent=execution,
        fills=fills,
        portfolio_state_after=None,
        market_selection_input=market_selection_input,
        market_selection=market_selection,
    )


def _decision(
    action: str = "BUY",
    rationale: str | None = "Momentum confirmé",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "decision_id": str(DECISION),
        "cycle_id": str(CYCLE),
        "created_at": NOW.isoformat(),
        "action": action,
        "symbol": "ETH/USD",
        "market_type": "SPOT",
    }
    if action != "HOLD":
        payload["proposed_quantity"] = "2"
    if rationale is not None:
        payload["rationale"] = rationale
    return payload


def _risk(status: str = "ALLOW") -> dict[str, object]:
    payload: dict[str, object] = {
        "risk_assessment_id": str(RISK),
        "cycle_id": str(CYCLE),
        "decision_id": str(DECISION),
        "assessed_at": NOW.isoformat(),
        "status": status,
        "evaluated_limits": ["MAX_ORDER_NOTIONAL", "BUY_CASH"],
        "reasons": [],
    }
    if status == "ALLOW":
        payload.update(requested_quantity="2", authorized_quantity="2")
    elif status == "MODIFY":
        payload.update(
            requested_quantity="2",
            authorized_quantity="1.25",
            reasons=["MAX_ORDER_NOTIONAL_LIMIT"],
        )
    else:
        payload["reasons"] = ["INSUFFICIENT_CASH"]
    return payload


def _execution() -> dict[str, object]:
    return {
        "execution_id": str(EXECUTION),
        "cycle_id": str(CYCLE),
        "decision_id": str(DECISION),
        "risk_assessment_id": str(RISK),
        "created_at": NOW.isoformat(),
        "mode": "PAPER",
        "action": "BUY",
        "symbol": "ETH/USD",
        "quantity": "2",
        "market_type": "SPOT",
    }


def _fill() -> FillAuditItem:
    return FillAuditItem(
        fill_id=FILL,
        execution_id=EXECUTION,
        market_state_id=MARKET,
        filled_at=NOW,
        payload={
            "fill_id": str(FILL),
            "execution_id": str(EXECUTION),
            "action": "BUY",
            "symbol": "ETH/USD",
            "quantity": "2",
            "reference_price": "2500",
            "price": "2501",
            "notional": "5002",
            "fee": "5.002",
            "spread_cost": "1",
            "slippage_cost": "1",
            "market_type": "SPOT",
        },
    )


def test_buy_allow_fill_projects_real_facts_and_correlation() -> None:
    projected = build_cycle_explainability(
        _detail(decision=_decision(), risk=_risk(), execution=_execution(), fills=(_fill(),))
    )
    assert projected is not None
    assert projected.agent is not None
    assert projected.agent.rationale == "Momentum confirmé"
    assert projected.risk is not None
    assert projected.risk.status == "ALLOW"
    assert projected.risk.requested_quantity == "2"
    assert projected.risk.authorized_quantity == "2"
    assert projected.execution.outcome == "FILLED"
    assert projected.execution.fill_count == 1
    assert projected.execution.fills[0].price == "2501"
    assert projected.correlation.decision_id == DECISION
    assert projected.correlation.risk_assessment_id == RISK
    assert projected.correlation.execution_id == EXECUTION
    assert projected.correlation.fill_ids == (FILL,)


def test_modify_keeps_requested_and_authorized_quantities_separate() -> None:
    execution = _execution()
    execution["quantity"] = "1.25"
    projected = build_cycle_explainability(
        _detail(decision=_decision(), risk=_risk("MODIFY"), execution=execution)
    )
    assert projected is not None and projected.risk is not None
    assert projected.agent is not None
    assert projected.agent.proposed_quantity == "2"
    assert projected.risk.requested_quantity == "2"
    assert projected.risk.authorized_quantity == "1.25"
    assert projected.risk.reasons == ("MAX_ORDER_NOTIONAL_LIMIT",)
    assert projected.execution.quantity == "1.25"
    assert projected.execution.outcome == "INTENT_CREATED_NO_FILL"


def test_reject_and_hold_are_distinct_non_execution_outcomes() -> None:
    rejected = build_cycle_explainability(
        _detail(decision=_decision(), risk=_risk("REJECT"))
    )
    assert rejected is not None and rejected.risk is not None
    assert rejected.risk.reasons == ("INSUFFICIENT_CASH",)
    assert rejected.execution.outcome == "NOT_CREATED_RISK_REJECT"
    assert rejected.execution.execution_id is None

    hold_risk = _risk("ALLOW")
    hold_risk.pop("requested_quantity")
    hold_risk.pop("authorized_quantity")
    hold_risk["reasons"] = ["HOLD_NO_EXECUTION"]
    hold = build_cycle_explainability(
        _detail(decision=_decision("HOLD"), risk=hold_risk)
    )
    assert hold is not None and hold.agent is not None
    assert hold.agent.action == "HOLD"
    assert hold.execution.outcome == "NOT_CREATED_HOLD"
    assert hold.risk is not None and hold.risk.status == "ALLOW"


def test_failed_cycle_preserves_stage_context_and_existing_intent() -> None:
    agent_failure = build_cycle_explainability(
        _detail(
            status="FAILED",
            failure=CycleFailureView(stage="AGENT", error_type="TimeoutError", timed_out=True),
        )
    )
    assert agent_failure is not None
    assert agent_failure.execution.outcome == "NOT_CREATED_FAILURE"

    broker_failure = build_cycle_explainability(
        _detail(
            status="FAILED",
            failure=CycleFailureView(stage="BROKER", error_type="TimeoutError", timed_out=True),
            decision=_decision(),
            risk=_risk(),
            execution=_execution(),
        )
    )
    assert broker_failure is not None
    assert broker_failure.agent is not None
    assert broker_failure.risk is not None
    assert broker_failure.execution.execution_id == EXECUTION
    assert broker_failure.execution.outcome == "INTENT_CREATED_NO_FILL"


def test_legacy_missing_rationale_remains_missing() -> None:
    projected = build_cycle_explainability(
        _detail(
            market_selection={
                "selection_id": str(SELECTION),
                "symbol": "ETH/USD",
                "market_type": "SPOT",
            },
            decision=_decision(rationale=None),
            risk=_risk(),
        )
    )
    assert projected is not None
    assert projected.market_selection is not None
    assert projected.market_selection.rationale is None
    assert projected.agent is not None
    assert projected.agent.rationale is None


def test_capacity_context_projects_normal_and_management_without_inference() -> None:
    normal = build_cycle_explainability(
        _detail(
            market_selection_input={
                "capacity_context": {
                    "mode": "NORMAL",
                    "reason": "OPENING_CAPACITY_AVAILABLE",
                    "spot_opening_capacity": "POSSIBLE",
                    "perpetual_opening_capacity": "NOT_APPLICABLE",
                    "new_opening_research_skipped": False,
                }
            }
        )
    )
    assert normal is not None and normal.context is not None
    assert normal.context.mode == "NORMAL"
    assert normal.context.new_opening_research_skipped is False

    management = build_cycle_explainability(
        _detail(
            market_selection_input={
                "capacity_context": {
                    "mode": "MANAGEMENT",
                    "reason": "NO_SETTLEMENT_CASH",
                    "spot_opening_capacity": "UNAVAILABLE",
                    "perpetual_opening_capacity": "NOT_APPLICABLE",
                    "new_opening_research_skipped": True,
                }
            }
        )
    )
    assert management is not None and management.context is not None
    assert management.context.mode == "MANAGEMENT"
    assert management.context.reason == "NO_SETTLEMENT_CASH"
    assert management.context.new_opening_research_skipped is True


def test_discovery_statuses_are_exposed_without_fabricating_new_agent_selection() -> None:
    refreshed = {
        "status": "REFRESHED",
        "discovery_id": str(DISCOVERY),
        "observed_at": NOW.isoformat(),
        "selection_rationale": "Deux marchés gardés pour surveillance",
        "selection_entries": [
            {
                "market": {"symbol": "ETH/USD", "market_type": "SPOT"},
                "rationale": "Volatilité exploitable à surveiller",
            }
        ],
        "effective_watchlist": [{"symbol": "ETH/USD", "market_type": "SPOT"}],
    }
    projected = build_cycle_explainability(
        _detail(market_selection_input={"market_discovery": refreshed})
    )
    assert projected is not None and projected.discovery is not None
    assert projected.discovery.status == "REFRESHED"
    assert projected.discovery.selection_entries[0].rationale == (
        "Volatilité exploitable à surveiller"
    )

    for status in ("CACHE_REUSED", "FALLBACK", "SKIPPED_MANAGEMENT"):
        audit: dict[str, object] = {
            "status": status,
            "observed_at": NOW.isoformat(),
            "effective_watchlist": [{"symbol": "ETH/USD", "market_type": "SPOT"}],
        }
        if status == "FALLBACK":
            audit["error_type"] = "TimeoutError"
        item = build_cycle_explainability(
            _detail(market_selection_input={"market_discovery": audit})
        )
        assert item is not None and item.discovery is not None
        assert item.discovery.status == status
        assert item.discovery.selection_rationale is None
        assert item.discovery.selection_entries == ()


def test_projection_does_not_mutate_persisted_payloads() -> None:
    selection_input = {
        "capacity_context": {
            "mode": "NORMAL",
            "reason": "OPENING_CAPACITY_AVAILABLE",
        },
        "market_discovery": {
            "status": "CACHE_REUSED",
            "observed_at": NOW.isoformat(),
            "effective_watchlist": [{"symbol": "ETH/USD", "market_type": "SPOT"}],
        },
    }
    decision = _decision()
    risk = _risk("MODIFY")
    execution = _execution()
    before = deepcopy((selection_input, decision, risk, execution))

    build_cycle_explainability(
        _detail(
            market_selection_input=selection_input,
            decision=decision,
            risk=risk,
            execution=execution,
        )
    )

    assert (selection_input, decision, risk, execution) == before
