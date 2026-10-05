from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_spot_trader.domain.enums import MarketType, PositionSide
from ai_spot_trader.domain.models import PortfolioState
from ai_spot_trader.domain.planning import CycleDecisionPlanInput
from ai_spot_trader.domain.strategic_thesis import (
    ActiveStrategicThesis,
    StrategicPositionContext,
    StrategicThesisOrigin,
    StrategicThesisReview,
    StrategicThesisUpdate,
    active_thesis_key,
    build_strategic_position_context,
)
from ai_spot_trader.domain.symbols import parse_canonical_symbol
from ai_spot_trader.persistence.audit import CurrentPaperRunProvider
from ai_spot_trader.persistence.models import CycleRecord, PaperRunRecord
from ai_spot_trader.trading.engine import TradingCycleStatus
from ai_spot_trader.trading.multi_market import (
    DecisionExecutionResult,
    MultiMarketTradingCycleResult,
)

StrategicThesisKey = tuple[str, MarketType, PositionSide]


class StrategicThesisStoreUnavailableError(RuntimeError):
    """Raised when durable thesis state cannot be read."""


class StrategicThesisDataIntegrityError(RuntimeError):
    """Raised when a persisted strategic thesis snapshot is malformed."""


class RunBoundStrategicPositionContextSource:
    """Read the latest committed thesis snapshot through the current PAPER run lineage."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        run_provider: CurrentPaperRunProvider,
    ) -> None:
        self._sessions = sessions
        self._run_provider = run_provider

    async def build_context(
        self,
        plan_input: CycleDecisionPlanInput,
    ) -> StrategicPositionContext:
        paper_run_id = self._run_provider.current_run_id
        if paper_run_id is None:
            raise RuntimeError("PAPER run is not initialized")
        try:
            async with self._sessions() as session:
                active = await load_latest_active_theses(session, paper_run_id)
        except StrategicThesisDataIntegrityError:
            raise
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise StrategicThesisStoreUnavailableError(
                "strategic thesis store unavailable"
            ) from exc
        return build_strategic_position_context(
            portfolio_state=plan_input.portfolio_state,
            market_states=plan_input.market_states,
            active_theses=active,
            as_of=plan_input.created_at,
        )


async def load_latest_active_theses(
    session: AsyncSession,
    paper_run_id: UUID,
) -> tuple[ActiveStrategicThesis, ...]:
    """Load one canonical snapshot, following only explicit PAPER recovery lineage."""

    visited: set[UUID] = set()
    current_id: UUID | None = paper_run_id
    while current_id is not None:
        if current_id in visited:
            raise StrategicThesisDataIntegrityError("PAPER run lineage contains a cycle")
        visited.add(current_id)

        latest = await session.scalar(
            select(CycleRecord)
            .where(
                CycleRecord.paper_run_id == current_id,
                CycleRecord.status == TradingCycleStatus.COMPLETED.value,
            )
            .order_by(CycleRecord.recorded_at.desc(), CycleRecord.cycle_id.desc())
            .limit(1)
        )
        if latest is not None:
            # NULL means the latest committed cycle predates Batch 50.1. Never infer a thesis
            # from historical rationale; current open positions become UNAVAILABLE_LEGACY.
            return deserialize_active_theses(latest.strategic_thesis_state_payload)

        run = await session.get(PaperRunRecord, current_id)
        if run is None:
            raise StrategicThesisDataIntegrityError(
                f"PAPER run {current_id} is missing while resolving thesis lineage"
            )
        current_id = run.resumed_from_paper_run_id

    return ()


def deserialize_active_theses(
    payload: list[dict[str, object]] | None,
) -> tuple[ActiveStrategicThesis, ...]:
    if payload is None:
        return ()
    try:
        values = tuple(
            ActiveStrategicThesis.model_validate_json(
                json.dumps(item, ensure_ascii=False, sort_keys=True)
            )
            for item in payload
        )
    except (TypeError, ValueError) as exc:
        raise StrategicThesisDataIntegrityError(
            "invalid persisted strategic thesis snapshot"
        ) from exc
    keys = tuple(active_thesis_key(item) for item in values)
    if len(set(keys)) != len(keys):
        raise StrategicThesisDataIntegrityError(
            "persisted strategic thesis snapshot contains duplicate identities"
        )
    ordered = tuple(sorted(values, key=_thesis_sort_key))
    if ordered != values:
        raise StrategicThesisDataIntegrityError(
            "persisted strategic thesis snapshot is not deterministically ordered"
        )
    return values


def serialize_active_theses(
    theses: tuple[ActiveStrategicThesis, ...],
) -> list[dict[str, object]]:
    ordered = tuple(sorted(theses, key=_thesis_sort_key))
    if len({active_thesis_key(item) for item in ordered}) != len(ordered):
        raise StrategicThesisDataIntegrityError(
            "active strategic thesis snapshot contains duplicate identities"
        )
    return [dict(item.model_dump(mode="json")) for item in ordered]


def derive_committed_active_theses(
    previous: tuple[ActiveStrategicThesis, ...],
    result: MultiMarketTradingCycleResult,
) -> tuple[ActiveStrategicThesis, ...]:
    """Apply one committed economic cycle to the active thesis projection."""

    if result.status is not TradingCycleStatus.COMPLETED:
        return previous
    plan = result.decision_plan
    if plan is None:
        return previous

    thesis_by_key = {active_thesis_key(item): item for item in previous}
    if len(thesis_by_key) != len(previous):
        raise StrategicThesisDataIntegrityError(
            "previous strategic thesis snapshot contains duplicate identities"
        )
    updates = plan.thesis_updates

    for trajectory in result.decision_results:
        update = (
            updates[trajectory.decision_index]
            if updates and trajectory.decision_index < len(updates)
            else None
        )
        _apply_trajectory(thesis_by_key, trajectory=trajectory, update=update)

    return tuple(sorted(thesis_by_key.values(), key=_thesis_sort_key))


def _apply_trajectory(
    thesis_by_key: dict[StrategicThesisKey, ActiveStrategicThesis],
    *,
    trajectory: DecisionExecutionResult,
    update: StrategicThesisUpdate | None,
) -> None:
    decision = trajectory.decision
    before = _position_exposure(
        trajectory.portfolio_state_before,
        symbol=decision.symbol,
        market_type=decision.market_type,
    )
    after_state = trajectory.portfolio_state_after or trajectory.portfolio_state_before
    after = _position_exposure(
        after_state,
        symbol=decision.symbol,
        market_type=decision.market_type,
    )

    before_key = (
        None
        if before is None
        else (decision.symbol, decision.market_type, before[0])
    )
    after_key = (
        None
        if after is None
        else (decision.symbol, decision.market_type, after[0])
    )

    # Economic closure always retires the active projection. The final structured review remains
    # durably available in decision_plan_payload and is therefore not erased from audit history.
    if before_key is not None and after_key is None:
        thesis_by_key.pop(before_key, None)
        return

    # A side flip retires the old exposure identity before considering the newly opened side.
    if before_key is not None and after_key is not None and before_key != after_key:
        thesis_by_key.pop(before_key, None)
        if update is not None and trajectory.fills:
            thesis_by_key[after_key] = _new_opening_thesis(
                trajectory=trajectory,
                side=after_key[2],
                update=update,
            )
        return

    # No economic exposure exists. This covers rejected/non-filled opening intents.
    if after_key is None:
        return

    existing = thesis_by_key.get(after_key)
    if existing is not None:
        if update is not None:
            thesis_by_key[after_key] = _review_existing_thesis(
                existing,
                reviewed_at=decision.created_at,
                update=update,
            )
        return

    # Existing economic position without 50.1 memory is explicitly legacy. It can acquire a new
    # management thesis only from the current cycle onward; historical rationale is never used.
    if before_key == after_key:
        if update is not None:
            thesis_by_key[after_key] = _legacy_adoption_thesis(
                trajectory=trajectory,
                side=after_key[2],
                update=update,
            )
        return

    # A newly opened exposure becomes active only after an actual fill.
    if trajectory.fills and update is not None:
        thesis_by_key[after_key] = _new_opening_thesis(
            trajectory=trajectory,
            side=after_key[2],
            update=update,
        )


def _new_opening_thesis(
    *,
    trajectory: DecisionExecutionResult,
    side: PositionSide,
    update: StrategicThesisUpdate,
) -> ActiveStrategicThesis:
    decision = trajectory.decision
    activated_at = max(fill.filled_at for fill in trajectory.fills)
    updated_at = max(decision.created_at, activated_at)
    return ActiveStrategicThesis(
        thesis_id=uuid5(
            NAMESPACE_URL,
            "ai-spot-trader:strategic-thesis:"
            f"{decision.decision_id}:{decision.market_type.value}:{side.value}",
        ),
        symbol=decision.symbol,
        market_type=decision.market_type,
        side=side,
        origin=StrategicThesisOrigin.AGENT_OPENING,
        created_at=decision.created_at,
        activated_at=activated_at,
        horizon=update.horizon,
        thesis_summary=update.thesis_summary,
        supporting_facts=update.supporting_facts,
        invalidation_conditions=update.invalidation_conditions,
        status=update.status,
        last_review=StrategicThesisReview(
            reviewed_at=decision.created_at,
            status=update.status,
            summary=update.review_summary,
        ),
        updated_at=updated_at,
    )


def _legacy_adoption_thesis(
    *,
    trajectory: DecisionExecutionResult,
    side: PositionSide,
    update: StrategicThesisUpdate,
) -> ActiveStrategicThesis:
    decision = trajectory.decision
    return ActiveStrategicThesis(
        thesis_id=uuid5(
            NAMESPACE_URL,
            "ai-spot-trader:strategic-thesis:legacy-adoption:"
            f"{decision.decision_id}:{decision.market_type.value}:{side.value}",
        ),
        symbol=decision.symbol,
        market_type=decision.market_type,
        side=side,
        origin=StrategicThesisOrigin.LEGACY_ADOPTION,
        created_at=decision.created_at,
        activated_at=None,
        horizon=update.horizon,
        thesis_summary=update.thesis_summary,
        supporting_facts=update.supporting_facts,
        invalidation_conditions=update.invalidation_conditions,
        status=update.status,
        last_review=StrategicThesisReview(
            reviewed_at=decision.created_at,
            status=update.status,
            summary=update.review_summary,
        ),
        updated_at=decision.created_at,
    )


def _review_existing_thesis(
    thesis: ActiveStrategicThesis,
    *,
    reviewed_at: datetime,
    update: StrategicThesisUpdate,
) -> ActiveStrategicThesis:
    if reviewed_at < thesis.updated_at:
        raise StrategicThesisDataIntegrityError(
            "strategic thesis review predates the durable thesis state"
        )
    return ActiveStrategicThesis(
        thesis_id=thesis.thesis_id,
        symbol=thesis.symbol,
        market_type=thesis.market_type,
        side=thesis.side,
        origin=thesis.origin,
        created_at=thesis.created_at,
        activated_at=thesis.activated_at,
        horizon=update.horizon,
        thesis_summary=update.thesis_summary,
        supporting_facts=update.supporting_facts,
        invalidation_conditions=update.invalidation_conditions,
        status=update.status,
        last_review=StrategicThesisReview(
            reviewed_at=reviewed_at,
            status=update.status,
            summary=update.review_summary,
        ),
        updated_at=reviewed_at,
    )


def _position_exposure(
    portfolio: PortfolioState,
    *,
    symbol: str,
    market_type: MarketType,
) -> tuple[PositionSide, Decimal] | None:
    if market_type is MarketType.SPOT:
        base_asset, _quote_asset = parse_canonical_symbol(symbol)
        position = next(
            (
                item
                for item in portfolio.positions
                if item.asset == base_asset and item.quantity > 0
            ),
            None,
        )
        return None if position is None else (PositionSide.LONG, position.quantity)

    if market_type is MarketType.PERPETUAL:
        position = next(
            (
                item
                for item in portfolio.derivative_positions
                if item.symbol == symbol and item.quantity > 0
            ),
            None,
        )
        return None if position is None else (position.side, position.quantity)

    return None


def _thesis_sort_key(thesis: ActiveStrategicThesis) -> tuple[str, str, str]:
    return thesis.market_type.value, thesis.symbol, thesis.side.value


__all__ = [
    "RunBoundStrategicPositionContextSource",
    "StrategicThesisDataIntegrityError",
    "StrategicThesisStoreUnavailableError",
    "derive_committed_active_theses",
    "deserialize_active_theses",
    "load_latest_active_theses",
    "serialize_active_theses",
]
