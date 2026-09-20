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
    RiskDecision,
    RiskLimit,
    RiskReason,
    TradingAction,
)
from ai_spot_trader.domain.models import (
    DecisionCandidate,
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
    """Deterministic SPOT/PAPER safety boundary; it never creates strategy."""

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
            )

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
            if isinstance(result, RiskResult):
                return result
            authorized = result
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
            )

        status = RiskDecision.ALLOW if authorized == requested else RiskDecision.MODIFY
        assessment = self._assessment(
            decision=decision,
            assessed_at=assessed_at,
            status=status,
            requested_quantity=requested,
            authorized_quantity=authorized,
            reasons=tuple(reasons),
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
        )
        return RiskResult(assessment=assessment, execution_intent=intent)

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
            if market_state.context is None:
                return RiskReason.MARKET_FRESHNESS_UNAVAILABLE
            age = assessed_at - market_state.context.last_observed_at
            if age > self._policy.stale_after:
                return RiskReason.MARKET_DATA_STALE
        return None

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
            )
        quote_available = balances.get(quote_asset)
        if quote_available is None:
            return self._reject(
                decision=decision,
                assessed_at=assessed_at,
                requested_quantity=requested,
                reason=RiskReason.QUOTE_BALANCE_MISSING,
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
            )

        unit_cost = estimate_paper_execution(
            action=TradingAction.BUY,
            reference_price=market_state.last_price,
            quantity=Decimal(1),
            cost_model=self._cost_model,
        ).buy_quote_debit
        affordable = quote_available / unit_cost
        if affordable <= 0:
            return self._reject(
                decision=decision,
                assessed_at=assessed_at,
                requested_quantity=requested,
                reason=RiskReason.NO_EXECUTABLE_QUANTITY,
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
            )
        if quote_asset not in balances:
            return self._reject(
                decision=decision,
                assessed_at=assessed_at,
                requested_quantity=requested,
                reason=RiskReason.QUOTE_BALANCE_MISSING,
            )

        available = positions.get(base_asset)
        if available is None:
            return self._reject(
                decision=decision,
                assessed_at=assessed_at,
                requested_quantity=requested,
                reason=RiskReason.POSITION_NOT_HELD,
            )
        if current <= available:
            return current
        if not self._policy.allow_quantity_reduction:
            return self._reject(
                decision=decision,
                assessed_at=assessed_at,
                requested_quantity=requested,
                reason=RiskReason.INSUFFICIENT_POSITION,
            )
        if available <= 0:
            return self._reject(
                decision=decision,
                assessed_at=assessed_at,
                requested_quantity=requested,
                reason=RiskReason.NO_EXECUTABLE_QUANTITY,
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
    ) -> RiskResult:
        assessment = self._assessment(
            decision=decision,
            assessed_at=assessed_at,
            status=RiskDecision.REJECT,
            requested_quantity=requested_quantity,
            authorized_quantity=None,
            reasons=(reason,),
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
    ) -> RiskAssessment:
        return RiskAssessment(
            risk_assessment_id=self._risk_assessment_id_factory(),
            cycle_id=decision.cycle_id,
            decision_id=decision.decision_id,
            assessed_at=assessed_at,
            status=status,
            requested_quantity=requested_quantity,
            authorized_quantity=authorized_quantity,
            evaluated_limits=self._evaluated_limits(decision=decision, reasons=reasons),
            reasons=reasons,
        )

    def _evaluated_limits(
        self,
        *,
        decision: DecisionCandidate,
        reasons: tuple[RiskReason, ...],
    ) -> tuple[RiskLimit, ...]:
        if decision.action is TradingAction.HOLD:
            return ()

        rejection = reasons[0] if reasons else None
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

        if decision.action is TradingAction.BUY:
            limits.append(RiskLimit.BUY_CASH)
        else:
            limits.append(RiskLimit.SELL_POSITION)
        return tuple(limits)


def _normalize_assessment_time(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidRiskTimeError("Risk assessment clock must be timezone-aware")
    return value.astimezone(UTC)
