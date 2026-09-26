from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from ai_spot_trader.core.clock import Clock, SystemClock
from ai_spot_trader.domain.derivative_margin import resolve_derivative_margin
from ai_spot_trader.domain.enums import MarketType, PositionSide, TradingAction
from ai_spot_trader.domain.models import (
    AssetBalance,
    AssetPosition,
    DerivativePosition,
    MarketObservation,
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
    average_entry_price: Decimal | None = None
    remaining_cost_basis: Decimal | None = None
    realized_pnl: Decimal = ZERO
    accounting_complete: bool = False
    mark_price: Decimal | None = None
    mark_observed_at: datetime | None = None
    mark_source: str | None = None
    market_value: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    valuation_complete: bool = False


@dataclass(frozen=True, slots=True)
class SpotFillAccounting:
    """Ledger accounting returned to PaperBroker for durable SPOT Fill fields."""

    realized_pnl: Decimal = ZERO
    accounting_complete: bool = False


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
        settlement_asset: str | None = None,
        mark_stale_after: timedelta | None = None,
    ) -> None:
        if mark_stale_after is not None and mark_stale_after <= timedelta(0):
            raise ValueError("mark_stale_after must be positive")
        self._clock = clock or SystemClock()
        self._portfolio_state_id_factory = portfolio_state_id_factory
        self._configured_settlement_asset = settlement_asset
        self._mark_stale_after = mark_stale_after
        self.restore(initial_state)

    def restore(self, state: PortfolioState) -> None:
        """Atomically replace the process-local ledger from one validated durable snapshot."""

        if (
            self._configured_settlement_asset is not None
            and state.settlement_asset is not None
            and state.settlement_asset != self._configured_settlement_asset
        ):
            raise ValueError("restored settlement_asset conflicts with runtime configuration")
        settlement_asset = self._configured_settlement_asset or state.settlement_asset
        balances = {balance.asset: balance.available for balance in state.balances}
        if settlement_asset is None and len(balances) == 1:
            settlement_asset = next(iter(balances))

        positions = {
            position.asset: _PositionAmount(
                quantity=position.quantity,
                available=position.available,
                average_entry_price=position.average_entry_price,
                remaining_cost_basis=position.remaining_cost_basis,
                realized_pnl=position.realized_pnl,
                accounting_complete=position.accounting_complete,
                mark_price=position.mark_price,
                mark_observed_at=position.mark_observed_at,
                mark_source=position.mark_source,
                market_value=position.market_value,
                unrealized_pnl=position.unrealized_pnl,
                valuation_complete=position.valuation_complete,
            )
            for position in state.positions
        }
        derivative_positions = {
            position.symbol: position for position in state.derivative_positions
        }
        self._settlement_asset = settlement_asset
        self._spot_realized_pnl_total = state.spot_realized_pnl_total
        self._balances = balances
        self._positions = positions
        self._derivative_positions = derivative_positions

    def snapshot(self, *, as_of: datetime | None = None) -> PortfolioState:
        """Return an immutable canonical snapshot with deterministic ordering and fresh marks only."""

        timestamp = self._clock.now() if as_of is None else as_of
        positions = tuple(
            self._asset_position(asset=asset, amount=amount, as_of=timestamp)
            for asset, amount in sorted(self._positions.items())
        )
        balances = tuple(
            AssetBalance(asset=asset, available=available)
            for asset, available in sorted(self._balances.items())
        )
        derivatives = tuple(
            position for _, position in sorted(self._derivative_positions.items())
        )
        metrics = self._portfolio_metrics(
            as_of=timestamp,
            positions=positions,
            derivatives=derivatives,
        )
        return PortfolioState(
            portfolio_state_id=self._portfolio_state_id_factory(),
            as_of=timestamp,
            settlement_asset=self._settlement_asset,
            balances=balances,
            positions=positions,
            derivative_positions=derivatives,
            cash_available=metrics["cash_available"],
            spot_remaining_cost_basis_total=metrics["spot_remaining_cost_basis_total"],
            spot_market_value_total=metrics["spot_market_value_total"],
            spot_realized_pnl_total=self._spot_realized_pnl_total,
            spot_unrealized_pnl_total=metrics["spot_unrealized_pnl_total"],
            equity=metrics["equity"],
            exposure_value=metrics["exposure_value"],
            exposure_fraction=metrics["exposure_fraction"],
            valuation_complete=metrics["valuation_complete"],
        )

    def mark_spot_observation(self, observation: MarketObservation) -> None:
        """Apply one causal SPOT last-price observation to an already-held position."""

        now = self._clock.now()
        if observation.observed_at > now:
            raise ValueError("SPOT mark observation cannot be newer than the ledger clock")
        base_asset, quote_asset = parse_canonical_symbol(observation.symbol)
        if self._settlement_asset is not None and quote_asset != self._settlement_asset:
            raise ValueError("SPOT mark quote asset must match the portfolio settlement asset")
        current = self._positions.get(base_asset)
        if current is None:
            return
        if current.mark_observed_at is not None:
            if observation.observed_at < current.mark_observed_at:
                return
            if (
                observation.observed_at == current.mark_observed_at
                and current.mark_price is not None
                and observation.last_price != current.mark_price
            ):
                raise ValueError("SPOT mark conflicts with an existing observation timestamp")

        market_value = observation.last_price * current.quantity
        unrealized_pnl = None
        valuation_complete = False
        if current.accounting_complete:
            assert current.remaining_cost_basis is not None
            unrealized_pnl = market_value - current.remaining_cost_basis
            valuation_complete = True
        self._positions = {
            **self._positions,
            base_asset: _PositionAmount(
                quantity=current.quantity,
                available=current.available,
                average_entry_price=current.average_entry_price,
                remaining_cost_basis=current.remaining_cost_basis,
                realized_pnl=current.realized_pnl,
                accounting_complete=current.accounting_complete,
                mark_price=observation.last_price,
                mark_observed_at=observation.observed_at,
                mark_source="LAST_PRICE",
                market_value=market_value,
                unrealized_pnl=unrealized_pnl,
                valuation_complete=valuation_complete,
            ),
        }

    def mark_spot_market(self, market_state: MarketState) -> None:
        """Apply the canonical SPOT last price from one already validated MarketState."""

        if market_state.market_type is not MarketType.SPOT:
            return
        observed_at = (
            market_state.context.last_observed_at
            if market_state.context is not None
            else market_state.as_of
        )
        self.mark_spot_observation(
            MarketObservation(
                observed_at=observed_at,
                symbol=market_state.symbol,
                last_price=market_state.last_price,
            )
        )

    def clear_spot_mark(self, asset: str) -> None:
        """Make one SPOT valuation explicitly unavailable without altering accounting."""

        current = self._positions.get(asset)
        if current is None:
            return
        self._positions = {
            **self._positions,
            asset: self._without_mark(current),
        }

    def apply_buy(
        self,
        *,
        base_asset: str,
        quote_asset: str,
        quantity: Decimal,
        quote_debit: Decimal,
        execution_price: Decimal | None = None,
    ) -> None:
        """Atomically debit settlement cash and increase a SPOT base-asset position."""

        _validate_positive(quantity, "quantity")
        _validate_positive(quote_debit, "quote_debit")
        if execution_price is not None:
            _validate_positive(execution_price, "execution_price")
            if quote_debit < execution_price * quantity:
                raise ValueError(
                    "quote_debit cannot be lower than execution_price * quantity"
                )
        if self._settlement_asset is not None and quote_asset != self._settlement_asset:
            raise ValueError("SPOT trade quote asset must match portfolio settlement asset")
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
        current = positions.get(base_asset)
        if current is not None and current.accounting_complete and execution_price is None:
            raise ValueError("execution_price is required to preserve complete SPOT accounting")

        balances[quote_asset] = quote_available - quote_debit
        if current is None:
            positions[base_asset] = _PositionAmount(
                quantity=quantity,
                available=quantity,
                average_entry_price=(
                    quote_debit / quantity if execution_price is not None else None
                ),
                remaining_cost_basis=quote_debit if execution_price is not None else None,
                realized_pnl=ZERO,
                accounting_complete=execution_price is not None,
            )
        elif current.accounting_complete:
            assert current.average_entry_price is not None
            assert current.remaining_cost_basis is not None
            assert execution_price is not None
            total_quantity = current.quantity + quantity
            total_cost_basis = current.remaining_cost_basis + quote_debit
            positions[base_asset] = _PositionAmount(
                quantity=total_quantity,
                available=current.available + quantity,
                average_entry_price=total_cost_basis / total_quantity,
                remaining_cost_basis=total_cost_basis,
                realized_pnl=current.realized_pnl,
                accounting_complete=True,
            )
        else:
            positions[base_asset] = _PositionAmount(
                quantity=current.quantity + quantity,
                available=current.available + quantity,
                realized_pnl=current.realized_pnl,
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
    ) -> SpotFillAccounting:
        """Atomically decrease SPOT inventory, realize P&L and credit settlement cash."""

        _validate_positive(quantity, "quantity")
        _validate_non_negative(quote_credit, "quote_credit")
        if self._settlement_asset is not None and quote_asset != self._settlement_asset:
            raise ValueError("SPOT trade quote asset must match portfolio settlement asset")
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
        remaining_quantity = current.quantity - quantity
        remaining_available = current.available - quantity
        accounting = SpotFillAccounting()
        realized_total = self._spot_realized_pnl_total

        if current.accounting_complete:
            assert current.average_entry_price is not None
            assert current.remaining_cost_basis is not None
            released_cost_basis = current.remaining_cost_basis * quantity / current.quantity
            realized_pnl = quote_credit - released_cost_basis
            accounting = SpotFillAccounting(
                realized_pnl=realized_pnl,
                accounting_complete=True,
            )
            if realized_total is not None:
                realized_total += realized_pnl
            if remaining_quantity == ZERO and remaining_available == ZERO:
                del positions[base_asset]
            else:
                remaining_cost_basis = current.remaining_cost_basis - released_cost_basis
                positions[base_asset] = _PositionAmount(
                    quantity=remaining_quantity,
                    available=remaining_available,
                    average_entry_price=remaining_cost_basis / remaining_quantity,
                    remaining_cost_basis=remaining_cost_basis,
                    realized_pnl=current.realized_pnl + realized_pnl,
                    accounting_complete=True,
                )
        else:
            realized_total = None
            remaining = _PositionAmount(
                quantity=remaining_quantity,
                available=remaining_available,
                realized_pnl=current.realized_pnl,
            )
            if remaining.quantity == ZERO and remaining.available == ZERO:
                del positions[base_asset]
            else:
                positions[base_asset] = remaining

        self._balances = balances
        self._positions = positions
        self._spot_realized_pnl_total = realized_total
        return accounting

    def mark_derivative_market(self, market_state: MarketState) -> None:
        """Mark one derivative position and accrue perpetual funding without trading."""

        if market_state.market_type is MarketType.SPOT or market_state.derivative is None:
            return
        current = self._derivative_positions.get(market_state.symbol)
        if current is None:
            return
        context = market_state.derivative
        instrument = context.instrument
        # Preserve the established derivative event-time semantics: derivative marks may be
        # replayed with an explicitly dated MarketState even when a test ledger uses a fixed
        # wall clock. Causality is enforced by monotonic observation timestamps below.
        if current.mark_observed_at is not None:
            if context.observed_at < current.mark_observed_at:
                return
            if (
                context.observed_at == current.mark_observed_at
                and context.mark_price != current.mark_price
            ):
                raise ValueError("derivative mark conflicts with an existing observation timestamp")
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
                mark_observed_at=context.observed_at,
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
                    mark_observed_at=context.observed_at,
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
        if current is not None and current.leverage != leverage:
            raise ValueError("cannot silently change leverage on an open PAPER position")

        execution_notional = execution_price * quantity * instrument.contract_size
        current_quantity = current.quantity if current is not None else ZERO
        total_quantity = current_quantity + quantity
        projected_mark_notional = context.mark_price * total_quantity * instrument.contract_size
        margin = resolve_derivative_margin(
            instrument,
            projected_quantity=total_quantity,
            projected_notional=projected_mark_notional,
        )
        current_entry_notional = (
            current.average_entry_price * current.quantity * current.contract_size
            if current is not None
            else ZERO
        )
        projected_entry_notional = current_entry_notional + execution_notional
        target_margin = max(
            projected_entry_notional / leverage,
            projected_entry_notional * margin.initial_margin_rate,
        )
        existing_margin = current.margin_used if current is not None else ZERO
        additional_margin = max(target_margin - existing_margin, ZERO)
        required_cash = additional_margin + fee
        if quote_available < required_cash:
            raise InsufficientBalanceError(
                f"insufficient {quote_asset} for derivative margin and fee"
            )

        if current is None:
            average_entry = execution_price
            total_margin = additional_margin
            realized = ZERO
            funding = ZERO
        else:
            average_entry = (
                current.average_entry_price * current.quantity
                + execution_price * quantity
            ) / total_quantity
            total_margin = current.margin_used + additional_margin
            realized = current.realized_pnl
            funding = current.cumulative_funding

        raw = DerivativePosition(
            symbol=market_state.symbol,
            side=order_side,
            quantity=total_quantity,
            average_entry_price=average_entry,
            mark_price=context.mark_price,
            mark_observed_at=context.observed_at,
            contract_size=instrument.contract_size,
            notional=projected_mark_notional,
            realized_pnl=realized,
            unrealized_pnl=ZERO,
            leverage=leverage,
            margin_used=total_margin,
            initial_margin_rate=margin.initial_margin_rate,
            maintenance_margin_rate=margin.maintenance_margin_rate,
            maintenance_margin=projected_mark_notional * margin.maintenance_margin_rate,
            cumulative_funding=funding,
            liquidation_price=None,
            funding_updated_at=context.observed_at,
        )
        position = _revalue_position(
            raw,
            mark_price=context.mark_price,
            mark_observed_at=context.observed_at,
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
        return DerivativeFillAccounting(margin_delta=additional_margin)

    def _asset_position(
        self,
        *,
        asset: str,
        amount: _PositionAmount,
        as_of: datetime,
    ) -> AssetPosition:
        visible = amount
        if amount.mark_observed_at is not None:
            if amount.mark_observed_at > as_of:
                raise ValueError("PortfolioState.as_of cannot precede a retained SPOT mark")
            if (
                self._mark_stale_after is not None
                and as_of - amount.mark_observed_at > self._mark_stale_after
            ):
                visible = self._without_mark(amount)
        return AssetPosition(
            asset=asset,
            quantity=visible.quantity,
            available=visible.available,
            average_entry_price=visible.average_entry_price,
            remaining_cost_basis=visible.remaining_cost_basis,
            realized_pnl=visible.realized_pnl,
            accounting_complete=visible.accounting_complete,
            mark_price=visible.mark_price,
            mark_observed_at=visible.mark_observed_at,
            mark_source=visible.mark_source,
            market_value=visible.market_value,
            unrealized_pnl=visible.unrealized_pnl,
            valuation_complete=visible.valuation_complete,
        )

    def _without_mark(self, amount: _PositionAmount) -> _PositionAmount:
        return _PositionAmount(
            quantity=amount.quantity,
            available=amount.available,
            average_entry_price=amount.average_entry_price,
            remaining_cost_basis=amount.remaining_cost_basis,
            realized_pnl=amount.realized_pnl,
            accounting_complete=amount.accounting_complete,
        )

    def _portfolio_metrics(
        self,
        *,
        as_of: datetime,
        positions: tuple[AssetPosition, ...],
        derivatives: tuple[DerivativePosition, ...],
    ) -> dict[str, Decimal | bool | None]:
        settlement = self._settlement_asset
        cash_available = self._balances.get(settlement) if settlement is not None else None

        if all(position.remaining_cost_basis is not None for position in positions):
            spot_cost = sum(
                (
                    position.remaining_cost_basis
                    for position in positions
                    if position.remaining_cost_basis is not None
                ),
                ZERO,
            )
        else:
            spot_cost = None

        if all(position.market_value is not None for position in positions):
            spot_value = sum(
                (position.market_value for position in positions if position.market_value is not None),
                ZERO,
            )
        else:
            spot_value = None

        if all(position.unrealized_pnl is not None for position in positions):
            spot_unrealized = sum(
                (
                    position.unrealized_pnl
                    for position in positions
                    if position.unrealized_pnl is not None
                ),
                ZERO,
            )
        else:
            spot_unrealized = None

        derivatives_fresh = True
        for position in derivatives:
            marked_at = position.mark_observed_at
            if marked_at is None or marked_at > as_of:
                derivatives_fresh = False
                break
            if (
                self._mark_stale_after is not None
                and as_of - marked_at > self._mark_stale_after
            ):
                derivatives_fresh = False
                break

        valuation_complete = (
            cash_available is not None
            and spot_value is not None
            and derivatives_fresh
        )
        equity: Decimal | None = None
        exposure_value: Decimal | None = None
        exposure_fraction: Decimal | None = None
        if valuation_complete:
            assert cash_available is not None
            assert spot_value is not None
            derivative_equity = sum(
                (
                    position.margin_used
                    + position.unrealized_pnl
                    + position.cumulative_funding
                    for position in derivatives
                ),
                ZERO,
            )
            derivative_exposure = sum((position.notional for position in derivatives), ZERO)
            equity = cash_available + spot_value + derivative_equity
            exposure_value = spot_value + derivative_exposure
            if equity > ZERO:
                exposure_fraction = exposure_value / equity

        return {
            "cash_available": cash_available,
            "spot_remaining_cost_basis_total": spot_cost,
            "spot_market_value_total": spot_value,
            "spot_unrealized_pnl_total": spot_unrealized,
            "equity": equity,
            "exposure_value": exposure_value,
            "exposure_fraction": exposure_fraction,
            "valuation_complete": valuation_complete,
        }


def _revalue_position(
    position: DerivativePosition,
    *,
    mark_price: Decimal,
    mark_observed_at: datetime,
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
            "mark_observed_at": mark_observed_at,
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
