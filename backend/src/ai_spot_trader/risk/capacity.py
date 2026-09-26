from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket, PortfolioState
from ai_spot_trader.domain.symbols import parse_canonical_symbol
from ai_spot_trader.risk.policy import RiskPolicy

CAPACITY_PROTOCOL_VERSION = "capacity-management-v1"

CapacityMode = Literal["NORMAL", "MANAGEMENT"]
CapacityState = Literal["POSSIBLE", "UNAVAILABLE", "UNKNOWN", "NOT_APPLICABLE"]

REASON_OPENING_CAPACITY_AVAILABLE = "OPENING_CAPACITY_AVAILABLE"
REASON_VALUATION_INCOMPLETE = "VALUATION_INCOMPLETE"
REASON_CAPACITY_UNCERTAIN = "CAPACITY_UNCERTAIN"
REASON_NO_SETTLEMENT_CASH = "NO_SETTLEMENT_CASH"
REASON_DERIVATIVE_TOTAL_EXPOSURE_SATURATED = "DERIVATIVE_TOTAL_EXPOSURE_SATURATED"
REASON_DERIVATIVE_POSITION_CAPACITY_SATURATED = "DERIVATIVE_POSITION_CAPACITY_SATURATED"
REASON_NO_OPENING_CAPACITY = "NO_OPENING_CAPACITY"

ZERO = Decimal(0)


@dataclass(frozen=True, slots=True)
class CapacityAssessment:
    """Deterministic portfolio-level opening-capacity assessment for one cycle."""

    mode: CapacityMode
    reason: str
    spot_opening_capacity: CapacityState
    perpetual_opening_capacity: CapacityState
    management_markets: tuple[ExecutableMarket, ...] = ()
    protocol_version: str = CAPACITY_PROTOCOL_VERSION

    @property
    def new_opening_research_skipped(self) -> bool:
        return self.mode == "MANAGEMENT"

    def to_payload(self) -> dict[str, object]:
        return {
            "protocol_version": self.protocol_version,
            "mode": self.mode,
            "reason": self.reason,
            "spot_opening_capacity": self.spot_opening_capacity,
            "perpetual_opening_capacity": self.perpetual_opening_capacity,
            "management_markets": [
                market.model_dump(mode="json") for market in self.management_markets
            ],
            "new_opening_research_skipped": self.new_opening_research_skipped,
        }


class CapacityEvaluator:
    """Derive NORMAL/MANAGEMENT from the canonical portfolio and the same RiskPolicy.

    This evaluator intentionally reasons only about portfolio-level constraints that can be
    established before selecting/acquiring a market. Market-specific minimum quantity,
    instrument leverage, liquidation and exact margin requirements remain exclusively under
    RiskEngine after canonical MarketState acquisition.
    """

    def __init__(self, *, policy: RiskPolicy) -> None:
        self._policy = policy

    def evaluate(
        self,
        *,
        portfolio_state: PortfolioState,
        executable_markets: tuple[ExecutableMarket, ...],
    ) -> CapacityAssessment:
        management_markets = management_markets_for_portfolio(
            portfolio_state,
            executable_markets,
        )
        has_spot = any(market.market_type is MarketType.SPOT for market in executable_markets)
        perpetual_markets = tuple(
            market for market in executable_markets if market.market_type is MarketType.PERPETUAL
        )

        if not portfolio_state.valuation_complete:
            return CapacityAssessment(
                mode="MANAGEMENT",
                reason=REASON_VALUATION_INCOMPLETE,
                spot_opening_capacity="UNKNOWN" if has_spot else "NOT_APPLICABLE",
                perpetual_opening_capacity=(
                    "UNKNOWN" if perpetual_markets else "NOT_APPLICABLE"
                ),
                management_markets=management_markets,
            )

        cash = portfolio_state.cash_available
        if cash is None:
            return CapacityAssessment(
                mode="MANAGEMENT",
                reason=REASON_CAPACITY_UNCERTAIN,
                spot_opening_capacity="UNKNOWN" if has_spot else "NOT_APPLICABLE",
                perpetual_opening_capacity=(
                    "UNKNOWN" if perpetual_markets else "NOT_APPLICABLE"
                ),
                management_markets=management_markets,
            )

        spot_state: CapacityState = "NOT_APPLICABLE"
        if has_spot:
            spot_state = "POSSIBLE" if cash > ZERO else "UNAVAILABLE"

        perpetual_state, perpetual_reason = self._perpetual_capacity(
            portfolio_state=portfolio_state,
            perpetual_markets=perpetual_markets,
            cash=cash,
        )

        if "POSSIBLE" in (spot_state, perpetual_state):
            return CapacityAssessment(
                mode="NORMAL",
                reason=REASON_OPENING_CAPACITY_AVAILABLE,
                spot_opening_capacity=spot_state,
                perpetual_opening_capacity=perpetual_state,
                # Batch 19.10: open positions remain strategic management opportunities even
                # when new exposure is possible. This is descriptive only; it does not force SELL.
                management_markets=management_markets,
            )

        if "UNKNOWN" in (spot_state, perpetual_state):
            return CapacityAssessment(
                mode="MANAGEMENT",
                reason=REASON_CAPACITY_UNCERTAIN,
                spot_opening_capacity=spot_state,
                perpetual_opening_capacity=perpetual_state,
                management_markets=management_markets,
            )

        reason = perpetual_reason or REASON_NO_OPENING_CAPACITY
        if cash <= ZERO and (has_spot or perpetual_markets):
            reason = REASON_NO_SETTLEMENT_CASH
        return CapacityAssessment(
            mode="MANAGEMENT",
            reason=reason,
            spot_opening_capacity=spot_state,
            perpetual_opening_capacity=perpetual_state,
            management_markets=management_markets,
        )

    def _perpetual_capacity(
        self,
        *,
        portfolio_state: PortfolioState,
        perpetual_markets: tuple[ExecutableMarket, ...],
        cash: Decimal,
    ) -> tuple[CapacityState, str | None]:
        if not perpetual_markets:
            return "NOT_APPLICABLE", None
        if cash <= ZERO:
            return "UNAVAILABLE", REASON_NO_SETTLEMENT_CASH

        total_cap = self._policy.max_total_derivative_exposure
        if total_cap is None:
            return "UNKNOWN", REASON_CAPACITY_UNCERTAIN

        total_exposure = sum(
            (position.notional for position in portfolio_state.derivative_positions),
            ZERO,
        )
        if total_exposure >= total_cap:
            return "UNAVAILABLE", REASON_DERIVATIVE_TOTAL_EXPOSURE_SATURATED

        position_cap = self._policy.max_derivative_position_notional
        if position_cap is not None:
            current_by_symbol = {
                position.symbol: position for position in portfolio_state.derivative_positions
            }
            every_market_at_cap = all(
                (
                    current_by_symbol.get(market.symbol) is not None
                    and current_by_symbol[market.symbol].notional >= position_cap
                )
                for market in perpetual_markets
            )
            if every_market_at_cap:
                return "UNAVAILABLE", REASON_DERIVATIVE_POSITION_CAPACITY_SATURATED

        # Positive settlement cash plus remaining portfolio-level Risk headroom means opening
        # capacity is theoretically possible. Exact order/margin executability still belongs to
        # RiskEngine once the selected instrument's MarketState is known.
        return "POSSIBLE", None


def open_position_markets(
    portfolio_state: PortfolioState,
    *,
    settlement_asset: str | None = None,
) -> tuple[ExecutableMarket, ...]:
    """Return the canonical typed markets represented by currently open positions.

    The function is intentionally descriptive. It centralizes the held-position -> market mapping
    reused by capacity evaluation, dynamic watchlist expansion and Agent context construction.
    """

    settlement = settlement_asset or portfolio_state.settlement_asset
    selected: list[ExecutableMarket] = []
    if settlement is not None:
        normalized_settlement = settlement.strip().upper()
        if normalized_settlement:
            selected.extend(
                ExecutableMarket(
                    symbol=f"{position.asset}/{normalized_settlement}",
                    market_type=MarketType.SPOT,
                )
                for position in portfolio_state.positions
                if position.quantity > ZERO
            )

    selected.extend(
        ExecutableMarket(
            symbol=position.symbol,
            market_type=MarketType.PERPETUAL,
        )
        for position in portfolio_state.derivative_positions
        if position.quantity > ZERO
    )
    return tuple(sorted(set(selected), key=lambda item: (item.market_type.value, item.symbol)))


def management_markets_for_portfolio(
    portfolio_state: PortfolioState,
    executable_markets: tuple[ExecutableMarket, ...],
) -> tuple[ExecutableMarket, ...]:
    """Intersect open-position markets with the executable universe for this cycle."""

    held = set(open_position_markets(portfolio_state))
    selected: list[ExecutableMarket] = []
    for market in executable_markets:
        # Preserve the canonical symbol parser as a boundary check for executable markets.
        parse_canonical_symbol(market.symbol)
        if market in held:
            selected.append(market)
    return tuple(sorted(selected, key=lambda item: (item.market_type.value, item.symbol)))


# Backward-compatible private name retained for internal/tests that may still import it.
def _management_markets(
    portfolio_state: PortfolioState,
    executable_markets: tuple[ExecutableMarket, ...],
) -> tuple[ExecutableMarket, ...]:
    return management_markets_for_portfolio(portfolio_state, executable_markets)


__all__ = [
    "CAPACITY_PROTOCOL_VERSION",
    "CapacityAssessment",
    "CapacityEvaluator",
    "CapacityMode",
    "CapacityState",
    "management_markets_for_portfolio",
    "open_position_markets",
]
