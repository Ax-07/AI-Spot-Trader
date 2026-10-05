from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

from ai_spot_trader.api.strategic_thesis_schemas import StrategicThesisObservabilityResponse
from ai_spot_trader.domain.enums import MarketType, PositionSide
from ai_spot_trader.domain.models import AssetPosition, DerivativePosition, PortfolioState
from ai_spot_trader.domain.strategic_thesis import (
    ActiveStrategicThesis,
    StrategicPositionMemoryState,
    StrategicThesisOrigin,
    StrategicThesisReview,
    StrategicThesisStatus,
    StrategicThesisUpdate,
)
import ai_spot_trader.strategic_thesis_observability as thesis_observability
from ai_spot_trader.strategic_thesis_observability import (
    StrategicThesisRevisionState,
    project_strategic_thesis_observability,
)

NOW = datetime(2026, 10, 5, 20, 0, tzinfo=UTC)
RUN_PARENT = UUID(int=50_200)
RUN_CHILD = UUID(int=50_201)


def _run(run_id: UUID, *markets: tuple[str, MarketType]):
    return SimpleNamespace(
        paper_run_id=run_id,
        execution_universe=tuple(
            SimpleNamespace(symbol=symbol, market_type=market_type)
            for symbol, market_type in markets
        ),
    )


def _spot_position(asset: str = "BTC", quantity: str = "1") -> AssetPosition:
    return AssetPosition(asset=asset, quantity=Decimal(quantity), available=Decimal(quantity))


def _perp_position(
    *,
    symbol: str = "BTC/USD",
    side: PositionSide = PositionSide.LONG,
    quantity: str = "2",
) -> DerivativePosition:
    qty = Decimal(quantity)
    mark = Decimal("100")
    notional = mark * qty
    return DerivativePosition(
        symbol=symbol,
        side=side,
        quantity=qty,
        average_entry_price=Decimal("100"),
        mark_price=mark,
        mark_observed_at=NOW,
        notional=notional,
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        leverage=Decimal("2"),
        margin_used=notional / Decimal("2"),
        initial_margin_rate=Decimal("0.5"),
        maintenance_margin_rate=Decimal("0.05"),
        maintenance_margin=notional * Decimal("0.05"),
    )


def _portfolio(
    *,
    at: datetime = NOW,
    spot: tuple[AssetPosition, ...] = (),
    perp: tuple[DerivativePosition, ...] = (),
) -> PortfolioState:
    return PortfolioState(
        portfolio_state_id=UUID(int=int(at.timestamp()) % 1_000_000 + 1),
        as_of=at,
        positions=spot,
        derivative_positions=perp,
    )


def _update(
    status: StrategicThesisStatus,
    *,
    label: str | None = None,
) -> StrategicThesisUpdate:
    suffix = label or status.value.lower()
    return StrategicThesisUpdate(
        status=status,
        horizon="1h-4h",
        thesis_summary=f"Thèse {suffix}",
        supporting_facts=(f"fait {suffix}",),
        invalidation_conditions=(f"invalidation {suffix}",),
        review_summary=f"revue {suffix}",
    )


def _thesis(
    *,
    number: int,
    symbol: str,
    market_type: MarketType,
    side: PositionSide,
    status: StrategicThesisStatus,
    at: datetime,
    origin: StrategicThesisOrigin = StrategicThesisOrigin.AGENT_OPENING,
) -> ActiveStrategicThesis:
    update = _update(status)
    return ActiveStrategicThesis(
        thesis_id=UUID(int=50_200_000 + number),
        symbol=symbol,
        market_type=market_type,
        side=side,
        origin=origin,
        created_at=at,
        activated_at=(at if origin is StrategicThesisOrigin.AGENT_OPENING else None),
        horizon=update.horizon,
        thesis_summary=update.thesis_summary,
        supporting_facts=update.supporting_facts,
        invalidation_conditions=update.invalidation_conditions,
        status=status,
        last_review=StrategicThesisReview(
            reviewed_at=at,
            status=status,
            summary=update.review_summary,
        ),
        updated_at=at,
    )


def _snapshot(*theses: ActiveStrategicThesis) -> tuple[dict[str, object], ...]:
    ordered = sorted(theses, key=lambda item: (item.market_type.value, item.symbol, item.side.value))
    return tuple(item.model_dump(mode="json") for item in ordered)


def _decision(
    *,
    cycle_id: UUID,
    decision_id: UUID,
    at: datetime,
    action: str,
    symbol: str,
    market_type: MarketType,
) -> dict[str, object]:
    return {
        "decision_id": str(decision_id),
        "cycle_id": str(cycle_id),
        "created_at": at.isoformat().replace("+00:00", "Z"),
        "action": action,
        "symbol": symbol,
        "market_type": market_type.value,
    }


def _result(
    *,
    index: int,
    decision: dict[str, object],
    portfolio_after: PortfolioState | None,
    risk: str | None = "ALLOW",
    fills: int = 0,
):
    return SimpleNamespace(
        decision_index=index,
        agent_input=None,
        decision=decision,
        risk_assessment=None if risk is None else {"status": risk},
        fills=tuple(SimpleNamespace() for _ in range(fills)),
        portfolio_state_after=(
            None if portfolio_after is None else portfolio_after.model_dump(mode="json")
        ),
    )


def _cycle(
    *,
    number: int,
    at: datetime,
    portfolio: PortfolioState | None,
    snapshot: tuple[dict[str, object], ...] | None,
    decision: dict[str, object] | None = None,
    update: StrategicThesisUpdate | None = None,
    risk: str | None = "ALLOW",
    fills: int = 0,
    status: str = "COMPLETED",
    run_id: UUID = RUN_CHILD,
):
    results = ()
    plan = None
    cycle_id = UUID(int=50_210_000 + number)
    if decision is not None:
        plan = {
            "cycle_id": str(cycle_id),
            "created_at": at.isoformat().replace("+00:00", "Z"),
            "decisions": [decision],
            "thesis_updates": [None if update is None else update.model_dump(mode="json")],
        }
        results = (
            _result(
                index=0,
                decision=decision,
                portfolio_after=portfolio,
                risk=risk,
                fills=fills,
            ),
        )
    return SimpleNamespace(
        cycle_id=cycle_id,
        paper_run_id=run_id,
        status=status,
        recorded_at=at + timedelta(seconds=5),
        decision_plan=plan,
        decision_results=results,
        agent_input=None,
        portfolio_state_after=(
            None if portfolio is None else portfolio.model_dump(mode="json")
        ),
        strategic_thesis_state=snapshot,
    )


def _decision_for_cycle(
    number: int,
    *,
    at: datetime,
    action: str,
    symbol: str,
    market_type: MarketType,
) -> dict[str, object]:
    return _decision(
        cycle_id=UUID(int=50_210_000 + number),
        decision_id=UUID(int=50_220_000 + number),
        at=at,
        action=action,
        symbol=symbol,
        market_type=market_type,
    )


def test_active_spot_and_perpetual_same_symbol_remain_distinct() -> None:
    spot_thesis = _thesis(
        number=1,
        symbol="BTC/USD",
        market_type=MarketType.SPOT,
        side=PositionSide.LONG,
        status=StrategicThesisStatus.CONFIRMED,
        at=NOW,
    )
    perp_thesis = _thesis(
        number=2,
        symbol="BTC/USD",
        market_type=MarketType.PERPETUAL,
        side=PositionSide.LONG,
        status=StrategicThesisStatus.WEAKENING,
        at=NOW,
    )
    portfolio = _portfolio(
        at=NOW + timedelta(minutes=1),
        spot=(_spot_position(),),
        perp=(_perp_position(),),
    )
    cycle = _cycle(
        number=1,
        at=NOW,
        portfolio=portfolio,
        snapshot=_snapshot(spot_thesis, perp_thesis),
    )

    report = project_strategic_thesis_observability(
        paper_run_id=RUN_CHILD,
        cycles=(cycle,),
        lineage=(_run(RUN_CHILD, ("BTC/USD", MarketType.SPOT), ("BTC/USD", MarketType.PERPETUAL)),),
    )

    assert [(item.symbol, item.market_type, item.side) for item in report.positions] == [
        ("BTC/USD", MarketType.PERPETUAL, PositionSide.LONG),
        ("BTC/USD", MarketType.SPOT, PositionSide.LONG),
    ]
    assert report.positions[0].status is StrategicThesisStatus.WEAKENING
    assert report.positions[1].status is StrategicThesisStatus.CONFIRMED
    assert all(item.memory_state is StrategicPositionMemoryState.ACTIVE for item in report.positions)


def test_perpetual_short_is_exposed_with_explicit_side() -> None:
    thesis = _thesis(
        number=3,
        symbol="ETH/USD",
        market_type=MarketType.PERPETUAL,
        side=PositionSide.SHORT,
        status=StrategicThesisStatus.NEW,
        at=NOW,
    )
    portfolio = _portfolio(perp=(_perp_position(symbol="ETH/USD", side=PositionSide.SHORT),))
    report = project_strategic_thesis_observability(
        paper_run_id=RUN_CHILD,
        cycles=(_cycle(number=2, at=NOW, portfolio=portfolio, snapshot=_snapshot(thesis)),),
        lineage=(_run(RUN_CHILD, ("ETH/USD", MarketType.PERPETUAL)),),
    )
    assert len(report.positions) == 1
    assert report.positions[0].side is PositionSide.SHORT


def test_pre_50_1_position_stays_legacy_without_rationale_reconstruction() -> None:
    portfolio = _portfolio(spot=(_spot_position(),))
    cycle = _cycle(number=3, at=NOW, portfolio=portfolio, snapshot=None)
    cycle.decision_plan = None
    cycle.decision_results = ()
    cycle.agent_input = {"rationale": "ancienne rationale qui ne doit pas devenir une thèse"}

    report = project_strategic_thesis_observability(
        paper_run_id=RUN_CHILD,
        cycles=(cycle,),
        lineage=(_run(RUN_CHILD, ("BTC/USD", MarketType.SPOT)),),
    )

    assert len(report.positions) == 1
    item = report.positions[0]
    assert item.memory_state is StrategicPositionMemoryState.UNAVAILABLE_LEGACY
    assert item.thesis_id is None
    assert item.thesis_summary is None
    assert report.revisions == ()


def test_revisions_are_causal_hold_is_visible_and_future_status_does_not_leak() -> None:
    first_at = NOW
    second_at = NOW + timedelta(minutes=5)
    first = _thesis(
        number=4,
        symbol="BTC/USD",
        market_type=MarketType.SPOT,
        side=PositionSide.LONG,
        status=StrategicThesisStatus.NEW,
        at=first_at,
    )
    second = ActiveStrategicThesis(
        **{
            **first.model_dump(mode="python"),
            "status": StrategicThesisStatus.CONFIRMED,
            "thesis_summary": "Thèse confirmed",
            "supporting_facts": ("fait confirmed",),
            "invalidation_conditions": ("invalidation confirmed",),
            "last_review": StrategicThesisReview(
                reviewed_at=second_at,
                status=StrategicThesisStatus.CONFIRMED,
                summary="revue confirmed",
            ),
            "updated_at": second_at,
        }
    )
    portfolio = _portfolio(at=second_at, spot=(_spot_position(),))
    cycle1 = _cycle(
        number=4,
        at=first_at,
        portfolio=portfolio.model_copy(update={"as_of": first_at}),
        snapshot=_snapshot(first),
        decision=_decision_for_cycle(4, at=first_at, action="BUY", symbol="BTC/USD", market_type=MarketType.SPOT),
        update=_update(StrategicThesisStatus.NEW),
        fills=1,
    )
    cycle2 = _cycle(
        number=5,
        at=second_at,
        portfolio=portfolio,
        snapshot=_snapshot(second),
        decision=_decision_for_cycle(5, at=second_at, action="HOLD", symbol="BTC/USD", market_type=MarketType.SPOT),
        update=_update(StrategicThesisStatus.CONFIRMED),
        fills=0,
    )

    report = project_strategic_thesis_observability(
        paper_run_id=RUN_CHILD,
        cycles=(cycle2, cycle1),
        lineage=(_run(RUN_CHILD, ("BTC/USD", MarketType.SPOT)),),
    )

    assert [item.status for item in report.revisions] == [
        StrategicThesisStatus.NEW,
        StrategicThesisStatus.CONFIRMED,
    ]
    assert report.revisions[0].revision_state is StrategicThesisRevisionState.ACTIVE_COMMITTED
    assert report.revisions[0].active_after_cycle is True
    assert report.revisions[1].agent_action == "HOLD"
    assert report.revisions[1].fill_count == 0
    assert report.positions[0].status is StrategicThesisStatus.CONFIRMED


def test_rejected_opening_is_a_proposal_but_never_an_active_thesis() -> None:
    decision = _decision_for_cycle(
        6,
        at=NOW,
        action="SELL",
        symbol="SOL/USD",
        market_type=MarketType.PERPETUAL,
    )
    cycle = _cycle(
        number=6,
        at=NOW,
        portfolio=_portfolio(),
        snapshot=(),
        decision=decision,
        update=_update(StrategicThesisStatus.NEW),
        risk="REJECT",
        fills=0,
    )

    report = project_strategic_thesis_observability(
        paper_run_id=RUN_CHILD,
        cycles=(cycle,),
        lineage=(_run(RUN_CHILD, ("SOL/USD", MarketType.PERPETUAL)),),
    )

    assert report.positions == ()
    assert len(report.revisions) == 1
    revision = report.revisions[0]
    assert revision.side is PositionSide.SHORT
    assert revision.risk_status == "REJECT"
    assert revision.active_after_cycle is False
    assert revision.revision_state is StrategicThesisRevisionState.PROPOSED_NOT_ACTIVATED


def test_partial_reduction_keeps_thesis_and_full_close_retires_it_durably() -> None:
    thesis = _thesis(
        number=7,
        symbol="BTC/USD",
        market_type=MarketType.PERPETUAL,
        side=PositionSide.LONG,
        status=StrategicThesisStatus.CONFIRMED,
        at=NOW,
    )
    initial = _portfolio(perp=(_perp_position(quantity="2"),))
    reduced = _portfolio(
        at=NOW + timedelta(minutes=5),
        perp=(_perp_position(quantity="1"),),
    )
    cycle1 = _cycle(number=7, at=NOW, portfolio=initial, snapshot=_snapshot(thesis))
    reduced_thesis = ActiveStrategicThesis(
        **{
            **thesis.model_dump(mode="python"),
            "last_review": StrategicThesisReview(
                reviewed_at=NOW + timedelta(minutes=5),
                status=StrategicThesisStatus.CONFIRMED,
                summary="réduction partielle revue",
            ),
            "updated_at": NOW + timedelta(minutes=5),
        }
    )
    cycle2 = _cycle(
        number=8,
        at=NOW + timedelta(minutes=5),
        portfolio=reduced,
        snapshot=_snapshot(reduced_thesis),
        decision=_decision_for_cycle(8, at=NOW + timedelta(minutes=5), action="SELL", symbol="BTC/USD", market_type=MarketType.PERPETUAL),
        update=_update(StrategicThesisStatus.CONFIRMED, label="partial"),
        fills=1,
    )
    closed = _portfolio(at=NOW + timedelta(minutes=10))
    cycle3 = _cycle(
        number=9,
        at=NOW + timedelta(minutes=10),
        portfolio=closed,
        snapshot=(),
        decision=_decision_for_cycle(9, at=NOW + timedelta(minutes=10), action="SELL", symbol="BTC/USD", market_type=MarketType.PERPETUAL),
        update=_update(StrategicThesisStatus.COMPLETED),
        fills=1,
    )

    after_partial = project_strategic_thesis_observability(
        paper_run_id=RUN_CHILD,
        cycles=(cycle1, cycle2),
        lineage=(_run(RUN_CHILD, ("BTC/USD", MarketType.PERPETUAL)),),
    )
    assert len(after_partial.positions) == 1
    assert after_partial.positions[0].quantity == Decimal("1")
    assert after_partial.revisions[-1].revision_state is StrategicThesisRevisionState.ACTIVE_COMMITTED

    after_close = project_strategic_thesis_observability(
        paper_run_id=RUN_CHILD,
        cycles=(cycle1, cycle2, cycle3),
        lineage=(_run(RUN_CHILD, ("BTC/USD", MarketType.PERPETUAL)),),
    )
    assert after_close.positions == ()
    assert after_close.revisions[-1].status is StrategicThesisStatus.COMPLETED
    assert after_close.revisions[-1].revision_state is StrategicThesisRevisionState.RETIRED_COMMITTED


def test_failed_cycle_is_not_promoted_and_lineage_recovery_keeps_parent_snapshot() -> None:
    thesis = _thesis(
        number=8,
        symbol="ETH/USD",
        market_type=MarketType.PERPETUAL,
        side=PositionSide.LONG,
        status=StrategicThesisStatus.CONFIRMED,
        at=NOW,
    )
    portfolio = _portfolio(perp=(_perp_position(symbol="ETH/USD"),))
    parent = _cycle(
        number=10,
        at=NOW,
        portfolio=portfolio,
        snapshot=_snapshot(thesis),
        run_id=RUN_PARENT,
    )
    failed = _cycle(
        number=11,
        at=NOW + timedelta(minutes=5),
        portfolio=_portfolio(),
        snapshot=None,
        decision=_decision_for_cycle(11, at=NOW + timedelta(minutes=5), action="SELL", symbol="ETH/USD", market_type=MarketType.PERPETUAL),
        update=_update(StrategicThesisStatus.INVALIDATED),
        fills=1,
        status="FAILED",
        run_id=RUN_CHILD,
    )

    report = project_strategic_thesis_observability(
        paper_run_id=RUN_CHILD,
        cycles=(parent, failed),
        lineage=(
            _run(RUN_PARENT, ("ETH/USD", MarketType.PERPETUAL)),
            _run(RUN_CHILD, ("ETH/USD", MarketType.PERPETUAL)),
        ),
    )

    assert report.lineage_paper_run_ids == (RUN_PARENT, RUN_CHILD)
    assert len(report.positions) == 1
    assert report.positions[0].status is StrategicThesisStatus.CONFIRMED
    assert report.revisions[-1].status is StrategicThesisStatus.INVALIDATED
    assert report.revisions[-1].revision_state is StrategicThesisRevisionState.FAILED_CYCLE
    assert report.revisions[-1].active_after_cycle is None


def test_history_is_bounded_and_api_serialization_is_stable() -> None:
    thesis = _thesis(
        number=9,
        symbol="BTC/USD",
        market_type=MarketType.SPOT,
        side=PositionSide.LONG,
        status=StrategicThesisStatus.NEW,
        at=NOW,
    )
    portfolio = _portfolio(spot=(_spot_position(),))
    cycles = []
    current = thesis
    for number, status in enumerate(
        (StrategicThesisStatus.NEW, StrategicThesisStatus.CONFIRMED, StrategicThesisStatus.WEAKENING),
        start=12,
    ):
        at = NOW + timedelta(minutes=number)
        current = ActiveStrategicThesis(
            **{
                **current.model_dump(mode="python"),
                "status": status,
                "last_review": StrategicThesisReview(reviewed_at=at, status=status, summary=f"revue {status.value}"),
                "updated_at": at,
            }
        )
        cycles.append(
            _cycle(
                number=number,
                at=at,
                portfolio=portfolio.model_copy(update={"as_of": at}),
                snapshot=_snapshot(current),
                decision=_decision_for_cycle(number, at=at, action="HOLD", symbol="BTC/USD", market_type=MarketType.SPOT),
                update=_update(status),
                fills=0,
            )
        )

    report = project_strategic_thesis_observability(
        paper_run_id=RUN_CHILD,
        cycles=tuple(cycles),
        lineage=(_run(RUN_CHILD, ("BTC/USD", MarketType.SPOT)),),
        history_limit=2,
    )
    assert report.total_revision_count == 3
    assert [item.status for item in report.revisions] == [
        StrategicThesisStatus.CONFIRMED,
        StrategicThesisStatus.WEAKENING,
    ]

    response = StrategicThesisObservabilityResponse.model_validate(report, from_attributes=True)
    payload = response.model_dump(mode="json")
    assert payload["positions"][0]["market_type"] == "SPOT"
    assert payload["positions"][0]["side"] == "LONG"
    assert payload["positions"][0]["memory_state"] == "ACTIVE"
    assert payload["revisions"][-1]["revision_state"] == "ACTIVE_COMMITTED"
    assert payload["history_limit"] == 2


def test_projection_has_no_risk_broker_or_llm_dependency() -> None:
    source = inspect.getsource(thesis_observability)
    assert "ai_spot_trader.risk" not in source
    assert "ai_spot_trader.broker" not in source
    assert "OpenAI" not in source
    assert "rationale" not in source
