import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from ai_spot_trader.broker.paper import PaperBroker
from ai_spot_trader.broker.pricing import PaperExecutionCostModel
from ai_spot_trader.domain.derivative_margin import (
    DerivativeMarginTier,
    TieredDerivativeInstrument,
)
from ai_spot_trader.domain.enums import (
    DerivativeContractKind,
    MarketType,
    PositionSide,
    TradingAction,
)
from ai_spot_trader.domain.models import (
    AssetBalance,
    DerivativeInstrument,
    DerivativeMarketContext,
    ExecutionIntent,
    MarketState,
    PortfolioState,
)
from ai_spot_trader.persistence.audit import AuditedTradingCycleRunner
from ai_spot_trader.portfolio.ledger import PaperPortfolioLedger
from ai_spot_trader.trading.engine import (
    TradingCycleFailure,
    TradingCycleResult,
    TradingCycleStage,
    TradingCycleStatus,
)

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


class FixedClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


def instrument(*, tiered: bool = False) -> DerivativeInstrument:
    values: dict[str, object] = {
        "symbol": "BTC/USD",
        "venue_symbol": "PF_XBTUSD",
        "market_type": MarketType.PERPETUAL,
        "contract_kind": DerivativeContractKind.LINEAR,
        "underlying_asset": "BTC",
        "quote_asset": "USD",
        "contract_size": Decimal("1"),
        "tick_size": Decimal("1"),
        "min_order_quantity": Decimal("0.01"),
        "initial_margin_rate": Decimal("0.10"),
        "maintenance_margin_rate": Decimal("0.05"),
        "max_leverage": Decimal("10"),
        "funding_interval_seconds": Decimal("3600"),
    }
    if not tiered:
        return DerivativeInstrument(**values)  # type: ignore[arg-type]
    return TieredDerivativeInstrument(
        **values,  # type: ignore[arg-type]
        margin_tiers=(
            DerivativeMarginTier(
                threshold=Decimal("0"),
                threshold_basis="POSITION_NOTIONAL",
                initial_margin_rate=Decimal("0.10"),
                maintenance_margin_rate=Decimal("0.05"),
            ),
            DerivativeMarginTier(
                threshold=Decimal("250"),
                threshold_basis="POSITION_NOTIONAL",
                initial_margin_rate=Decimal("0.30"),
                maintenance_margin_rate=Decimal("0.15"),
            ),
            DerivativeMarginTier(
                threshold=Decimal("1000"),
                threshold_basis="POSITION_NOTIONAL",
                initial_margin_rate=Decimal("0.50"),
                maintenance_margin_rate=Decimal("0.25"),
            ),
        ),
        margin_schedule_source="retailMarginLevels",
    )


def market(
    mark: str = "100",
    funding: str = "0.001",
    at: datetime = NOW,
    *,
    tiered: bool = False,
) -> MarketState:
    return MarketState(
        market_state_id=uuid4(),
        as_of=at,
        symbol="BTC/USD",
        last_price=Decimal(mark),
        market_type=MarketType.PERPETUAL,
        derivative=DerivativeMarketContext(
            observed_at=at,
            instrument=instrument(tiered=tiered),
            mark_price=Decimal(mark),
            index_price=Decimal(mark),
            funding_rate=Decimal(funding),
        ),
    )


def intent(
    action: TradingAction,
    quantity: str,
    *,
    reduce_only: bool = False,
    leverage: str = "1",
    at: datetime = NOW,
) -> ExecutionIntent:
    return ExecutionIntent(
        execution_id=uuid4(),
        cycle_id=uuid4(),
        decision_id=uuid4(),
        risk_assessment_id=uuid4(),
        created_at=at,
        action=action,
        symbol="BTC/USD",
        quantity=Decimal(quantity),
        market_type=MarketType.PERPETUAL,
        reduce_only=reduce_only,
        leverage=Decimal(leverage),
    )


def ledger(clock: FixedClock) -> PaperPortfolioLedger:
    return PaperPortfolioLedger(
        initial_state=PortfolioState(
            portfolio_state_id=uuid4(),
            as_of=NOW,
            balances=(AssetBalance(asset="USD", available=Decimal("1000")),),
        ),
        clock=clock,
    )


def broker(portfolio: PaperPortfolioLedger, clock: FixedClock) -> PaperBroker:
    return PaperBroker(
        ledger=portfolio,
        cost_model=PaperExecutionCostModel(
            fee_rate=Decimal("0.001"),
            spread_bps=Decimal("0"),
            slippage_bps=Decimal("0"),
        ),
        clock=clock,
    )


def test_open_increase_reduce_and_close_long_position() -> None:
    clock = FixedClock(NOW)
    portfolio = ledger(clock)
    paper = broker(portfolio, clock)

    asyncio.run(paper.execute(intent(TradingAction.BUY, "1"), market()))
    asyncio.run(paper.execute(intent(TradingAction.BUY, "1"), market()))
    opened = portfolio.snapshot().derivative_positions[0]
    assert opened.side is PositionSide.LONG
    assert opened.quantity == Decimal("2")
    assert opened.average_entry_price == Decimal("100")
    assert opened.margin_used == Decimal("200")

    later = NOW + timedelta(hours=1)
    clock.value = later
    marked = market("110", "0.01", later)
    portfolio.mark_derivative_market(marked)
    marked_position = portfolio.snapshot().derivative_positions[0]
    assert marked_position.unrealized_pnl == Decimal("20")
    assert marked_position.cumulative_funding == Decimal("-2.20")

    fill = asyncio.run(
        paper.execute(
            intent(TradingAction.SELL, "1", reduce_only=True, at=later),
            marked,
        )
    )[0]
    assert fill.realized_pnl == Decimal("10")
    assert fill.funding_payment == Decimal("-1.10")
    remaining = portfolio.snapshot().derivative_positions[0]
    assert remaining.quantity == Decimal("1")
    assert remaining.cumulative_funding == Decimal("-1.10")

    asyncio.run(
        paper.execute(
            intent(TradingAction.SELL, "1", reduce_only=True, at=later),
            marked,
        )
    )
    assert portfolio.snapshot().derivative_positions == ()


def test_sell_can_open_short_without_spot_inventory() -> None:
    clock = FixedClock(NOW)
    portfolio = ledger(clock)
    paper = broker(portfolio, clock)
    asyncio.run(paper.execute(intent(TradingAction.SELL, "1"), market()))
    position = portfolio.snapshot().derivative_positions[0]
    assert position.side is PositionSide.SHORT
    assert position.quantity == Decimal("1")


def test_positive_funding_debits_long_and_credits_short() -> None:
    long_clock = FixedClock(NOW)
    long_ledger = ledger(long_clock)
    long_broker = PaperBroker(
        ledger=long_ledger,
        cost_model=PaperExecutionCostModel(
            fee_rate=Decimal("0"),
            spread_bps=Decimal("0"),
            slippage_bps=Decimal("0"),
        ),
        clock=long_clock,
    )
    asyncio.run(long_broker.execute(intent(TradingAction.BUY, "1"), market()))
    later = NOW + timedelta(hours=1)
    long_ledger.mark_derivative_market(market("110", "0.01", later))
    assert long_ledger.snapshot().derivative_positions[0].cumulative_funding == Decimal("-1.10")

    short_clock = FixedClock(NOW)
    short_ledger = ledger(short_clock)
    short_broker = PaperBroker(
        ledger=short_ledger,
        cost_model=PaperExecutionCostModel(
            fee_rate=Decimal("0"),
            spread_bps=Decimal("0"),
            slippage_bps=Decimal("0"),
        ),
        clock=short_clock,
    )
    asyncio.run(short_broker.execute(intent(TradingAction.SELL, "1"), market()))
    short_ledger.mark_derivative_market(market("110", "0.01", later))
    assert short_ledger.snapshot().derivative_positions[0].cumulative_funding == Decimal("1.10")


def test_derivative_fill_accounts_for_fee_spread_and_slippage() -> None:
    clock = FixedClock(NOW)
    portfolio = ledger(clock)
    paper = PaperBroker(
        ledger=portfolio,
        cost_model=PaperExecutionCostModel(
            fee_rate=Decimal("0.001"),
            spread_bps=Decimal("10"),
            slippage_bps=Decimal("20"),
        ),
        clock=clock,
    )
    fill = asyncio.run(paper.execute(intent(TradingAction.BUY, "1"), market()))[0]
    assert fill.price == Decimal("100.3")
    assert fill.spread_cost == Decimal("0.1")
    assert fill.slippage_cost == Decimal("0.2")
    assert fill.notional == Decimal("100.3")
    assert fill.fee == Decimal("0.1003")


def test_short_close_realizes_profit_when_price_falls() -> None:
    clock = FixedClock(NOW)
    portfolio = ledger(clock)
    paper = broker(portfolio, clock)
    asyncio.run(paper.execute(intent(TradingAction.SELL, "1"), market()))

    later = NOW + timedelta(hours=1)
    clock.value = later
    lower = market("90", "0", later)
    portfolio.mark_derivative_market(lower)
    fill = asyncio.run(
        paper.execute(
            intent(TradingAction.BUY, "1", reduce_only=True, at=later),
            lower,
        )
    )[0]
    assert fill.realized_pnl == Decimal("10")
    assert portfolio.snapshot().derivative_positions == ()


def test_tier_crossing_remargins_total_position_with_same_canonical_tier() -> None:
    clock = FixedClock(NOW)
    portfolio = ledger(clock)
    paper = broker(portfolio, clock)
    tiered_market = market(tiered=True)

    first = asyncio.run(
        paper.execute(intent(TradingAction.BUY, "2", leverage="5"), tiered_market)
    )[0]
    opened = portfolio.snapshot().derivative_positions[0]
    assert first.margin_delta == Decimal("40")
    assert opened.margin_used == Decimal("40")
    assert opened.initial_margin_rate == Decimal("0.10")
    assert opened.maintenance_margin_rate == Decimal("0.05")

    second = asyncio.run(
        paper.execute(intent(TradingAction.BUY, "1", leverage="5"), tiered_market)
    )[0]
    increased = portfolio.snapshot().derivative_positions[0]
    assert second.margin_delta == Decimal("50")
    assert increased.quantity == Decimal("3")
    assert increased.margin_used == Decimal("90")
    assert increased.initial_margin_rate == Decimal("0.30")
    assert increased.maintenance_margin_rate == Decimal("0.15")
    assert increased.maintenance_margin == Decimal("45")


def test_high_precision_perpetual_fill_from_notional_cap_is_exact() -> None:
    reference_price = Decimal("310.2472717758515210664404972")
    max_order_notional = Decimal("40")

    for contract_size in (Decimal("1"), Decimal("0.1"), Decimal("10")):
        quantity = max_order_notional / reference_price / contract_size
        clock = FixedClock(NOW)
        portfolio = ledger(clock)
        aave_instrument = DerivativeInstrument(
            symbol="AAVE/USD",
            venue_symbol="PF_AAVEUSD",
            market_type=MarketType.PERPETUAL,
            contract_kind=DerivativeContractKind.LINEAR,
            underlying_asset="AAVE",
            quote_asset="USD",
            contract_size=contract_size,
            tick_size=Decimal("0.001"),
            min_order_quantity=Decimal("0.01"),
            initial_margin_rate=Decimal("0.10"),
            maintenance_margin_rate=Decimal("0.05"),
            max_leverage=Decimal("10"),
            funding_interval_seconds=Decimal("3600"),
        )
        aave_market = MarketState(
            market_state_id=uuid4(),
            as_of=NOW,
            symbol="AAVE/USD",
            last_price=reference_price,
            market_type=MarketType.PERPETUAL,
            derivative=DerivativeMarketContext(
                observed_at=NOW,
                instrument=aave_instrument,
                mark_price=reference_price,
                index_price=reference_price,
                funding_rate=Decimal("0"),
            ),
        )
        aave_intent = ExecutionIntent(
            execution_id=uuid4(),
            cycle_id=uuid4(),
            decision_id=uuid4(),
            risk_assessment_id=uuid4(),
            created_at=NOW,
            action=TradingAction.BUY,
            symbol="AAVE/USD",
            quantity=quantity,
            market_type=MarketType.PERPETUAL,
            leverage=Decimal("1"),
        )
        paper = PaperBroker(
            ledger=portfolio,
            cost_model=PaperExecutionCostModel(
                fee_rate=Decimal("0.001"),
                spread_bps=Decimal("5"),
                slippage_bps=Decimal("7"),
            ),
            clock=clock,
        )

        fill = asyncio.run(paper.execute(aave_intent, aave_market))[0]
        adverse_delta = fill.price - fill.reference_price

        assert fill.notional == fill.price * fill.quantity * fill.contract_size
        assert (
            fill.spread_cost + fill.slippage_cost
            == adverse_delta * fill.quantity * fill.contract_size
        )
        assert fill.spread_cost > 0
        assert fill.slippage_cost > 0


def test_audited_runner_rolls_back_derivative_mutation_on_broker_failure() -> None:
    class Writer:
        async def ensure_available(self) -> None:
            return None

        async def record(self, result: TradingCycleResult) -> bool:
            assert result.status is TradingCycleStatus.FAILED
            return True

    class MutatingBrokerFailureDelegate:
        def __init__(self, portfolio: PaperPortfolioLedger) -> None:
            self.portfolio = portfolio

        async def run_cycle(self) -> TradingCycleResult:
            self.portfolio.apply_derivative_fill(
                market_state=market(),
                action=TradingAction.BUY,
                quantity=Decimal("1"),
                execution_price=Decimal("100"),
                fee=Decimal("0"),
                leverage=Decimal("1"),
                reduce_only=False,
            )
            return TradingCycleResult(
                cycle_id=uuid4(),
                status=TradingCycleStatus.FAILED,
                failure=TradingCycleFailure(
                    stage=TradingCycleStage.BROKER,
                    error_type="ValidationError",
                ),
            )

    clock = FixedClock(NOW)
    portfolio = ledger(clock)
    runner = AuditedTradingCycleRunner(
        delegate=MutatingBrokerFailureDelegate(portfolio),
        audit_writer=Writer(),
        portfolio=portfolio,
    )

    result = asyncio.run(runner.run_cycle())
    snapshot = portfolio.snapshot()

    assert result.status is TradingCycleStatus.FAILED
    assert result.failure is not None
    assert result.failure.stage is TradingCycleStage.BROKER
    assert snapshot.derivative_positions == ()
    assert snapshot.balances[0].available == Decimal("1000")
