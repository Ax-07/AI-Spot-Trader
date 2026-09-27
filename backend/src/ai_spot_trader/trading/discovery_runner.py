from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from pydantic import ConfigDict

from ai_spot_trader.core.clock import Clock
from ai_spot_trader.domain.models import (
    ExecutionCostContext,
    ExecutableMarket,
    MarketSelectionInput,
    PortfolioState,
    TradingStyleContext,
)
from ai_spot_trader.domain.planning import DEFAULT_MAX_DECISIONS_PER_CYCLE
from ai_spot_trader.domain.ports import Broker, ExecutableMarketDataSource, MultiMarketLLMProvider
from ai_spot_trader.market.discovery import MarketDiscoveryAudit, MarketDiscoveryCoordinator
from ai_spot_trader.risk.capacity import CapacityEvaluator, open_position_markets
from ai_spot_trader.risk.engine import RiskEngine
from ai_spot_trader.trading.engine import (
    PortfolioSnapshotSource,
    TradingCycleResult,
    TradingCycleTimeouts,
)
from ai_spot_trader.trading.multi_market import (
    MultiMarketTradingCycleResult,
    MultiMarketTradingCycleRunner,
)

# Backward-compatible monkeypatch/import seam retained while the canonical runtime
# implementation is now the multi-market runner.
TradingCycleRunner = MultiMarketTradingCycleRunner


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
    """Resolve an audited watchlist, then execute one ordered multi-market strategic plan."""

    def __init__(
        self,
        *,
        portfolio: PortfolioSnapshotSource,
        agent: MultiMarketLLMProvider,
        risk_engine: RiskEngine,
        broker: Broker,
        aggressiveness: int,
        timeouts: TradingCycleTimeouts,
        executable_market_data: ExecutableMarketDataSource,
        bootstrap_markets: tuple[ExecutableMarket, ...],
        capacity_evaluator: CapacityEvaluator,
        discovery: MarketDiscoveryCoordinator,
        settlement_asset: str,
        max_decisions_per_cycle: int = DEFAULT_MAX_DECISIONS_PER_CYCLE,
        trading_style_context: TradingStyleContext | None = None,
        execution_cost_context: ExecutionCostContext | None = None,
        clock: Clock | None = None,
        cycle_id_factory: Callable[[], UUID] | None = None,
    ) -> None:
        if not bootstrap_markets:
            raise ValueError("dynamic runner requires bootstrap markets")
        normalized_settlement = settlement_asset.strip().upper()
        if not normalized_settlement:
            raise ValueError("dynamic runner settlement_asset cannot be empty")
        if (trading_style_context is None) != (execution_cost_context is None):
            raise ValueError(
                "trading_style_context and execution_cost_context must be supplied together"
            )
        self._portfolio = portfolio
        self._agent = agent
        self._risk_engine = risk_engine
        self._broker = broker
        self._aggressiveness = aggressiveness
        self._max_decisions_per_cycle = max_decisions_per_cycle
        self._timeouts = timeouts
        self._executable_market_data = executable_market_data
        self._bootstrap_markets = _ordered(bootstrap_markets)
        self._capacity_evaluator = capacity_evaluator
        self._discovery = discovery
        self._settlement_asset = normalized_settlement
        self._trading_style_context = trading_style_context
        self._execution_cost_context = execution_cost_context
        self._clock = clock
        self._cycle_id_factory = cycle_id_factory
        self._cycle_lock = asyncio.Lock()

    async def run_cycle(self) -> MultiMarketTradingCycleResult:
        async with self._cycle_lock:
            try:
                portfolio = self._portfolio.snapshot()
            except Exception:
                return await self._run_canonical(
                    effective=_ordered(self._bootstrap_markets + self._discovery.watchlist),
                    portfolio_source=self._portfolio,
                )

            prefetched = _PrefetchedPortfolio(self._portfolio, portfolio)
            existing = open_position_markets(
                portfolio,
                settlement_asset=self._settlement_asset,
            )
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
    ) -> MultiMarketTradingCycleResult:
        runner_kwargs: dict[str, object] = {
            "executable_market_data": self._executable_market_data,
            "executable_markets": effective,
            "capacity_evaluator": self._capacity_evaluator,
            "portfolio": portfolio_source,
            "agent": self._agent,
            "risk_engine": self._risk_engine,
            "broker": self._broker,
            "aggressiveness": self._aggressiveness,
            "max_decisions_per_cycle": self._max_decisions_per_cycle,
            "timeouts": self._timeouts,
            "trading_style_context": self._trading_style_context,
            "execution_cost_context": self._execution_cost_context,
        }
        if self._clock is not None:
            runner_kwargs["clock"] = self._clock
        if self._cycle_id_factory is not None:
            runner_kwargs["cycle_id_factory"] = self._cycle_id_factory
        runner = TradingCycleRunner(**runner_kwargs)  # type: ignore[arg-type]
        return await runner.run_cycle()


def _attach_discovery_audit(
    result: MultiMarketTradingCycleResult | TradingCycleResult,
    audit: MarketDiscoveryAudit,
) -> MultiMarketTradingCycleResult | TradingCycleResult:
    value = result.market_selection_input
    if value is None:
        return result
    extended = DiscoveredMarketSelectionInput(
        **value.model_dump(),
        market_discovery=audit,
    )
    if isinstance(result, MultiMarketTradingCycleResult):
        return MultiMarketTradingCycleResult(
            cycle_id=result.cycle_id,
            status=result.status,
            failure=result.failure,
            capacity_assessment=result.capacity_assessment,
            market_selection_input=extended,
            decision_plan_input=result.decision_plan_input,
            decision_plan=result.decision_plan,
            decision_results=result.decision_results,
            final_portfolio_state=result.final_portfolio_state,
            agent_tool_traces=result.agent_tool_traces,
            decision=result.decision,
            risk_assessment=result.risk_assessment,
            execution_intent=result.execution_intent,
            fills=result.fills,
            portfolio_state_after=result.portfolio_state_after,
        )

    # Historical tests/callers may still substitute the pre-19.13 canonical runner.
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
    """Backward-compatible alias for the centralized open-position market mapping."""

    return open_position_markets(portfolio, settlement_asset=settlement_asset)


def _ordered(markets: tuple[ExecutableMarket, ...]) -> tuple[ExecutableMarket, ...]:
    return tuple(sorted(set(markets), key=lambda item: (item.market_type.value, item.symbol)))
