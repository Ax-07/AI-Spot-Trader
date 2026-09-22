import asyncio
import math
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import UUID, uuid4

from ai_spot_trader.core.clock import Clock, SystemClock
from ai_spot_trader.domain.enums import RiskDecision, TradingAction
from ai_spot_trader.domain.experiments import (
    aggressiveness_context,
    validate_experiment_manifest_digest,
)
from ai_spot_trader.domain.models import (
    AgentInput,
    AgentToolTrace,
    DecisionCandidate,
    ExecutableMarket,
    ExecutionIntent,
    ExperimentManifest,
    Fill,
    MarketSelection,
    MarketSelectionInput,
    MarketState,
    PortfolioState,
    RiskAssessment,
)
from ai_spot_trader.domain.ports import (
    Broker,
    ExecutableMarketDataSource,
    LLMProvider,
    MarketDataSource,
    MarketSelectingLLMProvider,
)
from ai_spot_trader.domain.symbols import parse_canonical_symbol
from ai_spot_trader.portfolio.ledger import PaperPortfolioLedger
from ai_spot_trader.risk.engine import RiskEngine, RiskResult

CycleIdFactory = Callable[[], UUID]


@runtime_checkable
class AgentToolTraceSource(Protocol):
    """Optional Agent surface exposing completed read-only research from its latest call."""

    @property
    def last_tool_traces(self) -> tuple[AgentToolTrace, ...]: ...


class TradingCycleStatus(StrEnum):
    """Technical completion state for one orchestration cycle."""

    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TradingCycleStage(StrEnum):
    """Stage at which a technical cycle failure occurred."""

    MARKET = "MARKET"
    PORTFOLIO = "PORTFOLIO"
    SELECTION_INPUT = "SELECTION_INPUT"
    MARKET_SELECTION = "MARKET_SELECTION"
    INPUT = "INPUT"
    AGENT = "AGENT"
    RISK = "RISK"
    BROKER = "BROKER"
    POST_PORTFOLIO = "POST_PORTFOLIO"


@dataclass(frozen=True, slots=True)
class TradingCycleTimeouts:
    """Explicit I/O bounds for one trading cycle; no product defaults are implied."""

    market_seconds: float
    agent_seconds: float
    broker_seconds: float

    def __post_init__(self) -> None:
        for name, value in (
            ("market_seconds", self.market_seconds),
            ("agent_seconds", self.agent_seconds),
            ("broker_seconds", self.broker_seconds),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a positive finite number")
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a positive finite number")


@dataclass(frozen=True, slots=True)
class TradingCycleFailure:
    """Sanitized technical failure metadata safe to keep in memory."""

    stage: TradingCycleStage
    error_type: str
    timed_out: bool = False


@dataclass(frozen=True, slots=True)
class TradingCycleResult:
    """Internal orchestration result preserving canonical causal business artefacts."""

    cycle_id: UUID
    status: TradingCycleStatus
    failure: TradingCycleFailure | None = None
    market_selection_input: MarketSelectionInput | None = None
    market_selection: MarketSelection | None = None
    agent_input: AgentInput | None = None
    decision: DecisionCandidate | None = None
    risk_assessment: RiskAssessment | None = None
    execution_intent: ExecutionIntent | None = None
    fills: tuple[Fill, ...] = ()
    portfolio_state_after: PortfolioState | None = None
    agent_tool_traces: tuple[AgentToolTrace, ...] = ()

    def __post_init__(self) -> None:
        call_ids = tuple(trace.call_id for trace in self.agent_tool_traces)
        if len(set(call_ids)) != len(call_ids):
            raise ValueError("cycle Agent tool traces must have unique call_id values")
        if self.market_selection is not None:
            if self.market_selection.cycle_id != self.cycle_id:
                raise ValueError("MarketSelection cycle_id must match TradingCycleResult")
            if self.market_selection.tool_traces != self.agent_tool_traces:
                raise ValueError("cycle Agent tool traces must match MarketSelection traces")
        if (
            self.market_selection_input is not None
            and self.market_selection_input.cycle_id != self.cycle_id
        ):
            raise ValueError("MarketSelectionInput cycle_id must match TradingCycleResult")
        if self.market_selection is not None and self.market_selection_input is None:
            raise ValueError("MarketSelection requires its causal MarketSelectionInput")
        if self.decision is not None and self.decision.tool_traces != self.agent_tool_traces:
            raise ValueError("cycle Agent tool traces must match DecisionCandidate traces")
        if (
            self.agent_input is not None
            and self.market_selection is not None
            and self.agent_input.market_selection != self.market_selection
        ):
            raise ValueError("AgentInput must reference the cycle MarketSelection")
        if self.status is TradingCycleStatus.FAILED:
            if self.failure is None:
                raise ValueError("FAILED cycle results require failure metadata")
            return
        if self.failure is not None:
            raise ValueError("COMPLETED cycles cannot carry failure metadata")
        if self.agent_input is None or self.decision is None or self.risk_assessment is None:
            raise ValueError("COMPLETED cycles require AgentInput, decision and RiskAssessment")
        if self.execution_intent is None:
            if self.fills or self.portfolio_state_after is not None:
                raise ValueError("non-executed cycles cannot carry fills or a post-trade snapshot")
            return
        if not self.fills or self.portfolio_state_after is None:
            raise ValueError("executed cycles require fills and a post-trade portfolio snapshot")


class TradingCycleInvariantError(RuntimeError):
    """A canonical component returned artefacts inconsistent with this cycle."""


class TradingEngineAlreadyRunningError(RuntimeError):
    """Raised when start() would create a second autonomous loop."""


class TradingCycleRunner:
    """Execute one serialized PAPER cycle, in legacy or causal market-selection mode."""

    def __init__(
        self,
        *,
        portfolio: PaperPortfolioLedger,
        agent: LLMProvider,
        risk_engine: RiskEngine,
        broker: Broker,
        aggressiveness: int,
        timeouts: TradingCycleTimeouts,
        market_data: MarketDataSource | None = None,
        symbol: str | None = None,
        executable_market_data: ExecutableMarketDataSource | None = None,
        executable_markets: tuple[ExecutableMarket, ...] | None = None,
        experiment_manifest: ExperimentManifest | None = None,
        clock: Clock | None = None,
        cycle_id_factory: CycleIdFactory = uuid4,
    ) -> None:
        legacy_mode = market_data is not None or symbol is not None
        selection_mode = executable_market_data is not None or executable_markets is not None
        if legacy_mode == selection_mode:
            raise ValueError(
                "configure exactly one runner mode: legacy symbol or executable market selection"
            )
        if legacy_mode:
            if market_data is None or symbol is None:
                raise ValueError("legacy mode requires market_data and symbol")
            parse_canonical_symbol(symbol)
        else:
            if executable_market_data is None or not executable_markets:
                raise ValueError(
                    "selection mode requires executable_market_data and executable_markets"
                )
            ordered = tuple(
                sorted(
                    executable_markets,
                    key=lambda market: (market.market_type.value, market.symbol),
                )
            )
            if ordered != executable_markets:
                raise ValueError("executable_markets must use deterministic sorted order")
            if len(set(executable_markets)) != len(executable_markets):
                raise ValueError("executable_markets must be unique")
            if not isinstance(agent, MarketSelectingLLMProvider):
                raise TypeError("selection mode requires the same Agent to implement select_market")

        context = aggressiveness_context(aggressiveness)
        if experiment_manifest is not None:
            validate_experiment_manifest_digest(experiment_manifest)
            if experiment_manifest.aggressiveness != context:
                raise ValueError(
                    "experiment manifest aggressiveness must match the runner configuration"
                )
            if experiment_manifest.agent_protocol is not None:
                if legacy_mode:
                    raise ValueError(
                        "multi-market experiment manifests require executable market selection mode"
                    )
                if experiment_manifest.agent_protocol.executable_markets != executable_markets:
                    raise ValueError(
                        "runner executable markets must match the typed experiment universe"
                    )
            else:
                required_symbols = (
                    {symbol}
                    if symbol is not None
                    else {item.symbol for item in executable_markets or ()}
                )
                if not required_symbols.issubset(set(experiment_manifest.universe)):
                    raise ValueError("runner markets must belong to the experiment universe")

        self._market_data = market_data
        self._symbol = symbol
        self._executable_market_data = executable_market_data
        self._executable_markets = executable_markets or ()
        self._portfolio = portfolio
        self._agent = agent
        self._risk_engine = risk_engine
        self._broker = broker
        self._aggressiveness = aggressiveness
        self._aggressiveness_context = context
        self._experiment_manifest = experiment_manifest
        self._timeouts = timeouts
        self._clock = clock or SystemClock()
        self._cycle_id_factory = cycle_id_factory
        self._cycle_lock = asyncio.Lock()

    async def run_cycle(self) -> TradingCycleResult:
        """Run one cycle; technical step failures are returned, never converted to HOLD."""

        async with self._cycle_lock:
            if self._executable_market_data is not None:
                return await self._run_selected_cycle_locked()
            return await self._run_legacy_cycle_locked()

    async def _run_selected_cycle_locked(self) -> TradingCycleResult:
        cycle_id = self._cycle_id_factory()

        try:
            selection_portfolio = self._portfolio.snapshot()
        except Exception as exc:
            return self._failed(cycle_id, TradingCycleStage.PORTFOLIO, exc)

        try:
            selection_created_at = self._now()
            selection_input = MarketSelectionInput(
                cycle_id=cycle_id,
                created_at=selection_created_at,
                portfolio_state=selection_portfolio,
                executable_markets=self._executable_markets,
                aggressiveness=self._aggressiveness,
                aggressiveness_context=self._aggressiveness_context,
                experiment_manifest=self._experiment_manifest,
            )
        except Exception as exc:
            return self._failed(cycle_id, TradingCycleStage.SELECTION_INPUT, exc)

        try:
            selecting_agent = self._agent
            assert isinstance(selecting_agent, MarketSelectingLLMProvider)
            async with asyncio.timeout(self._timeouts.agent_seconds):
                market_selection = await selecting_agent.select_market(selection_input)
            self._validate_market_selection(
                selection_input=selection_input,
                selection=market_selection,
            )
        except Exception as exc:
            return self._failed(
                cycle_id,
                TradingCycleStage.MARKET_SELECTION,
                exc,
                market_selection_input=selection_input,
                agent_tool_traces=self._agent_tool_traces(),
            )

        try:
            execution_source = self._executable_market_data
            assert execution_source is not None
            async with asyncio.timeout(self._timeouts.market_seconds):
                market_state = await execution_source.snapshot(
                    market_selection.symbol,
                    market_selection.market_type,
                )
            self._validate_selected_market_state(
                selection=market_selection,
                market_state=market_state,
            )
        except Exception as exc:
            return self._failed(
                cycle_id,
                TradingCycleStage.MARKET,
                exc,
                market_selection_input=selection_input,
                market_selection=market_selection,
                agent_tool_traces=market_selection.tool_traces,
            )

        # The selected Derivatives execution source is allowed to mark an already-open
        # position/funding. Capture the complete portfolio only after this canonical market
        # acquisition. Research sources remain side-effect free and cannot reach this ledger.
        try:
            portfolio_state = self._portfolio.snapshot()
        except Exception as exc:
            return self._failed(
                cycle_id,
                TradingCycleStage.PORTFOLIO,
                exc,
                market_selection_input=selection_input,
                market_selection=market_selection,
                agent_tool_traces=market_selection.tool_traces,
            )

        try:
            created_at = self._now()
            if market_state.as_of > created_at:
                raise TradingCycleInvariantError(
                    "MarketState cannot be newer than AgentInput.created_at"
                )
            if portfolio_state.as_of > created_at:
                raise TradingCycleInvariantError(
                    "PortfolioState cannot be newer than AgentInput.created_at"
                )
            if market_selection.selected_at > created_at:
                raise TradingCycleInvariantError(
                    "MarketSelection cannot be newer than AgentInput.created_at"
                )
            agent_input = AgentInput(
                cycle_id=cycle_id,
                created_at=created_at,
                market_state=market_state,
                portfolio_state=portfolio_state,
                aggressiveness=self._aggressiveness,
                aggressiveness_context=self._aggressiveness_context,
                experiment_manifest=self._experiment_manifest,
                market_selection=market_selection,
            )
            market_state = agent_input.market_state
            portfolio_state = agent_input.portfolio_state
        except Exception as exc:
            return self._failed(
                cycle_id,
                TradingCycleStage.INPUT,
                exc,
                market_selection_input=selection_input,
                market_selection=market_selection,
                agent_tool_traces=market_selection.tool_traces,
            )

        return await self._finish_cycle(
            cycle_id=cycle_id,
            agent_input=agent_input,
            market_state=market_state,
            portfolio_state=portfolio_state,
            market_selection_input=selection_input,
            market_selection=market_selection,
        )

    async def _run_legacy_cycle_locked(self) -> TradingCycleResult:
        cycle_id = self._cycle_id_factory()
        market_source = self._market_data
        symbol = self._symbol
        assert market_source is not None and symbol is not None

        try:
            async with asyncio.timeout(self._timeouts.market_seconds):
                market_state = await market_source.snapshot(symbol)
        except Exception as exc:
            return self._failed(cycle_id, TradingCycleStage.MARKET, exc)

        try:
            portfolio_state = self._portfolio.snapshot()
        except Exception as exc:
            return self._failed(cycle_id, TradingCycleStage.PORTFOLIO, exc)

        try:
            created_at = self._now()
            if market_state.as_of > created_at:
                raise TradingCycleInvariantError(
                    "MarketState cannot be newer than AgentInput.created_at"
                )
            if portfolio_state.as_of > created_at:
                raise TradingCycleInvariantError(
                    "PortfolioState cannot be newer than AgentInput.created_at"
                )
            agent_input = AgentInput(
                cycle_id=cycle_id,
                created_at=created_at,
                market_state=market_state,
                portfolio_state=portfolio_state,
                aggressiveness=self._aggressiveness,
                aggressiveness_context=self._aggressiveness_context,
                experiment_manifest=self._experiment_manifest,
            )
            market_state = agent_input.market_state
            portfolio_state = agent_input.portfolio_state
        except Exception as exc:
            return self._failed(cycle_id, TradingCycleStage.INPUT, exc)

        return await self._finish_cycle(
            cycle_id=cycle_id,
            agent_input=agent_input,
            market_state=market_state,
            portfolio_state=portfolio_state,
        )

    async def _finish_cycle(
        self,
        *,
        cycle_id: UUID,
        agent_input: AgentInput,
        market_state: MarketState,
        portfolio_state: PortfolioState,
        market_selection_input: MarketSelectionInput | None = None,
        market_selection: MarketSelection | None = None,
    ) -> TradingCycleResult:
        try:
            async with asyncio.timeout(self._timeouts.agent_seconds):
                decision = await self._agent.generate_decision(agent_input)
            self._validate_decision(agent_input=agent_input, decision=decision)
            if (
                market_selection is not None
                and decision.tool_traces != market_selection.tool_traces
            ):
                raise TradingCycleInvariantError(
                    "final decision must preserve market-selection research traces"
                )
        except Exception as exc:
            return self._failed(
                cycle_id,
                TradingCycleStage.AGENT,
                exc,
                market_selection_input=market_selection_input,
                market_selection=market_selection,
                agent_input=agent_input,
                agent_tool_traces=(
                    market_selection.tool_traces
                    if market_selection is not None
                    else self._agent_tool_traces()
                ),
            )

        try:
            risk_result = self._risk_engine.evaluate(
                decision=decision,
                market_state=market_state,
                portfolio_state=portfolio_state,
            )
            self._validate_risk_result(decision=decision, result=risk_result)
        except Exception as exc:
            return self._failed(
                cycle_id,
                TradingCycleStage.RISK,
                exc,
                market_selection_input=market_selection_input,
                market_selection=market_selection,
                agent_input=agent_input,
                decision=decision,
            )

        assessment = risk_result.assessment
        intent = risk_result.execution_intent
        if intent is None:
            return TradingCycleResult(
                cycle_id=cycle_id,
                status=TradingCycleStatus.COMPLETED,
                market_selection_input=market_selection_input,
                market_selection=market_selection,
                agent_input=agent_input,
                decision=decision,
                risk_assessment=assessment,
                agent_tool_traces=decision.tool_traces,
            )

        try:
            async with asyncio.timeout(self._timeouts.broker_seconds):
                fills = await self._broker.execute(intent, market_state)
            self._validate_fills(intent=intent, market_state=market_state, fills=fills)
        except Exception as exc:
            return self._failed(
                cycle_id,
                TradingCycleStage.BROKER,
                exc,
                market_selection_input=market_selection_input,
                market_selection=market_selection,
                agent_input=agent_input,
                decision=decision,
                risk_assessment=assessment,
                execution_intent=intent,
            )

        try:
            post_at = self._now()
            if any(fill.filled_at > post_at for fill in fills):
                raise TradingCycleInvariantError(
                    "post-trade portfolio snapshot cannot precede a returned fill"
                )
            portfolio_after = self._portfolio.snapshot(as_of=post_at)
        except Exception as exc:
            return self._failed(
                cycle_id,
                TradingCycleStage.POST_PORTFOLIO,
                exc,
                market_selection_input=market_selection_input,
                market_selection=market_selection,
                agent_input=agent_input,
                decision=decision,
                risk_assessment=assessment,
                execution_intent=intent,
                fills=fills,
            )

        return TradingCycleResult(
            cycle_id=cycle_id,
            status=TradingCycleStatus.COMPLETED,
            market_selection_input=market_selection_input,
            market_selection=market_selection,
            agent_input=agent_input,
            decision=decision,
            risk_assessment=assessment,
            execution_intent=intent,
            fills=fills,
            portfolio_state_after=portfolio_after,
            agent_tool_traces=decision.tool_traces,
        )

    def _validate_market_selection(
        self,
        *,
        selection_input: MarketSelectionInput,
        selection: MarketSelection,
    ) -> None:
        if selection.cycle_id != selection_input.cycle_id:
            raise TradingCycleInvariantError("MarketSelection cycle_id mismatch")
        if selection.selected_at < selection_input.created_at:
            raise TradingCycleInvariantError("MarketSelection predates MarketSelectionInput")
        selected = ExecutableMarket(
            symbol=selection.symbol,
            market_type=selection.market_type,
        )
        if selected not in selection_input.executable_markets:
            raise TradingCycleInvariantError("MarketSelection is outside executable universe")

    def _validate_selected_market_state(
        self,
        *,
        selection: MarketSelection,
        market_state: MarketState,
    ) -> None:
        if market_state.symbol != selection.symbol:
            raise TradingCycleInvariantError("selected MarketState symbol mismatch")
        if market_state.market_type is not selection.market_type:
            raise TradingCycleInvariantError("selected MarketState market_type mismatch")

    def _validate_decision(
        self,
        *,
        agent_input: AgentInput,
        decision: DecisionCandidate,
    ) -> None:
        if decision.cycle_id != agent_input.cycle_id:
            raise TradingCycleInvariantError("DecisionCandidate cycle_id mismatch")
        if decision.symbol != agent_input.market_state.symbol:
            raise TradingCycleInvariantError("DecisionCandidate symbol mismatch")
        if decision.market_type is not agent_input.market_state.market_type:
            raise TradingCycleInvariantError("DecisionCandidate market_type mismatch")
        if decision.created_at < agent_input.created_at:
            raise TradingCycleInvariantError("DecisionCandidate predates AgentInput")

    def _validate_risk_result(
        self,
        *,
        decision: DecisionCandidate,
        result: RiskResult,
    ) -> None:
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
                raise TradingCycleInvariantError("REJECT cannot produce an execution intent")
            return
        if intent is None:
            raise TradingCycleInvariantError("executable Risk outcome requires an intent")
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

    def _validate_fills(
        self,
        *,
        intent: ExecutionIntent,
        market_state: MarketState,
        fills: tuple[Fill, ...],
    ) -> None:
        if not fills:
            raise TradingCycleInvariantError("successful broker execution returned no fills")
        total_quantity = Decimal(0)
        for fill in fills:
            if fill.execution_id != intent.execution_id:
                raise TradingCycleInvariantError("Fill execution_id mismatch")
            if fill.market_state_id != market_state.market_state_id:
                raise TradingCycleInvariantError("Fill MarketState mismatch")
            if fill.pricing_as_of != market_state.as_of:
                raise TradingCycleInvariantError("Fill pricing timestamp mismatch")
            if fill.reference_price != market_state.last_price:
                raise TradingCycleInvariantError("Fill reference price mismatch")
            if fill.action is not intent.action or fill.symbol != intent.symbol:
                raise TradingCycleInvariantError("Fill action or symbol mismatch")
            if fill.market_type is not intent.market_type:
                raise TradingCycleInvariantError("Fill market_type mismatch")
            if fill.filled_at < market_state.as_of:
                raise TradingCycleInvariantError("Fill predates MarketState")
            total_quantity += fill.quantity
        if total_quantity != intent.quantity:
            raise TradingCycleInvariantError("Fill quantities must equal the authorized intent")

    def _agent_tool_traces(self) -> tuple[AgentToolTrace, ...]:
        if not isinstance(self._agent, AgentToolTraceSource):
            return ()
        traces = self._agent.last_tool_traces
        if any(not isinstance(trace, AgentToolTrace) for trace in traces):
            raise TradingCycleInvariantError("Agent returned invalid tool traces")
        return traces

    def _now(self) -> datetime:
        value = self._clock.now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise TradingCycleInvariantError("trading cycle clock must be timezone-aware")
        return value.astimezone(UTC)

    def _failed(
        self,
        cycle_id: UUID,
        stage: TradingCycleStage,
        exc: Exception,
        *,
        market_selection_input: MarketSelectionInput | None = None,
        market_selection: MarketSelection | None = None,
        agent_input: AgentInput | None = None,
        decision: DecisionCandidate | None = None,
        risk_assessment: RiskAssessment | None = None,
        execution_intent: ExecutionIntent | None = None,
        fills: tuple[Fill, ...] = (),
        agent_tool_traces: tuple[AgentToolTrace, ...] | None = None,
    ) -> TradingCycleResult:
        traces = (
            agent_tool_traces
            if agent_tool_traces is not None
            else market_selection.tool_traces
            if market_selection is not None
            else decision.tool_traces
            if decision is not None
            else ()
        )
        return TradingCycleResult(
            cycle_id=cycle_id,
            status=TradingCycleStatus.FAILED,
            failure=TradingCycleFailure(
                stage=stage,
                error_type=type(exc).__name__,
                timed_out=isinstance(exc, TimeoutError),
            ),
            market_selection_input=market_selection_input,
            market_selection=market_selection,
            agent_input=agent_input,
            decision=decision,
            risk_assessment=risk_assessment,
            execution_intent=execution_intent,
            fills=fills,
            agent_tool_traces=traces,
        )


class TradingEngine:
    """Sequential autonomous loop; a new cycle starts only after cadence wait."""

    def __init__(self, *, runner: TradingCycleRunner, cadence_seconds: float) -> None:
        if isinstance(cadence_seconds, bool) or not isinstance(cadence_seconds, (int, float)):
            raise ValueError("cadence_seconds must be a positive finite number")
        if not math.isfinite(cadence_seconds) or cadence_seconds <= 0:
            raise ValueError("cadence_seconds must be a positive finite number")
        self._runner = runner
        self._cadence_seconds = float(cadence_seconds)
        self._stop_requested = asyncio.Event()
        self._lifecycle_lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._last_result: TradingCycleResult | None = None
        self._last_unexpected_error_type: str | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def last_result(self) -> TradingCycleResult | None:
        return self._last_result

    @property
    def last_unexpected_error_type(self) -> str | None:
        return self._last_unexpected_error_type

    async def run_cycle(self) -> TradingCycleResult:
        """Expose the same serialized primitive used by the autonomous loop."""

        result = await self._runner.run_cycle()
        self._last_result = result
        return result

    async def start(self) -> None:
        """Start one background loop and reject duplicate starts."""

        async with self._lifecycle_lock:
            if self.is_running:
                raise TradingEngineAlreadyRunningError("trading engine is already running")
            if self._task is not None and self._task.done():
                self._task = None
            self._stop_requested.clear()
            self._last_unexpected_error_type = None
            self._task = asyncio.create_task(
                self._run_loop(),
                name="ai-spot-trader-autonomous-loop",
            )

    async def stop(self) -> None:
        """Cooperatively stop after the in-flight bounded cycle, waking cadence wait."""

        async with self._lifecycle_lock:
            task = self._task
            if task is None:
                return
            self._stop_requested.set()
        await task
        async with self._lifecycle_lock:
            if self._task is task:
                self._task = None

    async def _run_loop(self) -> None:
        while not self._stop_requested.is_set():
            try:
                self._last_result = await self._runner.run_cycle()
            except Exception as exc:
                self._last_unexpected_error_type = type(exc).__name__
            if self._stop_requested.is_set():
                break
            await self._wait_for_cadence_or_stop()

    async def _wait_for_cadence_or_stop(self) -> None:
        with suppress(TimeoutError):
            await asyncio.wait_for(
                self._stop_requested.wait(),
                timeout=self._cadence_seconds,
            )
