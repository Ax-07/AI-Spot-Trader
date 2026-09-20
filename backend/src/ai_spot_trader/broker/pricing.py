from dataclasses import dataclass
from decimal import Decimal

from ai_spot_trader.broker.errors import InvalidPaperCostModelError
from ai_spot_trader.domain.enums import TradingAction

BASIS_POINTS = Decimal(10_000)


@dataclass(frozen=True, slots=True)
class PaperExecutionCostModel:
    """Injected deterministic PAPER costs; spread_bps is adverse impact per side."""

    fee_rate: Decimal
    spread_bps: Decimal
    slippage_bps: Decimal

    def __post_init__(self) -> None:
        values = {
            "fee_rate": self.fee_rate,
            "spread_bps": self.spread_bps,
            "slippage_bps": self.slippage_bps,
        }
        for name, value in values.items():
            if not isinstance(value, Decimal):
                raise InvalidPaperCostModelError(f"{name} must be a Decimal")
            if not value.is_finite() or value < 0:
                raise InvalidPaperCostModelError(
                    f"{name} must be a finite non-negative Decimal"
                )
        if self.fee_rate >= Decimal(1):
            raise InvalidPaperCostModelError("fee_rate must be lower than 1")
        adverse_rate = (self.spread_bps + self.slippage_bps) / BASIS_POINTS
        if adverse_rate >= Decimal(1):
            raise InvalidPaperCostModelError(
                "combined spread and slippage must keep SELL execution price positive"
            )


@dataclass(frozen=True, slots=True)
class PaperExecutionEstimate:
    """Pure deterministic PAPER pricing estimate shared by Risk and PaperBroker."""

    action: TradingAction
    quantity: Decimal
    reference_price: Decimal
    price: Decimal
    notional: Decimal
    fee: Decimal
    spread_cost: Decimal
    slippage_cost: Decimal

    @property
    def buy_quote_debit(self) -> Decimal:
        if self.action is not TradingAction.BUY:
            raise ValueError("buy_quote_debit is only defined for BUY")
        return self.notional + self.fee

    @property
    def sell_quote_credit(self) -> Decimal:
        if self.action is not TradingAction.SELL:
            raise ValueError("sell_quote_credit is only defined for SELL")
        return self.notional - self.fee


def estimate_paper_execution(
    *,
    action: TradingAction,
    reference_price: Decimal,
    quantity: Decimal,
    cost_model: PaperExecutionCostModel,
) -> PaperExecutionEstimate:
    """Estimate one immediate full PAPER fill without side effects."""

    _validate_positive_decimal(reference_price, "reference_price")
    _validate_positive_decimal(quantity, "quantity")
    if action is TradingAction.HOLD:
        raise ValueError("HOLD has no execution estimate")

    spread_per_unit = reference_price * cost_model.spread_bps / BASIS_POINTS
    slippage_per_unit = reference_price * cost_model.slippage_bps / BASIS_POINTS
    if action is TradingAction.BUY:
        price = reference_price + spread_per_unit + slippage_per_unit
    else:
        price = reference_price - spread_per_unit - slippage_per_unit

    notional = price * quantity
    return PaperExecutionEstimate(
        action=action,
        quantity=quantity,
        reference_price=reference_price,
        price=price,
        notional=notional,
        fee=notional * cost_model.fee_rate,
        spread_cost=spread_per_unit * quantity,
        slippage_cost=slippage_per_unit * quantity,
    )


def _validate_positive_decimal(value: Decimal, name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError(f"{name} must be a finite positive Decimal")
