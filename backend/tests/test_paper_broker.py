import asyncio
import inspect
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID

import pytest
from pydantic import ValidationError

import ai_spot_trader.broker.paper as paper_broker_module
import ai_spot_trader.portfolio.ledger as portfolio_ledger_module
from ai_spot_trader.broker import (
    FuturePricingContextError,
    InvalidCanonicalSymbolError,
    InvalidExecutionTimeError,
    InvalidPaperCostModelError,
    PaperBroker,
    PaperExecutionCostModel,
    PricingSymbolMismatchError,
)
from ai_spot_trader.domain.enums import TradingAction
from ai_spot_trader.domain.models import (
    AssetBalance,
    AssetPosition,
    ExecutionIntent,
    Fill,
    MarketState,
    PortfolioState,
)
from ai_spot_trader.domain.ports import Broker
from ai_spot_trader.portfolio import (
    InsufficientBalanceError,
    InsufficientPositionError,
    PaperPortfolioLedger,
    PositionNotHeldError,
)

NOW = datetime(2026, 9, 20, 15, 0, tzinfo=UTC)
CYCLE_ID = UUID("10000000-0000-0000-0000-000000000001")
DECISION_ID = UUID("10000000-0000-0000-0000-000000000002")
RISK_ID = UUID("10000000-0000-0000-0000-000000000003")
EXECUTION_ID = UUID("10000000-0000-0000-0000-000000000004")
MARKET_ID = UUID("10000000-0000-0000-0000-000000000005")
FILL_ID = UUID("10000000-0000-0000-0000-000000000006")
PORTFOLIO_ID = UUID("10000000-0000-0000-0000-000000000007")


@dataclass
class FixedClock:
    current: datetime

    def now(self) -> datetime:
        return self.current


def portfolio(*, cash: str = "1000", btc: str | None = None) -> PortfolioState:
    positions: tuple[AssetPosition, ...] = ()
    if btc is not None:
        positions = (
            AssetPosition(asset="BTC", quantity=Decimal(btc), available=Decimal(btc)),
        )
    return PortfolioState(
        portfolio_state_id=PORTFOLIO_ID,
        as_of=NOW - timedelta(minutes=1),
        balances=(AssetBalance(asset="EUR", available=Decimal(cash)),),
        positions=positions,
    )


def market(
    *,
    price: str = "100",
    symbol: str = "BTC/EUR",
    as_of: datetime | None = None,
) -> MarketState:
    return MarketState(
        market_state_id=MARKET_ID,
        as_of=as_of or NOW - timedelta(seconds=1),
        symbol=symbol,
        last_price=Decimal(price),
    )


def intent(
    action: TradingAction,
    *,
    quantity: str = "2",
    symbol: str = "BTC/EUR",
    created_at: datetime = NOW,
) -> ExecutionIntent:
    return ExecutionIntent(
        execution_id=EXECUTION_ID,
        cycle_id=CYCLE_ID,
        decision_id=DECISION_ID,
        risk_assessment_id=RISK_ID,
        created_at=created_at,
        action=action,
        symbol=symbol,
        quantity=Decimal(quantity),
    )


def broker(
    state: PortfolioState,
    *,
    fee_rate: str = "0",
    spread_bps: str = "0",
    slippage_bps: str = "0",
    clock: datetime = NOW,
) -> tuple[PaperBroker, PaperPortfolioLedger]:
    ledger = PaperPortfolioLedger(
        initial_state=state,
        clock=FixedClock(clock),
        portfolio_state_id_factory=lambda: PORTFOLIO_ID,
    )
    paper_broker = PaperBroker(
        ledger=ledger,
        cost_model=PaperExecutionCostModel(
            fee_rate=Decimal(fee_rate),
            spread_bps=Decimal(spread_bps),
            slippage_bps=Decimal(slippage_bps),
        ),
        clock=FixedClock(clock),
        fill_id_factory=lambda: FILL_ID,
    )
    return paper_broker, ledger


def execute_broker(
    paper_broker: PaperBroker,
    execution_intent: ExecutionIntent,
    market_state: MarketState,
) -> tuple[Fill, ...]:
    return asyncio.run(paper_broker.execute(execution_intent, market_state))


def test_paper_broker_structurally_implements_broker_port() -> None:
    paper_broker, _ = broker(portfolio())
    broker_port: Broker = paper_broker

    assert broker_port is paper_broker


def test_simple_buy_full_fill_updates_portfolio() -> None:
    paper_broker, ledger = broker(portfolio(cash="1000"))

    fills = execute_broker(paper_broker, intent(TradingAction.BUY), market())

    assert len(fills) == 1
    fill = fills[0]
    assert fill.fill_id == FILL_ID
    assert fill.execution_id == EXECUTION_ID
    assert fill.market_state_id == MARKET_ID
    assert fill.reference_price == Decimal("100")
    assert fill.price == Decimal("100")
    assert fill.notional == Decimal("200")
    assert fill.fee == 0
    snapshot = ledger.snapshot()
    assert snapshot.balances[0].available == Decimal("800")
    assert snapshot.positions == (
        AssetPosition(asset="BTC", quantity=Decimal("2"), available=Decimal("2")),
    )


def test_simple_sell_full_fill_updates_portfolio() -> None:
    paper_broker, ledger = broker(portfolio(cash="1000", btc="3"))

    fills = execute_broker(paper_broker, intent(TradingAction.SELL), market())

    assert fills[0].notional == Decimal("200")
    snapshot = ledger.snapshot()
    assert snapshot.balances[0].available == Decimal("1200")
    assert snapshot.positions[0].quantity == Decimal("1")


def test_buy_fee_is_debited_from_quote_asset_and_audited() -> None:
    paper_broker, ledger = broker(portfolio(cash="1000"), fee_rate="0.001")

    fill = (execute_broker(paper_broker, intent(TradingAction.BUY), market()))[0]

    assert fill.fee == Decimal("0.200")
    assert ledger.snapshot().balances[0].available == Decimal("799.800")


def test_sell_fee_is_deducted_from_quote_proceeds_and_audited() -> None:
    paper_broker, ledger = broker(portfolio(cash="1000", btc="3"), fee_rate="0.001")

    fill = (execute_broker(paper_broker, intent(TradingAction.SELL), market()))[0]

    assert fill.fee == Decimal("0.200")
    assert ledger.snapshot().balances[0].available == Decimal("1199.800")


def test_spread_is_adverse_per_side_and_explicitly_audited() -> None:
    buy_broker, _ = broker(portfolio(cash="1000"), spread_bps="10")
    sell_broker, _ = broker(portfolio(cash="1000", btc="3"), spread_bps="10")

    buy_fill = (execute_broker(buy_broker, intent(TradingAction.BUY), market()))[0]
    sell_fill = (execute_broker(sell_broker, intent(TradingAction.SELL), market()))[0]

    assert buy_fill.price == Decimal("100.100")
    assert sell_fill.price == Decimal("99.900")
    assert buy_fill.spread_cost == Decimal("0.200")
    assert sell_fill.spread_cost == Decimal("0.200")


def test_slippage_is_adverse_per_side_and_explicitly_audited() -> None:
    buy_broker, _ = broker(portfolio(cash="1000"), slippage_bps="20")
    sell_broker, _ = broker(portfolio(cash="1000", btc="3"), slippage_bps="20")

    buy_fill = (execute_broker(buy_broker, intent(TradingAction.BUY), market()))[0]
    sell_fill = (execute_broker(sell_broker, intent(TradingAction.SELL), market()))[0]

    assert buy_fill.price == Decimal("100.200")
    assert sell_fill.price == Decimal("99.800")
    assert buy_fill.slippage_cost == Decimal("0.400")
    assert sell_fill.slippage_cost == Decimal("0.400")


def test_combined_costs_use_decimal_without_hidden_rounding() -> None:
    paper_broker, ledger = broker(
        portfolio(cash="1000"),
        fee_rate="0.001",
        spread_bps="10",
        slippage_bps="20",
    )

    fill = (execute_broker(paper_broker, intent(TradingAction.BUY), market()))[0]

    assert fill.price == Decimal("100.300")
    assert fill.notional == Decimal("200.600")
    assert fill.fee == Decimal("0.200600")
    assert fill.spread_cost == Decimal("0.200")
    assert fill.slippage_cost == Decimal("0.400")
    assert ledger.snapshot().balances[0].available == Decimal("799.199400")


def test_insufficient_cash_rejects_without_mutation_or_fill() -> None:
    paper_broker, ledger = broker(portfolio(cash="200"), fee_rate="0.001")
    before = ledger.snapshot()

    with pytest.raises(InsufficientBalanceError):
        execute_broker(paper_broker, intent(TradingAction.BUY), market())

    after = ledger.snapshot()
    assert after.balances == before.balances
    assert after.positions == before.positions


def test_sell_above_available_position_rejects_atomically() -> None:
    paper_broker, ledger = broker(portfolio(cash="1000", btc="1"))
    before = ledger.snapshot()

    with pytest.raises(InsufficientPositionError):
        execute_broker(paper_broker, intent(TradingAction.SELL, quantity="1.01"), market())

    after = ledger.snapshot()
    assert after.balances == before.balances
    assert after.positions == before.positions


def test_sell_of_non_held_asset_is_rejected() -> None:
    paper_broker, _ = broker(portfolio(cash="1000"))

    with pytest.raises(PositionNotHeldError):
        execute_broker(paper_broker, intent(TradingAction.SELL), market())


def test_market_symbol_must_match_execution_intent() -> None:
    paper_broker, _ = broker(portfolio(cash="1000"))

    with pytest.raises(PricingSymbolMismatchError):
        execute_broker(paper_broker, intent(TradingAction.BUY), market(symbol="ETH/EUR"))


def test_future_pricing_context_is_rejected_for_no_look_ahead() -> None:
    paper_broker, _ = broker(portfolio(cash="1000"))

    with pytest.raises(FuturePricingContextError):
        execute_broker(
            paper_broker,
            intent(TradingAction.BUY),
            market(as_of=NOW + timedelta(microseconds=1)),
        )


def test_execution_clock_cannot_precede_intent() -> None:
    paper_broker, _ = broker(portfolio(cash="1000"), clock=NOW - timedelta(seconds=1))

    with pytest.raises(InvalidExecutionTimeError):
        execute_broker(paper_broker, intent(TradingAction.BUY), market())


def test_malformed_canonical_symbol_is_rejected() -> None:
    paper_broker, _ = broker(portfolio(cash="1000"))
    malformed = intent(TradingAction.BUY, symbol="BTCEUR")
    same_symbol_market = market(symbol="BTCEUR")

    with pytest.raises(InvalidCanonicalSymbolError):
        execute_broker(paper_broker, malformed, same_symbol_market)


def test_cost_model_rejects_float_negative_non_finite_and_impossible_sell_price() -> None:
    with pytest.raises(InvalidPaperCostModelError):
        PaperExecutionCostModel(
            fee_rate=cast(Decimal, 0.001),
            spread_bps=Decimal("0"),
            slippage_bps=Decimal("0"),
        )
    with pytest.raises(InvalidPaperCostModelError):
        PaperExecutionCostModel(
            fee_rate=Decimal("-0.01"),
            spread_bps=Decimal("0"),
            slippage_bps=Decimal("0"),
        )
    with pytest.raises(InvalidPaperCostModelError):
        PaperExecutionCostModel(
            fee_rate=Decimal("0"),
            spread_bps=Decimal("NaN"),
            slippage_bps=Decimal("0"),
        )
    with pytest.raises(InvalidPaperCostModelError):
        PaperExecutionCostModel(
            fee_rate=Decimal("0"),
            spread_bps=Decimal("5000"),
            slippage_bps=Decimal("5000"),
        )


def test_hold_and_live_remain_structurally_impossible() -> None:
    base = {
        "execution_id": EXECUTION_ID,
        "cycle_id": CYCLE_ID,
        "decision_id": DECISION_ID,
        "risk_assessment_id": RISK_ID,
        "created_at": NOW,
        "symbol": "BTC/EUR",
        "quantity": Decimal("1"),
    }
    with pytest.raises(ValidationError):
        ExecutionIntent.model_validate(base | {"action": TradingAction.HOLD})
    with pytest.raises(ValidationError):
        ExecutionIntent.model_validate(
            base | {"action": TradingAction.BUY, "mode": "LIVE"}
        )


def test_model_is_deterministic_for_same_inputs_and_injected_factories() -> None:
    broker_one, ledger_one = broker(
        portfolio(cash="1000"),
        fee_rate="0.001",
        spread_bps="10",
        slippage_bps="20",
    )
    broker_two, ledger_two = broker(
        portfolio(cash="1000"),
        fee_rate="0.001",
        spread_bps="10",
        slippage_bps="20",
    )

    fill_one = (execute_broker(broker_one, intent(TradingAction.BUY), market()))[0]
    fill_two = (execute_broker(broker_two, intent(TradingAction.BUY), market()))[0]

    assert fill_one == fill_two
    assert ledger_one.snapshot() == ledger_two.snapshot()


def test_portfolio_and_broker_packages_have_no_kraken_dependency() -> None:
    source = inspect.getsource(paper_broker_module) + inspect.getsource(portfolio_ledger_module)
    assert "integrations.kraken" not in source
    assert "Kraken" not in source
