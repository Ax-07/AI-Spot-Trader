from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from ai_spot_trader.domain.enums import MarginMode
from ai_spot_trader.domain.symbols import parse_canonical_symbol


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    """Explicit deterministic limits shared by SPOT and derivative PAPER execution."""

    max_order_notional: Decimal | None = None
    allowed_pairs: frozenset[str] | None = None
    stale_after: timedelta | None = None
    allow_quantity_reduction: bool = False
    derivative_leverage: Decimal = Decimal(1)
    max_derivative_leverage: Decimal = Decimal(1)
    max_derivative_position_notional: Decimal | None = None
    max_total_derivative_exposure: Decimal | None = None
    derivative_liquidation_buffer_ratio: Decimal = Decimal("1.10")
    derivative_margin_mode: MarginMode = MarginMode.ISOLATED

    def __post_init__(self) -> None:
        _positive_optional(self.max_order_notional, "max_order_notional")
        _positive_optional(
            self.max_derivative_position_notional,
            "max_derivative_position_notional",
        )
        _positive_optional(
            self.max_total_derivative_exposure,
            "max_total_derivative_exposure",
        )
        _positive(self.derivative_leverage, "derivative_leverage")
        _positive(self.max_derivative_leverage, "max_derivative_leverage")
        if self.derivative_leverage < Decimal(1):
            raise ValueError("derivative_leverage must be at least 1")
        if self.max_derivative_leverage < Decimal(1):
            raise ValueError("max_derivative_leverage must be at least 1")
        if self.derivative_leverage > self.max_derivative_leverage:
            raise ValueError("derivative_leverage cannot exceed max_derivative_leverage")
        _positive(
            self.derivative_liquidation_buffer_ratio,
            "derivative_liquidation_buffer_ratio",
        )
        if self.derivative_liquidation_buffer_ratio < Decimal(1):
            raise ValueError("derivative_liquidation_buffer_ratio must be at least 1")

        if self.stale_after is not None and self.stale_after <= timedelta(0):
            raise ValueError("stale_after must be positive when configured")

        if self.allowed_pairs is not None:
            normalized = frozenset(self.allowed_pairs)
            if not normalized:
                raise ValueError("allowed_pairs cannot be empty; use None for no whitelist")
            for symbol in normalized:
                if not isinstance(symbol, str):
                    raise ValueError("allowed_pairs must contain strings")
                parse_canonical_symbol(symbol)
            object.__setattr__(self, "allowed_pairs", normalized)


def _positive_optional(value: Decimal | None, name: str) -> None:
    if value is not None:
        _positive(value, name)


def _positive(value: Decimal, name: str) -> None:
    if not isinstance(value, Decimal):
        raise ValueError(f"{name} must be a Decimal")
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{name} must be a finite positive Decimal")
