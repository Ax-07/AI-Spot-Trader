from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from pydantic import ConfigDict

from ai_spot_trader.core.clock import Clock
from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket, MarketSelectionInput, PortfolioState
from ai_spot_trader.domain.ports import Broker, ExecutableMarketDataSource, LLMProvider
from ai_spot_trader.domain.symbols import parse_canonical_symbol
from ai_spot_trader.market.discovery import MarketDiscoveryAudit, MarketDiscoveryCoordinator
from ai_spot_trader.risk.capacity import CapacityEvaluator
from ai_spot_trader.risk.engine import RiskEngine
from ai_spot_trader.trading.engine import (
    PortfolioSnapshotSource,
    TradingCycleResult,
    TradingCycleRunner,
    TradingCycleTimeouts,
)


class DiscoveredMarketSelectionInput(MarketSelectionInput):
    """Persisted extension of the canonical selection input with Batch 19.4 audit facts."""

    model_config = ConfigDict(extra="forbid")
    market_discovery: MarketDiscoveryAudit


class _PrefetchedPortfolio:
    """Reuse the causal preflight snapshot for the canonical runner's first portfolio read."""

    def __init__(self, delegate: PortfolioSnapshotSource, initial: PortfolioState) -> None:
        self._delegate = delegate
        self._initial = initial
        self._consumed = False

    def snapshot(self, *, as_of: datetime | None = None) -> PortfolioState:
        if as_of is None and not self._consumed:
            self._consumed = True
            return self._initial
        return self._delegate.snapshot(as_of=as_of)


class DynamicMarketTradingCycleRunner:
    """Resolve an audited dynamic watchlist, then reuse the canonical cycle runner.

    MANAGEMENT is evaluated before any discovery refresh. Existing positions are always injected
    into the effective universe so a watchlist removal can never make an open position unmanageable.
    """

    def __init__(
        self,
        *,
        portfolio: PortfolioSnapshotSource,
        agent: LLMProvider,
        risk_engine: RiskEngine,
        broker: Broker,
        aggressiveness: int,
        timeouts: TradingCycleTimeouts,
        executable_market_data: ExecutableMarketDataSource,
        bootstrap_markets: tuple[ExecutableMarket, ...],
        capacity_evaluator: CapacityEvaluator,
        discovery: MarketDiscoveryCoordinator,
        settlement_asset: str,
        clock: Clock | None = None,
        cycle_id_factory: Callable[[], UUID] | None = None,
    ) -> None:
        if not bootstrap_markets:
            raise ValueError("dynamic runner requires bootstrap markets")
        normalized_settlement = settlement_asset.strip().upper()
        if not normalized_settlement:
            raise ValueError("dynamic runner settlement_asset cannot be empty")
        self._portfolio = portfolio
        self._agent = agent
        self._risk_engine = risk_engine
        self._broker = broker
        self._aggressiveness = aggressiveness
        self._timeouts = timeouts
        self._executable_market_data = executable_market_data
        self._bootstrap_markets = _ordered(bootstrap_markets)
        self._capacity_evaluator = capacity_evaluator
        self._discovery = discovery
        self._settlement_asset = normalized_settlement
        self._clock = clock
        self._cycle_id_factory = cycle_id_factory
        self._cycle_lock = asyncio.Lock()

    async def run_cycle(self) -> TradingCycleResult:
        async with self._cycle_lock:
            try:
                portfolio = self._portfolio.snapshot()
            except Exception:
                # Preserve the canonical runner's FAILED-cycle semantics instead of turning a
                # preflight portfolio outage into an uncaught/audit-latching exception.
                return await self._run_canonical(
                    effective=_ordered(self._bootstrap_markets + self._discovery.watchlist),
                    portfolio_source=self._portfolio,
                )

            prefetched = _PrefetchedPortfolio(self._portfolio, portfolio)
            existing = _position_markets(portfolio, settlement_asset=self._settlement_asset)
            preflight_universe = _ordered(
                self._bootstrap_markets + self._discovery.watchlist + existing
            )
            try:
                capacity = self._capacity_evaluator.evaluate(
                    portfolio_state=portfolio,
                    executable_markets=preflight_universe,
                )
            except Exception:
                return await self._run_canonical(
                    effective=preflight_universe,
                    portfolio_source=prefetched,
                )

            if capacity.mode == "MANAGEMENT":
                discovery_result = self._discovery.cache_result(status="SKIPPED_MANAGEMENT")
                effective = _ordered(
                    self._bootstrap_markets + existing + discovery_result.watchlist
                )
            else:
                discovery_result = await self._discovery.refresh_if_due(
                    portfolio_state=portfolio
                )
                effective = _ordered(discovery_result.watchlist + existing)

            result = await self._run_canonical(
                effective=effective,
                portfolio_source=prefetched,
            )
            return _attach_discovery_audit(result, discovery_result.audit)

    async def _run_canonical(
        self,
        *,
        effective: tuple[ExecutableMarket, ...],
        portfolio_source: PortfolioSnapshotSource,
    ) -> TradingCycleResult:
        runner_kwargs: dict[str, object] = {
            "executable_market_data": self._executable_market_data,
            "executable_markets": effective,
            "capacity_evaluator": self._capacity_evaluator,
            "portfolio": portfolio_source,
            "agent": self._agent,
            "risk_engine": self._risk_engine,
            "broker": self._broker,
            "aggressiveness": self._aggressiveness,
            "timeouts": self._timeouts,
            "experiment_manifest": None,
        }
        if self._clock is not None:
            runner_kwargs["clock"] = self._clock
        if self._cycle_id_factory is not None:
            runner_kwargs["cycle_id_factory"] = self._cycle_id_factory
        runner = TradingCycleRunner(**runner_kwargs)  # type: ignore[arg-type]
        return await runner.run_cycle()


def _attach_discovery_audit(
    result: TradingCycleResult,
    audit: MarketDiscoveryAudit,
) -> TradingCycleResult:
    value = result.market_selection_input
    if value is None:
        return result
    extended = DiscoveredMarketSelectionInput(
        **value.model_dump(),
        market_discovery=audit,
    )
    return TradingCycleResult(
        cycle_id=result.cycle_id,
        status=result.status,
        failure=result.failure,
        capacity_assessment=result.capacity_assessment,
        market_selection_input=extended,
        market_selection=result.market_selection,
        agent_input=result.agent_input,
        decision=result.decision,
        risk_assessment=result.risk_assessment,
        execution_intent=result.execution_intent,
        fills=result.fills,
        portfolio_state_after=result.portfolio_state_after,
        agent_tool_traces=result.agent_tool_traces,
    )


def _position_markets(
    portfolio: PortfolioState,
    *,
    settlement_asset: str,
) -> tuple[ExecutableMarket, ...]:
    markets: list[ExecutableMarket] = []
    for position in portfolio.positions:
        if position.quantity <= 0:
            continue
        markets.append(
            ExecutableMarket(
                symbol=f"{position.asset}/{settlement_asset}",
                market_type=MarketType.SPOT,
            )
        )
    for position in portfolio.derivative_positions:
        parse_canonical_symbol(position.symbol)
        markets.append(
            ExecutableMarket(
                symbol=position.symbol,
                market_type=MarketType.PERPETUAL,
            )
        )
    return _ordered(tuple(markets)) if markets else ()


def _ordered(markets: tuple[ExecutableMarket, ...]) -> tuple[ExecutableMarket, ...]:
    return tuple(sorted(set(markets), key=lambda item: (item.market_type.value, item.symbol)))
