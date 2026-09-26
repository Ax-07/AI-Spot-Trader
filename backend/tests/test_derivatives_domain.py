from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from ai_spot_trader.domain.derivative_margin import (
    DerivativeMarginTier,
    TieredDerivativeInstrument,
    resolve_derivative_margin,
)
from ai_spot_trader.domain.enums import (
    DerivativeContractKind,
    MarketType,
    PositionSide,
    TradingAction,
)
from ai_spot_trader.domain.models import (
    DecisionCandidate,
    DerivativeInstrument,
    DerivativeMarketContext,
    DerivativePosition,
    ExecutionIntent,
    MarketState,
)

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


def instrument() -> DerivativeInstrument:
    return DerivativeInstrument(
        symbol="BTC/USD",
        venue_symbol="PF_XBTUSD",
        market_type=MarketType.PERPETUAL,
        contract_kind=DerivativeContractKind.LINEAR,
        underlying_asset="BTC",
        quote_asset="USD",
        contract_size=Decimal("1"),
        tick_size=Decimal("1"),
        min_order_quantity=Decimal("0.0001"),
        max_position_quantity=Decimal("100"),
        initial_margin_rate=Decimal("0.10"),
        maintenance_margin_rate=Decimal("0.05"),
        max_leverage=Decimal("10"),
        funding_interval_seconds=Decimal("3600"),
    )


def tiered_instrument() -> TieredDerivativeInstrument:
    return TieredDerivativeInstrument(
        **instrument().model_dump(),
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
                initial_margin_rate=Decimal("0.20"),
                maintenance_margin_rate=Decimal("0.10"),
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


def test_derivative_market_state_is_explicit_and_uses_mark_price() -> None:
    derivative = DerivativeMarketContext(
        observed_at=NOW,
        instrument=instrument(),
        mark_price=Decimal("100"),
        index_price=Decimal("99.5"),
        funding_rate=Decimal("0.001"),
    )
    state = MarketState(
        market_state_id=uuid4(),
        as_of=NOW,
        symbol="BTC/USD",
        last_price=Decimal("100"),
        market_type=MarketType.PERPETUAL,
        derivative=derivative,
    )
    assert state.market_type is MarketType.PERPETUAL
    assert state.derivative is not None
    assert state.derivative.instrument.contract_kind is DerivativeContractKind.LINEAR


def test_spot_market_state_cannot_silently_carry_derivative_context() -> None:
    derivative = DerivativeMarketContext(
        observed_at=NOW,
        instrument=instrument(),
        mark_price=Decimal("100"),
        funding_rate=Decimal("0"),
    )
    with pytest.raises(ValidationError, match="SPOT MarketState"):
        MarketState(
            market_state_id=uuid4(),
            as_of=NOW,
            symbol="BTC/USD",
            last_price=Decimal("100"),
            derivative=derivative,
        )


def test_derivative_position_validates_notional_and_maintenance_margin() -> None:
    position = DerivativePosition(
        symbol="BTC/USD",
        side=PositionSide.LONG,
        quantity=Decimal("2"),
        average_entry_price=Decimal("100"),
        mark_price=Decimal("110"),
        notional=Decimal("220"),
        unrealized_pnl=Decimal("20"),
        leverage=Decimal("2"),
        margin_used=Decimal("100"),
        initial_margin_rate=Decimal("0.10"),
        maintenance_margin_rate=Decimal("0.05"),
        maintenance_margin=Decimal("11"),
    )
    assert position.side is PositionSide.LONG
    assert position.unrealized_pnl == Decimal("20")


def test_execution_intent_separates_spot_and_derivatives() -> None:
    execution_id = uuid4()
    cycle_id = uuid4()
    decision_id = uuid4()
    risk_assessment_id = uuid4()
    with pytest.raises(ValidationError, match="SPOT intents cannot use leverage"):
        ExecutionIntent(
            execution_id=execution_id,
            cycle_id=cycle_id,
            decision_id=decision_id,
            risk_assessment_id=risk_assessment_id,
            created_at=NOW,
            action=TradingAction.BUY,
            symbol="BTC/USD",
            quantity=Decimal("1"),
            leverage=Decimal("2"),
        )

    derivative = ExecutionIntent(
        execution_id=execution_id,
        cycle_id=cycle_id,
        decision_id=decision_id,
        risk_assessment_id=risk_assessment_id,
        created_at=NOW,
        action=TradingAction.BUY,
        symbol="BTC/USD",
        quantity=Decimal("1"),
        market_type=MarketType.PERPETUAL,
        leverage=Decimal("2"),
    )
    assert derivative.leverage == Decimal("2")
    assert derivative.reduce_only is False


def test_decision_candidate_remains_spot_by_default_for_backward_compatibility() -> None:
    decision = DecisionCandidate(
        decision_id=uuid4(),
        cycle_id=uuid4(),
        created_at=NOW,
        action=TradingAction.BUY,
        symbol="BTC/USD",
        proposed_quantity=Decimal("1"),
    )
    assert decision.market_type is MarketType.SPOT


def test_margin_tier_resolver_uses_projected_position_notional() -> None:
    inst = tiered_instrument()

    first = resolve_derivative_margin(
        inst,
        projected_quantity=Decimal("2.4"),
        projected_notional=Decimal("240"),
    )
    second = resolve_derivative_margin(
        inst,
        projected_quantity=Decimal("2.6"),
        projected_notional=Decimal("260"),
    )
    last = resolve_derivative_margin(
        inst,
        projected_quantity=Decimal("11"),
        projected_notional=Decimal("1100"),
    )

    assert first.initial_margin_rate == Decimal("0.10")
    assert first.max_leverage == Decimal("10")
    assert second.initial_margin_rate == Decimal("0.20")
    assert second.max_leverage == Decimal("5")
    assert last.initial_margin_rate == Decimal("0.50")
    assert last.max_leverage == Decimal("2")


def test_tiered_instrument_rejects_incoherent_curves() -> None:
    base = instrument().model_dump()
    with pytest.raises(ValidationError, match="unique ascending thresholds"):
        TieredDerivativeInstrument(
            **base,
            margin_tiers=(
                DerivativeMarginTier(
                    threshold=Decimal("0"),
                    threshold_basis="POSITION_NOTIONAL",
                    initial_margin_rate=Decimal("0.10"),
                    maintenance_margin_rate=Decimal("0.05"),
                ),
                DerivativeMarginTier(
                    threshold=Decimal("0"),
                    threshold_basis="POSITION_NOTIONAL",
                    initial_margin_rate=Decimal("0.20"),
                    maintenance_margin_rate=Decimal("0.10"),
                ),
            ),
            margin_schedule_source="fixture",
        )
