import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from ai_spot_trader.broker.errors import (
    FuturePricingContextError,
    InvalidCanonicalSymbolError,
    InvalidExecutionTimeError,
    PricingSymbolMismatchError,
)
from ai_spot_trader.broker.pricing import (
    PaperExecutionCostModel,
    estimate_paper_execution,
)
from ai_spot_trader.core.clock import Clock, SystemClock
from ai_spot_trader.domain.enums import ExecutionMode, TradingAction
from ai_spot_trader.domain.models import ExecutionIntent, Fill, MarketState
from ai_spot_trader.domain.symbols import parse_canonical_symbol
from ai_spot_trader.portfolio.ledger import PaperPortfolioLedger

FillIdFactory = Callable[[], UUID]


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

        try:
            base_asset, quote_asset = parse_canonical_symbol(intent.symbol)
        except ValueError as exc:
            raise InvalidCanonicalSymbolError(str(exc)) from exc

        estimate = estimate_paper_execution(
            action=intent.action,
            reference_price=market_state.last_price,
            quantity=intent.quantity,
            cost_model=self._cost_model,
        )
        fill = Fill(
            fill_id=self._fill_id_factory(),
            execution_id=intent.execution_id,
            market_state_id=market_state.market_state_id,
            filled_at=filled_at,
            pricing_as_of=market_state.as_of,
            action=intent.action,
            symbol=intent.symbol,
            quantity=intent.quantity,
            reference_price=estimate.reference_price,
            price=estimate.price,
            notional=estimate.notional,
            fee=estimate.fee,
            spread_cost=estimate.spread_cost,
            slippage_cost=estimate.slippage_cost,
        )

        if intent.action is TradingAction.BUY:
            self._ledger.apply_buy(
                base_asset=base_asset,
                quote_asset=quote_asset,
                quantity=intent.quantity,
                quote_debit=estimate.buy_quote_debit,
            )
        else:
            self._ledger.apply_sell(
                base_asset=base_asset,
                quote_asset=quote_asset,
                quantity=intent.quantity,
                quote_credit=estimate.sell_quote_credit,
            )
        return (fill,)


def _normalize_clock_time(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidExecutionTimeError("execution clock must be timezone-aware")
    return value.astimezone(UTC)
