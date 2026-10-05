from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import ConfigDict

from ai_spot_trader.agent.radar_context import FrozenRadarContextDecisionProvider
from ai_spot_trader.core.clock import Clock
from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import (
    ExecutionCostContext,
    ExecutableMarket,
    MarketSelectionInput,
    PortfolioState,
    TradingStyleContext,
)
from ai_spot_trader.domain.planning import DEFAULT_MAX_DECISIONS_PER_CYCLE
from ai_spot_trader.domain.ports import Broker, ExecutableMarketDataSource, MultiMarketLLMProvider
from ai_spot_trader.domain.radar_context import RadarAnalyticsStrategicContext
from ai_spot_trader.market.discovery import (
    MarketDiscoveryAudit,
    MarketDiscoveryCoordinator,
    MarketDiscoveryResult,
    RadarShortlistReader,
)
from ai_spot_trader.market.radar_agent_context import build_radar_analytics_strategic_context
from ai_spot_trader.risk.capacity import (
    CapacityAssessment,
    CapacityEvaluator,
    open_position_markets,
)
from ai_spot_trader.risk.engine import RiskEngine
from ai_spot_trader.trading.engine import (
    PortfolioSnapshotSource,
    TradingCycleFailure,
    TradingCycleResult,
    TradingCycleStage,
    TradingCycleStatus,
    TradingCycleTimeouts,
)
from ai_spot_trader.trading.multi_market import (
    MultiMarketTradingCycleResult,
    MultiMarketTradingCycleRunner,
)

RADAR_FAIL_CLOSED_REASON = "RADAR_UNIVERSE_UNAVAILABLE"

# Backward-compatible monkeypatch/import seam retained while the canonical runtime
# implementation is now the multi-market runner.
TradingCycleRunner = MultiMarketTradingCycleRunner


class RadarContextSnapshotMismatchError(RuntimeError):
    pass


class DiscoveredMarketSelectionInput(MarketSelectionInput):
    """Persisted extension of the canonical selection input with discovery/Radar audit facts."""

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


class _ManagementOnlyCapacityEvaluator:
    """Fail closed for new exposure while still allowing canonical management of open positions."""

    def __init__(self, *, settlement_asset: str, reason: str) -> None:
        self._settlement_asset = settlement_asset
        self._reason = reason

    def evaluate(
        self,
        *,
        portfolio_state: PortfolioState,
        executable_markets: tuple[ExecutableMarket, ...],
    ) -> CapacityAssessment:
        held = set(
            open_position_markets(
                portfolio_state,
                settlement_asset=self._settlement_asset,
            )
        )
        management = tuple(market for market in executable_markets if market in held)
        has_spot = any(market.market_type is MarketType.SPOT for market in executable_markets)
        has_perpetual = any(
            market.market_type is MarketType.PERPETUAL for market in executable_markets
        )
        return CapacityAssessment(
            mode="MANAGEMENT",
            reason=self._reason,
            spot_opening_capacity="UNAVAILABLE" if has_spot else "NOT_APPLICABLE",
            perpetual_opening_capacity=(
                "UNAVAILABLE" if has_perpetual else "NOT_APPLICABLE"
            ),
            management_markets=management,
        )


class DynamicMarketTradingCycleRunner:
    """Resolve an audited universe, then execute one ordered multi-market strategic plan."""

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
        radar_context_reader: RadarShortlistReader | None = None,
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
        self._radar_context_reader = radar_context_reader
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
                if self._discovery_source() == "RADAR_SHORTLIST":
                    return self._failed_without_agent("PortfolioSnapshotUnavailable")
                return await self._run_canonical(
                    effective=_ordered(self._bootstrap_markets + self._discovery.watchlist),
                    portfolio_source=self._portfolio,
                )

            prefetched = _PrefetchedPortfolio(self._portfolio, portfolio)
            existing = open_position_markets(
                portfolio,
                settlement_asset=self._settlement_asset,
            )
            if self._discovery_source() == "RADAR_SHORTLIST":
                return await self._run_radar_cycle(
                    portfolio=portfolio,
                    prefetched=prefetched,
                    existing=existing,
                )

            # Legacy discovery behavior remains unchanged for compatibility.
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

    async def _run_radar_cycle(
        self,
        *,
        portfolio: PortfolioState,
        prefetched: _PrefetchedPortfolio,
        existing: tuple[ExecutableMarket, ...],
    ) -> MultiMarketTradingCycleResult:
        # Resolve the typed Radar shortlist before planning; bootstrap is never a substitute.
        discovery_result = await self._discovery.refresh_if_due(portfolio_state=portfolio)
        radar_failed = discovery_result.audit.status == "FALLBACK"
        if radar_failed:
            if not existing:
                return self._failed_without_agent(
                    discovery_result.audit.error_type or "RadarUniverseUnavailable"
                )
            result = await self._run_canonical(
                effective=_ordered(existing),
                portfolio_source=prefetched,
                capacity_evaluator=_ManagementOnlyCapacityEvaluator(
                    settlement_asset=self._settlement_asset,
                    reason=RADAR_FAIL_CLOSED_REASON,
                ),
            )
            return _attach_discovery_audit(result, discovery_result.audit)

        try:
            radar_context = self._freeze_radar_context(discovery_result)
        except Exception as exc:
            if not existing:
                return self._failed_without_agent(type(exc).__name__)
            result = await self._run_canonical(
                effective=_ordered(existing),
                portfolio_source=prefetched,
                capacity_evaluator=_ManagementOnlyCapacityEvaluator(
                    settlement_asset=self._settlement_asset,
                    reason=RADAR_FAIL_CLOSED_REASON,
                ),
            )
            return _attach_discovery_audit(result, discovery_result.audit)

        effective = _ordered(discovery_result.watchlist + existing)
        if not effective:
            return self._failed_without_agent("EmptyDynamicUniverse")

        try:
            self._capacity_evaluator.evaluate(
                portfolio_state=portfolio,
                executable_markets=effective,
            )
        except Exception:
            if not existing:
                return self._failed_without_agent("CapacityEvaluationUnavailable")
            result = await self._run_canonical(
                effective=_ordered(existing),
                portfolio_source=prefetched,
                capacity_evaluator=_ManagementOnlyCapacityEvaluator(
                    settlement_asset=self._settlement_asset,
                    reason=RADAR_FAIL_CLOSED_REASON,
                ),
            )
            return _attach_discovery_audit(result, discovery_result.audit)

        result = await self._run_canonical(
            effective=effective,
            portfolio_source=prefetched,
            radar_context=radar_context,
        )
        return _attach_discovery_audit(result, discovery_result.audit)

    def _freeze_radar_context(
        self,
        discovery_result: MarketDiscoveryResult,
    ) -> RadarAnalyticsStrategicContext | None:
        reader = self._radar_context_reader
        if reader is None:
            return None
        expected = discovery_result.audit.radar_observed_at
        if expected is None:
            raise RadarContextSnapshotMismatchError(
                "Radar discovery did not expose a snapshot boundary"
            )
        overview = reader.latest
        actual = overview.observed_at
        if actual.tzinfo is None or actual.utcoffset() is None:
            raise RadarContextSnapshotMismatchError(
                "Radar context snapshot timestamp must be timezone-aware"
            )
        if actual.astimezone(UTC) != expected.astimezone(UTC):
            raise RadarContextSnapshotMismatchError(
                "Radar context snapshot changed after discovery"
            )
        return build_radar_analytics_strategic_context(
            overview,
            markets=discovery_result.watchlist,
        )

    async def _run_canonical(
        self,
        *,
        effective: tuple[ExecutableMarket, ...],
        portfolio_source: PortfolioSnapshotSource,
        capacity_evaluator: CapacityEvaluator | _ManagementOnlyCapacityEvaluator | None = None,
        radar_context: RadarAnalyticsStrategicContext | None = None,
    ) -> MultiMarketTradingCycleResult:
        agent: MultiMarketLLMProvider = self._agent
        if radar_context is not None:
            agent = FrozenRadarContextDecisionProvider(agent, radar_context)
        runner_kwargs: dict[str, object] = {
            "executable_market_data": self._executable_market_data,
            "executable_markets": effective,
            "capacity_evaluator": capacity_evaluator or self._capacity_evaluator,
            "portfolio": portfolio_source,
            "agent": agent,
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

    def _discovery_source(self) -> str:
        return str(getattr(self._discovery, "source", "LEGACY_AGENT"))

    def _failed_without_agent(self, error_type: str) -> MultiMarketTradingCycleResult:
        cycle_id = self._cycle_id_factory() if self._cycle_id_factory is not None else uuid4()
        return MultiMarketTradingCycleResult(
            cycle_id=cycle_id,
            status=TradingCycleStatus.FAILED,
            failure=TradingCycleFailure(
                stage=TradingCycleStage.SELECTION_INPUT,
                error_type=error_type,
            ),
        )


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
