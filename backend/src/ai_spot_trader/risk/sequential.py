from datetime import datetime

from ai_spot_trader.domain.enums import RiskReason
from ai_spot_trader.domain.models import DecisionCandidate, MarketState, PortfolioState
from ai_spot_trader.domain.symbols import parse_canonical_symbol
from ai_spot_trader.risk.engine import RiskEngine


class SequentialCycleRiskEngine(RiskEngine):
    """RiskEngine variant for an immutable plan evaluated against evolving cycle state.

    The strategic decision timestamp remains the original Agent timestamp. Only the portfolio
    causality rule changes: a later portfolio snapshot is legitimate when it was produced by an
    earlier decision in the same serialized PAPER cycle. It still cannot postdate Risk assessment.
    """

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
        if self._policy.allowed_pairs is not None and decision.symbol not in self._policy.allowed_pairs:
            return RiskReason.PAIR_NOT_ALLOWED
        if market_state.as_of > decision.created_at:
            return RiskReason.FUTURE_MARKET_STATE
        if portfolio_state.as_of > assessed_at:
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


__all__ = ["SequentialCycleRiskEngine"]
