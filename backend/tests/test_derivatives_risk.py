from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from ai_spot_trader.broker.pricing import PaperExecutionCostModel
from ai_spot_trader.domain.enums import (
    DerivativeContractKind,
    MarketType,
    PositionSide,
    RiskDecision,
    RiskReason,
    TradingAction,
)
from ai_spot_trader.domain.models import (
    AssetBalance,
    DecisionCandidate,
    DerivativeInstrument,
    DerivativeMarketContext,
    DerivativePosition,
    MarketState,
    PortfolioState,
)
from ai_spot_trader.risk.engine import RiskEngine
from ai_spot_trader.risk.policy import RiskPolicy

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


class FixedClock:
    def now(self) -> datetime:
        return NOW


def instrument(*, max_leverage: str = "10") -> DerivativeInstrument:
    return DerivativeInstrument(
        symbol="BTC/USD",
        venue_symbol="PF_XBTUSD",
        market_type=MarketType.PERPETUAL,
        contract_kind=DerivativeContractKind.LINEAR,
        underlying_asset="BTC",
        quote_asset="USD",
        contract_size=Decimal("1"),
        tick_size=Decimal("1"),
        min_order_quantity=Decimal("0.01"),
        max_position_quantity=Decimal("100"),
        initial_margin_rate=Decimal("0.10"),
        maintenance_margin_rate=Decimal("0.05"),
        max_leverage=Decimal(max_leverage),
        funding_interval_seconds=Decimal("3600"),
    )


def market(*, max_leverage: str = "10") -> MarketState:
    inst = instrument(max_leverage=max_leverage)
    return MarketState(
        market_state_id=uuid4(),
        as_of=NOW,
        symbol="BTC/USD",
        last_price=Decimal("100"),
        market_type=MarketType.PERPETUAL,
        derivative=DerivativeMarketContext(
            observed_at=NOW,
            instrument=inst,
            mark_price=Decimal("100"),
            index_price=Decimal("100"),
            funding_rate=Decimal("0.001"),
        ),
    )


def decision(
    action: TradingAction,
    quantity: str,
    *,
    market_type: MarketType = MarketType.PERPETUAL,
) -> DecisionCandidate:
    return DecisionCandidate(
        decision_id=uuid4(),
        cycle_id=uuid4(),
        created_at=NOW,
        action=action,
        symbol="BTC/USD",
        proposed_quantity=Decimal(quantity),
        market_type=market_type,
    )


def position(
    side: PositionSide,
    *,
    quantity: str = "2",
    margin: str = "200",
    leverage: str = "1",
) -> DerivativePosition:
    q = Decimal(quantity)
    return DerivativePosition(
        symbol="BTC/USD",
        side=side,
        quantity=q,
        average_entry_price=Decimal("100"),
        mark_price=Decimal("100"),
        notional=Decimal("100") * q,
        unrealized_pnl=Decimal("0"),
        leverage=Decimal(leverage),
        margin_used=Decimal(margin),
        initial_margin_rate=Decimal("0.10"),
        maintenance_margin_rate=Decimal("0.05"),
        maintenance_margin=Decimal("5") * q,
        cumulative_funding=Decimal("0"),
        funding_updated_at=NOW,
    )


def portfolio(*positions: DerivativePosition, cash: str = "1000") -> PortfolioState:
    return PortfolioState(
        portfolio_state_id=uuid4(),
        as_of=NOW,
        balances=(AssetBalance(asset="USD", available=Decimal(cash)),),
        derivative_positions=tuple(positions),
    )


def policy(**overrides: object) -> RiskPolicy:
    values: dict[str, object] = {
        "allowed_pairs": frozenset({"BTC/USD"}),
        "allow_quantity_reduction": True,
        "derivative_leverage": Decimal("1"),
        "max_derivative_leverage": Decimal("3"),
        "max_derivative_position_notional": Decimal("2000"),
        "max_total_derivative_exposure": Decimal("3000"),
        "derivative_liquidation_buffer_ratio": Decimal("1.10"),
    }
    values.update(overrides)
    return RiskPolicy(**values)  # type: ignore[arg-type]


def engine(p: RiskPolicy | None = None) -> RiskEngine:
    return RiskEngine(
        policy=p or policy(),
        cost_model=PaperExecutionCostModel(
            fee_rate=Decimal("0.001"),
            spread_bps=Decimal("0"),
            slippage_bps=Decimal("0"),
        ),
        clock=FixedClock(),
    )


def test_buy_opens_long_and_sell_opens_short_without_spot_inventory() -> None:
    long_result = engine().evaluate(
        decision=decision(TradingAction.BUY, "1"),
        market_state=market(),
        portfolio_state=portfolio(),
    )
    short_result = engine().evaluate(
        decision=decision(TradingAction.SELL, "1"),
        market_state=market(),
        portfolio_state=portfolio(),
    )
    assert long_result.assessment.status is RiskDecision.ALLOW
    assert short_result.assessment.status is RiskDecision.ALLOW
    assert short_result.execution_intent is not None
    assert short_result.execution_intent.reduce_only is False


def test_leverage_above_instrument_cap_is_rejected() -> None:
    result = engine(policy(derivative_leverage=Decimal("3"))).evaluate(
        decision=decision(TradingAction.BUY, "1"),
        market_state=market(max_leverage="2"),
        portfolio_state=portfolio(),
    )
    assert result.assessment.status is RiskDecision.REJECT
    assert result.assessment.reasons == (RiskReason.DERIVATIVE_LEVERAGE_EXCEEDED,)


def test_reduce_only_can_decrease_position_already_above_current_caps() -> None:
    legacy_position = position(PositionSide.LONG, quantity="5", leverage="3")
    result = engine(
        policy(
            max_derivative_leverage=Decimal("2"),
            max_derivative_position_notional=Decimal("100"),
            max_total_derivative_exposure=Decimal("100"),
        )
    ).evaluate(
        decision=decision(TradingAction.SELL, "1"),
        market_state=market(),
        portfolio_state=portfolio(legacy_position),
    )

    assert result.assessment.status is RiskDecision.ALLOW
    assert result.assessment.reasons == ()
    assert result.execution_intent is not None
    assert result.execution_intent.reduce_only is True
    assert result.execution_intent.quantity == Decimal("1")
    assert result.execution_intent.leverage == Decimal("3")


def test_position_above_current_leverage_cap_cannot_increase_exposure() -> None:
    legacy_position = position(PositionSide.LONG, quantity="5", leverage="3")
    result = engine(policy(max_derivative_leverage=Decimal("2"))).evaluate(
        decision=decision(TradingAction.BUY, "1"),
        market_state=market(),
        portfolio_state=portfolio(legacy_position),
    )

    assert result.assessment.status is RiskDecision.REJECT
    assert result.assessment.reasons == (RiskReason.DERIVATIVE_LEVERAGE_EXCEEDED,)
    assert result.execution_intent is None


def test_accidental_reversal_is_clamped_to_reduce_only_when_reduction_enabled() -> None:
    result = engine().evaluate(
        decision=decision(TradingAction.SELL, "3"),
        market_state=market(),
        portfolio_state=portfolio(position(PositionSide.LONG, quantity="2")),
    )
    assert result.assessment.status is RiskDecision.MODIFY
    assert result.assessment.authorized_quantity == Decimal("2")
    assert result.assessment.reasons == (RiskReason.DERIVATIVE_REDUCE_ONLY_LIMIT,)
    assert result.execution_intent is not None
    assert result.execution_intent.reduce_only is True


def test_accidental_reversal_is_rejected_when_reduction_disabled() -> None:
    result = engine(policy(allow_quantity_reduction=False)).evaluate(
        decision=decision(TradingAction.SELL, "3"),
        market_state=market(),
        portfolio_state=portfolio(position(PositionSide.LONG, quantity="2")),
    )
    assert result.assessment.reasons == (RiskReason.DERIVATIVE_ACCIDENTAL_REVERSAL,)
    assert result.execution_intent is None


def test_insufficient_margin_and_liquidation_headroom_are_vetoes() -> None:
    insufficient = engine(policy(allow_quantity_reduction=False)).evaluate(
        decision=decision(TradingAction.BUY, "1"),
        market_state=market(),
        portfolio_state=portfolio(cash="50"),
    )
    assert insufficient.assessment.reasons == (RiskReason.DERIVATIVE_MARGIN_INSUFFICIENT,)

    near_liquidation = position(PositionSide.LONG, quantity="2", margin="10")
    blocked = engine().evaluate(
        decision=decision(TradingAction.BUY, "1"),
        market_state=market(),
        portfolio_state=portfolio(near_liquidation),
    )
    assert blocked.assessment.reasons == (RiskReason.DERIVATIVE_LIQUIDATION_RISK,)


def test_market_type_separation_and_spot_sell_without_inventory_remain_strict() -> None:
    mismatch = engine().evaluate(
        decision=decision(TradingAction.BUY, "1", market_type=MarketType.SPOT),
        market_state=market(),
        portfolio_state=portfolio(),
    )
    assert mismatch.assessment.reasons == (RiskReason.MARKET_TYPE_MISMATCH,)

    spot_market = MarketState(
        market_state_id=uuid4(),
        as_of=NOW,
        symbol="BTC/USD",
        last_price=Decimal("100"),
    )
    spot_decision = decision(TradingAction.SELL, "1", market_type=MarketType.SPOT)
    spot = engine(RiskPolicy(allowed_pairs=frozenset({"BTC/USD"}))).evaluate(
        decision=spot_decision,
        market_state=spot_market,
        portfolio_state=portfolio(),
    )
    assert spot.assessment.reasons == (RiskReason.POSITION_NOT_HELD,)
    assert spot.execution_intent is None


def test_derivative_position_and_total_exposure_caps_are_deterministic_vetoes() -> None:
    per_instrument = engine(policy(max_derivative_position_notional=Decimal("50"))).evaluate(
        decision=decision(TradingAction.BUY, "1"),
        market_state=market(),
        portfolio_state=portfolio(),
    )
    assert per_instrument.assessment.reasons == (
        RiskReason.DERIVATIVE_POSITION_NOTIONAL_EXCEEDED,
    )

    total = engine(policy(max_total_derivative_exposure=Decimal("150"))).evaluate(
        decision=decision(TradingAction.BUY, "1"),
        market_state=market(),
        portfolio_state=portfolio(position(PositionSide.LONG, quantity="1")),
    )
    assert total.assessment.reasons == (
        RiskReason.DERIVATIVE_TOTAL_EXPOSURE_EXCEEDED,
    )
