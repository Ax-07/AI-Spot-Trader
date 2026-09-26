from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from ai_spot_trader.broker.pricing import (
    PaperExecutionCostModel,
    estimate_paper_execution,
)
from ai_spot_trader.core.clock import Clock, SystemClock
from ai_spot_trader.domain.enums import (
    DerivativeContractKind,
    MarginMode,
    MarketType,
    PositionSide,
    RiskDecision,
    RiskLimit,
    RiskReason,
    TradingAction,
)
from ai_spot_trader.domain.models import (
    DecisionCandidate,
    DerivativePosition,
    ExecutionIntent,
    MarketState,
    PortfolioState,
    RiskAssessment,
)
from ai_spot_trader.domain.symbols import parse_canonical_symbol
from ai_spot_trader.risk.errors import InvalidRiskTimeError
from ai_spot_trader.risk.policy import RiskPolicy

RiskAssessmentIdFactory = Callable[[], UUID]
ExecutionIdFactory = Callable[[], UUID]
ZERO = Decimal(0)
ONE = Decimal(1)


@dataclass(frozen=True, slots=True)
class RiskResult:
    """Risk assessment plus the optional PAPER intent authorized by it."""

    assessment: RiskAssessment
    execution_intent: ExecutionIntent | None

    def __post_init__(self) -> None:
        authorized = self.assessment.authorized_quantity
        if authorized is None:
            if self.execution_intent is not None:
                raise ValueError("an assessment without authorized quantity cannot have an intent")
            return
        if self.execution_intent is None:
            raise ValueError("an authorized quantity requires an ExecutionIntent")
        if self.execution_intent.risk_assessment_id != self.assessment.risk_assessment_id:
            raise ValueError("ExecutionIntent must reference its RiskAssessment")
        if self.execution_intent.quantity != authorized:
            raise ValueError("ExecutionIntent quantity must equal authorized_quantity")


class RiskEngine:
    """Deterministic SPOT/derivatives PAPER boundary; it never creates strategy."""

    def __init__(
        self,
        *,
        policy: RiskPolicy,
        cost_model: PaperExecutionCostModel,
        clock: Clock | None = None,
        risk_assessment_id_factory: RiskAssessmentIdFactory = uuid4,
        execution_id_factory: ExecutionIdFactory = uuid4,
    ) -> None:
        self._policy = policy
        self._cost_model = cost_model
        self._clock = clock or SystemClock()
        self._risk_assessment_id_factory = risk_assessment_id_factory
        self._execution_id_factory = execution_id_factory

    def evaluate(
        self,
        *,
        decision: DecisionCandidate,
        market_state: MarketState,
        portfolio_state: PortfolioState,
        management_mode: bool = False,
    ) -> RiskResult:
        """Return ALLOW/MODIFY/REJECT and create an intent only when executable."""

        assessed_at = _normalize_assessment_time(self._clock.now())
        if assessed_at < decision.created_at:
            raise InvalidRiskTimeError("Risk assessment clock cannot precede the decision")

        if decision.action is TradingAction.HOLD:
            assessment = self._assessment(
                decision=decision,
                assessed_at=assessed_at,
                status=RiskDecision.ALLOW,
                requested_quantity=None,
                authorized_quantity=None,
                reasons=(RiskReason.HOLD_NO_EXECUTION,),
                evaluated_limits=(),
            )
            return RiskResult(assessment=assessment, execution_intent=None)

        requested = decision.proposed_quantity
        assert requested is not None

        common_rejection = self._evaluate_common_constraints(
            decision=decision,
            market_state=market_state,
            portfolio_state=portfolio_state,
            assessed_at=assessed_at,
        )
        if common_rejection is not None:
            return self._reject(
                decision=decision,
                assessed_at=assessed_at,
                requested_quantity=requested,
                reason=common_rejection,
                evaluated_limits=self._common_evaluated_limits(
                    decision=decision,
                    reason=common_rejection,
                ),
            )

        if management_mode and _would_increase_exposure(
            decision=decision,
            portfolio_state=portfolio_state,
        ):
            return self._reject(
                decision=decision,
                assessed_at=assessed_at,
                requested_quantity=requested,
                reason=RiskReason.MANAGEMENT_EXPOSURE_INCREASE,
                evaluated_limits=self._capacity_evaluated_limits(decision=decision),
            )

        if decision.market_type is MarketType.SPOT:
            return self._evaluate_spot(
                decision=decision,
                market_state=market_state,
                portfolio_state=portfolio_state,
                assessed_at=assessed_at,
                requested=requested,
            )
        return self._evaluate_derivative(
            decision=decision,
            market_state=market_state,
            portfolio_state=portfolio_state,
            assessed_at=assessed_at,
            requested=requested,
        )

    def _evaluate_common_constraints(
        self,
        *,
        decision: DecisionCandidate,
        market_state: MarketState,
        portfolio_state: PortfolioState,
        assessed_at: datetime,
    ) -> RiskReason | None:
        try:
            parse_canonical_symbol(decision.symbol)
        except ValueError:
            return RiskReason.INVALID_SYMBOL
        if market_state.symbol != decision.symbol:
            return RiskReason.MARKET_SYMBOL_MISMATCH
        if market_state.market_type is not decision.market_type:
            return RiskReason.MARKET_TYPE_MISMATCH
        if (
            self._policy.allowed_pairs is not None
            and decision.symbol not in self._policy.allowed_pairs
        ):
            return RiskReason.PAIR_NOT_ALLOWED
        if market_state.as_of > decision.created_at:
            return RiskReason.FUTURE_MARKET_STATE
        if portfolio_state.as_of > decision.created_at:
            return RiskReason.FUTURE_PORTFOLIO_STATE

        if self._policy.stale_after is not None:
            observed_at = (
                market_state.derivative.observed_at
                if market_state.derivative is not None
                else (
                    market_state.context.last_observed_at
                    if market_state.context is not None
                    else None
                )
            )
            if observed_at is None:
                return RiskReason.MARKET_FRESHNESS_UNAVAILABLE
            if assessed_at - observed_at > self._policy.stale_after:
                return RiskReason.MARKET_DATA_STALE
        return None

    def _evaluate_spot(
        self,
        *,
        decision: DecisionCandidate,
        market_state: MarketState,
        portfolio_state: PortfolioState,
        assessed_at: datetime,
        requested: Decimal,
    ) -> RiskResult:
        base_asset, quote_asset = parse_canonical_symbol(decision.symbol)
        authorized = requested
        reasons: list[RiskReason] = []

        if self._policy.max_order_notional is not None:
            max_quantity = self._policy.max_order_notional / market_state.last_price
            if authorized > max_quantity:
                if not self._policy.allow_quantity_reduction:
                    return self._reject(
                        decision=decision,
                        assessed_at=assessed_at,
                        requested_quantity=requested,
                        reason=RiskReason.MAX_ORDER_NOTIONAL_EXCEEDED,
                        evaluated_limits=self._spot_evaluated_limits(
                            decision=decision,
                            rejection=RiskReason.MAX_ORDER_NOTIONAL_EXCEEDED,
                        ),
                    )
                authorized = max_quantity
                reasons.append(RiskReason.MAX_ORDER_NOTIONAL_LIMIT)

        if decision.action is TradingAction.BUY:
            result = self._bound_buy_quantity(
                decision=decision,
                portfolio_state=portfolio_state,
                market_state=market_state,
                assessed_at=assessed_at,
                requested=requested,
                current=authorized,
                base_asset=base_asset,
                quote_asset=quote_asset,
                reasons=reasons,
            )
        else:
            result = self._bound_sell_quantity(
                decision=decision,
                portfolio_state=portfolio_state,
                assessed_at=assessed_at,
                requested=requested,
                current=authorized,
                base_asset=base_asset,
                quote_asset=quote_asset,
                reasons=reasons,
            )
        if isinstance(result, RiskResult):
            return result
        authorized = result

        if authorized <= 0:
            return self._reject(
                decision=decision,
                assessed_at=assessed_at,
                requested_quantity=requested,
                reason=RiskReason.NO_EXECUTABLE_QUANTITY,
                evaluated_limits=self._spot_evaluated_limits(
                    decision=decision,
                    rejection=RiskReason.NO_EXECUTABLE_QUANTITY,
                ),
            )

        status = RiskDecision.ALLOW if authorized == requested else RiskDecision.MODIFY
        assessment = self._assessment(
            decision=decision,
            assessed_at=assessed_at,
            status=status,
            requested_quantity=requested,
            authorized_quantity=authorized,
            reasons=tuple(reasons),
            evaluated_limits=self._spot_evaluated_limits(
                decision=decision,
                rejection=None,
            ),
        )
        intent = ExecutionIntent(
            execution_id=self._execution_id_factory(),
            cycle_id=decision.cycle_id,
            decision_id=decision.decision_id,
            risk_assessment_id=assessment.risk_assessment_id,
            created_at=assessed_at,
            action=decision.action,
            symbol=decision.symbol,
            quantity=authorized,
            market_type=MarketType.SPOT,
        )
        return RiskResult(assessment=assessment, execution_intent=intent)

    def _evaluate_derivative(
        self,
        *,
        decision: DecisionCandidate,
        market_state: MarketState,
        portfolio_state: PortfolioState,
        assessed_at: datetime,
        requested: Decimal,
    ) -> RiskResult:
        context = market_state.derivative
        evaluated = list(self._derivative_base_limits())
        if context is None:
            return self._reject(
                decision=decision,
                assessed_at=assessed_at,
                requested_quantity=requested,
                reason=RiskReason.DERIVATIVE_CONTEXT_MISSING,
                evaluated_limits=tuple(evaluated),
            )
        instrument = context.instrument
        if (
            decision.market_type is not MarketType.PERPETUAL
            or instrument.contract_kind is not DerivativeContractKind.LINEAR
        ):
            return self._reject(
                decision=decision,
                assessed_at=assessed_at,
                requested_quantity=requested,
                reason=RiskReason.DERIVATIVE_CONTRACT_UNSUPPORTED,
                evaluated_limits=tuple(evaluated),
            )
        if self._policy.derivative_margin_mode is not MarginMode.ISOLATED:
            return self._reject(
                decision=decision,
                assessed_at=assessed_at,
                requested_quantity=requested,
                reason=RiskReason.DERIVATIVE_CROSS_MARGIN_UNSUPPORTED,
                evaluated_limits=tuple(evaluated),
            )

        current = next(
            (
                position
                for position in portfolio_state.derivative_positions
                if position.symbol == decision.symbol
            ),
            None,
        )
        if current is not None and current.margin_mode is not MarginMode.ISOLATED:
            return self._reject(
                decision=decision,
                assessed_at=assessed_at,
                requested_quantity=requested,
                reason=RiskReason.DERIVATIVE_CROSS_MARGIN_UNSUPPORTED,
                evaluated_limits=tuple(evaluated),
            )

        reduce_only = _is_reducing(decision.action, current)
        authorized = requested
        reasons: list[RiskReason] = []

        if reduce_only:
            assert current is not None
            if authorized > current.quantity:
                if not self._policy.allow_quantity_reduction:
                    return self._reject(
                        decision=decision,
                        assessed_at=assessed_at,
                        requested_quantity=requested,
                        reason=RiskReason.DERIVATIVE_ACCIDENTAL_REVERSAL,
                        evaluated_limits=tuple(evaluated),
                    )
                authorized = current.quantity
                reasons.append(RiskReason.DERIVATIVE_REDUCE_ONLY_LIMIT)
        elif current is not None and _action_side(decision.action) is not current.side:
            return self._reject(
                decision=decision,
                assessed_at=assessed_at,
                requested_quantity=requested,
                reason=RiskReason.DERIVATIVE_ACCIDENTAL_REVERSAL,
                evaluated_limits=tuple(evaluated),
            )

        if authorized < instrument.min_order_quantity:
            return self._reject(
                decision=decision,
                assessed_at=assessed_at,
                requested_quantity=requested,
                reason=RiskReason.DERIVATIVE_MIN_ORDER_QUANTITY,
                evaluated_limits=tuple(evaluated),
            )

        order_notional = market_state.last_price * authorized * instrument.contract_size
        if (
            self._policy.max_order_notional is not None
            and order_notional > self._policy.max_order_notional
        ):
            if reduce_only:
                pass
            elif not self._policy.allow_quantity_reduction:
                return self._reject(
                    decision=decision,
                    assessed_at=assessed_at,
                    requested_quantity=requested,
                    reason=RiskReason.MAX_ORDER_NOTIONAL_EXCEEDED,
                    evaluated_limits=tuple(evaluated),
                )
            else:
                max_quantity = (
                    self._policy.max_order_notional
                    / market_state.last_price
                    / instrument.contract_size
                )
                authorized = min(authorized, max_quantity)
                reasons.append(RiskReason.MAX_ORDER_NOTIONAL_LIMIT)
                order_notional = market_state.last_price * authorized * instrument.contract_size

        if authorized < instrument.min_order_quantity:
            return self._reject(
                decision=decision,
                assessed_at=assessed_at,
                requested_quantity=requested,
                reason=RiskReason.DERIVATIVE_MIN_ORDER_QUANTITY,
                evaluated_limits=tuple(evaluated),
            )

        leverage = current.leverage if current is not None else self._policy.derivative_leverage
        effective_max_leverage = min(
            self._policy.max_derivative_leverage,
            instrument.max_leverage,
            ONE / instrument.initial_margin_rate,
        )
        if not reduce_only and leverage > effective_max_leverage:
            return self._reject(
                decision=decision,
                assessed_at=assessed_at,
                requested_quantity=requested,
                reason=RiskReason.DERIVATIVE_LEVERAGE_EXCEEDED,
                evaluated_limits=tuple(evaluated),
            )

        if current is not None and not reduce_only:
            isolated_equity = (
                current.margin_used
                + current.unrealized_pnl
                + current.cumulative_funding
            )
            required_buffer = (
                current.maintenance_margin * self._policy.derivative_liquidation_buffer_ratio
            )
            if isolated_equity <= required_buffer:
                return self._reject(
                    decision=decision,
                    assessed_at=assessed_at,
                    requested_quantity=requested,
                    reason=RiskReason.DERIVATIVE_LIQUIDATION_RISK,
                    evaluated_limits=tuple(evaluated),
                )

        projected_quantity = _projected_derivative_quantity(
            current=current,
            authorized=authorized,
            reduce_only=reduce_only,
        )
        if (
            not reduce_only
            and instrument.max_position_quantity is not None
            and projected_quantity > instrument.max_position_quantity
        ):
            return self._reject(
                decision=decision,
                assessed_at=assessed_at,
                requested_quantity=requested,
                reason=RiskReason.DERIVATIVE_POSITION_SIZE_EXCEEDED,
                evaluated_limits=tuple(evaluated),
            )

        projected_notional = market_state.last_price * projected_quantity * instrument.contract_size
        if (
            not reduce_only
            and self._policy.max_derivative_position_notional is not None
            and projected_notional > self._policy.max_derivative_position_notional
        ):
            return self._reject(
                decision=decision,
                assessed_at=assessed_at,
                requested_quantity=requested,
                reason=RiskReason.DERIVATIVE_POSITION_NOTIONAL_EXCEEDED,
                evaluated_limits=tuple(evaluated),
            )

        existing_notional = current.notional if current is not None else ZERO
        total_exposure = sum(
            (position.notional for position in portfolio_state.derivative_positions),
            ZERO,
        )
        projected_total = total_exposure - existing_notional + projected_notional
        if (
            not reduce_only
            and self._policy.max_total_derivative_exposure is not None
            and projected_total > self._policy.max_total_derivative_exposure
        ):
            return self._reject(
                decision=decision,
                assessed_at=assessed_at,
                requested_quantity=requested,
                reason=RiskReason.DERIVATIVE_TOTAL_EXPOSURE_EXCEEDED,
                evaluated_limits=tuple(evaluated),
            )

        if not reduce_only:
            _, quote_asset = parse_canonical_symbol(decision.symbol)
            quote_available = next(
                (
                    balance.available
                    for balance in portfolio_state.balances
                    if balance.asset == quote_asset
                ),
                None,
            )
            if quote_available is None:
                return self._reject(
                    decision=decision,
                    assessed_at=assessed_at,
                    requested_quantity=requested,
                    reason=RiskReason.QUOTE_BALANCE_MISSING,
                    evaluated_limits=tuple(evaluated),
                )
            initial_margin = max(
                order_notional / leverage,
                order_notional * instrument.initial_margin_rate,
            )
            estimate = estimate_paper_execution(
                action=decision.action,
                reference_price=market_state.last_price,
                quantity=authorized,
                cost_model=self._cost_model,
                contract_size=instrument.contract_size,
            )
            required_cash = initial_margin + estimate.fee
            if required_cash > quote_available:
                if not self._policy.allow_quantity_reduction:
                    return self._reject(
                        decision=decision,
                        assessed_at=assessed_at,
                        requested_quantity=requested,
                        reason=RiskReason.DERIVATIVE_MARGIN_INSUFFICIENT,
                        evaluated_limits=tuple(evaluated),
                    )
                unit_notional = market_state.last_price * instrument.contract_size
                unit_fee = estimate_paper_execution(
                    action=decision.action,
                    reference_price=market_state.last_price,
                    quantity=ONE,
                    cost_model=self._cost_model,
                    contract_size=instrument.contract_size,
                ).fee
                unit_margin = max(
                    unit_notional / leverage,
                    unit_notional * instrument.initial_margin_rate,
                )
                affordable = quote_available / (unit_margin + unit_fee)
                authorized = min(authorized, affordable)
                if authorized < instrument.min_order_quantity:
                    return self._reject(
                        decision=decision,
                        assessed_at=assessed_at,
                        requested_quantity=requested,
                        reason=RiskReason.DERIVATIVE_MARGIN_INSUFFICIENT,
                        evaluated_limits=tuple(evaluated),
                    )
                reasons.append(RiskReason.DERIVATIVE_MARGIN_LIMIT)

        if authorized <= 0:
            return self._reject(
                decision=decision,
                assessed_at=assessed_at,
                requested_quantity=requested,
                reason=RiskReason.NO_EXECUTABLE_QUANTITY,
                evaluated_limits=tuple(evaluated),
            )

        status = RiskDecision.ALLOW if authorized == requested else RiskDecision.MODIFY
        assessment = self._assessment(
            decision=decision,
            assessed_at=assessed_at,
            status=status,
            requested_quantity=requested,
            authorized_quantity=authorized,
            reasons=tuple(reasons),
            evaluated_limits=tuple(evaluated),
        )
        intent = ExecutionIntent(
            execution_id=self._execution_id_factory(),
            cycle_id=decision.cycle_id,
            decision_id=decision.decision_id,
            risk_assessment_id=assessment.risk_assessment_id,
            created_at=assessed_at,
            action=decision.action,
            symbol=decision.symbol,
            quantity=authorized,
            market_type=decision.market_type,
            reduce_only=reduce_only,
            leverage=leverage,
        )
        return RiskResult(assessment=assessment, execution_intent=intent)

    def _bound_buy_quantity(
        self,
        *,
        decision: DecisionCandidate,
        portfolio_state: PortfolioState,
        market_state: MarketState,
        assessed_at: datetime,
        requested: Decimal,
        current: Decimal,
        base_asset: str,
        quote_asset: str,
        reasons: list[RiskReason],
    ) -> Decimal | RiskResult:
        balances = {balance.asset: balance.available for balance in portfolio_state.balances}
        position_assets = {position.asset for position in portfolio_state.positions}
        if base_asset in balances or quote_asset in position_assets:
            return self._reject(
                decision=decision,
                assessed_at=assessed_at,
                requested_quantity=requested,
                reason=RiskReason.ASSET_ROLE_CONFLICT,
                evaluated_limits=self._spot_evaluated_limits(
                    decision=decision,
                    rejection=RiskReason.ASSET_ROLE_CONFLICT,
                ),
            )
        quote_available = balances.get(quote_asset)
        if quote_available is None:
            return self._reject(
                decision=decision,
                assessed_at=assessed_at,
                requested_quantity=requested,
                reason=RiskReason.QUOTE_BALANCE_MISSING,
                evaluated_limits=self._spot_evaluated_limits(
                    decision=decision,
                    rejection=RiskReason.QUOTE_BALANCE_MISSING,
                ),
            )

        estimate = estimate_paper_execution(
            action=TradingAction.BUY,
            reference_price=market_state.last_price,
            quantity=current,
            cost_model=self._cost_model,
        )
        if estimate.buy_quote_debit <= quote_available:
            return current
        if not self._policy.allow_quantity_reduction:
            return self._reject(
                decision=decision,
                assessed_at=assessed_at,
                requested_quantity=requested,
                reason=RiskReason.INSUFFICIENT_CASH,
                evaluated_limits=self._spot_evaluated_limits(
                    decision=decision,
                    rejection=RiskReason.INSUFFICIENT_CASH,
                ),
            )

        unit_cost = estimate_paper_execution(
            action=TradingAction.BUY,
            reference_price=market_state.last_price,
            quantity=ONE,
            cost_model=self._cost_model,
        ).buy_quote_debit
        affordable = quote_available / unit_cost
        if affordable <= 0:
            return self._reject(
                decision=decision,
                assessed_at=assessed_at,
                requested_quantity=requested,
                reason=RiskReason.NO_EXECUTABLE_QUANTITY,
                evaluated_limits=self._spot_evaluated_limits(
                    decision=decision,
                    rejection=RiskReason.NO_EXECUTABLE_QUANTITY,
                ),
            )
        reasons.append(RiskReason.BUY_CASH_LIMIT)
        return min(current, affordable)

    def _bound_sell_quantity(
        self,
        *,
        decision: DecisionCandidate,
        portfolio_state: PortfolioState,
        assessed_at: datetime,
        requested: Decimal,
        current: Decimal,
        base_asset: str,
        quote_asset: str,
        reasons: list[RiskReason],
    ) -> Decimal | RiskResult:
        balances = {balance.asset: balance.available for balance in portfolio_state.balances}
        positions = {position.asset: position.available for position in portfolio_state.positions}
        if base_asset in balances or quote_asset in positions:
            return self._reject(
                decision=decision,
                assessed_at=assessed_at,
                requested_quantity=requested,
                reason=RiskReason.ASSET_ROLE_CONFLICT,
                evaluated_limits=self._spot_evaluated_limits(
                    decision=decision,
                    rejection=RiskReason.ASSET_ROLE_CONFLICT,
                ),
            )
        if quote_asset not in balances:
            return self._reject(
                decision=decision,
                assessed_at=assessed_at,
                requested_quantity=requested,
                reason=RiskReason.QUOTE_BALANCE_MISSING,
                evaluated_limits=self._spot_evaluated_limits(
                    decision=decision,
                    rejection=RiskReason.QUOTE_BALANCE_MISSING,
                ),
            )

        available = positions.get(base_asset)
        if available is None:
            return self._reject(
                decision=decision,
                assessed_at=assessed_at,
                requested_quantity=requested,
                reason=RiskReason.POSITION_NOT_HELD,
                evaluated_limits=self._spot_evaluated_limits(
                    decision=decision,
                    rejection=RiskReason.POSITION_NOT_HELD,
                ),
            )
        if current <= available:
            return current
        if not self._policy.allow_quantity_reduction:
            return self._reject(
                decision=decision,
                assessed_at=assessed_at,
                requested_quantity=requested,
                reason=RiskReason.INSUFFICIENT_POSITION,
                evaluated_limits=self._spot_evaluated_limits(
                    decision=decision,
                    rejection=RiskReason.INSUFFICIENT_POSITION,
                ),
            )
        if available <= 0:
            return self._reject(
                decision=decision,
                assessed_at=assessed_at,
                requested_quantity=requested,
                reason=RiskReason.NO_EXECUTABLE_QUANTITY,
                evaluated_limits=self._spot_evaluated_limits(
                    decision=decision,
                    rejection=RiskReason.NO_EXECUTABLE_QUANTITY,
                ),
            )
        reasons.append(RiskReason.SELL_AVAILABLE_LIMIT)
        return min(current, available)

    def _reject(
        self,
        *,
        decision: DecisionCandidate,
        assessed_at: datetime,
        requested_quantity: Decimal,
        reason: RiskReason,
        evaluated_limits: tuple[RiskLimit, ...],
    ) -> RiskResult:
        assessment = self._assessment(
            decision=decision,
            assessed_at=assessed_at,
            status=RiskDecision.REJECT,
            requested_quantity=requested_quantity,
            authorized_quantity=None,
            reasons=(reason,),
            evaluated_limits=evaluated_limits,
        )
        return RiskResult(assessment=assessment, execution_intent=None)

    def _assessment(
        self,
        *,
        decision: DecisionCandidate,
        assessed_at: datetime,
        status: RiskDecision,
        requested_quantity: Decimal | None,
        authorized_quantity: Decimal | None,
        reasons: tuple[RiskReason, ...],
        evaluated_limits: tuple[RiskLimit, ...],
    ) -> RiskAssessment:
        return RiskAssessment(
            risk_assessment_id=self._risk_assessment_id_factory(),
            cycle_id=decision.cycle_id,
            decision_id=decision.decision_id,
            assessed_at=assessed_at,
            status=status,
            requested_quantity=requested_quantity,
            authorized_quantity=authorized_quantity,
            evaluated_limits=evaluated_limits,
            reasons=reasons,
        )

    def _common_evaluated_limits(
        self,
        *,
        decision: DecisionCandidate,
        reason: RiskReason,
    ) -> tuple[RiskLimit, ...]:
        limits: list[RiskLimit] = [RiskLimit.CANONICAL_SYMBOL]
        if reason is RiskReason.INVALID_SYMBOL:
            return tuple(limits)
        limits.append(RiskLimit.MARKET_SYMBOL)
        if reason is RiskReason.MARKET_SYMBOL_MISMATCH:
            return tuple(limits)
        if reason is RiskReason.MARKET_TYPE_MISMATCH:
            limits.append(RiskLimit.MARKET_TYPE)
            return tuple(limits)
        if self._policy.allowed_pairs is not None:
            limits.append(RiskLimit.PAIR_WHITELIST)
            if reason is RiskReason.PAIR_NOT_ALLOWED:
                return tuple(limits)
        limits.append(RiskLimit.MARKET_CHRONOLOGY)
        if reason is RiskReason.FUTURE_MARKET_STATE:
            return tuple(limits)
        limits.append(RiskLimit.PORTFOLIO_CHRONOLOGY)
        if reason is RiskReason.FUTURE_PORTFOLIO_STATE:
            return tuple(limits)
        if self._policy.stale_after is not None:
            limits.append(RiskLimit.MARKET_FRESHNESS)
        return tuple(limits)

    def _capacity_evaluated_limits(
        self,
        *,
        decision: DecisionCandidate,
    ) -> tuple[RiskLimit, ...]:
        limits = list(
            self._common_evaluated_limits(
                decision=decision,
                reason=RiskReason.MANAGEMENT_EXPOSURE_INCREASE,
            )
        )
        limits.append(RiskLimit.CAPACITY_MODE)
        return tuple(limits)

    def _spot_evaluated_limits(
        self,
        *,
        decision: DecisionCandidate,
        rejection: RiskReason | None,
    ) -> tuple[RiskLimit, ...]:
        limits: list[RiskLimit] = [RiskLimit.CANONICAL_SYMBOL]
        if rejection is RiskReason.INVALID_SYMBOL:
            return tuple(limits)

        limits.append(RiskLimit.MARKET_SYMBOL)
        if rejection is RiskReason.MARKET_SYMBOL_MISMATCH:
            return tuple(limits)

        if self._policy.allowed_pairs is not None:
            limits.append(RiskLimit.PAIR_WHITELIST)
            if rejection is RiskReason.PAIR_NOT_ALLOWED:
                return tuple(limits)

        limits.append(RiskLimit.MARKET_CHRONOLOGY)
        if rejection is RiskReason.FUTURE_MARKET_STATE:
            return tuple(limits)

        limits.append(RiskLimit.PORTFOLIO_CHRONOLOGY)
        if rejection is RiskReason.FUTURE_PORTFOLIO_STATE:
            return tuple(limits)

        if self._policy.stale_after is not None:
            limits.append(RiskLimit.MARKET_FRESHNESS)
            if rejection in {
                RiskReason.MARKET_FRESHNESS_UNAVAILABLE,
                RiskReason.MARKET_DATA_STALE,
            }:
                return tuple(limits)

        if self._policy.max_order_notional is not None:
            limits.append(RiskLimit.MAX_ORDER_NOTIONAL)
            if rejection is RiskReason.MAX_ORDER_NOTIONAL_EXCEEDED:
                return tuple(limits)

        limits.append(RiskLimit.ASSET_ROLES)
        if rejection is RiskReason.ASSET_ROLE_CONFLICT:
            return tuple(limits)

        limits.append(RiskLimit.QUOTE_BALANCE)
        if rejection is RiskReason.QUOTE_BALANCE_MISSING:
            return tuple(limits)

        limits.append(
            RiskLimit.BUY_CASH
            if decision.action is TradingAction.BUY
            else RiskLimit.SELL_POSITION
        )
        return tuple(limits)

    def _derivative_base_limits(self) -> tuple[RiskLimit, ...]:
        limits: list[RiskLimit] = [
            RiskLimit.CANONICAL_SYMBOL,
            RiskLimit.MARKET_SYMBOL,
            RiskLimit.MARKET_TYPE,
        ]
        if self._policy.allowed_pairs is not None:
            limits.append(RiskLimit.PAIR_WHITELIST)
        limits.extend(
            [
                RiskLimit.MARKET_CHRONOLOGY,
                RiskLimit.PORTFOLIO_CHRONOLOGY,
            ]
        )
        if self._policy.stale_after is not None:
            limits.append(RiskLimit.MARKET_FRESHNESS)
        if self._policy.max_order_notional is not None:
            limits.append(RiskLimit.MAX_ORDER_NOTIONAL)
        limits.extend(
            [
                RiskLimit.DERIVATIVE_CONTRACT,
                RiskLimit.DERIVATIVE_ORDER_SIZE,
                RiskLimit.DERIVATIVE_LEVERAGE,
                RiskLimit.DERIVATIVE_MARGIN,
                RiskLimit.DERIVATIVE_POSITION_NOTIONAL,
                RiskLimit.DERIVATIVE_TOTAL_EXPOSURE,
                RiskLimit.DERIVATIVE_LIQUIDATION_BUFFER,
                RiskLimit.DERIVATIVE_REVERSAL,
            ]
        )
        return tuple(limits)


def _action_side(action: TradingAction) -> PositionSide:
    if action is TradingAction.BUY:
        return PositionSide.LONG
    if action is TradingAction.SELL:
        return PositionSide.SHORT
    raise ValueError("HOLD has no derivative side")


def _is_reducing(action: TradingAction, position: DerivativePosition | None) -> bool:
    if position is None:
        return False
    return _action_side(action) is not position.side


def _would_increase_exposure(
    *,
    decision: DecisionCandidate,
    portfolio_state: PortfolioState,
) -> bool:
    if decision.market_type is MarketType.SPOT:
        return decision.action is TradingAction.BUY
    current = next(
        (
            position
            for position in portfolio_state.derivative_positions
            if position.symbol == decision.symbol
        ),
        None,
    )
    return not _is_reducing(decision.action, current)


def _projected_derivative_quantity(
    *,
    current: DerivativePosition | None,
    authorized: Decimal,
    reduce_only: bool,
) -> Decimal:
    if current is None:
        return authorized
    if reduce_only:
        return max(current.quantity - authorized, ZERO)
    return current.quantity + authorized


def _normalize_assessment_time(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidRiskTimeError("Risk assessment clock must be timezone-aware")
    return value.astimezone(UTC)
