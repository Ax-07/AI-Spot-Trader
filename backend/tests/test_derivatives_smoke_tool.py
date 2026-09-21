import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from ai_spot_trader.core.config import Settings
from ai_spot_trader.domain.enums import (
    DerivativeContractKind,
    MarketType,
    TradingAction,
)
from ai_spot_trader.domain.models import (
    AgentInput,
    AssetBalance,
    DerivativeInstrument,
    DerivativeMarketContext,
    MarketState,
    PortfolioState,
)
from ai_spot_trader.tools.derivatives_smoke import (
    ScriptedSmokeDecisionProvider,
    SmokeSafetyError,
    SmokeSide,
    build_derivatives_smoke_runtime,
    build_smoke_plan,
)

NOW = datetime(2026, 9, 21, 20, 0, tzinfo=UTC)


def _agent_input(
    *,
    market_type: MarketType = MarketType.PERPETUAL,
    venue_symbol: str = "PF_XBTUSD",
    min_order_quantity: str = "0.0001",
    mark_price: str = "100000",
) -> AgentInput:
    derivative = None
    if market_type is not MarketType.SPOT:
        derivative = DerivativeMarketContext(
            observed_at=NOW,
            instrument=DerivativeInstrument(
                symbol="BTC/USD",
                venue_symbol=venue_symbol,
                market_type=market_type,
                contract_kind=DerivativeContractKind.LINEAR,
                underlying_asset="BTC",
                quote_asset="USD",
                contract_size=Decimal("1"),
                tick_size=Decimal("0.1"),
                min_order_quantity=Decimal(min_order_quantity),
                initial_margin_rate=Decimal("0.02"),
                maintenance_margin_rate=Decimal("0.01"),
                max_leverage=Decimal("10"),
                funding_interval_seconds=(
                    Decimal("3600") if market_type is MarketType.PERPETUAL else None
                ),
                expires_at=None,
            ),
            mark_price=Decimal(mark_price),
            index_price=Decimal(mark_price),
            funding_rate=Decimal("0.00001") if market_type is MarketType.PERPETUAL else None,
        )
    return AgentInput(
        cycle_id=uuid4(),
        created_at=NOW,
        market_state=MarketState(
            market_state_id=uuid4(),
            as_of=NOW,
            symbol="BTC/USD",
            last_price=Decimal(mark_price),
            market_type=market_type,
            derivative=derivative,
        ),
        portfolio_state=PortfolioState(
            portfolio_state_id=uuid4(),
            as_of=NOW,
            balances=(AssetBalance(asset="USD", available=Decimal("1000")),),
        ),
        aggressiveness=5,
    )


def test_long_smoke_plan_uses_kraken_minimum_and_never_changes_market_type() -> None:
    provider = ScriptedSmokeDecisionProvider(
        plan=build_smoke_plan(SmokeSide.LONG),
        max_smoke_notional=Decimal("50"),
    )
    decisions = [
        asyncio.run(provider.generate_decision(_agent_input()))
        for _ in range(4)
    ]

    assert [item.action for item in decisions] == [
        TradingAction.BUY,
        TradingAction.HOLD,
        TradingAction.SELL,
        TradingAction.SELL,
    ]
    assert [item.proposed_quantity for item in decisions] == [
        Decimal("0.0002"),
        None,
        Decimal("0.0001"),
        Decimal("0.0002"),
    ]
    assert all(item.market_type is MarketType.PERPETUAL for item in decisions)
    assert all("CONTROLLED_SMOKE_BATCH_16_3" in (item.rationale or "") for item in decisions)
    assert provider.remaining_steps == 0


def test_short_smoke_plan_mirrors_open_and_close_actions() -> None:
    provider = ScriptedSmokeDecisionProvider(
        plan=build_smoke_plan(SmokeSide.SHORT),
        max_smoke_notional=Decimal("50"),
    )
    decisions = [
        asyncio.run(provider.generate_decision(_agent_input()))
        for _ in range(4)
    ]
    assert [item.action for item in decisions] == [
        TradingAction.SELL,
        TradingAction.HOLD,
        TradingAction.BUY,
        TradingAction.BUY,
    ]


def test_smoke_provider_fails_closed_outside_pinned_contract() -> None:
    provider = ScriptedSmokeDecisionProvider(
        plan=build_smoke_plan(SmokeSide.LONG),
        max_smoke_notional=Decimal("50"),
    )
    with pytest.raises(SmokeSafetyError, match="PF_XBTUSD"):
        asyncio.run(
            provider.generate_decision(_agent_input(venue_symbol="PI_XBTUSD"))
        )


def test_smoke_provider_refuses_reference_notional_over_safety_cap() -> None:
    provider = ScriptedSmokeDecisionProvider(
        plan=build_smoke_plan(SmokeSide.LONG),
        max_smoke_notional=Decimal("10"),
    )
    with pytest.raises(SmokeSafetyError, match="safety cap"):
        asyncio.run(provider.generate_decision(_agent_input()))


def test_smoke_runtime_is_forbidden_in_production() -> None:
    with pytest.raises(SmokeSafetyError, match="forbidden in production"):
        build_derivatives_smoke_runtime(
            Settings(environment="production"),
            side=SmokeSide.LONG,
            max_smoke_notional=Decimal("50"),
        )
