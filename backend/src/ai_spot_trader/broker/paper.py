import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from ai_spot_trader.broker.errors import (
    FuturePricingContextError,
    InvalidCanonicalSymbolError,
    InvalidExecutionTimeError,
    InvalidPaperCostModelError,
    PricingSymbolMismatchError,
)
from ai_spot_trader.core.clock import Clock, SystemClock
from ai_spot_trader.domain.enums import ExecutionMode, TradingAction
from ai_spot_trader.domain.models import ExecutionIntent, Fill, MarketState
from ai_spot_trader.portfolio.ledger import PaperPortfolioLedger

BASIS_POINTS = Decimal(10_000)
FillIdFactory = Callable[[], UUID]


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


class PaperBroker:
    """Immediate full-fill PAPER broker using explicit canonical MarketState pricing."""

    def __init__(
        self,
        *,
        ledger: PaperPortfolioLedger,
        cost_model: PaperExecutionCostModel,
        clock: Clock | None = None,
        fill_id_factory: FillIdFactory = uuid4,
    ) -> None:
        self._ledger = ledger
        self._cost_model = cost_model
        self._clock = clock or SystemClock()
        self._fill_id_factory = fill_id_factory
        self._lock = asyncio.Lock()

    async def execute(
        self,
        intent: ExecutionIntent,
        market_state: MarketState,
    ) -> tuple[Fill, ...]:
        """Execute one complete PAPER fill or raise without mutating the portfolio."""

        async with self._lock:
            return self._execute_locked(intent=intent, market_state=market_state)

    def _execute_locked(
        self,
        *,
        intent: ExecutionIntent,
        market_state: MarketState,
    ) -> tuple[Fill, ...]:
        if intent.mode is not ExecutionMode.PAPER:
            raise ValueError("PaperBroker only accepts PAPER execution intents")
        if intent.action is TradingAction.HOLD:
            raise ValueError("HOLD cannot be executed")
        if market_state.symbol != intent.symbol:
            raise PricingSymbolMismatchError(
                f"intent symbol {intent.symbol} does not match pricing symbol {market_state.symbol}"
            )
        if market_state.as_of > intent.created_at:
            raise FuturePricingContextError(
                "MarketState cannot be newer than the ExecutionIntent"
            )

        filled_at = _normalize_clock_time(self._clock.now())
        if filled_at < intent.created_at:
            raise InvalidExecutionTimeError(
                "execution clock cannot precede the ExecutionIntent creation time"
            )

        base_asset, quote_asset = _parse_symbol(intent.symbol)
        reference_price = market_state.last_price
        spread_rate = self._cost_model.spread_bps / BASIS_POINTS
        slippage_rate = self._cost_model.slippage_bps / BASIS_POINTS
        spread_per_unit = reference_price * spread_rate
        slippage_per_unit = reference_price * slippage_rate

        if intent.action is TradingAction.BUY:
            execution_price = reference_price + spread_per_unit + slippage_per_unit
        else:
            execution_price = reference_price - spread_per_unit - slippage_per_unit

        quantity = intent.quantity
        notional = execution_price * quantity
        fee = notional * self._cost_model.fee_rate
        fill = Fill(
            fill_id=self._fill_id_factory(),
            execution_id=intent.execution_id,
            market_state_id=market_state.market_state_id,
            filled_at=filled_at,
            pricing_as_of=market_state.as_of,
            action=intent.action,
            symbol=intent.symbol,
            quantity=quantity,
            reference_price=reference_price,
            price=execution_price,
            notional=notional,
            fee=fee,
            spread_cost=spread_per_unit * quantity,
            slippage_cost=slippage_per_unit * quantity,
        )

        if intent.action is TradingAction.BUY:
            self._ledger.apply_buy(
                base_asset=base_asset,
                quote_asset=quote_asset,
                quantity=quantity,
                quote_debit=notional + fee,
            )
        else:
            self._ledger.apply_sell(
                base_asset=base_asset,
                quote_asset=quote_asset,
                quantity=quantity,
                quote_credit=notional - fee,
            )
        return (fill,)


def _parse_symbol(symbol: str) -> tuple[str, str]:
    parts = symbol.split("/")
    if len(parts) != 2:
        raise InvalidCanonicalSymbolError("symbol must use canonical BASE/QUOTE form")
    base_asset, quote_asset = (part.strip() for part in parts)
    if not base_asset or not quote_asset or base_asset == quote_asset:
        raise InvalidCanonicalSymbolError("symbol must contain distinct BASE and QUOTE assets")
    return base_asset, quote_asset


def _normalize_clock_time(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidExecutionTimeError("execution clock must be timezone-aware")
    return value.astimezone(UTC)
