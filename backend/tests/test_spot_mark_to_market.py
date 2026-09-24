import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_spot_trader.api.routes.portfolio import router as portfolio_router
from ai_spot_trader.api.schemas import PortfolioResponse
from ai_spot_trader.broker.paper import PaperBroker
from ai_spot_trader.broker.pricing import PaperExecutionCostModel
from ai_spot_trader.core.clock import Clock
from ai_spot_trader.core.runtime import AppRuntime
from ai_spot_trader.domain.enums import (
    DerivativeContractKind,
    MarketType,
    PositionSide,
    TradingAction,
)
from ai_spot_trader.domain.models import (
    AssetBalance,
    AssetPosition,
    DerivativeInstrument,
    DerivativeMarketContext,
    DerivativePosition,
    ExecutionIntent,
    MarketObservation,
    MarketState,
    PortfolioState,
)
from ai_spot_trader.portfolio.ledger import PaperPortfolioLedger
from ai_spot_trader.portfolio.mark_to_market import (
    PaperDerivativeMarkToMarketMonitor,
    PaperSpotMarkToMarketMonitor,
)

T0 = datetime(2026, 9, 24, 20, 0, tzinfo=UTC)


class MutableClock(Clock):
    def __init__(self, now: datetime = T0) -> None:
        self.current = now

    def now(self) -> datetime:
        return self.current


class ObservationSource:
    def __init__(self, values: dict[str, MarketObservation]) -> None:
        self.values = values
        self.calls: list[str] = []

    async def observation(self, symbol: str) -> MarketObservation:
        self.calls.append(symbol)
        return self.values[symbol]


class SnapshotSource:
    def __init__(self, state: MarketState) -> None:
        self.state = state
        self.calls: list[str] = []

    async def snapshot(self, symbol: str) -> MarketState:
        self.calls.append(symbol)
        if symbol != self.state.symbol:
            raise ValueError("unexpected test symbol")
        return self.state


def initial_state(*, cash: str = "1000") -> PortfolioState:
    return PortfolioState(
        portfolio_state_id=UUID(int=1),
        as_of=T0,
        settlement_asset="USD",
        balances=(AssetBalance(asset="USD", available=Decimal(cash)),),
        cash_available=Decimal(cash),
        spot_remaining_cost_basis_total=Decimal(0),
        spot_market_value_total=Decimal(0),
        spot_realized_pnl_total=Decimal(0),
        spot_unrealized_pnl_total=Decimal(0),
        equity=Decimal(cash),
        exposure_value=Decimal(0),
        exposure_fraction=Decimal(0),
        valuation_complete=True,
    )


def ledger(*, cash: str = "1000", clock: MutableClock | None = None) -> PaperPortfolioLedger:
    return PaperPortfolioLedger(
        initial_state=initial_state(cash=cash),
        clock=clock or MutableClock(),
        settlement_asset="USD",
        mark_stale_after=timedelta(seconds=30),
        portfolio_state_id_factory=lambda: UUID(int=2),
    )


def mark(value: str, *, at: datetime = T0, symbol: str = "BTC/USD") -> MarketObservation:
    return MarketObservation(observed_at=at, symbol=symbol, last_price=Decimal(value))


def test_spot_mark_values_position_and_positive_unrealized_pnl() -> None:
    book = ledger()
    book.apply_buy(
        base_asset="BTC",
        quote_asset="USD",
        quantity=Decimal("2"),
        execution_price=Decimal("100"),
        quote_debit=Decimal("202"),
    )
    book.mark_spot_observation(mark("110"))

    state = book.snapshot(as_of=T0)
    position = state.positions[0]
    assert position.mark_price == Decimal("110")
    assert position.mark_source == "LAST_PRICE"
    assert position.market_value == Decimal("220")
    assert position.unrealized_pnl == Decimal("18")
    assert position.valuation_complete is True
    assert state.cash_available == Decimal("798")
    assert state.spot_remaining_cost_basis_total == Decimal("202")
    assert state.spot_market_value_total == Decimal("220")
    assert state.spot_unrealized_pnl_total == Decimal("18")
    assert state.equity == Decimal("1018")
    assert state.exposure_value == Decimal("220")
    assert state.exposure_fraction == Decimal("220") / Decimal("1018")
    assert state.valuation_complete is True


def test_negative_unrealized_pnl_uses_remaining_cost_basis() -> None:
    book = ledger()
    book.apply_buy(
        base_asset="BTC",
        quote_asset="USD",
        quantity=Decimal("2"),
        execution_price=Decimal("100"),
        quote_debit=Decimal("202"),
    )
    book.mark_spot_observation(mark("90"))
    position = book.snapshot(as_of=T0).positions[0]
    assert position.market_value == Decimal("180")
    assert position.unrealized_pnl == Decimal("-22")


def test_multiple_buys_keep_weighted_accounting_and_use_one_current_mark() -> None:
    book = ledger(cash="2000")
    book.apply_buy(
        base_asset="BTC", quote_asset="USD", quantity=Decimal("1"),
        execution_price=Decimal("100"), quote_debit=Decimal("101"),
    )
    book.apply_buy(
        base_asset="BTC", quote_asset="USD", quantity=Decimal("2"),
        execution_price=Decimal("120"), quote_debit=Decimal("242"),
    )
    book.mark_spot_observation(mark("130"))
    position = book.snapshot(as_of=T0).positions[0]
    assert position.quantity == Decimal("3")
    assert position.remaining_cost_basis == Decimal("343")
    assert position.average_entry_price == Decimal("343") / Decimal("3")
    assert position.market_value == Decimal("390")
    assert position.unrealized_pnl == Decimal("47")


def test_partial_sell_releases_basis_then_mark_to_market_uses_only_remaining_cost() -> None:
    book = ledger(cash="2000")
    book.apply_buy(
        base_asset="BTC", quote_asset="USD", quantity=Decimal("4"),
        execution_price=Decimal("100"), quote_debit=Decimal("404"),
    )
    accounting = book.apply_sell(
        base_asset="BTC", quote_asset="USD", quantity=Decimal("1"),
        quote_credit=Decimal("119"),
    )
    assert accounting.realized_pnl == Decimal("18")
    book.mark_spot_observation(mark("110"))
    state = book.snapshot(as_of=T0)
    position = state.positions[0]
    assert position.quantity == Decimal("3")
    assert position.remaining_cost_basis == Decimal("303")
    assert position.realized_pnl == Decimal("18")
    assert position.market_value == Decimal("330")
    assert position.unrealized_pnl == Decimal("27")
    assert state.spot_realized_pnl_total == Decimal("18")


def test_snapshot_restore_preserves_fresh_mark_and_stale_snapshot_hides_it() -> None:
    clock = MutableClock()
    book = ledger(clock=clock)
    book.apply_buy(
        base_asset="BTC", quote_asset="USD", quantity=Decimal("1"),
        execution_price=Decimal("100"), quote_debit=Decimal("101"),
    )
    book.mark_spot_observation(mark("105"))
    durable = book.snapshot(as_of=T0)
    recovered = PortfolioState.model_validate_json(durable.model_dump_json())

    restored_clock = MutableClock(T0 + timedelta(seconds=20))
    restored = PaperPortfolioLedger(
        initial_state=recovered,
        clock=restored_clock,
        settlement_asset="USD",
        mark_stale_after=timedelta(seconds=30),
        portfolio_state_id_factory=lambda: UUID(int=3),
    )
    fresh = restored.snapshot()
    assert fresh.positions[0].mark_price == Decimal("105")
    assert fresh.positions[0].unrealized_pnl == Decimal("4")

    restored_clock.current = T0 + timedelta(seconds=31)
    stale = restored.snapshot()
    assert stale.positions[0].mark_price is None
    assert stale.positions[0].market_value is None
    assert stale.positions[0].unrealized_pnl is None
    assert stale.spot_market_value_total is None
    assert stale.equity is None
    assert stale.valuation_complete is False


def test_legacy_incomplete_accounting_can_expose_market_value_but_never_unrealized_pnl() -> None:
    legacy = PortfolioState(
        portfolio_state_id=UUID(int=10),
        as_of=T0,
        balances=(AssetBalance(asset="USD", available=Decimal("900")),),
        positions=(AssetPosition(asset="BTC", quantity=Decimal("1"), available=Decimal("1")),),
    )
    book = PaperPortfolioLedger(
        initial_state=legacy,
        clock=MutableClock(),
        settlement_asset="USD",
        mark_stale_after=timedelta(seconds=30),
    )
    book.mark_spot_observation(mark("110"))
    state = book.snapshot(as_of=T0)
    position = state.positions[0]
    assert position.accounting_complete is False
    assert position.mark_price == Decimal("110")
    assert position.market_value == Decimal("110")
    assert position.unrealized_pnl is None
    assert position.valuation_complete is False
    assert state.spot_remaining_cost_basis_total is None
    assert state.spot_unrealized_pnl_total is None
    assert state.spot_realized_pnl_total is None


def test_mark_unavailable_is_explicit_and_no_pnl_is_invented() -> None:
    book = ledger()
    book.apply_buy(
        base_asset="BTC", quote_asset="USD", quantity=Decimal("1"),
        execution_price=Decimal("100"), quote_debit=Decimal("101"),
    )
    state = book.snapshot(as_of=T0)
    position = state.positions[0]
    assert position.mark_price is None
    assert position.market_value is None
    assert position.unrealized_pnl is None
    assert position.valuation_complete is False
    assert state.spot_market_value_total is None
    assert state.equity is None
    assert state.exposure_value is None
    assert state.valuation_complete is False


def test_spot_mark_uses_reference_price_without_double_counting_fee_spread_or_slippage() -> None:
    book = ledger()
    broker = PaperBroker(
        ledger=book,
        cost_model=PaperExecutionCostModel(
            fee_rate=Decimal("0.001"),
            spread_bps=Decimal("10"),
            slippage_bps=Decimal("20"),
        ),
        clock=MutableClock(T0 + timedelta(seconds=1)),
        fill_id_factory=lambda: UUID(int=50),
    )
    market = MarketState(
        market_state_id=UUID(int=20),
        as_of=T0,
        symbol="BTC/USD",
        last_price=Decimal("100"),
    )
    intent = ExecutionIntent(
        execution_id=UUID(int=21), cycle_id=UUID(int=22), decision_id=UUID(int=23),
        risk_assessment_id=UUID(int=24), created_at=T0,
        action=TradingAction.BUY, symbol="BTC/USD", quantity=Decimal("2"),
    )
    fill = asyncio.run(broker.execute(intent, market))[0]

    # Execution owns accounting only; valuation is supplied independently by market data.
    unmarked = book.snapshot(as_of=T0)
    assert unmarked.positions[0].mark_price is None
    book.mark_spot_observation(mark("100"))
    position = book.snapshot(as_of=T0).positions[0]

    assert fill.price == Decimal("100.300")
    assert position.mark_price == Decimal("100")
    assert position.market_value == Decimal("200")
    expected_debit = fill.notional + fill.fee
    assert position.remaining_cost_basis == expected_debit
    assert position.unrealized_pnl == Decimal("200") - expected_debit
    assert position.unrealized_pnl == -(fill.spread_cost + fill.slippage_cost + fill.fee)


def test_portfolio_api_exposes_backend_mark_to_market_without_recalculation() -> None:
    book = ledger()
    book.apply_buy(
        base_asset="BTC", quote_asset="USD", quantity=Decimal("1.25"),
        execution_price=Decimal("80"), quote_debit=Decimal("101"),
    )
    book.mark_spot_observation(mark("100"))
    app = FastAPI()
    app.state.runtime = AppRuntime(portfolio=book)
    app.include_router(portfolio_router)

    with TestClient(app) as client:
        response = client.get("/api/v1/portfolio")

    assert response.status_code == 200
    payload = response.json()
    assert payload["positions"][0]["mark_price"] == "100"
    assert payload["positions"][0]["market_value"] == "125.00"
    assert payload["positions"][0]["unrealized_pnl"] == "24.00"
    assert payload["exposure_value"] == "125.00"
    assert payload["equity"] == "1024.00"


def test_portfolio_api_schema_preserves_decimal_strings_and_backend_exposure() -> None:
    book = ledger()
    book.apply_buy(
        base_asset="BTC", quote_asset="USD", quantity=Decimal("1.25"),
        execution_price=Decimal("80"), quote_debit=Decimal("101"),
    )
    book.mark_spot_observation(mark("100"))
    response = PortfolioResponse.model_validate(book.snapshot(as_of=T0).model_dump(mode="python"))
    payload = json.loads(response.model_dump_json())
    assert payload["positions"][0]["mark_price"] == "100"
    assert payload["positions"][0]["market_value"] == "125.00"
    assert payload["positions"][0]["unrealized_pnl"] == "24.00"
    assert payload["exposure_value"] == "125.00"
    assert payload["equity"] == "1024.00"
    assert isinstance(payload["exposure_fraction"], str)


def test_future_mark_is_rejected_and_older_mark_cannot_replace_newer_mark() -> None:
    clock = MutableClock(T0)
    book = ledger(clock=clock)
    book.apply_buy(
        base_asset="BTC", quote_asset="USD", quantity=Decimal("1"),
        execution_price=Decimal("100"), quote_debit=Decimal("101"),
    )
    with pytest.raises(ValueError, match="newer"):
        book.mark_spot_observation(mark("110", at=T0 + timedelta(seconds=1)))

    book.mark_spot_observation(mark("105", at=T0))
    book.mark_spot_observation(mark("90", at=T0 - timedelta(seconds=1)))
    assert book.snapshot(as_of=T0).positions[0].mark_price == Decimal("105")


def test_monitor_refreshes_open_spot_positions_without_agent_dependency() -> None:
    clock = MutableClock(T0)
    book = ledger(clock=clock)
    book.apply_buy(
        base_asset="BTC", quote_asset="USD", quantity=Decimal("1"),
        execution_price=Decimal("100"), quote_debit=Decimal("101"),
    )
    source = ObservationSource({"BTC/USD": mark("107")})
    monitor = PaperSpotMarkToMarketMonitor(
        market_data=source,
        portfolio=book,
        settlement_asset="USD",
        executable_symbols=("BTC/USD",),
        cadence_seconds=5,
        timeout_seconds=5,
    )
    refreshed = asyncio.run(monitor.refresh_once())
    assert refreshed == 1
    assert source.calls == ["BTC/USD"]
    assert book.snapshot(as_of=T0).positions[0].mark_price == Decimal("107")



def test_derivative_mark_ignores_older_cross_source_observation() -> None:
    clock = MutableClock(T0 + timedelta(seconds=2))
    initial = PortfolioState(
        portfolio_state_id=UUID(int=60),
        as_of=T0,
        settlement_asset="USD",
        balances=(AssetBalance(asset="USD", available=Decimal("900")),),
        derivative_positions=(
            DerivativePosition(
                symbol="BTC/USD", side=PositionSide.LONG, quantity=Decimal("1"),
                average_entry_price=Decimal("100"), mark_price=Decimal("110"),
                mark_observed_at=T0, notional=Decimal("110"), unrealized_pnl=Decimal("10"),
                leverage=Decimal("1"), margin_used=Decimal("100"),
                initial_margin_rate=Decimal("0.1"), maintenance_margin_rate=Decimal("0.05"),
                maintenance_margin=Decimal("5.50"),
            ),
        ),
    )
    book = PaperPortfolioLedger(
        initial_state=initial, clock=clock, settlement_asset="USD",
        mark_stale_after=timedelta(seconds=30),
    )
    instrument = DerivativeInstrument(
        symbol="BTC/USD", venue_symbol="PF_XBTUSD", market_type=MarketType.PERPETUAL,
        contract_kind=DerivativeContractKind.LINEAR, underlying_asset="BTC", quote_asset="USD",
        contract_size=Decimal("1"), tick_size=Decimal("0.5"), min_order_quantity=Decimal("1"),
        initial_margin_rate=Decimal("0.1"), maintenance_margin_rate=Decimal("0.05"),
        max_leverage=Decimal("10"), funding_interval_seconds=Decimal("3600"),
    )
    def state(at: datetime, price: str, ident: int) -> MarketState:
        return MarketState(
            market_state_id=UUID(int=ident), as_of=at, symbol="BTC/USD",
            last_price=Decimal(price), market_type=MarketType.PERPETUAL,
            derivative=DerivativeMarketContext(
                observed_at=at, instrument=instrument, mark_price=Decimal(price),
                index_price=None, funding_rate=None,
            ),
        )

    book.mark_derivative_market(state(T0 + timedelta(seconds=2), "112", 61))
    book.mark_derivative_market(state(T0 + timedelta(seconds=1), "90", 62))
    assert book.snapshot().derivative_positions[0].mark_price == Decimal("112")


def test_derivative_monitor_refreshes_existing_position_without_agent_dependency() -> None:
    clock = MutableClock(T0 + timedelta(seconds=1))
    initial = PortfolioState(
        portfolio_state_id=UUID(int=70),
        as_of=T0,
        settlement_asset="USD",
        balances=(AssetBalance(asset="USD", available=Decimal("900")),),
        derivative_positions=(
            DerivativePosition(
                symbol="BTC/USD", side=PositionSide.LONG, quantity=Decimal("1"),
                average_entry_price=Decimal("100"), mark_price=Decimal("110"),
                mark_observed_at=T0, notional=Decimal("110"), unrealized_pnl=Decimal("10"),
                leverage=Decimal("1"), margin_used=Decimal("100"),
                initial_margin_rate=Decimal("0.1"), maintenance_margin_rate=Decimal("0.05"),
                maintenance_margin=Decimal("5.50"),
            ),
        ),
    )
    book = PaperPortfolioLedger(
        initial_state=initial, clock=clock, settlement_asset="USD",
        mark_stale_after=timedelta(seconds=30),
    )
    instrument = DerivativeInstrument(
        symbol="BTC/USD", venue_symbol="PF_XBTUSD", market_type=MarketType.PERPETUAL,
        contract_kind=DerivativeContractKind.LINEAR, underlying_asset="BTC", quote_asset="USD",
        contract_size=Decimal("1"), tick_size=Decimal("0.5"), min_order_quantity=Decimal("1"),
        initial_margin_rate=Decimal("0.1"), maintenance_margin_rate=Decimal("0.05"),
        max_leverage=Decimal("10"), funding_interval_seconds=Decimal("3600"),
    )
    state = MarketState(
        market_state_id=UUID(int=71), as_of=T0 + timedelta(seconds=1), symbol="BTC/USD",
        last_price=Decimal("115"), market_type=MarketType.PERPETUAL,
        derivative=DerivativeMarketContext(
            observed_at=T0 + timedelta(seconds=1), instrument=instrument,
            mark_price=Decimal("115"), index_price=Decimal("114.5"), funding_rate=None,
        ),
    )
    source = SnapshotSource(state)
    monitor = PaperDerivativeMarkToMarketMonitor(
        market_data=source, portfolio=book, executable_symbols=("BTC/USD",),
        cadence_seconds=15, timeout_seconds=5,
    )
    assert asyncio.run(monitor.refresh_once()) == 1
    refreshed = book.snapshot()
    assert source.calls == ["BTC/USD"]
    assert refreshed.derivative_positions[0].mark_price == Decimal("115")
    assert refreshed.derivative_positions[0].mark_observed_at == T0 + timedelta(seconds=1)
    assert refreshed.derivative_positions[0].unrealized_pnl == Decimal("15")


def test_derivative_mark_freshness_is_distinct_from_funding_timestamp() -> None:
    clock = MutableClock(T0)
    state = PortfolioState(
        portfolio_state_id=UUID(int=80),
        as_of=T0,
        settlement_asset="USD",
        balances=(AssetBalance(asset="USD", available=Decimal("900")),),
        derivative_positions=(
            DerivativePosition(
                symbol="BTC/USD",
                side=PositionSide.LONG,
                quantity=Decimal("1"),
                average_entry_price=Decimal("100"),
                mark_price=Decimal("110"),
                mark_observed_at=T0,
                notional=Decimal("110"),
                unrealized_pnl=Decimal("10"),
                leverage=Decimal("1"),
                margin_used=Decimal("100"),
                initial_margin_rate=Decimal("0.1"),
                maintenance_margin_rate=Decimal("0.05"),
                maintenance_margin=Decimal("5.50"),
                funding_updated_at=None,
            ),
        ),
    )
    book = PaperPortfolioLedger(
        initial_state=state,
        clock=clock,
        settlement_asset="USD",
        mark_stale_after=timedelta(seconds=30),
    )
    fresh = book.snapshot()
    assert fresh.valuation_complete is True
    assert fresh.equity == Decimal("1010")
    assert fresh.exposure_value == Decimal("110")

    clock.current = T0 + timedelta(seconds=31)
    stale = book.snapshot()
    assert stale.valuation_complete is False
    assert stale.equity is None
    assert stale.exposure_value is None

def test_frontend_positions_panel_uses_backend_mark_fields_without_financial_recalculation() -> None:
    root = Path(__file__).resolve().parents[2]
    panel = (root / "frontend/src/components/cockpit/positions-panel.tsx").read_text(encoding="utf-8")
    assert "position.mark_price" in panel
    assert "position.market_value" in panel
    assert "position.unrealized_pnl" in panel
    assert "position.remaining_cost_basis" in panel
    assert "market?.symbol.startsWith" not in panel
    assert "position.quantity *" not in panel
    assert "position.mark_price *" not in panel
    assert "remaining_cost_basis -" not in panel


def test_full_sell_keeps_global_realized_pnl_when_open_position_disappears() -> None:
    book = ledger()
    book.apply_buy(
        base_asset="BTC", quote_asset="USD", quantity=Decimal("1"),
        execution_price=Decimal("100"), quote_debit=Decimal("101"),
    )
    book.apply_sell(
        base_asset="BTC", quote_asset="USD", quantity=Decimal("1"),
        quote_credit=Decimal("119"),
    )
    state = book.snapshot(as_of=T0)
    assert state.positions == ()
    assert state.spot_realized_pnl_total == Decimal("18")
    assert state.spot_market_value_total == Decimal(0)
    assert state.spot_unrealized_pnl_total == Decimal(0)
    assert state.equity == Decimal("1018")


def test_portfolio_state_accepts_derivative_event_mark_newer_than_snapshot_as_of() -> None:
    """Derivative funding/mark event time is not constrained by the snapshot clock."""

    state = PortfolioState(
        portfolio_state_id=UUID(int=90),
        as_of=T0,
        settlement_asset="USD",
        balances=(AssetBalance(asset="USD", available=Decimal("900")),),
        derivative_positions=(
            DerivativePosition(
                symbol="BTC/USD",
                side=PositionSide.LONG,
                quantity=Decimal("1"),
                average_entry_price=Decimal("100"),
                mark_price=Decimal("110"),
                mark_observed_at=T0 + timedelta(hours=1),
                notional=Decimal("110"),
                unrealized_pnl=Decimal("10"),
                leverage=Decimal("1"),
                margin_used=Decimal("100"),
                initial_margin_rate=Decimal("0.1"),
                maintenance_margin_rate=Decimal("0.05"),
                maintenance_margin=Decimal("5.50"),
            ),
        ),
    )

    assert state.derivative_positions[0].mark_observed_at == T0 + timedelta(hours=1)
