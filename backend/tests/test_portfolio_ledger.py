from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from ai_spot_trader.domain.models import AssetBalance, AssetPosition, PortfolioState
from ai_spot_trader.portfolio import (
    AmbiguousAssetRoleError,
    InsufficientBalanceError,
    InsufficientPositionError,
    PaperPortfolioLedger,
    PositionNotHeldError,
    UnknownBalanceAssetError,
)

NOW = datetime(2026, 9, 20, 15, 0, tzinfo=UTC)
STATE_ID = UUID("22222222-2222-2222-2222-222222222222")


@dataclass
class FixedClock:
    current: datetime

    def now(self) -> datetime:
        return self.current


def initial_state(
    *,
    eur: str = "1000",
    btc_quantity: str | None = "0.50",
    btc_available: str | None = "0.40",
) -> PortfolioState:
    positions: tuple[AssetPosition, ...] = ()
    if btc_quantity is not None and btc_available is not None:
        positions = (
            AssetPosition(
                asset="BTC",
                quantity=Decimal(btc_quantity),
                available=Decimal(btc_available),
            ),
        )
    return PortfolioState(
        portfolio_state_id=STATE_ID,
        as_of=NOW,
        balances=(AssetBalance(asset="EUR", available=Decimal(eur)),),
        positions=positions,
    )


def make_ledger(state: PortfolioState | None = None) -> PaperPortfolioLedger:
    return PaperPortfolioLedger(
        initial_state=state or initial_state(),
        clock=FixedClock(NOW),
        portfolio_state_id_factory=lambda: STATE_ID,
    )


def test_initial_state_is_explicit_and_snapshot_is_deterministic() -> None:
    ledger = make_ledger()

    snapshot = ledger.snapshot()

    assert snapshot.portfolio_state_id == STATE_ID
    assert snapshot.as_of == NOW
    assert snapshot.balances == (AssetBalance(asset="EUR", available=Decimal("1000")),)
    assert snapshot.positions == (
        AssetPosition(asset="BTC", quantity=Decimal("0.50"), available=Decimal("0.40")),
    )


def test_snapshot_normalizes_timezone_aware_timestamp() -> None:
    ledger = make_ledger()
    paris = timezone(timedelta(hours=2))

    snapshot = ledger.snapshot(as_of=datetime(2026, 9, 20, 17, 0, tzinfo=paris))

    assert snapshot.as_of == NOW
    assert snapshot.as_of.tzinfo is UTC


def test_buy_updates_quote_balance_and_base_position_exactly() -> None:
    ledger = make_ledger()

    ledger.apply_buy(
        base_asset="BTC",
        quote_asset="EUR",
        quantity=Decimal("0.10"),
        quote_debit=Decimal("501.25"),
    )
    snapshot = ledger.snapshot()

    assert snapshot.balances[0].available == Decimal("498.75")
    assert snapshot.positions[0].quantity == Decimal("0.60")
    assert snapshot.positions[0].available == Decimal("0.50")


def test_buy_can_create_new_position_without_hidden_initial_capital() -> None:
    ledger = make_ledger(initial_state(eur="1000", btc_quantity=None, btc_available=None))

    ledger.apply_buy(
        base_asset="ETH",
        quote_asset="EUR",
        quantity=Decimal("2"),
        quote_debit=Decimal("500"),
    )

    snapshot = ledger.snapshot()
    assert snapshot.balances[0].available == Decimal("500")
    assert snapshot.positions == (
        AssetPosition(asset="ETH", quantity=Decimal("2"), available=Decimal("2")),
    )


def test_sell_updates_position_and_quote_balance_exactly() -> None:
    ledger = make_ledger()

    ledger.apply_sell(
        base_asset="BTC",
        quote_asset="EUR",
        quantity=Decimal("0.25"),
        quote_credit=Decimal("12000.125"),
    )
    snapshot = ledger.snapshot()

    assert snapshot.balances[0].available == Decimal("13000.125")
    assert snapshot.positions[0].quantity == Decimal("0.25")
    assert snapshot.positions[0].available == Decimal("0.15")


def test_sell_to_zero_removes_empty_position() -> None:
    ledger = make_ledger(initial_state(eur="1000", btc_quantity="0.40", btc_available="0.40"))

    ledger.apply_sell(
        base_asset="BTC",
        quote_asset="EUR",
        quantity=Decimal("0.40"),
        quote_credit=Decimal("20000"),
    )

    assert ledger.snapshot().positions == ()


def test_buy_rejection_is_atomic_when_cash_is_insufficient() -> None:
    ledger = make_ledger()
    before = ledger.snapshot()

    with pytest.raises(InsufficientBalanceError):
        ledger.apply_buy(
            base_asset="BTC",
            quote_asset="EUR",
            quantity=Decimal("1"),
            quote_debit=Decimal("1000.01"),
        )

    after = ledger.snapshot()
    assert after.balances == before.balances
    assert after.positions == before.positions


def test_sell_rejection_is_atomic_when_available_position_is_insufficient() -> None:
    ledger = make_ledger()
    before = ledger.snapshot()

    with pytest.raises(InsufficientPositionError):
        ledger.apply_sell(
            base_asset="BTC",
            quote_asset="EUR",
            quantity=Decimal("0.41"),
            quote_credit=Decimal("1"),
        )

    after = ledger.snapshot()
    assert after.balances == before.balances
    assert after.positions == before.positions


def test_sell_of_non_held_asset_is_rejected() -> None:
    ledger = make_ledger()

    with pytest.raises(PositionNotHeldError):
        ledger.apply_sell(
            base_asset="ETH",
            quote_asset="EUR",
            quantity=Decimal("1"),
            quote_credit=Decimal("1"),
        )


def test_missing_quote_balance_is_rejected() -> None:
    state = PortfolioState(
        portfolio_state_id=STATE_ID,
        as_of=NOW,
        positions=(AssetPosition(asset="BTC", quantity=Decimal("1"), available=Decimal("1")),),
    )
    ledger = make_ledger(state)

    with pytest.raises(UnknownBalanceAssetError):
        ledger.apply_sell(
            base_asset="BTC",
            quote_asset="EUR",
            quantity=Decimal("1"),
            quote_credit=Decimal("100"),
        )


def test_asset_cannot_silently_switch_from_balance_to_position_role() -> None:
    state = PortfolioState(
        portfolio_state_id=STATE_ID,
        as_of=NOW,
        balances=(AssetBalance(asset="BTC", available=Decimal("1")),),
    )
    ledger = make_ledger(state)

    with pytest.raises(AmbiguousAssetRoleError):
        ledger.apply_buy(
            base_asset="BTC",
            quote_asset="BTC",
            quantity=Decimal("0.1"),
            quote_debit=Decimal("0.1"),
        )
