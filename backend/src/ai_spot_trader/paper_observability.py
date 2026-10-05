from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from ai_spot_trader.domain.enums import MarketType, RiskDecision, TradingAction
from ai_spot_trader.domain.models import DecisionCandidate, PortfolioState, RiskAssessment
from ai_spot_trader.domain.symbols import parse_canonical_symbol
from ai_spot_trader.economic_history import EconomicHistoryReport, EconomicOperation
from ai_spot_trader.persistence.query import CycleAuditDetail, FillAuditItem

ZERO = Decimal(0)


class PaperObservabilityDataError(ValueError):
    """Raised when persisted audit facts cannot be projected without guessing."""


@dataclass(frozen=True, slots=True)
class PaperObservabilityBreakdown:
    scope: str
    gross_pnl: Decimal | None
    net_pnl: Decimal | None
    realized_pnl: Decimal
    unrealized_pnl: Decimal | None
    fees: Decimal
    spread_cost: Decimal
    slippage_cost: Decimal
    funding_pnl: Decimal
    execution_costs: Decimal
    total_costs: Decimal
    total_notional: Decimal
    trade_count: int
    fill_count: int
    current_exposure_value: Decimal | None
    current_exposure_fraction: Decimal | None


@dataclass(frozen=True, slots=True)
class PaperDecisionFunnel:
    decision_count: int
    buy_count: int
    sell_count: int
    hold_count: int
    risk_allow_count: int
    risk_modify_count: int
    risk_reject_count: int
    execution_intent_count: int
    decisions_with_fill: int
    decisions_without_fill: int
    fill_count: int
    economic_trade_count: int


@dataclass(frozen=True, slots=True)
class PaperMarketObservability:
    symbol: str
    market_type: str
    decision_count: int
    buy_count: int
    sell_count: int
    hold_count: int
    risk_allow_count: int
    risk_modify_count: int
    risk_reject_count: int
    decisions_with_fill: int
    decisions_without_fill: int
    trade_count: int
    fill_count: int
    total_notional: Decimal
    fees: Decimal
    spread_cost: Decimal
    slippage_cost: Decimal
    funding_pnl: Decimal | None
    execution_costs: Decimal
    total_costs: Decimal | None
    realized_pnl: Decimal
    current_exposure_value: Decimal | None
    current_exposure_fraction: Decimal | None
    unrealized_pnl: Decimal | None


@dataclass(frozen=True, slots=True)
class PaperObservabilityReport:
    calculation_version: str
    timezone: str
    source_digest: str
    breakdowns: tuple[PaperObservabilityBreakdown, ...]
    funnel: PaperDecisionFunnel
    markets: tuple[PaperMarketObservability, ...]
    unavailable_metrics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _DecisionTrajectory:
    decision_index: int
    decision: dict[str, object]
    risk_assessment: dict[str, object] | None
    execution_intent: dict[str, object] | None
    fills: tuple[FillAuditItem, ...]


@dataclass(slots=True)
class _MarketAccumulator:
    symbol: str
    market_type: str
    decision_count: int = 0
    buy_count: int = 0
    sell_count: int = 0
    hold_count: int = 0
    risk_allow_count: int = 0
    risk_modify_count: int = 0
    risk_reject_count: int = 0
    decisions_with_fill: int = 0
    trade_count: int = 0
    fill_count: int = 0
    total_notional: Decimal = ZERO
    fees: Decimal = ZERO
    spread_cost: Decimal = ZERO
    slippage_cost: Decimal = ZERO
    funding_pnl: Decimal = ZERO
    realized_pnl: Decimal = ZERO


def project_paper_observability(
    *,
    history: EconomicHistoryReport,
    cycles: tuple[CycleAuditDetail, ...],
) -> PaperObservabilityReport:
    """Build read-only PAPER observability from canonical economics and durable audits.

    The projection never recomputes global equity, gross/net P&L, drawdown or canonical
    execution costs. Those values are copied from ``EconomicHistoryReport``. Per-market-type
    gross/net P&L is deliberately left unavailable because the current durable facts do not
    provide an exact causal allocation of total equity changes across SPOT and PERPETUAL.
    """

    ordered_cycles = tuple(
        sorted(cycles, key=lambda item: (item.recorded_at, str(item.cycle_id)))
    )
    terminal_portfolio = _terminal_portfolio(ordered_cycles)
    ending_equity = history.summary.ending_equity

    market_accumulators: dict[tuple[str, str], _MarketAccumulator] = {}
    decision_count = 0
    buy_count = 0
    sell_count = 0
    hold_count = 0
    risk_allow_count = 0
    risk_modify_count = 0
    risk_reject_count = 0
    execution_intent_count = 0
    decisions_with_fill = 0

    for cycle in ordered_cycles:
        committed = cycle.status != "FAILED"
        for trajectory in _decision_trajectories(cycle):
            decision = _decision(trajectory.decision)
            risk = _risk(trajectory.risk_assessment)
            key = (decision.symbol, decision.market_type.value)
            market = market_accumulators.setdefault(
                key,
                _MarketAccumulator(symbol=decision.symbol, market_type=decision.market_type.value),
            )

            decision_count += 1
            market.decision_count += 1
            if decision.action is TradingAction.BUY:
                buy_count += 1
                market.buy_count += 1
            elif decision.action is TradingAction.SELL:
                sell_count += 1
                market.sell_count += 1
            else:
                hold_count += 1
                market.hold_count += 1

            if risk is not None:
                if risk.status is RiskDecision.ALLOW:
                    risk_allow_count += 1
                    market.risk_allow_count += 1
                elif risk.status is RiskDecision.MODIFY:
                    risk_modify_count += 1
                    market.risk_modify_count += 1
                elif risk.status is RiskDecision.REJECT:
                    risk_reject_count += 1
                    market.risk_reject_count += 1

            if trajectory.execution_intent is not None:
                execution_intent_count += 1

            if committed and trajectory.fills:
                decisions_with_fill += 1
                market.decisions_with_fill += 1

    for operation in history.operations:
        key = (operation.symbol, operation.market_type)
        market = market_accumulators.setdefault(
            key,
            _MarketAccumulator(symbol=operation.symbol, market_type=operation.market_type),
        )
        _add_operation(market, operation)

    fill_count = history.summary.fill_count
    funnel = PaperDecisionFunnel(
        decision_count=decision_count,
        buy_count=buy_count,
        sell_count=sell_count,
        hold_count=hold_count,
        risk_allow_count=risk_allow_count,
        risk_modify_count=risk_modify_count,
        risk_reject_count=risk_reject_count,
        execution_intent_count=execution_intent_count,
        decisions_with_fill=decisions_with_fill,
        decisions_without_fill=decision_count - decisions_with_fill,
        fill_count=fill_count,
        economic_trade_count=history.summary.trade_count,
    )

    breakdowns = (
        _total_breakdown(history),
        _market_type_breakdown(
            scope="SPOT",
            history=history,
            terminal_portfolio=terminal_portfolio,
            market_type=MarketType.SPOT,
        ),
        _market_type_breakdown(
            scope="PERPETUAL",
            history=history,
            terminal_portfolio=terminal_portfolio,
            market_type=MarketType.PERPETUAL,
        ),
    )

    spot_symbols_by_asset: dict[str, set[str]] = {}
    for symbol, market_type in market_accumulators:
        if market_type != MarketType.SPOT.value:
            continue
        try:
            base_asset, _ = parse_canonical_symbol(symbol)
        except ValueError as exc:
            raise PaperObservabilityDataError("invalid durable SPOT market symbol") from exc
        spot_symbols_by_asset.setdefault(base_asset, set()).add(symbol)

    markets = tuple(
        _market_report(
            accumulator=market_accumulators[key],
            terminal_portfolio=terminal_portfolio,
            ending_equity=ending_equity,
            spot_symbols_by_asset=spot_symbols_by_asset,
        )
        for key in sorted(market_accumulators)
    )

    return PaperObservabilityReport(
        calculation_version=f"{history.calculation_version}+paper-observability-v1",
        timezone=history.timezone,
        source_digest=history.source_digest,
        breakdowns=breakdowns,
        funnel=funnel,
        markets=markets,
        unavailable_metrics=(
            "SPOT.gross_pnl: exact causal allocation unavailable from current durable facts",
            "SPOT.net_pnl: exact causal allocation unavailable from current durable facts",
            "PERPETUAL.gross_pnl: exact causal allocation unavailable from current durable facts",
            "PERPETUAL.net_pnl: exact causal allocation unavailable from current durable facts",
        ),
    )


def _decision_trajectories(cycle: CycleAuditDetail) -> tuple[_DecisionTrajectory, ...]:
    if cycle.decision_results:
        return tuple(
            _DecisionTrajectory(
                decision_index=item.decision_index,
                decision=dict(item.decision),
                risk_assessment=(
                    None if item.risk_assessment is None else dict(item.risk_assessment)
                ),
                execution_intent=(
                    None if item.execution_intent is None else dict(item.execution_intent)
                ),
                fills=item.fills,
            )
            for item in sorted(cycle.decision_results, key=lambda item: item.decision_index)
        )
    if cycle.decision is None:
        return ()
    return (
        _DecisionTrajectory(
            decision_index=0,
            decision=dict(cycle.decision),
            risk_assessment=(
                None if cycle.risk_assessment is None else dict(cycle.risk_assessment)
            ),
            execution_intent=(
                None if cycle.execution_intent is None else dict(cycle.execution_intent)
            ),
            fills=cycle.fills,
        ),
    )


def _decision(payload: dict[str, object]) -> DecisionCandidate:
    try:
        return DecisionCandidate.model_validate_json(json.dumps(payload))
    except ValueError as exc:
        raise PaperObservabilityDataError("invalid durable DecisionCandidate payload") from exc


def _risk(payload: dict[str, object] | None) -> RiskAssessment | None:
    if payload is None:
        return None
    try:
        return RiskAssessment.model_validate_json(json.dumps(payload))
    except ValueError as exc:
        raise PaperObservabilityDataError("invalid durable RiskAssessment payload") from exc


def _add_operation(accumulator: _MarketAccumulator, operation: EconomicOperation) -> None:
    if operation.market_type == MarketType.SPOT.value and operation.funding_pnl != ZERO:
        raise PaperObservabilityDataError("SPOT operation carries non-zero funding P&L")
    accumulator.trade_count += 1
    accumulator.fill_count += operation.fill_count
    accumulator.total_notional += operation.notional
    accumulator.fees += operation.fee
    accumulator.spread_cost += operation.spread_cost
    accumulator.slippage_cost += operation.slippage_cost
    accumulator.funding_pnl += operation.funding_pnl
    accumulator.realized_pnl += operation.realized_pnl


def _total_breakdown(history: EconomicHistoryReport) -> PaperObservabilityBreakdown:
    summary = history.summary
    return PaperObservabilityBreakdown(
        scope="TOTAL",
        gross_pnl=summary.gross_pnl,
        net_pnl=summary.net_pnl,
        realized_pnl=summary.realized_pnl,
        unrealized_pnl=summary.unrealized_pnl,
        fees=summary.fees,
        spread_cost=summary.spread_cost,
        slippage_cost=summary.slippage_cost,
        funding_pnl=summary.funding_pnl,
        execution_costs=summary.execution_costs,
        total_costs=summary.total_costs,
        total_notional=summary.total_notional,
        trade_count=summary.trade_count,
        fill_count=summary.fill_count,
        current_exposure_value=summary.current_exposure_value,
        current_exposure_fraction=summary.current_exposure_fraction,
    )


def _market_type_breakdown(
    *,
    scope: str,
    history: EconomicHistoryReport,
    terminal_portfolio: PortfolioState | None,
    market_type: MarketType,
) -> PaperObservabilityBreakdown:
    operations = tuple(
        item for item in history.operations if item.market_type == market_type.value
    )
    realized_funding = sum((item.funding_pnl for item in operations), ZERO)
    if market_type is MarketType.SPOT and realized_funding != ZERO:
        raise PaperObservabilityDataError("SPOT operations carry non-zero funding P&L")
    funding = (
        ZERO
        if market_type is MarketType.SPOT
        else history.summary.funding_pnl
        if market_type is MarketType.PERPETUAL
        else realized_funding
    )
    fees = sum((item.fee for item in operations), ZERO)
    spread = sum((item.spread_cost for item in operations), ZERO)
    slippage = sum((item.slippage_cost for item in operations), ZERO)
    execution_costs = fees + spread + slippage
    exposure, unrealized = _type_terminal_metrics(terminal_portfolio, market_type)
    return PaperObservabilityBreakdown(
        scope=scope,
        gross_pnl=None,
        net_pnl=None,
        realized_pnl=sum((item.realized_pnl for item in operations), ZERO),
        unrealized_pnl=unrealized,
        fees=fees,
        spread_cost=spread,
        slippage_cost=slippage,
        funding_pnl=funding,
        execution_costs=execution_costs,
        total_costs=execution_costs - funding,
        total_notional=sum((item.notional for item in operations), ZERO),
        trade_count=len(operations),
        fill_count=sum(item.fill_count for item in operations),
        current_exposure_value=exposure,
        current_exposure_fraction=_ratio(exposure, history.summary.ending_equity),
    )


def _type_terminal_metrics(
    state: PortfolioState | None,
    market_type: MarketType,
) -> tuple[Decimal | None, Decimal | None]:
    if state is None:
        return None, None
    if market_type is MarketType.PERPETUAL:
        return (
            sum((item.notional for item in state.derivative_positions), ZERO),
            sum((item.unrealized_pnl for item in state.derivative_positions), ZERO),
        )
    if market_type is MarketType.SPOT:
        if any(item.market_value is None for item in state.positions):
            exposure: Decimal | None = None
        else:
            exposure = sum((item.market_value or ZERO for item in state.positions), ZERO)
        if any(item.unrealized_pnl is None for item in state.positions):
            unrealized: Decimal | None = None
        else:
            unrealized = sum((item.unrealized_pnl or ZERO for item in state.positions), ZERO)
        return exposure, unrealized
    return None, None


def _market_report(
    *,
    accumulator: _MarketAccumulator,
    terminal_portfolio: PortfolioState | None,
    ending_equity: Decimal | None,
    spot_symbols_by_asset: dict[str, set[str]],
) -> PaperMarketObservability:
    exposure, unrealized = _market_terminal_metrics(
        terminal_portfolio,
        symbol=accumulator.symbol,
        market_type=accumulator.market_type,
        spot_symbols_by_asset=spot_symbols_by_asset,
    )
    funding = _market_funding_pnl(
        accumulator=accumulator,
        terminal_portfolio=terminal_portfolio,
    )
    execution_costs = accumulator.fees + accumulator.spread_cost + accumulator.slippage_cost
    return PaperMarketObservability(
        symbol=accumulator.symbol,
        market_type=accumulator.market_type,
        decision_count=accumulator.decision_count,
        buy_count=accumulator.buy_count,
        sell_count=accumulator.sell_count,
        hold_count=accumulator.hold_count,
        risk_allow_count=accumulator.risk_allow_count,
        risk_modify_count=accumulator.risk_modify_count,
        risk_reject_count=accumulator.risk_reject_count,
        decisions_with_fill=accumulator.decisions_with_fill,
        decisions_without_fill=(
            accumulator.decision_count - accumulator.decisions_with_fill
        ),
        trade_count=accumulator.trade_count,
        fill_count=accumulator.fill_count,
        total_notional=accumulator.total_notional,
        fees=accumulator.fees,
        spread_cost=accumulator.spread_cost,
        slippage_cost=accumulator.slippage_cost,
        funding_pnl=funding,
        execution_costs=execution_costs,
        total_costs=None if funding is None else execution_costs - funding,
        realized_pnl=accumulator.realized_pnl,
        current_exposure_value=exposure,
        current_exposure_fraction=_ratio(exposure, ending_equity),
        unrealized_pnl=unrealized,
    )


def _market_funding_pnl(
    *,
    accumulator: _MarketAccumulator,
    terminal_portfolio: PortfolioState | None,
) -> Decimal | None:
    if accumulator.market_type == MarketType.SPOT.value:
        if accumulator.funding_pnl != ZERO:
            raise PaperObservabilityDataError("SPOT operation carries non-zero funding P&L")
        return ZERO
    if accumulator.market_type != MarketType.PERPETUAL.value:
        return accumulator.funding_pnl
    if terminal_portfolio is None:
        return None
    position = next(
        (
            item
            for item in terminal_portfolio.derivative_positions
            if item.symbol == accumulator.symbol
        ),
        None,
    )
    open_funding = ZERO if position is None else position.cumulative_funding
    return accumulator.funding_pnl + open_funding


def _market_terminal_metrics(
    state: PortfolioState | None,
    *,
    symbol: str,
    market_type: str,
    spot_symbols_by_asset: dict[str, set[str]],
) -> tuple[Decimal | None, Decimal | None]:
    if state is None:
        return None, None
    if market_type == MarketType.PERPETUAL.value:
        position = next(
            (item for item in state.derivative_positions if item.symbol == symbol),
            None,
        )
        if position is None:
            return ZERO, ZERO
        return position.notional, position.unrealized_pnl
    if market_type != MarketType.SPOT.value:
        return None, None
    try:
        base_asset, _ = parse_canonical_symbol(symbol)
    except ValueError as exc:
        raise PaperObservabilityDataError("invalid durable SPOT market symbol") from exc
    if len(spot_symbols_by_asset.get(base_asset, set())) != 1:
        return None, None
    position = next((item for item in state.positions if item.asset == base_asset), None)
    if position is None:
        return ZERO, ZERO
    return position.market_value, position.unrealized_pnl


def _terminal_portfolio(cycles: tuple[CycleAuditDetail, ...]) -> PortfolioState | None:
    candidate: PortfolioState | None = None
    for cycle in cycles:
        if cycle.status == "FAILED":
            continue
        if cycle.decision_results:
            for item in sorted(cycle.decision_results, key=lambda value: value.decision_index):
                if item.portfolio_state_after is not None:
                    candidate = _portfolio(dict(item.portfolio_state_after))
                    continue
                candidate = _portfolio_from_agent_input(item.agent_input) or candidate
            if cycle.portfolio_state_after is not None:
                candidate = _portfolio(dict(cycle.portfolio_state_after))
        elif cycle.portfolio_state_after is not None:
            candidate = _portfolio(dict(cycle.portfolio_state_after))
        else:
            candidate = _portfolio_from_agent_input(cycle.agent_input) or candidate
    return candidate


def _portfolio_from_agent_input(payload: dict[str, object] | None) -> PortfolioState | None:
    if payload is None:
        return None
    value = payload.get("portfolio_state")
    if value is None:
        return None
    if not isinstance(value, dict):
        raise PaperObservabilityDataError("AgentInput portfolio_state is not an object")
    return _portfolio(value)


def _portfolio(payload: dict[str, object]) -> PortfolioState:
    try:
        return PortfolioState.model_validate_json(json.dumps(payload))
    except ValueError as exc:
        raise PaperObservabilityDataError("invalid durable PortfolioState payload") from exc


def _ratio(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or denominator is None or denominator == ZERO:
        return None
    return numerator / denominator


__all__ = [
    "PaperDecisionFunnel",
    "PaperMarketObservability",
    "PaperObservabilityBreakdown",
    "PaperObservabilityDataError",
    "PaperObservabilityReport",
    "project_paper_observability",
]
