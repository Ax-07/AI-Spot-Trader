from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from ai_spot_trader.core.clock import Clock, SystemClock
from ai_spot_trader.domain.enums import MarketType, PositionSide, TradingAction
from ai_spot_trader.domain.models import (
    AssetBalance,
    AssetPosition,
    DerivativePosition,
    MarketState,
    PortfolioState,
)
from ai_spot_trader.domain.symbols import parse_canonical_symbol
from ai_spot_trader.portfolio.errors import (
    AmbiguousAssetRoleError,
    InsufficientBalanceError,
    InsufficientPositionError,
    PositionNotHeldError,
    UnknownBalanceAssetError,
)

PortfolioStateIdFactory = Callable[[], UUID]
ZERO = Decimal(0)
ONE = Decimal(1)


@dataclass(frozen=True, slots=True)
class _PositionAmount:
    quantity: Decimal
    available: Decimal


@dataclass(frozen=True, slots=True)
class DerivativeFillAccounting:
    """Ledger accounting returned to PaperBroker for durable Fill fields."""

    realized_pnl: Decimal = ZERO
    margin_delta: Decimal = ZERO
    funding_payment: Decimal = ZERO


class PaperPortfolioLedger:
    """Deterministic in-memory source of truth for one SPOT+derivatives PAPER portfolio."""

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
        self._derivative_positions = {
            position.symbol: position for position in initial_state.derivative_positions
        }

    def snapshot(self, *, as_of: datetime | None = None) -> PortfolioState:
        """Return an immutable canonical snapshot with deterministic ordering."""

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
            derivative_positions=tuple(
                position
                for _, position in sorted(self._derivative_positions.items())
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
        """Atomically debit settlement cash and increase a SPOT base-asset position."""

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
            _PositionAmount(quantity=ZERO, available=ZERO),
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
        """Atomically decrease a sellable SPOT base position and credit settlement cash."""

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
        if remaining.quantity == ZERO and remaining.available == ZERO:
            del positions[base_asset]
        else:
            positions[base_asset] = remaining
        self._balances = balances
        self._positions = positions

    def mark_derivative_market(self, market_state: MarketState) -> None:
        """Mark one derivative position and accrue perpetual funding without trading."""

        if market_state.market_type is MarketType.SPOT or market_state.derivative is None:
            return
        current = self._derivative_positions.get(market_state.symbol)
        if current is None:
            return
        context = market_state.derivative
        instrument = context.instrument
        if instrument.contract_size != current.contract_size:
            raise ValueError("derivative contract_size changed for an open PAPER position")

        funding = current.cumulative_funding
        funding_updated_at = current.funding_updated_at
        if market_state.market_type is MarketType.PERPETUAL and context.funding_rate is not None:
            if funding_updated_at is not None and context.observed_at > funding_updated_at:
                interval_seconds = instrument.funding_interval_seconds
                assert interval_seconds is not None
                elapsed = Decimal(str((context.observed_at - funding_updated_at).total_seconds()))
                periods = elapsed / interval_seconds
                mark_notional = context.mark_price * current.quantity * current.contract_size
                direction = Decimal(-1) if current.side is PositionSide.LONG else ONE
                funding += mark_notional * context.funding_rate * periods * direction
            funding_updated_at = context.observed_at

        self._derivative_positions = {
            **self._derivative_positions,
            market_state.symbol: _revalue_position(
                current,
                mark_price=context.mark_price,
                cumulative_funding=funding,
                funding_updated_at=funding_updated_at,
            ),
        }

    def apply_derivative_fill(
        self,
        *,
        market_state: MarketState,
        action: TradingAction,
        quantity: Decimal,
        execution_price: Decimal,
        fee: Decimal,
        leverage: Decimal,
        reduce_only: bool,
    ) -> DerivativeFillAccounting:
        """Apply one linear isolated derivative fill atomically."""

        if market_state.market_type is not MarketType.PERPETUAL:
            raise ValueError("PAPER derivative execution currently supports PERPETUAL only")
        context = market_state.derivative
        if context is None:
            raise ValueError("derivative execution requires derivative market context")
        instrument = context.instrument
        _validate_positive(quantity, "quantity")
        _validate_positive(execution_price, "execution_price")
        _validate_non_negative(fee, "fee")
        _validate_positive(leverage, "leverage")
        _, quote_asset = parse_canonical_symbol(market_state.symbol)
        quote_available = self._balances.get(quote_asset)
        if quote_available is None:
            raise UnknownBalanceAssetError(f"missing balance for quote asset {quote_asset}")

        current = self._derivative_positions.get(market_state.symbol)
        order_side = PositionSide.LONG if action is TradingAction.BUY else PositionSide.SHORT

        if reduce_only:
            if current is None:
                raise PositionNotHeldError(
                    f"no derivative position held for {market_state.symbol}"
                )
            if order_side is current.side:
                raise ValueError("reduce_only derivative fill must oppose the current side")
            if quantity > current.quantity:
                raise InsufficientPositionError(
                    "reduce_only derivative fill cannot exceed the current position"
                )
            fraction = quantity / current.quantity
            released_margin = current.margin_used * fraction
            funding_payment = current.cumulative_funding * fraction
            realized = _realized_pnl(
                side=current.side,
                entry_price=current.average_entry_price,
                exit_price=execution_price,
                quantity=quantity,
                contract_size=current.contract_size,
            )
            balance_after = quote_available + released_margin + realized + funding_payment - fee
            if balance_after < ZERO:
                raise InsufficientBalanceError(
                    "derivative close would exceed available isolated equity"
                )

            remaining_quantity = current.quantity - quantity
            positions = dict(self._derivative_positions)
            if remaining_quantity == ZERO:
                del positions[market_state.symbol]
            else:
                remaining_margin = current.margin_used - released_margin
                remaining_funding = current.cumulative_funding - funding_payment
                remaining = current.model_copy(
                    update={
                        "quantity": remaining_quantity,
                        "margin_used": remaining_margin,
                        "realized_pnl": current.realized_pnl + realized,
                        "cumulative_funding": remaining_funding,
                    }
                )
                positions[market_state.symbol] = _revalue_position(
                    remaining,
                    mark_price=context.mark_price,
                    cumulative_funding=remaining_funding,
                    funding_updated_at=context.observed_at,
                )
            balances = dict(self._balances)
            balances[quote_asset] = balance_after
            self._balances = balances
            self._derivative_positions = positions
            return DerivativeFillAccounting(
                realized_pnl=realized,
                margin_delta=-released_margin,
                funding_payment=funding_payment,
            )

        if current is not None and current.side is not order_side:
            raise ValueError("opposite derivative fill must be reduce_only")

        execution_notional = execution_price * quantity * instrument.contract_size
        initial_margin = max(
            execution_notional / leverage,
            execution_notional * instrument.initial_margin_rate,
        )
        required_cash = initial_margin + fee
        if quote_available < required_cash:
            raise InsufficientBalanceError(
                f"insufficient {quote_asset} for derivative margin and fee"
            )

        if current is None:
            average_entry = execution_price
            total_quantity = quantity
            total_margin = initial_margin
            realized = ZERO
            funding = ZERO
        else:
            if current.leverage != leverage:
                raise ValueError("cannot silently change leverage on an open PAPER position")
            total_quantity = current.quantity + quantity
            average_entry = (
                current.average_entry_price * current.quantity
                + execution_price * quantity
            ) / total_quantity
            total_margin = current.margin_used + initial_margin
            realized = current.realized_pnl
            funding = current.cumulative_funding

        raw = DerivativePosition(
            symbol=market_state.symbol,
            side=order_side,
            quantity=total_quantity,
            average_entry_price=average_entry,
            mark_price=context.mark_price,
            contract_size=instrument.contract_size,
            notional=context.mark_price * total_quantity * instrument.contract_size,
            realized_pnl=realized,
            unrealized_pnl=ZERO,
            leverage=leverage,
            margin_used=total_margin,
            initial_margin_rate=instrument.initial_margin_rate,
            maintenance_margin_rate=instrument.maintenance_margin_rate,
            maintenance_margin=(
                context.mark_price
                * total_quantity
                * instrument.contract_size
                * instrument.maintenance_margin_rate
            ),
            cumulative_funding=funding,
            liquidation_price=None,
            funding_updated_at=context.observed_at,
        )
        position = _revalue_position(
            raw,
            mark_price=context.mark_price,
            cumulative_funding=funding,
            funding_updated_at=context.observed_at,
        )
        balances = dict(self._balances)
        balances[quote_asset] = quote_available - required_cash
        self._balances = balances
        self._derivative_positions = {
            **self._derivative_positions,
            market_state.symbol: position,
        }
        return DerivativeFillAccounting(margin_delta=initial_margin)


def _revalue_position(
    position: DerivativePosition,
    *,
    mark_price: Decimal,
    cumulative_funding: Decimal,
    funding_updated_at: datetime | None,
) -> DerivativePosition:
    exposure_units = position.quantity * position.contract_size
    notional = mark_price * exposure_units
    if position.side is PositionSide.LONG:
        unrealized = (mark_price - position.average_entry_price) * exposure_units
    else:
        unrealized = (position.average_entry_price - mark_price) * exposure_units
    maintenance = notional * position.maintenance_margin_rate
    liquidation_price = _liquidation_price(
        side=position.side,
        entry_price=position.average_entry_price,
        exposure_units=exposure_units,
        isolated_margin=position.margin_used + cumulative_funding,
        maintenance_margin_rate=position.maintenance_margin_rate,
    )
    return position.model_copy(
        update={
            "mark_price": mark_price,
            "notional": notional,
            "unrealized_pnl": unrealized,
            "maintenance_margin": maintenance,
            "cumulative_funding": cumulative_funding,
            "liquidation_price": liquidation_price,
            "funding_updated_at": funding_updated_at,
        }
    )


def _realized_pnl(
    *,
    side: PositionSide,
    entry_price: Decimal,
    exit_price: Decimal,
    quantity: Decimal,
    contract_size: Decimal,
) -> Decimal:
    exposure_units = quantity * contract_size
    if side is PositionSide.LONG:
        return (exit_price - entry_price) * exposure_units
    return (entry_price - exit_price) * exposure_units


def _liquidation_price(
    *,
    side: PositionSide,
    entry_price: Decimal,
    exposure_units: Decimal,
    isolated_margin: Decimal,
    maintenance_margin_rate: Decimal,
) -> Decimal | None:
    if exposure_units <= ZERO:
        return None
    margin_per_unit = isolated_margin / exposure_units
    if side is PositionSide.LONG:
        denominator = ONE - maintenance_margin_rate
        if denominator <= ZERO:
            return None
        value = (entry_price - margin_per_unit) / denominator
    else:
        denominator = ONE + maintenance_margin_rate
        value = (entry_price + margin_per_unit) / denominator
    if value <= ZERO:
        return None
    return value


def _validate_positive(value: Decimal, name: str) -> None:
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{name} must be a finite positive Decimal")


def _validate_non_negative(value: Decimal, name: str) -> None:
    if not value.is_finite() or value < 0:
        raise ValueError(f"{name} must be a finite non-negative Decimal")
