from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from ai_spot_trader.core.clock import Clock, SystemClock
from ai_spot_trader.domain.models import AssetBalance, AssetPosition, PortfolioState
from ai_spot_trader.portfolio.errors import (
    AmbiguousAssetRoleError,
    InsufficientBalanceError,
    InsufficientPositionError,
    PositionNotHeldError,
    UnknownBalanceAssetError,
)

PortfolioStateIdFactory = Callable[[], UUID]


@dataclass(frozen=True, slots=True)
class _PositionAmount:
    quantity: Decimal
    available: Decimal


class PaperPortfolioLedger:
    """Deterministic in-memory source of truth for one PAPER portfolio."""

    def __init__(
        self,
        *,
        initial_state: PortfolioState,
        clock: Clock | None = None,
        portfolio_state_id_factory: PortfolioStateIdFactory = uuid4,
    ) -> None:
        self._clock = clock or SystemClock()
        self._portfolio_state_id_factory = portfolio_state_id_factory
        self._balances = {
            balance.asset: balance.available for balance in initial_state.balances
        }
        self._positions = {
            position.asset: _PositionAmount(
                quantity=position.quantity,
                available=position.available,
            )
            for position in initial_state.positions
        }

    def snapshot(self, *, as_of: datetime | None = None) -> PortfolioState:
        """Return an immutable canonical snapshot with deterministic asset ordering."""

        timestamp = self._clock.now() if as_of is None else as_of
        return PortfolioState(
            portfolio_state_id=self._portfolio_state_id_factory(),
            as_of=timestamp,
            balances=tuple(
                AssetBalance(asset=asset, available=available)
                for asset, available in sorted(self._balances.items())
            ),
            positions=tuple(
                AssetPosition(
                    asset=asset,
                    quantity=amount.quantity,
                    available=amount.available,
                )
                for asset, amount in sorted(self._positions.items())
            ),
        )

    def apply_buy(
        self,
        *,
        base_asset: str,
        quote_asset: str,
        quantity: Decimal,
        quote_debit: Decimal,
    ) -> None:
        """Atomically debit settlement cash and increase a base-asset position."""

        _validate_positive(quantity, "quantity")
        _validate_positive(quote_debit, "quote_debit")
        if base_asset in self._balances:
            raise AmbiguousAssetRoleError(
                f"cannot create position for balance asset {base_asset}"
            )
        quote_available = self._balances.get(quote_asset)
        if quote_available is None:
            raise UnknownBalanceAssetError(f"missing balance for quote asset {quote_asset}")
        if quote_available < quote_debit:
            raise InsufficientBalanceError(
                f"insufficient {quote_asset}: required {quote_debit}, available {quote_available}"
            )

        balances = dict(self._balances)
        positions = dict(self._positions)
        balances[quote_asset] = quote_available - quote_debit
        current = positions.get(
            base_asset,
            _PositionAmount(quantity=Decimal(0), available=Decimal(0)),
        )
        positions[base_asset] = _PositionAmount(
            quantity=current.quantity + quantity,
            available=current.available + quantity,
        )
        self._balances = balances
        self._positions = positions

    def apply_sell(
        self,
        *,
        base_asset: str,
        quote_asset: str,
        quantity: Decimal,
        quote_credit: Decimal,
    ) -> None:
        """Atomically decrease a sellable base position and credit settlement cash."""

        _validate_positive(quantity, "quantity")
        _validate_non_negative(quote_credit, "quote_credit")
        if quote_asset in self._positions:
            raise AmbiguousAssetRoleError(
                f"cannot credit balance for position asset {quote_asset}"
            )
        quote_available = self._balances.get(quote_asset)
        if quote_available is None:
            raise UnknownBalanceAssetError(f"missing balance for quote asset {quote_asset}")
        current = self._positions.get(base_asset)
        if current is None:
            raise PositionNotHeldError(f"no position held for base asset {base_asset}")
        if current.available < quantity:
            raise InsufficientPositionError(
                f"insufficient available {base_asset}: required {quantity}, "
                f"available {current.available}"
            )

        balances = dict(self._balances)
        positions = dict(self._positions)
        balances[quote_asset] = quote_available + quote_credit
        remaining = _PositionAmount(
            quantity=current.quantity - quantity,
            available=current.available - quantity,
        )
        if remaining.quantity == 0 and remaining.available == 0:
            del positions[base_asset]
        else:
            positions[base_asset] = remaining
        self._balances = balances
        self._positions = positions


def _validate_positive(value: Decimal, name: str) -> None:
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{name} must be a finite positive Decimal")


def _validate_non_negative(value: Decimal, name: str) -> None:
    if not value.is_finite() or value < 0:
        raise ValueError(f"{name} must be a finite non-negative Decimal")
