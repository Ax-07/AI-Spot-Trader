from __future__ import annotations

from decimal import Decimal
from typing import Any

from ai_spot_trader.broker.pricing import PaperExecutionCostModel, estimate_paper_execution
from ai_spot_trader.domain.enums import MarketType, TradingAction
from ai_spot_trader.domain.models import (
    ExecutionCostContext,
    ExecutableMarket,
    PortfolioState,
)
from ai_spot_trader.domain.symbols import parse_canonical_symbol
from ai_spot_trader.risk.capacity import management_markets_for_portfolio

POSITION_MANAGEMENT_CONTEXT_VERSION = "position-management-v1"
ZERO = Decimal(0)


def build_position_management_context(
    *,
    portfolio_state: PortfolioState,
    executable_markets: tuple[ExecutableMarket, ...],
    execution_cost_context: ExecutionCostContext | None,
) -> dict[str, Any]:
    """Build factual open-position context for the single strategic Agent.

    The context is descriptive only. It exposes inventory/accounting facts and, when PAPER costs
    are available, estimates the economics of selling the currently available SPOT quantity. It
    never emits a score, threshold or `should_sell` decision.
    """

    management_markets = management_markets_for_portfolio(
        portfolio_state,
        executable_markets,
    )
    position_by_asset = {position.asset: position for position in portfolio_state.positions}
    derivative_by_symbol = {
        position.symbol: position for position in portfolio_state.derivative_positions
    }
    costs = _cost_model(execution_cost_context)

    spot_positions: list[dict[str, Any]] = []
    derivative_positions: list[dict[str, Any]] = []
    for market in management_markets:
        if market.market_type is MarketType.SPOT:
            base_asset, quote_asset = parse_canonical_symbol(market.symbol)
            position = position_by_asset.get(base_asset)
            if position is None or position.quantity <= ZERO:
                continue
            spot_positions.append(
                _spot_position_payload(
                    symbol=market.symbol,
                    quote_asset=quote_asset,
                    position=position,
                    costs=costs,
                )
            )
            continue

        position = derivative_by_symbol.get(market.symbol)
        if position is None:
            continue
        derivative_positions.append(
            {
                "symbol": position.symbol,
                "market_type": market.market_type.value,
                "side": position.side.value,
                "quantity": _decimal(position.quantity),
                "average_entry_price": _decimal(position.average_entry_price),
                "mark_price": _decimal(position.mark_price),
                "notional": _decimal(position.notional),
                "realized_pnl": _decimal(position.realized_pnl),
                "unrealized_pnl": _decimal(position.unrealized_pnl),
                "cumulative_funding": _decimal(position.cumulative_funding),
                "margin_used": _decimal(position.margin_used),
            }
        )

    return {
        "protocol_version": POSITION_MANAGEMENT_CONTEXT_VERSION,
        "portfolio_as_of": portfolio_state.as_of.isoformat().replace("+00:00", "Z"),
        "management_markets": [
            market.model_dump(mode="json") for market in management_markets
        ],
        "spot_positions": spot_positions,
        "derivative_positions": derivative_positions,
    }


def _spot_position_payload(
    *,
    symbol: str,
    quote_asset: str,
    position: Any,
    costs: PaperExecutionCostModel | None,
) -> dict[str, Any]:
    quantity = position.quantity
    available = position.available
    payload: dict[str, Any] = {
        "symbol": symbol,
        "market_type": MarketType.SPOT.value,
        "quote_asset": quote_asset,
        "quantity": _decimal(quantity),
        "available_quantity": _decimal(available),
        "can_reduce_now": available > ZERO,
        "can_fully_close_now": available > ZERO and available == quantity,
        "average_entry_price": _optional_decimal(position.average_entry_price),
        "remaining_cost_basis": _optional_decimal(position.remaining_cost_basis),
        "mark_price": _optional_decimal(position.mark_price),
        "market_value": _optional_decimal(position.market_value),
        "gross_unrealized_pnl": _optional_decimal(position.unrealized_pnl),
        "realized_pnl_to_date": _decimal(position.realized_pnl),
        "accounting_complete": position.accounting_complete,
        "valuation_complete": position.valuation_complete,
    }

    if costs is None or available <= ZERO or position.mark_price is None:
        payload["available_exit_estimate"] = None
        return payload

    estimate = estimate_paper_execution(
        action=TradingAction.SELL,
        reference_price=position.mark_price,
        quantity=available,
        cost_model=costs,
    )
    released_cost_basis: Decimal | None = None
    net_pnl: Decimal | None = None
    if (
        position.accounting_complete
        and position.remaining_cost_basis is not None
        and quantity > ZERO
    ):
        # The canonical ledger's remaining_cost_basis already contains BUY-side fees/costs.
        # Use its proportional release exactly once; do not add entry fees again.
        released_cost_basis = position.remaining_cost_basis * available / quantity
        net_pnl = estimate.sell_quote_credit - released_cost_basis

    payload["available_exit_estimate"] = {
        "quantity": _decimal(available),
        "reference_mark_price": _decimal(position.mark_price),
        "estimated_execution_price": _decimal(estimate.price),
        "estimated_exit_fee": _decimal(estimate.fee),
        "estimated_exit_spread_cost": _decimal(estimate.spread_cost),
        "estimated_exit_slippage_cost": _decimal(estimate.slippage_cost),
        "estimated_net_exit_proceeds": _decimal(estimate.sell_quote_credit),
        "estimated_released_cost_basis": _optional_decimal(released_cost_basis),
        "estimated_net_pnl_if_available_sold_now": _optional_decimal(net_pnl),
        "estimated_net_pnl_if_closed_now": (
            _optional_decimal(net_pnl) if available == quantity else None
        ),
    }
    return payload


def _cost_model(context: ExecutionCostContext | None) -> PaperExecutionCostModel | None:
    if context is None:
        return None
    return PaperExecutionCostModel(
        fee_rate=context.fee_rate,
        spread_bps=context.spread_bps,
        slippage_bps=context.slippage_bps,
    )


def _decimal(value: Decimal) -> str:
    return format(value, "f")


def _optional_decimal(value: Decimal | None) -> str | None:
    return None if value is None else _decimal(value)


__all__ = [
    "POSITION_MANAGEMENT_CONTEXT_VERSION",
    "build_position_management_context",
]
