import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, Protocol, cast
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ai_spot_trader.agent.errors import (
    AgentContractViolationError,
    LLMOutputValidationError,
)
from ai_spot_trader.agent.prompt import AGENT_PROMPT_VERSION, AGENT_SYSTEM_PROMPT
from ai_spot_trader.core.clock import Clock, SystemClock
from ai_spot_trader.domain.enums import LLMModel, MarketType, TradingAction
from ai_spot_trader.domain.experiments import (
    MARKET_SELECTION_PROTOCOL_VERSION,
    MULTI_MARKET_MODEL_EXPERIMENT_PROTOCOL_VERSION,
    aggressiveness_context,
    validate_experiment_manifest_digest,
)
from ai_spot_trader.domain.models import (
    AgentInput,
    AgentToolTrace,
    AggressivenessContext,
    DecisionCandidate,
    ExecutableMarket,
    ExperimentAgentProtocolSnapshot,
    ExperimentManifest,
    MarketSelection,
    MarketSelectionInput,
    market_selection_digest,
)
from ai_spot_trader.domain.symbols import parse_canonical_symbol
from ai_spot_trader.tools.read_only import ReadOnlyToolRegistry, ToolLoopResult

DecisionIdFactory = Callable[[], UUID]
SelectionIdFactory = Callable[[], UUID]
PositiveDecimal = Annotated[Decimal, Field(gt=0)]
StrategicAction = Literal["BUY", "SELL", "HOLD"]
SelectionMarketType = Literal["SPOT", "PERPETUAL"]

STRATEGIC_DECISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["BUY", "SELL", "HOLD"]},
        "symbol": {"type": "string", "minLength": 1},
        "proposed_quantity": {"type": ["number", "null"]},
        "rationale": {"type": ["string", "null"]},
    },
    "required": ["action", "symbol", "proposed_quantity", "rationale"],
    "additionalProperties": False,
}

MARKET_SELECTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string", "minLength": 1},
        "market_type": {"type": "string", "enum": ["SPOT", "PERPETUAL"]},
        "rationale": {"type": ["string", "null"]},
    },
    "required": ["symbol", "market_type", "rationale"],
    "additionalProperties": False,
}


class StructuredDecisionClient(Protocol):
    """Minimal testable boundary around a structured LLM response."""

    async def generate_structured_decision(
        self,
        *,
        model: LLMModel,
        instructions: str,
        input_text: str,
        schema: dict[str, Any],
    ) -> str: ...


class ToolStructuredDecisionClient(StructuredDecisionClient, Protocol):
    """Optional Responses function-calling extension used by the same strategic Agent."""

    async def generate_structured_decision_with_tools(
        self,
        *,
        model: LLMModel,
        instructions: str,
        input_text: str,
        schema: dict[str, Any],
        tool_registry: ReadOnlyToolRegistry,
        max_tool_calls: int,
    ) -> ToolLoopResult: ...


class _StrategicDecisionPayload(BaseModel):
    """Provider-only schema; the canonical business contract remains DecisionCandidate."""

    model_config = ConfigDict(extra="forbid", strict=True)

    action: StrategicAction
    symbol: Annotated[str, Field(min_length=1)]
    proposed_quantity: PositiveDecimal | None
    rationale: str | None

    @model_validator(mode="after")
    def validate_quantity_contract(self) -> "_StrategicDecisionPayload":
        if self.action == "HOLD":
            if self.proposed_quantity is not None:
                raise ValueError("HOLD cannot propose a quantity")
        elif self.proposed_quantity is None:
            raise ValueError("BUY and SELL require proposed_quantity")
        return self


class _MarketSelectionPayload(BaseModel):
    """Provider-only output used before canonical executable MarketState acquisition."""

    model_config = ConfigDict(extra="forbid", strict=True)

    symbol: Annotated[str, Field(min_length=1)]
    market_type: SelectionMarketType
    rationale: str | None


class OpenAIDecisionProvider:
    """Single Luna/Sol Agent: research/select first, then decide on the acquired market."""

    def __init__(
        self,
        *,
        client: StructuredDecisionClient,
        model: LLMModel = LLMModel.LUNA,
        clock: Clock | None = None,
        decision_id_factory: DecisionIdFactory = uuid4,
        selection_id_factory: SelectionIdFactory = uuid4,
        tool_registry: ReadOnlyToolRegistry | None = None,
        max_tool_calls: int = 0,
    ) -> None:
        if isinstance(max_tool_calls, bool) or max_tool_calls < 0:
            raise ValueError("max_tool_calls must be a non-negative integer")
        if tool_registry is None and max_tool_calls != 0:
            raise ValueError("max_tool_calls requires a read-only tool registry")
        self._client = client
        self._model = model
        self._clock = clock or SystemClock()
        self._decision_id_factory = decision_id_factory
        self._selection_id_factory = selection_id_factory
        self._tool_registry = tool_registry
        self._max_tool_calls = max_tool_calls
        self._last_tool_traces: tuple[AgentToolTrace, ...] = ()

    @property
    def last_tool_traces(self) -> tuple[AgentToolTrace, ...]:
        """Read-only research completed in the latest Agent phase, including partial failures."""

        return self._last_tool_traces

    async def select_market(self, selection_input: MarketSelectionInput) -> MarketSelection:
        """Let the same strategic Agent research and choose one typed executable market."""

        normalized_input = _normalize_selection_input(
            selection_input,
            model=self._model,
            tool_registry=self._tool_registry,
            max_tool_calls=self._max_tool_calls,
        )
        traces: tuple[AgentToolTrace, ...] = ()
        self._last_tool_traces = ()
        if self._tool_registry is not None and self._max_tool_calls > 0:
            tool_client = cast(ToolStructuredDecisionClient, self._client)
            try:
                loop_result = await tool_client.generate_structured_decision_with_tools(
                    model=self._model,
                    instructions=AGENT_SYSTEM_PROMPT,
                    input_text=normalized_input.model_dump_json(),
                    schema=MARKET_SELECTION_SCHEMA,
                    tool_registry=self._tool_registry,
                    max_tool_calls=self._max_tool_calls,
                )
            except Exception:
                self._capture_partial_traces(tool_client)
                raise
            raw_output = loop_result.output_text
            traces = loop_result.traces
            self._last_tool_traces = traces
        else:
            raw_output = await self._client.generate_structured_decision(
                model=self._model,
                instructions=AGENT_SYSTEM_PROMPT,
                input_text=normalized_input.model_dump_json(),
                schema=MARKET_SELECTION_SCHEMA,
            )

        payload = _parse_selection_output(raw_output)
        try:
            parse_canonical_symbol(payload.symbol)
        except ValueError as exc:
            raise AgentContractViolationError("selected market symbol is not canonical") from exc
        selected_market = ExecutableMarket(
            symbol=payload.symbol,
            market_type=MarketType(payload.market_type),
        )
        if selected_market not in normalized_input.executable_markets:
            raise AgentContractViolationError(
                "LLM selected symbol + market_type outside the executable universe"
            )

        selected_at = _normalize_decision_time(self._clock.now())
        if selected_at < normalized_input.created_at:
            raise AgentContractViolationError(
                "market-selection clock cannot precede MarketSelectionInput.created_at"
            )
        if any(trace.completed_at > selected_at for trace in traces):
            raise AgentContractViolationError(
                "tool trace cannot contain data completed after market selection"
            )

        selection_id = self._selection_id_factory()
        self._last_tool_traces = traces
        return MarketSelection(
            selection_id=selection_id,
            cycle_id=normalized_input.cycle_id,
            selected_at=selected_at,
            symbol=selected_market.symbol,
            market_type=selected_market.market_type,
            rationale=payload.rationale,
            tool_traces=traces,
            selection_digest=market_selection_digest(
                selection_id=selection_id,
                cycle_id=normalized_input.cycle_id,
                selected_at=selected_at,
                symbol=selected_market.symbol,
                market_type=selected_market.market_type,
                tool_traces=traces,
                rationale=payload.rationale,
            ),
        )

    async def generate_decision(self, agent_input: AgentInput) -> DecisionCandidate:
        """Generate the final BUY/SELL/HOLD decision on the exact executable MarketState."""

        normalized_input = _normalize_agent_input(
            agent_input,
            model=self._model,
            tool_registry=self._tool_registry,
            max_tool_calls=self._max_tool_calls,
        )
        selection = normalized_input.market_selection
        traces: tuple[AgentToolTrace, ...] = () if selection is None else selection.tool_traces
        self._last_tool_traces = traces

        # Legacy Batch 18.1 callers without an explicit MarketSelection keep the historical
        # optional research loop. The Batch 18.2 causal path never researches after acquiring
        # the executable MarketState: it reuses exactly the selection-phase traces.
        if selection is None and self._tool_registry is not None and self._max_tool_calls > 0:
            tool_client = cast(ToolStructuredDecisionClient, self._client)
            try:
                loop_result = await tool_client.generate_structured_decision_with_tools(
                    model=self._model,
                    instructions=AGENT_SYSTEM_PROMPT,
                    input_text=normalized_input.model_dump_json(),
                    schema=STRATEGIC_DECISION_SCHEMA,
                    tool_registry=self._tool_registry,
                    max_tool_calls=self._max_tool_calls,
                )
            except Exception:
                self._capture_partial_traces(tool_client)
                raise
            raw_output = loop_result.output_text
            traces = loop_result.traces
            self._last_tool_traces = traces
        else:
            raw_output = await self._client.generate_structured_decision(
                model=self._model,
                instructions=AGENT_SYSTEM_PROMPT,
                input_text=normalized_input.model_dump_json(),
                schema=STRATEGIC_DECISION_SCHEMA,
            )

        payload = _parse_strategic_output(raw_output)
        expected_symbol = normalized_input.market_state.symbol
        if payload.symbol != expected_symbol:
            raise AgentContractViolationError(
                "LLM decision symbol must equal the supplied executable MarketState symbol"
            )

        created_at = _normalize_decision_time(self._clock.now())
        if created_at < normalized_input.created_at:
            raise AgentContractViolationError(
                "decision clock cannot precede AgentInput.created_at"
            )
        if any(trace.completed_at > created_at for trace in traces):
            raise AgentContractViolationError(
                "tool trace cannot contain data completed after the final decision"
            )

        self._last_tool_traces = traces
        return DecisionCandidate(
            decision_id=self._decision_id_factory(),
            cycle_id=normalized_input.cycle_id,
            created_at=created_at,
            action=TradingAction(payload.action),
            symbol=payload.symbol,
            proposed_quantity=payload.proposed_quantity,
            rationale=payload.rationale,
            market_type=normalized_input.market_state.market_type,
            tool_traces=traces,
        )

    def _capture_partial_traces(self, tool_client: ToolStructuredDecisionClient) -> None:
        partial = getattr(tool_client, "last_tool_traces", ())
        if isinstance(partial, tuple) and all(
            isinstance(trace, AgentToolTrace) for trace in partial
        ):
            self._last_tool_traces = partial


def _normalize_selection_input(
    selection_input: MarketSelectionInput,
    *,
    model: LLMModel,
    tool_registry: ReadOnlyToolRegistry | None,
    max_tool_calls: int,
) -> MarketSelectionInput:
    if selection_input.portfolio_state.as_of > selection_input.created_at:
        raise AgentContractViolationError(
            "PortfolioState cannot be newer than MarketSelectionInput.created_at"
        )
    if not selection_input.executable_markets:
        raise AgentContractViolationError("executable market universe cannot be empty")
    for market in selection_input.executable_markets:
        try:
            parse_canonical_symbol(market.symbol)
        except ValueError as exc:
            raise AgentContractViolationError(
                "executable market universe contains a non-canonical symbol"
            ) from exc
        if market.market_type is MarketType.FUTURE:
            raise AgentContractViolationError(
                "dated FUTURE markets cannot enter the executable universe"
            )

    canonical_context = aggressiveness_context(selection_input.aggressiveness)
    if (
        selection_input.aggressiveness_context is not None
        and selection_input.aggressiveness_context != canonical_context
    ):
        raise AgentContractViolationError(
            "MarketSelectionInput aggressiveness_context does not match the canonical mapping"
        )
    _validate_manifest(
        selection_input.experiment_manifest,
        model=model,
        canonical_context=canonical_context,
        tool_registry=tool_registry,
        max_tool_calls=max_tool_calls,
        selection_markets=selection_input.executable_markets,
        has_market_selection=False,
    )
    if selection_input.aggressiveness_context is None:
        return selection_input.model_copy(
            update={"aggressiveness_context": canonical_context}
        )
    return selection_input


def _normalize_agent_input(
    agent_input: AgentInput,
    *,
    model: LLMModel,
    tool_registry: ReadOnlyToolRegistry | None,
    max_tool_calls: int,
) -> AgentInput:
    try:
        parse_canonical_symbol(agent_input.market_state.symbol)
    except ValueError as exc:
        raise AgentContractViolationError("MarketState symbol is not canonical") from exc

    if agent_input.market_state.as_of > agent_input.created_at:
        raise AgentContractViolationError(
            "MarketState cannot be newer than AgentInput.created_at"
        )
    if agent_input.portfolio_state.as_of > agent_input.created_at:
        raise AgentContractViolationError(
            "PortfolioState cannot be newer than AgentInput.created_at"
        )
    selection = agent_input.market_selection
    if selection is not None:
        if selection.cycle_id != agent_input.cycle_id:
            raise AgentContractViolationError("MarketSelection cycle_id mismatch")
        if selection.selected_at > agent_input.created_at:
            raise AgentContractViolationError("MarketSelection cannot postdate AgentInput")
        if selection.symbol != agent_input.market_state.symbol:
            raise AgentContractViolationError(
                "MarketSelection symbol does not match executable MarketState"
            )
        if selection.market_type is not agent_input.market_state.market_type:
            raise AgentContractViolationError(
                "MarketSelection market_type does not match executable MarketState"
            )

    canonical_context = aggressiveness_context(agent_input.aggressiveness)
    if (
        agent_input.aggressiveness_context is not None
        and agent_input.aggressiveness_context != canonical_context
    ):
        raise AgentContractViolationError(
            "AgentInput aggressiveness_context does not match the canonical mapping"
        )
    _validate_manifest(
        agent_input.experiment_manifest,
        model=model,
        canonical_context=canonical_context,
        tool_registry=tool_registry,
        max_tool_calls=max_tool_calls,
        selection_markets=None,
        has_market_selection=selection is not None,
    )
    if agent_input.aggressiveness_context is None:
        return agent_input.model_copy(update={"aggressiveness_context": canonical_context})
    return agent_input


def _validate_manifest(
    manifest: ExperimentManifest | None,
    *,
    model: LLMModel,
    canonical_context: AggressivenessContext,
    tool_registry: ReadOnlyToolRegistry | None,
    max_tool_calls: int,
    selection_markets: tuple[ExecutableMarket, ...] | None,
    has_market_selection: bool,
) -> None:
    if manifest is None:
        return
    try:
        validate_experiment_manifest_digest(manifest)
    except ValueError as exc:
        raise AgentContractViolationError(str(exc)) from exc
    if manifest.llm_model is not model:
        raise AgentContractViolationError(
            "experiment manifest LLM model does not match the configured provider"
        )
    if manifest.prompt_version != AGENT_PROMPT_VERSION:
        raise AgentContractViolationError(
            "experiment manifest prompt version does not match the active prompt"
        )
    if manifest.aggressiveness != canonical_context:
        raise AgentContractViolationError(
            "experiment manifest aggressiveness does not match the canonical mapping"
        )
    if manifest.protocol_version != MULTI_MARKET_MODEL_EXPERIMENT_PROTOCOL_VERSION:
        return

    protocol = manifest.agent_protocol
    assert protocol is not None
    if protocol.market_selection_protocol_version != MARKET_SELECTION_PROTOCOL_VERSION:
        raise AgentContractViolationError(
            "experiment manifest market-selection protocol does not match the active provider"
        )
    if selection_markets is not None and protocol.executable_markets != selection_markets:
        raise AgentContractViolationError(
            "experiment manifest executable markets do not match the active selection input"
        )
    if selection_markets is None and not has_market_selection:
        raise AgentContractViolationError(
            "paper-experiment-v3 requires the causal market-selection path"
        )
    _validate_v3_tool_environment(
        protocol,
        tool_registry=tool_registry,
        max_tool_calls=max_tool_calls,
    )


def _validate_v3_tool_environment(
    protocol: ExperimentAgentProtocolSnapshot,
    *,
    tool_registry: ReadOnlyToolRegistry | None,
    max_tool_calls: int,
) -> None:
    selection_tools_enabled = tool_registry is not None and max_tool_calls > 0
    if protocol.selection_phase.tools_enabled is not selection_tools_enabled:
        raise AgentContractViolationError(
            "experiment manifest selection-tool presence does not match the active provider"
        )
    expected_calls = max_tool_calls if selection_tools_enabled else 0
    if protocol.selection_phase.max_tool_calls != expected_calls:
        raise AgentContractViolationError(
            "experiment manifest selection tool-call budget does not match the active provider"
        )
    if protocol.final_decision_phase.tools_enabled or protocol.final_decision_phase.max_tool_calls:
        raise AgentContractViolationError(
            "paper-experiment-v3 requires tools only during market selection"
        )
    if not selection_tools_enabled:
        return

    assert tool_registry is not None
    if protocol.tool_definitions_digest != tool_registry.openai_tools_digest:
        raise AgentContractViolationError(
            "experiment manifest tool definitions do not match the active provider"
        )
    active_timeout = Decimal(str(tool_registry.timeout_seconds)).normalize()
    if protocol.tool_timeout_seconds != active_timeout:
        raise AgentContractViolationError(
            "experiment manifest tool timeout does not match the active provider"
        )
    if protocol.tool_max_result_bytes != tool_registry.max_result_bytes:
        raise AgentContractViolationError(
            "experiment manifest tool result bound does not match the active provider"
        )
    list_limit = tool_registry.integer_parameter_maximum("list_markets", "limit")
    if protocol.list_markets_max_limit != list_limit:
        raise AgentContractViolationError(
            "experiment manifest list_markets bound does not match the active provider"
        )


def _parse_selection_output(raw_output: str) -> _MarketSelectionPayload:
    parsed = _parse_json(raw_output)
    try:
        return _MarketSelectionPayload.model_validate(parsed)
    except ValidationError as exc:
        raise LLMOutputValidationError(
            "LLM structured output violates the market-selection schema"
        ) from exc


def _parse_strategic_output(raw_output: str) -> _StrategicDecisionPayload:
    parsed = _parse_json(raw_output)
    try:
        return _StrategicDecisionPayload.model_validate(parsed)
    except ValidationError as exc:
        raise LLMOutputValidationError(
            "LLM structured output violates the strategic schema"
        ) from exc


def _parse_json(raw_output: str) -> object:
    if not raw_output or not raw_output.strip():
        raise LLMOutputValidationError("LLM structured output is empty")
    try:
        return json.loads(
            raw_output,
            parse_float=Decimal,
            parse_int=Decimal,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise LLMOutputValidationError("LLM structured output is not valid JSON") from exc


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant is forbidden: {value}")


def _normalize_decision_time(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AgentContractViolationError("decision clock must be timezone-aware")
    return value.astimezone(UTC)
