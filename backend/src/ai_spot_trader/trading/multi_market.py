from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID, uuid4

from ai_spot_trader.core.clock import Clock, SystemClock
from ai_spot_trader.domain.enums import RiskDecision, TradingAction
from ai_spot_trader.domain.experiments import aggressiveness_context
from ai_spot_trader.domain.models import (
    AgentToolTrace,
    DecisionCandidate,
    ExecutableMarket,
    ExecutionCostContext,
    ExecutionIntent,
    Fill,
    MarketSelectionInput,
    MarketState,
    PortfolioState,
    RiskAssessment,
    TradingStyleContext,
)
from ai_spot_trader.domain.planning import (
    MAX_DECISIONS_PER_CYCLE_HARD_LIMIT,
    CycleDecisionPlan,
    CycleDecisionPlanInput,
)
from ai_spot_trader.domain.ports import Broker, ExecutableMarketDataSource, MultiMarketLLMProvider
from ai_spot_trader.risk.capacity import CapacityAssessment, CapacityEvaluator
from ai_spot_trader.risk.engine import RiskEngine, RiskResult
from ai_spot_trader.trading.engine import (
    AgentToolTraceSource,
    PortfolioSnapshotSource,
    TradingCycleFailure,
    TradingCycleInvariantError,
    TradingCycleStage,
    TradingCycleStatus,
    TradingCycleTimeouts,
)

CycleIdFactory = Callable[[], UUID]


@dataclass(frozen=True, slots=True)
class DecisionExecutionResult:
    decision_index: int
    decision: DecisionCandidate
    market_state: MarketState
    portfolio_state_before: PortfolioState
    risk_assessment: RiskAssessment | None = None
    execution_intent: ExecutionIntent | None = None
    fills: tuple[Fill, ...] = ()
    portfolio_state_after: PortfolioState | None = None

    def __post_init__(self) -> None:
        if self.decision_index < 0:
            raise ValueError("decision_index must be non-negative")
        if self.market_state.symbol != self.decision.symbol:
            raise ValueError("DecisionExecutionResult market symbol mismatch")
        if self.market_state.market_type is not self.decision.market_type:
            raise ValueError("DecisionExecutionResult market_type mismatch")
        assessment = self.risk_assessment
        if assessment is not None:
            if assessment.cycle_id != self.decision.cycle_id:
                raise ValueError("DecisionExecutionResult RiskAssessment cycle mismatch")
            if assessment.decision_id != self.decision.decision_id:
                raise ValueError("DecisionExecutionResult RiskAssessment mismatch")
        intent = self.execution_intent
        if intent is not None:
            if assessment is None:
                raise ValueError("ExecutionIntent requires RiskAssessment")
            if intent.cycle_id != self.decision.cycle_id:
                raise ValueError("DecisionExecutionResult ExecutionIntent cycle mismatch")
            if intent.decision_id != self.decision.decision_id:
                raise ValueError("DecisionExecutionResult ExecutionIntent mismatch")
            if intent.risk_assessment_id != assessment.risk_assessment_id:
                raise ValueError("DecisionExecutionResult Risk correlation mismatch")
            if intent.action is not self.decision.action or intent.symbol != self.decision.symbol:
                raise ValueError("DecisionExecutionResult intent changed action or symbol")
            if intent.market_type is not self.decision.market_type:
                raise ValueError("DecisionExecutionResult intent changed market_type")
        if self.fills and intent is None:
            raise ValueError("fills require an ExecutionIntent")
        if intent is not None:
            for fill in self.fills:
                if fill.execution_id != intent.execution_id:
                    raise ValueError("DecisionExecutionResult Fill execution mismatch")
                if fill.market_state_id != self.market_state.market_state_id:
                    raise ValueError("DecisionExecutionResult Fill market mismatch")


@dataclass(frozen=True, slots=True)
class MultiMarketTradingCycleResult:
    """Canonical 1:N cycle result while retaining explicit legacy singleton projections."""

    cycle_id: UUID
    status: TradingCycleStatus
    failure: TradingCycleFailure | None = None
    capacity_assessment: CapacityAssessment | None = None
    market_selection_input: MarketSelectionInput | None = None
    decision_plan_input: CycleDecisionPlanInput | None = None
    decision_plan: CycleDecisionPlan | None = None
    decision_results: tuple[DecisionExecutionResult, ...] = ()
    final_portfolio_state: PortfolioState | None = None
    agent_tool_traces: tuple[AgentToolTrace, ...] = ()

    # Compatibility projection. These fields are intentionally populated only for a true
    # singleton cycle, never by concatenating or inventing values for multi-decision cycles.
    market_selection: None = None
    agent_input: None = None
    decision: DecisionCandidate | None = None
    risk_assessment: RiskAssessment | None = None
    execution_intent: ExecutionIntent | None = None
    fills: tuple[Fill, ...] = ()
    portfolio_state_after: PortfolioState | None = None

    def __post_init__(self) -> None:
        if self.status is TradingCycleStatus.FAILED:
            if self.failure is None:
                raise ValueError("FAILED cycle results require failure metadata")
        elif self.failure is not None:
            raise ValueError("COMPLETED cycles cannot carry failure metadata")
        call_ids = tuple(trace.call_id for trace in self.agent_tool_traces)
        if len(set(call_ids)) != len(call_ids):
            raise ValueError("cycle Agent tool traces must have unique call_id values")
        if (
            self.capacity_assessment is not None
            and self.capacity_assessment.mode == "MANAGEMENT"
            and self.agent_tool_traces
        ):
            raise ValueError("MANAGEMENT cycles cannot carry new-opening research tool traces")
        if self.decision_plan is not None and self.decision_plan.tool_traces != self.agent_tool_traces:
            raise ValueError("cycle Agent tool traces must match CycleDecisionPlan traces")
        if self.decision_plan is not None and self.decision_plan.cycle_id != self.cycle_id:
            raise ValueError("CycleDecisionPlan cycle_id mismatch")
        if self.decision_plan_input is not None and self.decision_plan_input.cycle_id != self.cycle_id:
            raise ValueError("CycleDecisionPlanInput cycle_id mismatch")
        indexes = tuple(item.decision_index for item in self.decision_results)
        if indexes != tuple(range(len(indexes))):
            raise ValueError("decision_results must preserve contiguous strategic order")
        ids = tuple(item.decision.decision_id for item in self.decision_results)
        if len(set(ids)) != len(ids):
            raise ValueError("decision_results must have unique decision_id values")
        if self.decision_plan is not None:
            planned = tuple(item.decision_id for item in self.decision_plan.decisions)
            actual = ids
            if actual != planned[: len(actual)]:
                raise ValueError("decision_results must be a prefix of the strategic plan")
        if self.status is TradingCycleStatus.COMPLETED:
            if self.decision_plan is None or not self.decision_results:
                raise ValueError("COMPLETED multi-market cycles require a decision plan")
            if len(self.decision_results) != len(self.decision_plan.decisions):
                raise ValueError("COMPLETED cycles must contain every planned decision result")
            if self.final_portfolio_state is None:
                raise ValueError("COMPLETED cycles require final_portfolio_state")
        if len(self.decision_results) == 1:
            item = self.decision_results[0]
            if self.decision is not None and self.decision != item.decision:
                raise ValueError("singleton decision projection mismatch")
        elif any(
            value is not None
            for value in (self.decision, self.risk_assessment, self.execution_intent)
        ) or self.fills:
            raise ValueError("multi-decision cycles cannot expose misleading singleton projections")


class MultiMarketTradingCycleRunner:
    """Execute one bounded ordered strategic plan with sequential Risk/PAPER mutations."""

    def __init__(
        self,
        *,
        portfolio: PortfolioSnapshotSource,
        agent: MultiMarketLLMProvider,
        risk_engine: RiskEngine,
        broker: Broker,
        aggressiveness: int,
        max_decisions_per_cycle: int,
        timeouts: TradingCycleTimeouts,
        executable_market_data: ExecutableMarketDataSource,
        executable_markets: tuple[ExecutableMarket, ...],
        capacity_evaluator: CapacityEvaluator | None = None,
        trading_style_context: TradingStyleContext | None = None,
        execution_cost_context: ExecutionCostContext | None = None,
        clock: Clock | None = None,
        cycle_id_factory: CycleIdFactory = uuid4,
    ) -> None:
        if not executable_markets:
            raise ValueError("multi-market runner requires executable_markets")
        ordered = tuple(sorted(executable_markets, key=lambda item: (item.market_type.value, item.symbol)))
        if ordered != executable_markets or len(set(executable_markets)) != len(executable_markets):
            raise ValueError("executable_markets must be unique and deterministically sorted")
        if not 1 <= max_decisions_per_cycle <= MAX_DECISIONS_PER_CYCLE_HARD_LIMIT:
            raise ValueError(
                "max_decisions_per_cycle must be between 1 and "
                f"{MAX_DECISIONS_PER_CYCLE_HARD_LIMIT}"
            )
        if (trading_style_context is None) != (execution_cost_context is None):
            raise ValueError("trading_style_context and execution_cost_context must be supplied together")
        if not isinstance(agent, MultiMarketLLMProvider):
            raise TypeError("multi-market runner requires generate_decision_plan on the same Agent")
        self._portfolio = portfolio
        self._agent = agent
        self._risk_engine = risk_engine
        self._broker = broker
        self._aggressiveness = aggressiveness
        self._aggressiveness_context = aggressiveness_context(aggressiveness)
        self._max_decisions_per_cycle = max_decisions_per_cycle
        self._timeouts = timeouts
        self._market_data = executable_market_data
        self._markets = executable_markets
        self._capacity_evaluator = capacity_evaluator
        self._trading_style_context = trading_style_context
        self._execution_cost_context = execution_cost_context
        self._clock = clock or SystemClock()
        self._cycle_id_factory = cycle_id_factory
        self._cycle_lock = asyncio.Lock()

    async def run_cycle(self) -> MultiMarketTradingCycleResult:
        async with self._cycle_lock:
            return await self._run_locked()

    async def _run_locked(self) -> MultiMarketTradingCycleResult:
        cycle_id = self._cycle_id_factory()
        capacity: CapacityAssessment | None = None
        try:
            initial_portfolio = self._portfolio.snapshot()
        except Exception as exc:
            return self._failed(cycle_id, TradingCycleStage.PORTFOLIO, exc)

        try:
            if self._capacity_evaluator is not None:
                capacity = self._capacity_evaluator.evaluate(
                    portfolio_state=initial_portfolio,
                    executable_markets=self._markets,
                )
            active_markets = (
                capacity.management_markets
                if capacity is not None and capacity.mode == "MANAGEMENT"
                else self._markets
            )
            if not active_markets:
                raise TradingCycleInvariantError("cycle has no causal market available for planning")
            selection_input = MarketSelectionInput(
                cycle_id=cycle_id,
                created_at=self._now(),
                portfolio_state=initial_portfolio,
                executable_markets=active_markets,
                aggressiveness=self._aggressiveness,
                aggressiveness_context=self._aggressiveness_context,
                trading_style_context=self._trading_style_context,
                execution_cost_context=self._execution_cost_context,
            )
        except Exception as exc:
            return self._failed(
                cycle_id,
                TradingCycleStage.SELECTION_INPUT,
                exc,
                capacity_assessment=capacity,
            )

        try:
            states: list[MarketState] = []
            for market in active_markets:
                # Preserve the historical timeout meaning per market acquisition. A larger
                # bounded plan must not accidentally divide one single-market I/O budget among
                # every causal market snapshot.
                async with asyncio.timeout(self._timeouts.market_seconds):
                    state = await self._market_data.snapshot(market.symbol, market.market_type)
                self._validate_market_state(market, state)
                states.append(state)
        except Exception as exc:
            return self._failed(
                cycle_id,
                TradingCycleStage.MARKET,
                exc,
                capacity_assessment=capacity,
                market_selection_input=selection_input,
            )

        try:
            plan_input = CycleDecisionPlanInput(
                cycle_id=cycle_id,
                created_at=self._now(),
                portfolio_state=initial_portfolio,
                market_states=tuple(states),
                aggressiveness=self._aggressiveness,
                aggressiveness_context=self._aggressiveness_context,
                trading_style_context=self._trading_style_context,
                execution_cost_context=self._execution_cost_context,
                max_decisions_per_cycle=self._max_decisions_per_cycle,
                management_mode=capacity is not None and capacity.mode == "MANAGEMENT",
                capacity_reason=(capacity.reason if capacity is not None and capacity.mode == "MANAGEMENT" else None),
            )
            async with asyncio.timeout(self._timeouts.agent_seconds):
                plan = await self._agent.generate_decision_plan(plan_input)
            self._validate_plan(plan_input, plan)
        except Exception as exc:
            return self._failed(
                cycle_id,
                TradingCycleStage.AGENT,
                exc,
                capacity_assessment=capacity,
                market_selection_input=selection_input,
                decision_plan_input=locals().get("plan_input"),
                agent_tool_traces=self._agent_tool_traces(),
            )

        market_by_key = {(item.symbol, item.market_type): item for item in states}
        decision_results: list[DecisionExecutionResult] = []

        for index, decision in enumerate(plan.decisions):
            market_state = market_by_key[(decision.symbol, decision.market_type)]
            try:
                portfolio_before = self._portfolio.snapshot()
                risk_result = self._risk_engine.evaluate(
                    decision=decision,
                    market_state=market_state,
                    portfolio_state=portfolio_before,
                    management_mode=capacity is not None and capacity.mode == "MANAGEMENT",
                )
                self._validate_risk_result(decision, risk_result)
            except Exception as exc:
                return self._failed(
                    cycle_id,
                    TradingCycleStage.RISK,
                    exc,
                    capacity_assessment=capacity,
                    market_selection_input=selection_input,
                    decision_plan_input=plan_input,
                    decision_plan=plan,
                    decision_results=tuple(decision_results),
                    agent_tool_traces=plan.tool_traces,
                )

            assessment = risk_result.assessment
            intent = risk_result.execution_intent
            if intent is None:
                decision_results.append(
                    DecisionExecutionResult(
                        decision_index=index,
                        decision=decision,
                        market_state=market_state,
                        portfolio_state_before=portfolio_before,
                        risk_assessment=assessment,
                        portfolio_state_after=portfolio_before,
                    )
                )
                continue

            try:
                async with asyncio.timeout(self._timeouts.broker_seconds):
                    fills = await self._broker.execute(intent, market_state)
                self._validate_fills(intent, market_state, fills)
            except Exception as exc:
                partial = DecisionExecutionResult(
                    decision_index=index,
                    decision=decision,
                    market_state=market_state,
                    portfolio_state_before=portfolio_before,
                    risk_assessment=assessment,
                    execution_intent=intent,
                )
                return self._failed(
                    cycle_id,
                    TradingCycleStage.BROKER,
                    exc,
                    capacity_assessment=capacity,
                    market_selection_input=selection_input,
                    decision_plan_input=plan_input,
                    decision_plan=plan,
                    decision_results=tuple((*decision_results, partial)),
                    agent_tool_traces=plan.tool_traces,
                )

            try:
                portfolio_after = self._portfolio.snapshot(as_of=self._now())
            except Exception as exc:
                partial = DecisionExecutionResult(
                    decision_index=index,
                    decision=decision,
                    market_state=market_state,
                    portfolio_state_before=portfolio_before,
                    risk_assessment=assessment,
                    execution_intent=intent,
                    fills=fills,
                )
                return self._failed(
                    cycle_id,
                    TradingCycleStage.POST_PORTFOLIO,
                    exc,
                    capacity_assessment=capacity,
                    market_selection_input=selection_input,
                    decision_plan_input=plan_input,
                    decision_plan=plan,
                    decision_results=tuple((*decision_results, partial)),
                    agent_tool_traces=plan.tool_traces,
                )

            decision_results.append(
                DecisionExecutionResult(
                    decision_index=index,
                    decision=decision,
                    market_state=market_state,
                    portfolio_state_before=portfolio_before,
                    risk_assessment=assessment,
                    execution_intent=intent,
                    fills=fills,
                    portfolio_state_after=portfolio_after,
                )
            )

        try:
            final_portfolio = self._portfolio.snapshot(as_of=self._now())
        except Exception as exc:
            return self._failed(
                cycle_id,
                TradingCycleStage.POST_PORTFOLIO,
                exc,
                capacity_assessment=capacity,
                market_selection_input=selection_input,
                decision_plan_input=plan_input,
                decision_plan=plan,
                decision_results=tuple(decision_results),
                agent_tool_traces=plan.tool_traces,
            )

        return self._completed(
            cycle_id=cycle_id,
            capacity=capacity,
            selection_input=selection_input,
            plan_input=plan_input,
            plan=plan,
            decision_results=tuple(decision_results),
            final_portfolio=final_portfolio,
        )

    def _completed(
        self,
        *,
        cycle_id: UUID,
        capacity: CapacityAssessment | None,
        selection_input: MarketSelectionInput,
        plan_input: CycleDecisionPlanInput,
        plan: CycleDecisionPlan,
        decision_results: tuple[DecisionExecutionResult, ...],
        final_portfolio: PortfolioState,
    ) -> MultiMarketTradingCycleResult:
        legacy = decision_results[0] if len(decision_results) == 1 else None
        return MultiMarketTradingCycleResult(
            cycle_id=cycle_id,
            status=TradingCycleStatus.COMPLETED,
            capacity_assessment=capacity,
            market_selection_input=selection_input,
            decision_plan_input=plan_input,
            decision_plan=plan,
            decision_results=decision_results,
            final_portfolio_state=final_portfolio,
            agent_tool_traces=plan.tool_traces,
            decision=legacy.decision if legacy else None,
            risk_assessment=legacy.risk_assessment if legacy else None,
            execution_intent=legacy.execution_intent if legacy else None,
            fills=legacy.fills if legacy else (),
            portfolio_state_after=final_portfolio,
        )

    def _failed(
        self,
        cycle_id: UUID,
        stage: TradingCycleStage,
        exc: Exception,
        *,
        capacity_assessment: CapacityAssessment | None = None,
        market_selection_input: MarketSelectionInput | None = None,
        decision_plan_input: CycleDecisionPlanInput | None = None,
        decision_plan: CycleDecisionPlan | None = None,
        decision_results: tuple[DecisionExecutionResult, ...] = (),
        agent_tool_traces: tuple[AgentToolTrace, ...] = (),
    ) -> MultiMarketTradingCycleResult:
        legacy = decision_results[0] if len(decision_results) == 1 else None
        return MultiMarketTradingCycleResult(
            cycle_id=cycle_id,
            status=TradingCycleStatus.FAILED,
            failure=TradingCycleFailure(
                stage=stage,
                error_type=type(exc).__name__,
                timed_out=isinstance(exc, TimeoutError),
            ),
            capacity_assessment=capacity_assessment,
            market_selection_input=market_selection_input,
            decision_plan_input=decision_plan_input,
            decision_plan=decision_plan,
            decision_results=decision_results,
            agent_tool_traces=agent_tool_traces,
            decision=legacy.decision if legacy else None,
            risk_assessment=legacy.risk_assessment if legacy else None,
            execution_intent=legacy.execution_intent if legacy else None,
            fills=legacy.fills if legacy else (),
        )

    def _validate_plan(self, plan_input: CycleDecisionPlanInput, plan: CycleDecisionPlan) -> None:
        if plan.cycle_id != plan_input.cycle_id:
            raise TradingCycleInvariantError("CycleDecisionPlan cycle_id mismatch")
        if plan.created_at < plan_input.created_at:
            raise TradingCycleInvariantError("CycleDecisionPlan predates CycleDecisionPlanInput")
        if len(plan.decisions) > plan_input.max_decisions_per_cycle:
            raise TradingCycleInvariantError("CycleDecisionPlan exceeds max_decisions_per_cycle")
        allowed = {(item.symbol, item.market_type) for item in plan_input.market_states}
        seen: set[tuple[str, object]] = set()
        for decision in plan.decisions:
            key = (decision.symbol, decision.market_type)
            if key not in allowed:
                raise TradingCycleInvariantError("decision is outside the causal market universe")
            if key in seen:
                raise TradingCycleInvariantError("duplicate market in CycleDecisionPlan")
            seen.add(key)

    @staticmethod
    def _validate_market_state(market: ExecutableMarket, state: MarketState) -> None:
        if state.symbol != market.symbol or state.market_type is not market.market_type:
            raise TradingCycleInvariantError("MarketState does not match requested executable market")

    @staticmethod
    def _validate_risk_result(decision: DecisionCandidate, result: RiskResult) -> None:
        assessment = result.assessment
        intent = result.execution_intent
        if assessment.cycle_id != decision.cycle_id:
            raise TradingCycleInvariantError("RiskAssessment cycle_id mismatch")
        if assessment.decision_id != decision.decision_id:
            raise TradingCycleInvariantError("RiskAssessment decision_id mismatch")
        if assessment.assessed_at < decision.created_at:
            raise TradingCycleInvariantError("RiskAssessment predates DecisionCandidate")
        if decision.action is TradingAction.HOLD:
            if assessment.status is not RiskDecision.ALLOW or intent is not None:
                raise TradingCycleInvariantError("HOLD must be ALLOW without execution intent")
            return
        if assessment.status is RiskDecision.REJECT:
            if intent is not None:
                raise TradingCycleInvariantError("REJECT cannot create an ExecutionIntent")
            return
        if intent is None:
            raise TradingCycleInvariantError("executable Risk outcome requires an ExecutionIntent")
        if intent.cycle_id != decision.cycle_id or intent.decision_id != decision.decision_id:
            raise TradingCycleInvariantError("ExecutionIntent correlation mismatch")
        if intent.risk_assessment_id != assessment.risk_assessment_id:
            raise TradingCycleInvariantError("ExecutionIntent RiskAssessment mismatch")
        if intent.created_at != assessment.assessed_at:
            raise TradingCycleInvariantError("ExecutionIntent timestamp must equal assessed_at")
        if intent.action is not decision.action or intent.symbol != decision.symbol:
            raise TradingCycleInvariantError("Risk cannot change action or symbol")
        if intent.market_type is not decision.market_type:
            raise TradingCycleInvariantError("Risk cannot change market_type")
        if intent.quantity != assessment.authorized_quantity:
            raise TradingCycleInvariantError("ExecutionIntent quantity must be Risk-authorized")

    @staticmethod
    def _validate_fills(
        intent: ExecutionIntent,
        market_state: MarketState,
        fills: tuple[Fill, ...],
    ) -> None:
        if not fills:
            raise TradingCycleInvariantError("successful broker execution returned no fills")
        quantity = sum((item.quantity for item in fills), start=intent.quantity * 0)
        if quantity != intent.quantity:
            raise TradingCycleInvariantError("fill quantities must equal the Risk-authorized intent")
        for fill in fills:
            if fill.execution_id != intent.execution_id:
                raise TradingCycleInvariantError("Fill execution_id mismatch")
            if fill.market_state_id != market_state.market_state_id:
                raise TradingCycleInvariantError("Fill MarketState mismatch")
            if fill.pricing_as_of != market_state.as_of:
                raise TradingCycleInvariantError("Fill pricing timestamp mismatch")
            if fill.reference_price != market_state.last_price:
                raise TradingCycleInvariantError("Fill reference price mismatch")
            if fill.symbol != intent.symbol or fill.action is not intent.action:
                raise TradingCycleInvariantError("Fill action or symbol mismatch")
            if fill.market_type is not intent.market_type:
                raise TradingCycleInvariantError("Fill market_type mismatch")
            if fill.filled_at < market_state.as_of:
                raise TradingCycleInvariantError("Fill predates MarketState")

    def _agent_tool_traces(self) -> tuple[AgentToolTrace, ...]:
        if not isinstance(self._agent, AgentToolTraceSource):
            return ()
        return self._agent.last_tool_traces

    def _now(self):
        value = self._clock.now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise TradingCycleInvariantError("trading cycle clock must be timezone-aware")
        return value


__all__ = [
    "DecisionExecutionResult",
    "MultiMarketLLMProvider",
    "MultiMarketTradingCycleResult",
    "MultiMarketTradingCycleRunner",
]
