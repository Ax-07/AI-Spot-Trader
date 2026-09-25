import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import ai_spot_trader.trading.discovery_runner as discovery_runner_module

from ai_spot_trader.domain.enums import MarketType, PositionSide
from ai_spot_trader.domain.models import (
    AssetBalance,
    AssetPosition,
    DerivativePosition,
    ExecutableMarket,
    PortfolioState,
)
from ai_spot_trader.market.discovery import MarketDiscoveryAudit, MarketDiscoveryResult
from ai_spot_trader.risk.capacity import CapacityAssessment
from ai_spot_trader.trading.engine import (
    TradingCycleFailure,
    TradingCycleResult,
    TradingCycleStage,
    TradingCycleStatus,
    TradingCycleTimeouts,
)
from ai_spot_trader.trading.discovery_runner import DynamicMarketTradingCycleRunner

NOW = datetime(2026, 9, 25, 11, 0, tzinfo=UTC)
BTC = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT)
ETH = ExecutableMarket(symbol="ETH/USD", market_type=MarketType.SPOT)


class Ledger:
    def __init__(self, state: PortfolioState) -> None:
        self.state = state

    def snapshot(self, *, as_of=None):
        return self.state


class Capacity:
    def __init__(self, mode: str, management=()) -> None:
        self.mode = mode
        self.management = management
        self.calls = []

    def evaluate(self, *, portfolio_state, executable_markets):
        self.calls.append(executable_markets)
        return CapacityAssessment(
            mode=self.mode,
            reason="test",
            spot_opening_capacity="POSSIBLE" if self.mode == "NORMAL" else "UNAVAILABLE",
            perpetual_opening_capacity="NOT_APPLICABLE",
            management_markets=self.management,
        )


class Discovery:
    def __init__(self, watchlist=(ETH,)) -> None:
        self.watchlist = watchlist
        self.refresh_calls = 0
        self.cache_calls = []

    async def refresh_if_due(self, *, portfolio_state):
        self.refresh_calls += 1
        return MarketDiscoveryResult(
            watchlist=self.watchlist,
            audit=MarketDiscoveryAudit(
                status="CACHE_REUSED",
                observed_at=NOW,
                effective_watchlist=self.watchlist,
            ),
        )

    def cache_result(self, *, status):
        self.cache_calls.append(status)
        return MarketDiscoveryResult(
            watchlist=self.watchlist,
            audit=MarketDiscoveryAudit(
                status=status,
                observed_at=NOW,
                effective_watchlist=self.watchlist,
            ),
        )


class CapturingCanonicalRunner:
    last_kwargs = None

    def __init__(self, **kwargs):
        type(self).last_kwargs = kwargs

    async def run_cycle(self):
        return TradingCycleResult(
            cycle_id=uuid4(),
            status=TradingCycleStatus.FAILED,
            failure=TradingCycleFailure(
                stage=TradingCycleStage.MARKET,
                error_type="TestStop",
            ),
        )


def complete_portfolio(*, cash: str = "1000", spots=()) -> PortfolioState:
    cash_value = Decimal(cash)
    return PortfolioState(
        portfolio_state_id=uuid4(),
        as_of=NOW,
        settlement_asset="USD",
        balances=(AssetBalance(asset="USD", available=cash_value),),
        positions=spots,
        cash_available=cash_value,
        spot_remaining_cost_basis_total=None,
        spot_market_value_total=None,
        spot_realized_pnl_total=Decimal(0),
        spot_unrealized_pnl_total=None,
        valuation_complete=False,
    )


def held_eth() -> AssetPosition:
    return AssetPosition(asset="ETH", quantity=Decimal("1"), available=Decimal("1"))


def runner(state, capacity, discovery):
    return DynamicMarketTradingCycleRunner(
        portfolio=Ledger(state),
        agent=object(),  # canonical runner is replaced below
        risk_engine=object(),
        broker=object(),
        aggressiveness=5,
        timeouts=TradingCycleTimeouts(1, 1, 1),
        executable_market_data=object(),
        bootstrap_markets=(BTC,),
        capacity_evaluator=capacity,
        discovery=discovery,
        settlement_asset="USD",
    )


def test_normal_mode_refreshes_discovery_and_uses_strategic_watchlist(monkeypatch) -> None:
    monkeypatch.setattr(discovery_runner_module, "TradingCycleRunner", CapturingCanonicalRunner)
    capacity = Capacity("NORMAL")
    discovery = Discovery((ETH,))
    result = asyncio.run(runner(complete_portfolio(), capacity, discovery).run_cycle())

    assert result.status is TradingCycleStatus.FAILED
    assert discovery.refresh_calls == 1
    assert discovery.cache_calls == []
    assert CapturingCanonicalRunner.last_kwargs["executable_markets"] == (ETH,)


def test_management_skips_discovery_refresh_and_keeps_open_position_market(monkeypatch) -> None:
    monkeypatch.setattr(discovery_runner_module, "TradingCycleRunner", CapturingCanonicalRunner)
    capacity = Capacity("MANAGEMENT", management=(ETH,))
    discovery = Discovery(())
    state = complete_portfolio(cash="0", spots=(held_eth(),))
    asyncio.run(runner(state, capacity, discovery).run_cycle())

    assert discovery.refresh_calls == 0
    assert discovery.cache_calls == ["SKIPPED_MANAGEMENT"]
    effective = CapturingCanonicalRunner.last_kwargs["executable_markets"]
    assert BTC in effective
    assert ETH in effective


def test_position_market_survives_watchlist_removal_in_normal_mode(monkeypatch) -> None:
    monkeypatch.setattr(discovery_runner_module, "TradingCycleRunner", CapturingCanonicalRunner)
    capacity = Capacity("NORMAL")
    discovery = Discovery((BTC,))
    state = complete_portfolio(spots=(held_eth(),))
    asyncio.run(runner(state, capacity, discovery).run_cycle())

    effective = CapturingCanonicalRunner.last_kwargs["executable_markets"]
    assert BTC in effective
    assert ETH in effective


def test_mixed_portfolio_reinjects_spot_and_perpetual_position_markets() -> None:
    derivative = DerivativePosition(
        symbol="BTC/USD",
        side=PositionSide.LONG,
        quantity=Decimal("2"),
        average_entry_price=Decimal("100"),
        mark_price=Decimal("100"),
        mark_observed_at=NOW,
        notional=Decimal("200"),
        unrealized_pnl=Decimal("0"),
        leverage=Decimal("1"),
        margin_used=Decimal("200"),
        initial_margin_rate=Decimal("0.10"),
        maintenance_margin_rate=Decimal("0.05"),
        maintenance_margin=Decimal("10"),
    )
    state = complete_portfolio(spots=(held_eth(),)).model_copy(
        update={"derivative_positions": (derivative,)}
    )

    markets = discovery_runner_module._position_markets(  # noqa: SLF001
        state, settlement_asset="USD"
    )

    assert markets == (
        ExecutableMarket(symbol="BTC/USD", market_type=MarketType.PERPETUAL),
        ETH,
    )
