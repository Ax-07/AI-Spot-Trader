import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from ai_spot_trader.api.schemas import PortfolioResponse
from ai_spot_trader.broker.paper import PaperBroker
from ai_spot_trader.broker.pricing import PaperExecutionCostModel
from ai_spot_trader.core.clock import Clock
from ai_spot_trader.domain.enums import TradingAction
from ai_spot_trader.domain.models import (
    AssetBalance,
    AssetPosition,
    ExecutionIntent,
    Fill,
    MarketState,
    PortfolioState,
)
from ai_spot_trader.portfolio.errors import InsufficientPositionError
from ai_spot_trader.portfolio.ledger import PaperPortfolioLedger

T0 = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


class FrozenClock(Clock):
    def __init__(self, now: datetime = T0) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def _state(*, cash: str = "100000") -> PortfolioState:
    return PortfolioState(
        portfolio_state_id=UUID(int=1),
        as_of=T0,
        balances=(AssetBalance(asset="USD", available=Decimal(cash)),),
    )


def _ledger(*, cash: str = "100000") -> PaperPortfolioLedger:
    return PaperPortfolioLedger(
        initial_state=_state(cash=cash),
        clock=FrozenClock(),
        portfolio_state_id_factory=lambda: UUID(int=2),
    )


def _position(ledger: PaperPortfolioLedger) -> AssetPosition:
    return ledger.snapshot(as_of=T0).positions[0]


def test_first_buy_creates_complete_accounting_and_fee_enters_cost_basis() -> None:
    ledger = _ledger()
    ledger.apply_buy(
        base_asset="BTC",
        quote_asset="USD",
        quantity=Decimal("2"),
        execution_price=Decimal("101"),
        quote_debit=Decimal("202.20"),
    )

    position = _position(ledger)
    assert position.quantity == Decimal("2")
    assert position.average_entry_price == Decimal("101.10")
    assert position.remaining_cost_basis == Decimal("202.20")
    assert position.realized_pnl == Decimal("0")
    assert position.accounting_complete is True


def test_successive_buys_use_weighted_fill_price_and_add_cash_debits() -> None:
    ledger = _ledger()
    ledger.apply_buy(
        base_asset="BTC",
        quote_asset="USD",
        quantity=Decimal("1"),
        execution_price=Decimal("100"),
        quote_debit=Decimal("100.10"),
    )
    ledger.apply_buy(
        base_asset="BTC",
        quote_asset="USD",
        quantity=Decimal("2"),
        execution_price=Decimal("110"),
        quote_debit=Decimal("220.22"),
    )
    ledger.apply_buy(
        base_asset="BTC",
        quote_asset="USD",
        quantity=Decimal("1"),
        execution_price=Decimal("90"),
        quote_debit=Decimal("90.09"),
    )

    position = _position(ledger)
    assert position.quantity == Decimal("4")
    assert position.average_entry_price == Decimal("102.6025")
    assert position.remaining_cost_basis == Decimal("410.41")


def test_partial_sell_releases_pro_rata_basis_and_accumulates_realized_pnl() -> None:
    ledger = _ledger()
    ledger.apply_buy(
        base_asset="ETH",
        quote_asset="USD",
        quantity=Decimal("10"),
        execution_price=Decimal("100"),
        quote_debit=Decimal("1001"),
    )

    first = ledger.apply_sell(
        base_asset="ETH",
        quote_asset="USD",
        quantity=Decimal("4"),
        quote_credit=Decimal("439.56"),
    )
    assert first.accounting_complete is True
    assert first.realized_pnl == Decimal("39.16")

    position = _position(ledger)
    assert position.quantity == Decimal("6")
    assert position.average_entry_price == Decimal("100.1")
    assert position.remaining_cost_basis == Decimal("600.6")
    assert position.realized_pnl == Decimal("39.16")

    second = ledger.apply_sell(
        base_asset="ETH",
        quote_asset="USD",
        quantity=Decimal("2"),
        quote_credit=Decimal("180"),
    )
    assert second.realized_pnl == Decimal("-20.2")
    position = _position(ledger)
    assert position.quantity == Decimal("4")
    assert position.remaining_cost_basis == Decimal("400.4")
    assert position.realized_pnl == Decimal("18.96")


def test_total_sell_closes_position_but_returns_last_realized_pnl() -> None:
    ledger = _ledger()
    ledger.apply_buy(
        base_asset="BTC",
        quote_asset="USD",
        quantity=Decimal("3"),
        execution_price=Decimal("100"),
        quote_debit=Decimal("300.3"),
    )
    accounting = ledger.apply_sell(
        base_asset="BTC",
        quote_asset="USD",
        quantity=Decimal("3"),
        quote_credit=Decimal("329.67"),
    )
    assert accounting.realized_pnl == Decimal("29.37")
    assert ledger.snapshot(as_of=T0).positions == ()


def test_sell_more_than_available_is_rejected_without_mutation() -> None:
    ledger = _ledger()
    ledger.apply_buy(
        base_asset="BTC",
        quote_asset="USD",
        quantity=Decimal("1"),
        execution_price=Decimal("100"),
        quote_debit=Decimal("100"),
    )
    before = ledger.snapshot(as_of=T0)

    with pytest.raises(InsufficientPositionError):
        ledger.apply_sell(
            base_asset="BTC",
            quote_asset="USD",
            quantity=Decimal("2"),
            quote_credit=Decimal("200"),
        )

    after = ledger.snapshot(as_of=T0)
    assert after.balances == before.balances
    assert after.positions == before.positions


def test_decimal_precision_is_not_coerced_to_float() -> None:
    ledger = _ledger()
    ledger.apply_buy(
        base_asset="XRP",
        quote_asset="USD",
        quantity=Decimal("0.123456789123456789"),
        execution_price=Decimal("0.987654321987654321"),
        quote_debit=Decimal("0.121932631356500531347203169112635269"),
    )
    position = _position(ledger)
    assert isinstance(position.quantity, Decimal)
    assert isinstance(position.average_entry_price, Decimal)
    assert isinstance(position.remaining_cost_basis, Decimal)
    assert position.quantity == Decimal("0.123456789123456789")


def test_legacy_snapshot_remains_recoverable_without_fabricated_cost_basis() -> None:
    payload = {
        "portfolio_state_id": str(UUID(int=10)),
        "as_of": T0.isoformat(),
        "mode": "PAPER",
        "balances": [{"asset": "USD", "available": "900"}],
        "positions": [{"asset": "BTC", "quantity": "1", "available": "1"}],
        "derivative_positions": [],
    }
    recovered = PortfolioState.model_validate_json(json.dumps(payload))
    position = recovered.positions[0]
    assert position.accounting_complete is False
    assert position.average_entry_price is None
    assert position.remaining_cost_basis is None

    ledger = PaperPortfolioLedger(initial_state=recovered, clock=FrozenClock())
    ledger.apply_buy(
        base_asset="BTC",
        quote_asset="USD",
        quantity=Decimal("1"),
        execution_price=Decimal("120"),
        quote_debit=Decimal("120.12"),
    )
    position = _position(ledger)
    assert position.quantity == Decimal("2")
    assert position.accounting_complete is False
    assert position.average_entry_price is None
    assert position.remaining_cost_basis is None


def test_complete_snapshot_round_trips_and_restores_exact_spot_accounting() -> None:
    ledger = _ledger()
    ledger.apply_buy(
        base_asset="BTC",
        quote_asset="USD",
        quantity=Decimal("2"),
        execution_price=Decimal("100"),
        quote_debit=Decimal("200.2"),
    )
    ledger.apply_buy(
        base_asset="BTC",
        quote_asset="USD",
        quantity=Decimal("1"),
        execution_price=Decimal("130"),
        quote_debit=Decimal("130.13"),
    )
    ledger.apply_sell(
        base_asset="BTC",
        quote_asset="USD",
        quantity=Decimal("1"),
        quote_credit=Decimal("119.88"),
    )
    durable = ledger.snapshot(as_of=T0 + timedelta(minutes=1))

    recovered = PortfolioState.model_validate_json(durable.model_dump_json())
    restored = PaperPortfolioLedger(
        initial_state=recovered,
        clock=FrozenClock(T0 + timedelta(minutes=2)),
        portfolio_state_id_factory=lambda: UUID(int=3),
    ).snapshot(as_of=T0 + timedelta(minutes=2))

    expected = durable.positions[0]
    actual = restored.positions[0]
    assert actual.quantity == expected.quantity
    assert actual.available == expected.available
    assert actual.average_entry_price == expected.average_entry_price
    assert actual.remaining_cost_basis == expected.remaining_cost_basis
    assert actual.realized_pnl == expected.realized_pnl
    assert actual.accounting_complete is True
    assert restored.balances == durable.balances


def test_portfolio_api_contract_exposes_spot_accounting_fields() -> None:
    ledger = _ledger()
    ledger.apply_buy(
        base_asset="BTC",
        quote_asset="USD",
        quantity=Decimal("1"),
        execution_price=Decimal("100"),
        quote_debit=Decimal("100.1"),
    )
    response = PortfolioResponse.model_validate(
        ledger.snapshot(as_of=T0).model_dump(mode="python")
    )
    position = response.positions[0]
    assert position.average_entry_price == Decimal("100.1")
    assert position.remaining_cost_basis == Decimal("100.1")
    assert position.realized_pnl == Decimal("0")
    assert position.accounting_complete is True


def test_broker_spot_fill_realized_pnl_uses_net_proceeds_without_double_costs() -> None:
    ledger = _ledger()
    broker = PaperBroker(
        ledger=ledger,
        cost_model=PaperExecutionCostModel(
            fee_rate=Decimal("0.001"),
            spread_bps=Decimal("10"),
            slippage_bps=Decimal("20"),
        ),
        clock=FrozenClock(T0 + timedelta(seconds=2)),
        fill_id_factory=lambda: UUID(int=50),
    )

    buy_market = MarketState(
        market_state_id=UUID(int=20),
        as_of=T0,
        symbol="BTC/USD",
        last_price=Decimal("100"),
    )
    buy_intent = ExecutionIntent(
        execution_id=UUID(int=21),
        cycle_id=UUID(int=22),
        decision_id=UUID(int=23),
        risk_assessment_id=UUID(int=24),
        created_at=T0 + timedelta(seconds=1),
        action=TradingAction.BUY,
        symbol="BTC/USD",
        quantity=Decimal("2"),
    )
    buy_fill = (asyncio.run(broker.execute(buy_intent, buy_market)))[0]
    assert buy_fill.price == Decimal("100.300")
    assert buy_fill.spread_cost + buy_fill.slippage_cost == Decimal("0.600")
    assert buy_fill.realized_pnl == Decimal("0")

    sell_market = MarketState(
        market_state_id=UUID(int=30),
        as_of=T0 + timedelta(seconds=2),
        symbol="BTC/USD",
        last_price=Decimal("120"),
    )
    sell_intent = ExecutionIntent(
        execution_id=UUID(int=31),
        cycle_id=UUID(int=32),
        decision_id=UUID(int=33),
        risk_assessment_id=UUID(int=34),
        created_at=T0 + timedelta(seconds=2),
        action=TradingAction.SELL,
        symbol="BTC/USD",
        quantity=Decimal("1"),
    )
    sell_fill = (asyncio.run(broker.execute(sell_intent, sell_market)))[0]
    assert Fill.model_validate(sell_fill.model_dump(mode="python")) == sell_fill

    expected_released_basis = buy_fill.notional + buy_fill.fee
    expected_released_basis /= Decimal("2")
    expected_net_proceeds = sell_fill.notional - sell_fill.fee
    assert sell_fill.realized_pnl == expected_net_proceeds - expected_released_basis

    position = _position(ledger)
    assert position.remaining_cost_basis == expected_released_basis
    assert position.realized_pnl == sell_fill.realized_pnl
