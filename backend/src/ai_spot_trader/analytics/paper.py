from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from ai_spot_trader.domain.enums import MarketType, RiskDecision, TradingAction
from ai_spot_trader.domain.models import (
    AgentInput,
    AssetBalance,
    AssetPosition,
    DecisionCandidate,
    Fill,
    PortfolioState,
    RiskAssessment,
)
from ai_spot_trader.domain.symbols import parse_canonical_symbol

ANALYTICS_VERSION = "paper-analytics-v1"
DERIVATIVES_ANALYTICS_VERSION = "paper-analytics-v2"
ZERO = Decimal(0)


class PaperAnalyticsDataError(ValueError):
    """Raised when durable facts cannot be replayed honestly and deterministically."""


@dataclass(frozen=True, slots=True)
class PaperAnalyticsCycleFact:
    cycle_id: UUID
    status: str
    recorded_at: datetime
    result_digest: str
    agent_input_payload: dict[str, object] | None
    decision_payload: dict[str, object] | None
    risk_assessment_payload: dict[str, object] | None
    fill_payloads: tuple[dict[str, object], ...]
    portfolio_after_payload: dict[str, object] | None


@dataclass(frozen=True, slots=True)
class PaperAnalyticsPoint:
    cycle_id: UUID
    at: datetime
    status: str
    action: str | None
    risk_status: str | None
    symbol: str
    reference_price: Decimal
    equity: Decimal
    gross_pnl: Decimal
    net_pnl: Decimal
    cumulative_fees: Decimal
    cumulative_spread_cost: Decimal
    cumulative_slippage_cost: Decimal
    cumulative_funding_pnl: Decimal
    exposure_value: Decimal
    exposure_fraction: Decimal | None
    cumulative_return_fraction: Decimal | None
    drawdown_value: Decimal
    drawdown_fraction: Decimal | None
    trade_count: int


@dataclass(frozen=True, slots=True)
class PaperDailyPerformance:
    day: date
    closing_at: datetime
    closing_equity: Decimal
    gross_pnl: Decimal
    net_pnl: Decimal
    daily_net_pnl: Decimal
    daily_return_fraction: Decimal | None
    cumulative_return_fraction: Decimal | None
    fees: Decimal
    spread_cost: Decimal
    slippage_cost: Decimal
    funding_pnl: Decimal
    trade_count: int


@dataclass(frozen=True, slots=True)
class PaperAnalyticsSummary:
    initial_equity: Decimal | None
    ending_equity: Decimal | None
    gross_pnl: Decimal
    net_pnl: Decimal
    fees: Decimal
    spread_cost: Decimal
    slippage_cost: Decimal
    max_drawdown_value: Decimal
    max_drawdown_fraction: Decimal | None
    current_drawdown_value: Decimal
    current_drawdown_fraction: Decimal | None
    current_exposure_value: Decimal
    current_exposure_fraction: Decimal | None
    trade_count: int
    buy_trade_count: int
    sell_trade_count: int
    hold_count: int
    reject_count: int
    modify_count: int
    completed_cycle_count: int
    failed_cycle_count: int
    valued_cycle_count: int
    first_at: datetime | None
    last_at: datetime | None
    funding_pnl: Decimal = ZERO


@dataclass(frozen=True, slots=True)
class PaperAnalyticsReport:
    calculation_version: str
    timezone: str
    source_digest: str
    summary: PaperAnalyticsSummary
    points: tuple[PaperAnalyticsPoint, ...]
    daily: tuple[PaperDailyPerformance, ...]


@dataclass(frozen=True, slots=True)
class _PreparedCycle:
    cycle_id: UUID
    status: str
    at: datetime
    agent_input: AgentInput
    decision: DecisionCandidate | None
    risk_assessment: RiskAssessment | None
    fills: tuple[Fill, ...]
    portfolio_after: PortfolioState


def build_paper_analytics_report(
    facts: tuple[PaperAnalyticsCycleFact, ...],
) -> PaperAnalyticsReport:
    """Replay PAPER metrics from immutable durable facts without current-time input."""

    ordered_source = tuple(
        sorted(facts, key=lambda item: (_utc(item.recorded_at), str(item.cycle_id)))
    )
    source_digest = _source_digest(ordered_source)

    completed_cycle_count = sum(item.status == "COMPLETED" for item in ordered_source)
    failed_cycle_count = sum(item.status == "FAILED" for item in ordered_source)
    hold_count = 0
    reject_count = 0
    modify_count = 0

    prepared: list[_PreparedCycle] = []
    for fact in ordered_source:
        decision = _parse_decision(fact.decision_payload)
        risk = _parse_risk_assessment(fact.risk_assessment_payload)
        if decision is not None and decision.action is TradingAction.HOLD:
            hold_count += 1
        if risk is not None and risk.status is RiskDecision.REJECT:
            reject_count += 1
        if risk is not None and risk.status is RiskDecision.MODIFY:
            modify_count += 1

        if fact.agent_input_payload is None:
            continue
        try:
            agent_input = AgentInput.model_validate_json(json.dumps(fact.agent_input_payload))
        except ValueError as exc:
            raise PaperAnalyticsDataError("invalid durable AgentInput payload") from exc
        fills = _parse_fills(fact.fill_payloads)
        portfolio_after = _resolve_portfolio_after(
            agent_input=agent_input,
            fills=fills,
            payload=fact.portfolio_after_payload,
        )
        _validate_fill_market_link(agent_input=agent_input, fills=fills)
        at = _cycle_end_time(agent_input=agent_input, fills=fills, portfolio_after=portfolio_after)
        prepared.append(
            _PreparedCycle(
                cycle_id=fact.cycle_id,
                status=fact.status,
                at=at,
                agent_input=agent_input,
                decision=decision,
                risk_assessment=risk,
                fills=fills,
                portfolio_after=portfolio_after,
            )
        )

    prepared.sort(key=lambda item: (item.at, str(item.cycle_id)))
    calculation_version = (
        DERIVATIVES_ANALYTICS_VERSION
        if any(
            item.agent_input.market_state.market_type is not MarketType.SPOT
            for item in prepared
        )
        else ANALYTICS_VERSION
    )
    if not prepared:
        summary = PaperAnalyticsSummary(
            initial_equity=None,
            ending_equity=None,
            gross_pnl=ZERO,
            net_pnl=ZERO,
            fees=ZERO,
            spread_cost=ZERO,
            slippage_cost=ZERO,
            funding_pnl=ZERO,
            max_drawdown_value=ZERO,
            max_drawdown_fraction=None,
            current_drawdown_value=ZERO,
            current_drawdown_fraction=None,
            current_exposure_value=ZERO,
            current_exposure_fraction=None,
            trade_count=0,
            buy_trade_count=0,
            sell_trade_count=0,
            hold_count=hold_count,
            reject_count=reject_count,
            modify_count=modify_count,
            completed_cycle_count=completed_cycle_count,
            failed_cycle_count=failed_cycle_count,
            valued_cycle_count=0,
            first_at=None,
            last_at=None,
        )
        return PaperAnalyticsReport(
            calculation_version=ANALYTICS_VERSION,
            timezone="UTC",
            source_digest=source_digest,
            summary=summary,
            points=(),
            daily=(),
        )

    first = prepared[0]
    first_market = first.agent_input.market_state
    initial_equity, _, _ = _value_portfolio(
        first.agent_input.portfolio_state,
        symbol=first_market.symbol,
        reference_price=first_market.last_price,
    )

    previous_portfolio: PortfolioState | None = None
    cumulative_fees = ZERO
    cumulative_spread = ZERO
    cumulative_slippage = ZERO
    realized_funding = ZERO
    trade_ids: set[UUID] = set()
    buy_trade_ids: set[UUID] = set()
    sell_trade_ids: set[UUID] = set()
    equity_peak = initial_equity
    max_drawdown_value = ZERO
    max_drawdown_fraction: Decimal | None = None
    points: list[PaperAnalyticsPoint] = []

    for item in prepared:
        market = item.agent_input.market_state
        before = item.agent_input.portfolio_state
        if previous_portfolio is not None:
            _validate_portfolio_continuity(previous_portfolio, before)

        for fill in item.fills:
            cumulative_fees += fill.fee
            cumulative_spread += fill.spread_cost
            cumulative_slippage += fill.slippage_cost
            realized_funding += fill.funding_payment
            trade_ids.add(fill.execution_id)
            if fill.action is TradingAction.BUY:
                buy_trade_ids.add(fill.execution_id)
            elif fill.action is TradingAction.SELL:
                sell_trade_ids.add(fill.execution_id)

        equity, exposure_value, exposure_fraction = _value_portfolio(
            item.portfolio_after,
            symbol=market.symbol,
            reference_price=market.last_price,
        )
        open_funding = sum(
            position.cumulative_funding for position in item.portfolio_after.derivative_positions
        )
        cumulative_funding = realized_funding + open_funding
        net_pnl = equity - initial_equity
        total_execution_costs = cumulative_fees + cumulative_spread + cumulative_slippage
        gross_pnl = net_pnl + total_execution_costs - cumulative_funding
        cumulative_return = _fraction(net_pnl, initial_equity)

        if equity > equity_peak:
            equity_peak = equity
        drawdown_value = max(equity_peak - equity, ZERO)
        drawdown_fraction = _fraction(drawdown_value, equity_peak)
        if drawdown_value > max_drawdown_value:
            max_drawdown_value = drawdown_value
        if drawdown_fraction is not None and (
            max_drawdown_fraction is None or drawdown_fraction > max_drawdown_fraction
        ):
            max_drawdown_fraction = drawdown_fraction

        points.append(
            PaperAnalyticsPoint(
                cycle_id=item.cycle_id,
                at=item.at,
                status=item.status,
                action=item.decision.action.value if item.decision is not None else None,
                risk_status=(
                    item.risk_assessment.status.value
                    if item.risk_assessment is not None
                    else None
                ),
                symbol=market.symbol,
                reference_price=market.last_price,
                equity=equity,
                gross_pnl=gross_pnl,
                net_pnl=net_pnl,
                cumulative_fees=cumulative_fees,
                cumulative_spread_cost=cumulative_spread,
                cumulative_slippage_cost=cumulative_slippage,
                cumulative_funding_pnl=cumulative_funding,
                exposure_value=exposure_value,
                exposure_fraction=exposure_fraction,
                cumulative_return_fraction=cumulative_return,
                drawdown_value=drawdown_value,
                drawdown_fraction=drawdown_fraction,
                trade_count=len(trade_ids),
            )
        )
        previous_portfolio = item.portfolio_after

    daily = _daily_performance(points=tuple(points), initial_equity=initial_equity)
    last = points[-1]
    summary = PaperAnalyticsSummary(
        initial_equity=initial_equity,
        ending_equity=last.equity,
        gross_pnl=last.gross_pnl,
        net_pnl=last.net_pnl,
        fees=last.cumulative_fees,
        spread_cost=last.cumulative_spread_cost,
        slippage_cost=last.cumulative_slippage_cost,
        funding_pnl=last.cumulative_funding_pnl,
        max_drawdown_value=max_drawdown_value,
        max_drawdown_fraction=max_drawdown_fraction,
        current_drawdown_value=last.drawdown_value,
        current_drawdown_fraction=last.drawdown_fraction,
        current_exposure_value=last.exposure_value,
        current_exposure_fraction=last.exposure_fraction,
        trade_count=len(trade_ids),
        buy_trade_count=len(buy_trade_ids),
        sell_trade_count=len(sell_trade_ids),
        hold_count=hold_count,
        reject_count=reject_count,
        modify_count=modify_count,
        completed_cycle_count=completed_cycle_count,
        failed_cycle_count=failed_cycle_count,
        valued_cycle_count=len(points),
        first_at=points[0].at,
        last_at=last.at,
    )
    return PaperAnalyticsReport(
        calculation_version=calculation_version,
        timezone="UTC",
        source_digest=source_digest,
        summary=summary,
        points=tuple(points),
        daily=daily,
    )


def _parse_decision(payload: dict[str, object] | None) -> DecisionCandidate | None:
    if payload is None:
        return None
    try:
        return DecisionCandidate.model_validate_json(json.dumps(payload))
    except ValueError as exc:
        raise PaperAnalyticsDataError("invalid durable decision payload") from exc


def _parse_risk_assessment(payload: dict[str, object] | None) -> RiskAssessment | None:
    if payload is None:
        return None
    try:
        return RiskAssessment.model_validate_json(json.dumps(payload))
    except ValueError as exc:
        raise PaperAnalyticsDataError("invalid durable risk assessment payload") from exc


def _parse_fills(payloads: tuple[dict[str, object], ...]) -> tuple[Fill, ...]:
    fills: list[Fill] = []
    for payload in payloads:
        try:
            fills.append(Fill.model_validate_json(json.dumps(payload)))
        except ValueError as exc:
            raise PaperAnalyticsDataError("invalid durable fill payload") from exc
    return tuple(sorted(fills, key=lambda fill: (fill.filled_at, str(fill.fill_id))))


def _resolve_portfolio_after(
    *,
    agent_input: AgentInput,
    fills: tuple[Fill, ...],
    payload: dict[str, object] | None,
) -> PortfolioState:
    has_derivatives_fill = any(fill.market_type is not MarketType.SPOT for fill in fills)
    if has_derivatives_fill:
        if payload is None:
            raise PaperAnalyticsDataError(
                "derivatives fills require durable post-trade portfolio state"
            )
        try:
            return PortfolioState.model_validate_json(json.dumps(payload))
        except ValueError as exc:
            raise PaperAnalyticsDataError("invalid durable post-trade portfolio payload") from exc

    replayed = _replay_spot_fills(agent_input.portfolio_state, fills)
    if payload is None:
        return replayed
    try:
        persisted = PortfolioState.model_validate_json(json.dumps(payload))
    except ValueError as exc:
        raise PaperAnalyticsDataError("invalid durable post-trade portfolio payload") from exc
    _validate_portfolio_continuity(replayed, persisted)
    return persisted


def _replay_spot_fills(portfolio: PortfolioState, fills: tuple[Fill, ...]) -> PortfolioState:
    balances = {item.asset: item.available for item in portfolio.balances}
    positions = {item.asset: (item.quantity, item.available) for item in portfolio.positions}

    for fill in fills:
        if fill.market_type is not MarketType.SPOT:
            raise PaperAnalyticsDataError("derivatives fill cannot use SPOT replay")
        try:
            base_asset, quote_asset = parse_canonical_symbol(fill.symbol)
        except ValueError as exc:
            raise PaperAnalyticsDataError("invalid durable fill symbol") from exc
        if quote_asset not in balances:
            raise PaperAnalyticsDataError("fill quote asset is absent from durable portfolio")
        quantity, available = positions.get(base_asset, (ZERO, ZERO))
        if fill.action is TradingAction.BUY:
            balances[quote_asset] -= fill.notional + fill.fee
            quantity += fill.quantity
            available += fill.quantity
        else:
            if quantity < fill.quantity or available < fill.quantity:
                raise PaperAnalyticsDataError("durable SELL fill exceeds portfolio position")
            balances[quote_asset] += fill.notional - fill.fee
            quantity -= fill.quantity
            available -= fill.quantity
        if balances[quote_asset] < 0:
            raise PaperAnalyticsDataError("durable BUY fill would make quote balance negative")
        if quantity == ZERO and available == ZERO:
            positions.pop(base_asset, None)
        else:
            positions[base_asset] = (quantity, available)

    return PortfolioState(
        portfolio_state_id=portfolio.portfolio_state_id,
        as_of=portfolio.as_of,
        mode=portfolio.mode,
        balances=tuple(
            AssetBalance(asset=asset, available=amount)
            for asset, amount in sorted(balances.items())
        ),
        positions=tuple(
            AssetPosition(asset=asset, quantity=amount[0], available=amount[1])
            for asset, amount in sorted(positions.items())
        ),
        derivative_positions=portfolio.derivative_positions,
    )


def _validate_fill_market_link(*, agent_input: AgentInput, fills: tuple[Fill, ...]) -> None:
    market = agent_input.market_state
    for fill in fills:
        if fill.market_state_id != market.market_state_id:
            raise PaperAnalyticsDataError("fill references a different durable market state")
        if fill.pricing_as_of != market.as_of:
            raise PaperAnalyticsDataError(
                "fill pricing timestamp differs from durable market state"
            )
        if fill.symbol != market.symbol or fill.reference_price != market.last_price:
            raise PaperAnalyticsDataError("fill pricing differs from durable market state")
        if fill.market_type is not market.market_type:
            raise PaperAnalyticsDataError("fill market type differs from durable market state")


def _cycle_end_time(
    *,
    agent_input: AgentInput,
    fills: tuple[Fill, ...],
    portfolio_after: PortfolioState,
) -> datetime:
    candidates = [agent_input.created_at, portfolio_after.as_of]
    candidates.extend(fill.filled_at for fill in fills)
    at = max(candidates).astimezone(UTC)
    if agent_input.market_state.as_of > at:
        raise PaperAnalyticsDataError("valuation time precedes durable market state")
    return at


def _value_portfolio(
    portfolio: PortfolioState,
    *,
    symbol: str,
    reference_price: Decimal,
) -> tuple[Decimal, Decimal, Decimal | None]:
    try:
        base_asset, quote_asset = parse_canonical_symbol(symbol)
    except ValueError as exc:
        raise PaperAnalyticsDataError("invalid durable market symbol") from exc

    quote_available = ZERO
    for balance in portfolio.balances:
        if balance.asset == quote_asset:
            quote_available += balance.available
        elif balance.available != ZERO:
            raise PaperAnalyticsDataError(
                f"cannot value non-zero balance asset {balance.asset} from {symbol}"
            )

    spot_exposure = ZERO
    for position in portfolio.positions:
        if position.asset == base_asset:
            spot_exposure += position.quantity * reference_price
        elif position.quantity != ZERO:
            raise PaperAnalyticsDataError(
                f"cannot value non-zero position asset {position.asset} from {symbol}"
            )

    derivative_equity = sum(
        (
            position.margin_used + position.unrealized_pnl + position.cumulative_funding
            for position in portfolio.derivative_positions
        ),
        ZERO,
    )
    derivative_exposure = sum(
        (position.notional for position in portfolio.derivative_positions),
        ZERO,
    )
    exposure_value = spot_exposure + derivative_exposure
    equity = quote_available + spot_exposure + derivative_equity
    return equity, exposure_value, _fraction(exposure_value, equity)


def _validate_portfolio_continuity(left: PortfolioState, right: PortfolioState) -> None:
    if _spot_portfolio_amounts(left) != _spot_portfolio_amounts(right):
        raise PaperAnalyticsDataError("durable SPOT portfolio continuity is broken")
    if _derivative_structural_amounts(left) != _derivative_structural_amounts(right):
        raise PaperAnalyticsDataError("durable derivatives position continuity is broken")


def _spot_portfolio_amounts(
    portfolio: PortfolioState,
) -> tuple[
    tuple[tuple[str, Decimal], ...],
    tuple[tuple[str, Decimal, Decimal], ...],
]:
    balances = tuple(sorted((item.asset, item.available) for item in portfolio.balances))
    positions = tuple(
        sorted((item.asset, item.quantity, item.available) for item in portfolio.positions)
    )
    return balances, positions


def _derivative_structural_amounts(
    portfolio: PortfolioState,
) -> tuple[tuple[object, ...], ...]:
    return tuple(
        sorted(
            (
                position.symbol,
                position.side,
                position.quantity,
                position.average_entry_price,
                position.realized_pnl,
                position.leverage,
                position.margin_mode,
                position.margin_used,
            )
            for position in portfolio.derivative_positions
        )
    )


def _daily_performance(
    *,
    points: tuple[PaperAnalyticsPoint, ...],
    initial_equity: Decimal,
) -> tuple[PaperDailyPerformance, ...]:
    by_day: dict[date, list[PaperAnalyticsPoint]] = {}
    for point in points:
        by_day.setdefault(point.at.astimezone(UTC).date(), []).append(point)

    daily: list[PaperDailyPerformance] = []
    previous_close = initial_equity
    previous_fees = ZERO
    previous_spread = ZERO
    previous_slippage = ZERO
    previous_funding = ZERO
    previous_trades = 0
    for day in sorted(by_day):
        day_points = by_day[day]
        close = day_points[-1]
        daily_net_pnl = close.equity - previous_close
        fees = close.cumulative_fees - previous_fees
        spread = close.cumulative_spread_cost - previous_spread
        slippage = close.cumulative_slippage_cost - previous_slippage
        funding = close.cumulative_funding_pnl - previous_funding
        trade_count = close.trade_count - previous_trades
        daily.append(
            PaperDailyPerformance(
                day=day,
                closing_at=close.at,
                closing_equity=close.equity,
                gross_pnl=close.gross_pnl,
                net_pnl=close.net_pnl,
                daily_net_pnl=daily_net_pnl,
                daily_return_fraction=_fraction(daily_net_pnl, previous_close),
                cumulative_return_fraction=close.cumulative_return_fraction,
                fees=fees,
                spread_cost=spread,
                slippage_cost=slippage,
                funding_pnl=funding,
                trade_count=trade_count,
            )
        )
        previous_close = close.equity
        previous_fees = close.cumulative_fees
        previous_spread = close.cumulative_spread_cost
        previous_slippage = close.cumulative_slippage_cost
        previous_funding = close.cumulative_funding_pnl
        previous_trades = close.trade_count
    return tuple(daily)


def _fraction(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _source_digest(facts: tuple[PaperAnalyticsCycleFact, ...]) -> str:
    canonical = [
        {"cycle_id": str(item.cycle_id), "result_digest": item.result_digest}
        for item in facts
    ]
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
