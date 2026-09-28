from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Iterable
from uuid import UUID

from ai_spot_trader.analytics.paper import PaperAnalyticsReport
from ai_spot_trader.domain.enums import MarketType, PositionSide
from ai_spot_trader.domain.models import Fill, PortfolioState
from ai_spot_trader.domain.symbols import parse_canonical_symbol
from ai_spot_trader.persistence.query import (
    CycleAuditDetail,
    CycleAuditSummary,
    DecisionExecutionAuditItem,
    FillAuditItem,
)
from ai_spot_trader.persistence.runs import PaperRunView

ZERO = Decimal(0)


class EconomicHistoryDataError(ValueError):
    """Raised when durable audit facts cannot be projected economically without guessing."""


@dataclass(frozen=True, slots=True)
class EconomicOperation:
    paper_run_id: UUID | None
    cycle_id: UUID
    decision_index: int
    execution_id: UUID
    filled_at: datetime
    symbol: str
    market_type: str
    action: str
    economic_effect: str
    quantity: Decimal
    reference_price: Decimal
    price: Decimal
    notional: Decimal
    fee: Decimal
    spread_cost: Decimal
    slippage_cost: Decimal
    funding_pnl: Decimal
    execution_costs: Decimal
    total_costs: Decimal
    realized_pnl: Decimal
    position_before: Decimal
    position_after: Decimal
    fill_count: int
    fill_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class EconomicHistorySummary:
    initial_equity: Decimal | None
    ending_equity: Decimal | None
    gross_pnl: Decimal
    net_pnl: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal | None
    fees: Decimal
    spread_cost: Decimal
    slippage_cost: Decimal
    funding_pnl: Decimal
    execution_costs: Decimal
    total_costs: Decimal
    max_drawdown_value: Decimal
    max_drawdown_fraction: Decimal | None
    current_drawdown_value: Decimal
    current_drawdown_fraction: Decimal | None
    current_exposure_value: Decimal
    current_exposure_fraction: Decimal | None
    completed_cycle_count: int
    failed_cycle_count: int
    decision_count: int
    buy_decision_count: int
    sell_decision_count: int
    hold_count: int
    reject_count: int
    modify_count: int
    trade_count: int
    buy_trade_count: int
    sell_trade_count: int
    fill_count: int
    total_notional: Decimal
    turnover_fraction: Decimal | None
    costs_to_notional_fraction: Decimal | None
    costs_to_initial_equity_fraction: Decimal | None
    duration_hours: Decimal | None
    fills_per_hour: Decimal | None
    market_switch_count: int
    market_switches_per_hour: Decimal | None
    open_count: int
    increase_count: int
    reduce_count: int
    close_count: int
    flip_count: int
    long_effect_count: int
    short_effect_count: int
    first_at: datetime | None
    last_at: datetime | None


@dataclass(frozen=True, slots=True)
class EconomicHistoryReport:
    paper_run_id: UUID
    lineage_paper_run_ids: tuple[UUID, ...]
    calculation_version: str
    timezone: str
    source_digest: str
    summary: EconomicHistorySummary
    operations: tuple[EconomicOperation, ...]
    cycles: tuple[CycleAuditSummary, ...]


@dataclass(frozen=True, slots=True)
class _Trajectory:
    decision_index: int
    agent_input: dict[str, object] | None
    fills: tuple[FillAuditItem, ...]
    portfolio_state_after: dict[str, object] | None


def project_economic_history(
    *,
    paper_run_id: UUID,
    analytics: PaperAnalyticsReport,
    cycles: tuple[CycleAuditDetail, ...],
    cycle_summaries: tuple[CycleAuditSummary, ...],
    lineage: tuple[PaperRunView, ...],
) -> EconomicHistoryReport:
    """Project readable economic history from canonical analytics and persisted audit facts.

    P&L, equity, drawdown, exposure and funding are taken from the existing canonical
    PaperAnalyticsReport. This projection only adds descriptive operation/turnover views from
    persisted fills and portfolio snapshots; it never recomputes the trading ledger.
    """

    if not lineage:
        raise EconomicHistoryDataError("economic history requires a PAPER run lineage")
    if lineage[-1].paper_run_id != paper_run_id:
        raise EconomicHistoryDataError("PAPER run lineage does not end at the requested run")

    ordered_cycles = tuple(
        sorted(cycles, key=lambda item: (item.recorded_at, str(item.cycle_id)))
    )
    ordered_summaries = tuple(
        sorted(cycle_summaries, key=lambda item: (item.recorded_at, str(item.cycle_id)))
    )

    operations: list[EconomicOperation] = []
    terminal_portfolio: PortfolioState | None = None

    for cycle in ordered_cycles:
        if cycle.status == "FAILED":
            # Failed-cycle fills are audit evidence only. Canonical analytics roll them back and
            # this economic projection must do the same.
            continue

        for trajectory in _trajectories(cycle):
            before = _portfolio_from_agent_input(trajectory.agent_input)
            after = _portfolio_from_payload(trajectory.portfolio_state_after)
            if after is not None:
                terminal_portfolio = after
            elif before is not None:
                terminal_portfolio = before

            if not trajectory.fills:
                continue
            if before is None or after is None:
                raise EconomicHistoryDataError(
                    "executed decision is missing durable before/after portfolio state"
                )

            fills = tuple(_fill(item) for item in trajectory.fills)
            operations.append(
                _operation(
                    cycle=cycle,
                    trajectory=trajectory,
                    fills=fills,
                    before=before,
                    after=after,
                )
            )

    if terminal_portfolio is None:
        terminal_portfolio = _last_known_portfolio(ordered_cycles)

    operations.sort(
        key=lambda item: (
            item.filled_at,
            str(item.cycle_id),
            item.decision_index,
            str(item.execution_id),
        )
    )
    operation_tuple = tuple(operations)

    analytics_summary = analytics.summary
    execution_costs = (
        analytics_summary.fees
        + analytics_summary.spread_cost
        + analytics_summary.slippage_cost
    )
    # Funding P&L follows the analytics sign convention: negative is a cost, positive a benefit.
    total_costs = execution_costs - analytics_summary.funding_pnl
    total_notional = sum((item.notional for item in operation_tuple), ZERO)
    realized_pnl = sum((item.realized_pnl for item in operation_tuple), ZERO)
    unrealized_pnl = _unrealized_pnl(terminal_portfolio)

    decision_count = sum(item.decision_count for item in ordered_summaries)
    buy_decision_count = sum(item.buy_count for item in ordered_summaries)
    sell_decision_count = sum(item.sell_count for item in ordered_summaries)
    hold_count = sum(item.hold_count for item in ordered_summaries)
    reject_count = sum(item.risk_reject_count for item in ordered_summaries)
    modify_count = sum(item.risk_modify_count for item in ordered_summaries)

    duration_hours = _duration_hours(
        lineage=lineage,
        analytics=analytics,
        ordered_cycles=ordered_cycles,
    )
    fill_count = sum(item.fill_count for item in operation_tuple)
    market_switch_count = _market_switch_count(operation_tuple)

    effects = tuple(item.economic_effect for item in operation_tuple)
    open_count = sum(effect.startswith("OPEN_") or effect == "OPEN_SPOT" for effect in effects)
    increase_count = sum(
        effect.startswith("INCREASE_") or effect == "INCREASE_SPOT" for effect in effects
    )
    reduce_count = sum(
        effect.startswith("REDUCE_") or effect == "REDUCE_SPOT" for effect in effects
    )
    close_count = sum(
        effect.startswith("CLOSE_") or effect == "CLOSE_SPOT" for effect in effects
    )
    flip_count = sum(effect.startswith("FLIP_") for effect in effects)
    long_effect_count = sum(_is_long_effect(effect) for effect in effects)
    short_effect_count = sum(_is_short_effect(effect) for effect in effects)

    initial_equity = analytics_summary.initial_equity
    summary = EconomicHistorySummary(
        initial_equity=initial_equity,
        ending_equity=analytics_summary.ending_equity,
        gross_pnl=analytics_summary.gross_pnl,
        net_pnl=analytics_summary.net_pnl,
        realized_pnl=realized_pnl,
        unrealized_pnl=unrealized_pnl,
        fees=analytics_summary.fees,
        spread_cost=analytics_summary.spread_cost,
        slippage_cost=analytics_summary.slippage_cost,
        funding_pnl=analytics_summary.funding_pnl,
        execution_costs=execution_costs,
        total_costs=total_costs,
        max_drawdown_value=analytics_summary.max_drawdown_value,
        max_drawdown_fraction=analytics_summary.max_drawdown_fraction,
        current_drawdown_value=analytics_summary.current_drawdown_value,
        current_drawdown_fraction=analytics_summary.current_drawdown_fraction,
        current_exposure_value=analytics_summary.current_exposure_value,
        current_exposure_fraction=analytics_summary.current_exposure_fraction,
        completed_cycle_count=analytics_summary.completed_cycle_count,
        failed_cycle_count=analytics_summary.failed_cycle_count,
        decision_count=decision_count,
        buy_decision_count=buy_decision_count,
        sell_decision_count=sell_decision_count,
        hold_count=hold_count,
        reject_count=reject_count,
        modify_count=modify_count,
        trade_count=analytics_summary.trade_count,
        buy_trade_count=analytics_summary.buy_trade_count,
        sell_trade_count=analytics_summary.sell_trade_count,
        fill_count=fill_count,
        total_notional=total_notional,
        turnover_fraction=_ratio(total_notional, initial_equity),
        costs_to_notional_fraction=_ratio(total_costs, total_notional),
        costs_to_initial_equity_fraction=_ratio(total_costs, initial_equity),
        duration_hours=duration_hours,
        fills_per_hour=_ratio(Decimal(fill_count), duration_hours),
        market_switch_count=market_switch_count,
        market_switches_per_hour=_ratio(Decimal(market_switch_count), duration_hours),
        open_count=open_count,
        increase_count=increase_count,
        reduce_count=reduce_count,
        close_count=close_count,
        flip_count=flip_count,
        long_effect_count=long_effect_count,
        short_effect_count=short_effect_count,
        first_at=analytics_summary.first_at,
        last_at=analytics_summary.last_at,
    )

    return EconomicHistoryReport(
        paper_run_id=paper_run_id,
        lineage_paper_run_ids=tuple(item.paper_run_id for item in lineage),
        calculation_version=f"{analytics.calculation_version}+economic-history-v1",
        timezone=analytics.timezone,
        source_digest=analytics.source_digest,
        summary=summary,
        operations=operation_tuple,
        cycles=tuple(reversed(ordered_summaries)),
    )


def _trajectories(cycle: CycleAuditDetail) -> tuple[_Trajectory, ...]:
    if cycle.decision_results:
        return tuple(
            _Trajectory(
                decision_index=item.decision_index,
                agent_input=(
                    None if item.agent_input is None else dict(item.agent_input)
                ),
                fills=item.fills,
                portfolio_state_after=(
                    None
                    if item.portfolio_state_after is None
                    else dict(item.portfolio_state_after)
                ),
            )
            for item in cycle.decision_results
        )

    if cycle.decision is None:
        return ()
    return (
        _Trajectory(
            decision_index=0,
            agent_input=None if cycle.agent_input is None else dict(cycle.agent_input),
            fills=cycle.fills,
            portfolio_state_after=(
                None
                if cycle.portfolio_state_after is None
                else dict(cycle.portfolio_state_after)
            ),
        ),
    )


def _fill(item: FillAuditItem) -> Fill:
    try:
        return Fill.model_validate_json(json.dumps(item.payload))
    except ValueError as exc:
        raise EconomicHistoryDataError("invalid durable Fill payload") from exc


def _portfolio_from_agent_input(payload: dict[str, object] | None) -> PortfolioState | None:
    if payload is None:
        return None
    value = payload.get("portfolio_state")
    if not isinstance(value, dict):
        raise EconomicHistoryDataError("AgentInput has no durable portfolio_state")
    return _portfolio_from_payload(value)


def _portfolio_from_payload(payload: dict[str, object] | None) -> PortfolioState | None:
    if payload is None:
        return None
    try:
        return PortfolioState.model_validate_json(json.dumps(payload))
    except ValueError as exc:
        raise EconomicHistoryDataError("invalid durable PortfolioState payload") from exc


def _operation(
    *,
    cycle: CycleAuditDetail,
    trajectory: _Trajectory,
    fills: tuple[Fill, ...],
    before: PortfolioState,
    after: PortfolioState,
) -> EconomicOperation:
    first = fills[0]
    execution_ids = {item.execution_id for item in fills}
    symbols = {item.symbol for item in fills}
    actions = {item.action for item in fills}
    market_types = {item.market_type for item in fills}
    if len(execution_ids) != 1 or len(symbols) != 1 or len(actions) != 1 or len(market_types) != 1:
        raise EconomicHistoryDataError(
            "one decision trajectory contains incompatible fill identities"
        )

    quantity = sum((item.quantity for item in fills), ZERO)
    if quantity <= ZERO:
        raise EconomicHistoryDataError("economic operation has no positive filled quantity")
    reference_price = sum(
        (item.reference_price * item.quantity for item in fills), ZERO
    ) / quantity
    price = sum((item.price * item.quantity for item in fills), ZERO) / quantity
    notional = sum((item.notional for item in fills), ZERO)
    fee = sum((item.fee for item in fills), ZERO)
    spread = sum((item.spread_cost for item in fills), ZERO)
    slippage = sum((item.slippage_cost for item in fills), ZERO)
    funding = sum((item.funding_payment for item in fills), ZERO)
    realized = sum((item.realized_pnl for item in fills), ZERO)
    execution_costs = fee + spread + slippage
    total_costs = execution_costs - funding
    position_before = _signed_position(before, first)
    position_after = _signed_position(after, first)

    return EconomicOperation(
        paper_run_id=cycle.paper_run_id,
        cycle_id=cycle.cycle_id,
        decision_index=trajectory.decision_index,
        execution_id=first.execution_id,
        filled_at=max(item.filled_at for item in fills),
        symbol=first.symbol,
        market_type=first.market_type.value,
        action=first.action.value,
        economic_effect=_economic_effect(
            market_type=first.market_type,
            before=position_before,
            after=position_after,
        ),
        quantity=quantity,
        reference_price=reference_price,
        price=price,
        notional=notional,
        fee=fee,
        spread_cost=spread,
        slippage_cost=slippage,
        funding_pnl=funding,
        execution_costs=execution_costs,
        total_costs=total_costs,
        realized_pnl=realized,
        position_before=position_before,
        position_after=position_after,
        fill_count=len(fills),
        fill_ids=tuple(item.fill_id for item in fills),
    )


def _signed_position(state: PortfolioState, fill: Fill) -> Decimal:
    if fill.market_type is MarketType.SPOT:
        base_asset, _ = parse_canonical_symbol(fill.symbol)
        position = next(
            (item for item in state.positions if item.asset == base_asset),
            None,
        )
        return ZERO if position is None else position.quantity

    position = next(
        (item for item in state.derivative_positions if item.symbol == fill.symbol),
        None,
    )
    if position is None:
        return ZERO
    return position.quantity if position.side is PositionSide.LONG else -position.quantity


def _economic_effect(*, market_type: MarketType, before: Decimal, after: Decimal) -> str:
    if market_type is MarketType.SPOT:
        if before == ZERO and after > ZERO:
            return "OPEN_SPOT"
        if after > before:
            return "INCREASE_SPOT"
        if before > ZERO and after == ZERO:
            return "CLOSE_SPOT"
        if ZERO <= after < before:
            return "REDUCE_SPOT"
        return "EXECUTED_SPOT"

    if before == ZERO:
        if after > ZERO:
            return "OPEN_LONG"
        if after < ZERO:
            return "OPEN_SHORT"
        return "EXECUTED_FLAT"

    if before > ZERO:
        if after > before:
            return "INCREASE_LONG"
        if ZERO < after < before:
            return "REDUCE_LONG"
        if after == ZERO:
            return "CLOSE_LONG"
        if after < ZERO:
            return "FLIP_LONG_TO_SHORT"
        return "EXECUTED_LONG"

    if after < before:
        return "INCREASE_SHORT"
    if before < after < ZERO:
        return "REDUCE_SHORT"
    if after == ZERO:
        return "CLOSE_SHORT"
    if after > ZERO:
        return "FLIP_SHORT_TO_LONG"
    return "EXECUTED_SHORT"


def _last_known_portfolio(cycles: Iterable[CycleAuditDetail]) -> PortfolioState | None:
    candidate: PortfolioState | None = None
    for cycle in cycles:
        if cycle.status == "FAILED":
            continue
        for trajectory in _trajectories(cycle):
            after = _portfolio_from_payload(trajectory.portfolio_state_after)
            if after is not None:
                candidate = after
                continue
            before = _portfolio_from_agent_input(trajectory.agent_input)
            if before is not None:
                candidate = before
        if cycle.portfolio_state_after is not None:
            value = _portfolio_from_payload(dict(cycle.portfolio_state_after))
            if value is not None:
                candidate = value
    return candidate


def _unrealized_pnl(state: PortfolioState | None) -> Decimal | None:
    if state is None:
        return None
    if any(item.unrealized_pnl is None for item in state.positions):
        return None
    spot = sum(
        (item.unrealized_pnl or ZERO for item in state.positions),
        ZERO,
    )
    derivatives = sum(
        (item.unrealized_pnl for item in state.derivative_positions),
        ZERO,
    )
    return spot + derivatives


def _duration_hours(
    *,
    lineage: tuple[PaperRunView, ...],
    analytics: PaperAnalyticsReport,
    ordered_cycles: tuple[CycleAuditDetail, ...],
) -> Decimal | None:
    start = lineage[0].started_at
    end = lineage[-1].ended_at
    if end is None:
        candidates = [lineage[-1].started_at]
        if analytics.summary.last_at is not None:
            candidates.append(analytics.summary.last_at)
        if ordered_cycles:
            candidates.append(ordered_cycles[-1].recorded_at)
        end = max(candidates)
    if end is None or end <= start:
        return None
    return _timedelta_hours(end - start)


def _timedelta_hours(value: timedelta) -> Decimal:
    total_microseconds = (
        (value.days * 86_400 + value.seconds) * 1_000_000 + value.microseconds
    )
    return Decimal(total_microseconds) / Decimal(3_600_000_000)


def _market_switch_count(operations: tuple[EconomicOperation, ...]) -> int:
    switches = 0
    previous: tuple[str, str] | None = None
    for operation in operations:
        current = (operation.symbol, operation.market_type)
        if previous is not None and current != previous:
            switches += 1
        previous = current
    return switches


def _ratio(numerator: Decimal, denominator: Decimal | None) -> Decimal | None:
    if denominator is None or denominator == ZERO:
        return None
    return numerator / denominator


def _is_long_effect(effect: str) -> bool:
    return effect in {
        "OPEN_LONG",
        "INCREASE_LONG",
        "REDUCE_LONG",
        "CLOSE_LONG",
        "FLIP_SHORT_TO_LONG",
        "EXECUTED_LONG",
    }


def _is_short_effect(effect: str) -> bool:
    return effect in {
        "OPEN_SHORT",
        "INCREASE_SHORT",
        "REDUCE_SHORT",
        "CLOSE_SHORT",
        "FLIP_LONG_TO_SHORT",
        "EXECUTED_SHORT",
    }


__all__ = [
    "EconomicHistoryDataError",
    "EconomicHistoryReport",
    "EconomicHistorySummary",
    "EconomicOperation",
    "project_economic_history",
]
