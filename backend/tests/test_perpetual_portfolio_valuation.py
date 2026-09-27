import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from ai_spot_trader.domain.enums import (
    DerivativeContractKind,
    MarketType,
    PositionSide,
)
from ai_spot_trader.domain.models import (
    AssetBalance,
    DerivativeInstrument,
    DerivativeMarketContext,
    DerivativePosition,
    ExecutableMarket,
    MarketObservation,
    MarketState,
    PortfolioState,
)
from ai_spot_trader.portfolio.ledger import PaperPortfolioLedger
from ai_spot_trader.portfolio.mark_to_market import (
    PaperDerivativeMarkToMarketMonitor,
    PaperSpotMarkToMarketMonitor,
)
from ai_spot_trader.risk.capacity import (
    REASON_OPENING_CAPACITY_AVAILABLE,
    REASON_VALUATION_INCOMPLETE,
    CapacityEvaluator,
)
from ai_spot_trader.risk.policy import RiskPolicy

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
ZERO = Decimal(0)


class MutableClock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


def _position(
    symbol: str,
    *,
    side: PositionSide,
    quantity: str,
    entry: str,
    mark: str,
    margin: str,
    funding: str = "0",
    marked_at: datetime | None = NOW,
) -> DerivativePosition:
    q = Decimal(quantity)
    entry_price = Decimal(entry)
    mark_price = Decimal(mark)
    exposure_units = q
    notional = mark_price * exposure_units
    unrealized = (
        (mark_price - entry_price) * exposure_units
        if side is PositionSide.LONG
        else (entry_price - mark_price) * exposure_units
    )
    maintenance_rate = Decimal("0.05")
    return DerivativePosition(
        symbol=symbol,
        side=side,
        quantity=q,
        average_entry_price=entry_price,
        mark_price=mark_price,
        mark_observed_at=marked_at,
        contract_size=Decimal(1),
        notional=notional,
        realized_pnl=ZERO,
        unrealized_pnl=unrealized,
        leverage=Decimal(2),
        margin_used=Decimal(margin),
        initial_margin_rate=Decimal("0.10"),
        maintenance_margin_rate=maintenance_rate,
        maintenance_margin=notional * maintenance_rate,
        cumulative_funding=Decimal(funding),
    )


def _ledger(
    *,
    cash: str = "1000",
    derivatives: tuple[DerivativePosition, ...] = (),
    clock: MutableClock | None = None,
) -> PaperPortfolioLedger:
    current = clock or MutableClock()
    return PaperPortfolioLedger(
        initial_state=PortfolioState(
            portfolio_state_id=uuid4(),
            as_of=current.now(),
            settlement_asset="USD",
            balances=(AssetBalance(asset="USD", available=Decimal(cash)),),
            derivative_positions=derivatives,
        ),
        clock=current,
        settlement_asset="USD",
        mark_stale_after=timedelta(seconds=30),
    )


def _instrument(symbol: str) -> DerivativeInstrument:
    base, quote = symbol.split("/")
    return DerivativeInstrument(
        symbol=symbol,
        venue_symbol=f"PF_{base}{quote}",
        market_type=MarketType.PERPETUAL,
        contract_kind=DerivativeContractKind.LINEAR,
        underlying_asset=base,
        quote_asset=quote,
        contract_size=Decimal(1),
        tick_size=Decimal("0.01"),
        min_order_quantity=Decimal("0.001"),
        initial_margin_rate=Decimal("0.10"),
        maintenance_margin_rate=Decimal("0.05"),
        max_leverage=Decimal(10),
        funding_interval_seconds=Decimal(3600),
    )


def _market(symbol: str, price: str, *, observed_at: datetime) -> MarketState:
    mark_price = Decimal(price)
    return MarketState(
        market_state_id=uuid4(),
        as_of=observed_at,
        symbol=symbol,
        last_price=mark_price,
        market_type=MarketType.PERPETUAL,
        derivative=DerivativeMarketContext(
            observed_at=observed_at,
            instrument=_instrument(symbol),
            mark_price=mark_price,
        ),
    )


def _capacity_policy() -> RiskPolicy:
    return RiskPolicy(
        derivative_leverage=Decimal(2),
        max_derivative_leverage=Decimal(5),
        max_derivative_position_notional=Decimal("5000"),
        max_total_derivative_exposure=Decimal("10000"),
    )


def test_cash_only_portfolio_has_complete_zero_exposure_valuation() -> None:
    state = _ledger(cash="1000").snapshot()

    assert state.valuation_complete is True
    assert state.cash_available == Decimal("1000")
    assert state.equity == Decimal("1000")
    assert state.exposure_value == ZERO
    assert state.exposure_fraction == ZERO


def test_spot_valuation_remains_complete_and_uses_marked_market_value() -> None:
    book = _ledger(cash="1000")
    book.apply_buy(
        base_asset="BTC",
        quote_asset="USD",
        quantity=Decimal(1),
        quote_debit=Decimal("101"),
        execution_price=Decimal("100"),
    )
    book.mark_spot_observation(
        MarketObservation(observed_at=NOW, symbol="BTC/USD", last_price=Decimal("110"))
    )
    state = book.snapshot()

    assert state.valuation_complete is True
    assert state.cash_available == Decimal("899")
    assert state.spot_market_value_total == Decimal("110")
    assert state.equity == Decimal("1009")
    assert state.exposure_value == Decimal("110")


def test_fresh_perpetual_long_is_included_in_equity_and_notional_exposure() -> None:
    position = _position(
        "BTC/USD",
        side=PositionSide.LONG,
        quantity="2",
        entry="100",
        mark="110",
        margin="100",
        funding="-1",
    )
    state = _ledger(cash="800", derivatives=(position,)).snapshot()

    assert state.valuation_complete is True
    assert state.equity == Decimal("919")  # 800 cash + 100 margin + 20 UPL - 1 funding
    assert state.exposure_value == Decimal("220")
    assert state.exposure_fraction == Decimal("220") / Decimal("919")


def test_fresh_perpetual_short_is_included_in_equity_and_notional_exposure() -> None:
    position = _position(
        "ETH/USD",
        side=PositionSide.SHORT,
        quantity="3",
        entry="50",
        mark="40",
        margin="120",
        funding="2",
    )
    state = _ledger(cash="600", derivatives=(position,)).snapshot()

    assert state.valuation_complete is True
    assert state.equity == Decimal("752")  # 600 cash + 120 margin + 30 UPL + 2 funding
    assert state.exposure_value == Decimal("120")


def test_multiple_fresh_perpetual_positions_aggregate_equity_and_exposure() -> None:
    positions = (
        _position(
            "BTC/USD",
            side=PositionSide.LONG,
            quantity="2",
            entry="100",
            mark="110",
            margin="100",
            funding="-1",
        ),
        _position(
            "ETH/USD",
            side=PositionSide.SHORT,
            quantity="3",
            entry="50",
            mark="40",
            margin="120",
            funding="2",
        ),
        _position(
            "SOL/USD",
            side=PositionSide.LONG,
            quantity="4",
            entry="20",
            mark="25",
            margin="50",
        ),
    )
    state = _ledger(cash="500", derivatives=positions).snapshot()

    assert state.valuation_complete is True
    assert state.equity == Decimal("841")
    assert state.exposure_value == Decimal("440")
    assert state.exposure_fraction == Decimal("440") / Decimal("841")


def test_missing_derivative_mark_timestamp_keeps_fail_closed_even_with_price_and_pnl() -> None:
    position = _position(
        "BTC/USD",
        side=PositionSide.LONG,
        quantity="1",
        entry="100",
        mark="110",
        margin="100",
        marked_at=None,
    )
    state = _ledger(cash="900", derivatives=(position,)).snapshot()

    assert state.derivative_positions[0].mark_price == Decimal("110")
    assert state.derivative_positions[0].unrealized_pnl == Decimal("10")
    assert state.valuation_complete is False
    assert state.equity is None
    assert state.exposure_value is None
    assert state.exposure_fraction is None


def test_stale_derivative_mark_keeps_fail_closed() -> None:
    clock = MutableClock(NOW + timedelta(seconds=31))
    position = _position(
        "BTC/USD",
        side=PositionSide.LONG,
        quantity="1",
        entry="100",
        mark="110",
        margin="100",
        marked_at=NOW,
    )
    state = _ledger(cash="900", derivatives=(position,), clock=clock).snapshot()

    assert state.valuation_complete is False
    assert state.equity is None
    assert state.exposure_value is None


def test_complete_perpetual_portfolio_can_recover_normal_opening_capacity() -> None:
    position = _position(
        "BTC/USD",
        side=PositionSide.LONG,
        quantity="1",
        entry="100",
        mark="110",
        margin="100",
    )
    state = _ledger(cash="900", derivatives=(position,)).snapshot()
    market = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.PERPETUAL)

    assessment = CapacityEvaluator(policy=_capacity_policy()).evaluate(
        portfolio_state=state,
        executable_markets=(market,),
    )

    assert assessment.mode == "NORMAL"
    assert assessment.reason == REASON_OPENING_CAPACITY_AVAILABLE
    assert assessment.perpetual_opening_capacity == "POSSIBLE"


def test_incomplete_perpetual_portfolio_stays_management_fail_closed() -> None:
    position = _position(
        "BTC/USD",
        side=PositionSide.LONG,
        quantity="1",
        entry="100",
        mark="110",
        margin="100",
        marked_at=None,
    )
    state = _ledger(cash="900", derivatives=(position,)).snapshot()
    market = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.PERPETUAL)

    assessment = CapacityEvaluator(policy=_capacity_policy()).evaluate(
        portfolio_state=state,
        executable_markets=(market,),
    )

    assert assessment.mode == "MANAGEMENT"
    assert assessment.reason == REASON_VALUATION_INCOMPLETE
    assert assessment.perpetual_opening_capacity == "UNKNOWN"
    assert assessment.management_markets == (market,)


def test_derivative_monitor_start_waits_for_initial_revaluation_before_returning() -> None:
    async def scenario() -> None:
        clock = MutableClock(NOW + timedelta(hours=1))
        stale = _position(
            "BTC/USD",
            side=PositionSide.LONG,
            quantity="1",
            entry="100",
            mark="110",
            margin="100",
            marked_at=None,
        )
        book = _ledger(cash="900", derivatives=(stale,), clock=clock)
        fresh_market = _market("BTC/USD", "115", observed_at=clock.now())

        class BlockingSource:
            def __init__(self) -> None:
                self.entered = asyncio.Event()
                self.release = asyncio.Event()
                self.calls: list[str] = []

            async def snapshot(self, symbol: str) -> MarketState:
                self.calls.append(symbol)
                self.entered.set()
                await self.release.wait()
                return fresh_market

        source = BlockingSource()
        monitor = PaperDerivativeMarkToMarketMonitor(
            market_data=source,
            portfolio=book,
            executable_symbols=("BTC/USD",),
            cadence_seconds=15,
            timeout_seconds=5,
        )

        start_task = asyncio.create_task(monitor.start())
        await source.entered.wait()
        await asyncio.sleep(0)
        assert start_task.done() is False
        assert book.snapshot().valuation_complete is False

        source.release.set()
        await start_task
        refreshed = book.snapshot()
        assert source.calls == ["BTC/USD"]
        assert refreshed.valuation_complete is True
        assert refreshed.derivative_positions[0].mark_price == Decimal("115")
        assert refreshed.derivative_positions[0].mark_observed_at == clock.now()
        assert refreshed.equity == Decimal("1015")
        assert monitor.is_running is True
        await monitor.aclose()

    asyncio.run(scenario())


def test_failed_initial_derivative_refresh_preserves_fail_closed_management() -> None:
    async def scenario() -> None:
        clock = MutableClock(NOW + timedelta(hours=1))
        stale = _position(
            "BTC/USD",
            side=PositionSide.LONG,
            quantity="1",
            entry="100",
            mark="110",
            margin="100",
            marked_at=None,
        )
        book = _ledger(cash="900", derivatives=(stale,), clock=clock)

        class FailingSource:
            async def snapshot(self, symbol: str) -> MarketState:
                assert symbol == "BTC/USD"
                raise RuntimeError("public mark unavailable")

        monitor = PaperDerivativeMarkToMarketMonitor(
            market_data=FailingSource(),
            portfolio=book,
            executable_symbols=("BTC/USD",),
            cadence_seconds=15,
            timeout_seconds=5,
        )

        await monitor.start()
        state = book.snapshot()
        assessment = CapacityEvaluator(policy=_capacity_policy()).evaluate(
            portfolio_state=state,
            executable_markets=(
                ExecutableMarket(symbol="BTC/USD", market_type=MarketType.PERPETUAL),
            ),
        )

        assert state.valuation_complete is False
        assert state.equity is None
        assert monitor.last_error_type == "RuntimeError"
        assert assessment.mode == "MANAGEMENT"
        assert assessment.reason == REASON_VALUATION_INCOMPLETE
        await monitor.aclose()

    asyncio.run(scenario())


def test_spot_monitor_start_also_waits_for_initial_revaluation_before_returning() -> None:
    async def scenario() -> None:
        clock = MutableClock(NOW + timedelta(hours=1))
        book = _ledger(cash="1000", clock=clock)
        book.apply_buy(
            base_asset="BTC",
            quote_asset="USD",
            quantity=Decimal(1),
            quote_debit=Decimal("101"),
            execution_price=Decimal("100"),
        )

        class BlockingSpotSource:
            def __init__(self) -> None:
                self.entered = asyncio.Event()
                self.release = asyncio.Event()

            async def observation(self, symbol: str) -> MarketObservation:
                assert symbol == "BTC/USD"
                self.entered.set()
                await self.release.wait()
                return MarketObservation(
                    observed_at=clock.now(),
                    symbol=symbol,
                    last_price=Decimal("105"),
                )

        source = BlockingSpotSource()
        monitor = PaperSpotMarkToMarketMonitor(
            market_data=source,
            portfolio=book,
            settlement_asset="USD",
            executable_symbols=("BTC/USD",),
            cadence_seconds=5,
            timeout_seconds=5,
        )

        start_task = asyncio.create_task(monitor.start())
        await source.entered.wait()
        await asyncio.sleep(0)
        assert start_task.done() is False
        assert book.snapshot().valuation_complete is False

        source.release.set()
        await start_task
        state = book.snapshot()
        assert state.valuation_complete is True
        assert state.spot_market_value_total == Decimal("105")
        assert state.equity == Decimal("1004")
        await monitor.aclose()

    asyncio.run(scenario())
