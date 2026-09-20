from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from ai_spot_trader.domain.symbols import parse_canonical_symbol


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    """Explicitly injected deterministic limits; no product values are implied."""

    max_order_notional: Decimal | None = None
    allowed_pairs: frozenset[str] | None = None
    stale_after: timedelta | None = None
    allow_quantity_reduction: bool = False

    def __post_init__(self) -> None:
        if self.max_order_notional is not None:
            value = self.max_order_notional
            if not isinstance(value, Decimal):
                raise ValueError("max_order_notional must be a Decimal")
            if not value.is_finite() or value <= 0:
                raise ValueError("max_order_notional must be a finite positive Decimal")

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
