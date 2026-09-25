import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from ai_spot_trader.domain.enums import DerivativeContractKind, MarketType
from ai_spot_trader.domain.models import (
    DerivativeInstrument,
    DerivativeMarketContext,
    ExecutableMarket,
    MarketState,
)
from ai_spot_trader.market.execution import (
    MarketOutsideExecutableUniverseError,
    RoutedExecutableMarketDataSource,
)

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
BTC = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT)


class Source:
    def __init__(self, state: MarketState) -> None:
        self.state = state
        self.calls = []

    async def snapshot(self, symbol: str) -> MarketState:
        self.calls.append(symbol)
        return self.state


def spot(symbol: str) -> MarketState:
    return MarketState(
        market_state_id=uuid4(),
        as_of=NOW,
        symbol=symbol,
        last_price=Decimal("100"),
    )


def perp(symbol: str) -> MarketState:
    base, quote = symbol.split("/")
    instrument = DerivativeInstrument(
        symbol=symbol,
        venue_symbol=f"PF_{base}{quote}",
        market_type=MarketType.PERPETUAL,
        contract_kind=DerivativeContractKind.LINEAR,
        underlying_asset=base,
        quote_asset=quote,
        contract_size=Decimal("1"),
        tick_size=Decimal("0.1"),
        min_order_quantity=Decimal("0.001"),
        initial_margin_rate=Decimal("0.1"),
        maintenance_margin_rate=Decimal("0.05"),
        max_leverage=Decimal("10"),
        funding_interval_seconds=Decimal("3600"),
    )
    return MarketState(
        market_state_id=uuid4(),
        as_of=NOW,
        symbol=symbol,
        last_price=Decimal("100"),
        market_type=MarketType.PERPETUAL,
        derivative=DerivativeMarketContext(
            observed_at=NOW,
            instrument=instrument,
            mark_price=Decimal("100"),
        ),
    )


def test_dynamic_spot_address_is_authorized_only_for_configured_quote() -> None:
    dynamic = Source(spot("ETH/USD"))
    router = RoutedExecutableMarketDataSource(
        spot=dynamic,
        derivatives=Source(perp("BTC/USD")),
        allowed_markets=(BTC,),
        allow_dynamic_markets=True,
        settlement_asset="USD",
        dynamic_market_types=(MarketType.SPOT,),
    )
    state = asyncio.run(router.snapshot("ETH/USD", MarketType.SPOT))
    assert state.symbol == "ETH/USD"

    with pytest.raises(MarketOutsideExecutableUniverseError):
        asyncio.run(router.snapshot("ETH/EUR", MarketType.SPOT))


def test_dynamic_perpetual_address_uses_existing_linear_contract_validation() -> None:
    derivatives = Source(perp("ETH/USD"))
    router = RoutedExecutableMarketDataSource(
        spot=Source(spot("BTC/USD")),
        derivatives=derivatives,
        allowed_markets=(BTC,),
        allow_dynamic_markets=True,
        settlement_asset="USD",
        dynamic_market_types=(MarketType.PERPETUAL,),
    )
    state = asyncio.run(router.snapshot("ETH/USD", MarketType.PERPETUAL))
    assert state.market_type is MarketType.PERPETUAL
