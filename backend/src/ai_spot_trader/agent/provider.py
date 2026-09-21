import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ai_spot_trader.agent.errors import (
    AgentContractViolationError,
    LLMOutputValidationError,
)
from ai_spot_trader.agent.prompt import AGENT_PROMPT_VERSION, AGENT_SYSTEM_PROMPT
from ai_spot_trader.core.clock import Clock, SystemClock
from ai_spot_trader.domain.enums import LLMModel, TradingAction
from ai_spot_trader.domain.experiments import (
    aggressiveness_context,
    validate_experiment_manifest_digest,
)
from ai_spot_trader.domain.models import AgentInput, DecisionCandidate
from ai_spot_trader.domain.symbols import parse_canonical_symbol

DecisionIdFactory = Callable[[], UUID]
PositiveDecimal = Annotated[Decimal, Field(gt=0)]
StrategicAction = Literal["BUY", "SELL", "HOLD"]

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


class OpenAIDecisionProvider:
    """Canonical Luna/Sol strategic provider producing validated DecisionCandidate values."""

    def __init__(
        self,
        *,
        client: StructuredDecisionClient,
        model: LLMModel = LLMModel.LUNA,
        clock: Clock | None = None,
        decision_id_factory: DecisionIdFactory = uuid4,
    ) -> None:
        self._client = client
        self._model = model
        self._clock = clock or SystemClock()
        self._decision_id_factory = decision_id_factory

    async def generate_decision(self, agent_input: AgentInput) -> DecisionCandidate:
        """Generate one strict strategic decision without executing or enriching it."""

        normalized_input = _normalize_agent_input(agent_input, model=self._model)
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
                "LLM decision symbol must equal the supplied MarketState symbol"
            )

        created_at = _normalize_decision_time(self._clock.now())
        if created_at < normalized_input.created_at:
            raise AgentContractViolationError(
                "decision clock cannot precede AgentInput.created_at"
            )

        return DecisionCandidate(
            decision_id=self._decision_id_factory(),
            cycle_id=normalized_input.cycle_id,
            created_at=created_at,
            action=TradingAction(payload.action),
            symbol=payload.symbol,
            proposed_quantity=payload.proposed_quantity,
            rationale=payload.rationale,
            market_type=normalized_input.market_state.market_type,
        )


def _normalize_agent_input(agent_input: AgentInput, *, model: LLMModel) -> AgentInput:
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

    canonical_context = aggressiveness_context(agent_input.aggressiveness)
    if (
        agent_input.aggressiveness_context is not None
        and agent_input.aggressiveness_context != canonical_context
    ):
        raise AgentContractViolationError(
            "AgentInput aggressiveness_context does not match the canonical mapping"
        )

    manifest = agent_input.experiment_manifest
    if manifest is not None:
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

    if agent_input.aggressiveness_context is None:
        return agent_input.model_copy(update={"aggressiveness_context": canonical_context})
    return agent_input


def _parse_strategic_output(raw_output: str) -> _StrategicDecisionPayload:
    if not raw_output or not raw_output.strip():
        raise LLMOutputValidationError("LLM structured output is empty")

    try:
        parsed = json.loads(
            raw_output,
            parse_float=Decimal,
            parse_int=Decimal,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise LLMOutputValidationError("LLM structured output is not valid JSON") from exc

    try:
        return _StrategicDecisionPayload.model_validate(parsed)
    except ValidationError as exc:
        raise LLMOutputValidationError(
            "LLM structured output violates the strategic schema"
        ) from exc


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant is forbidden: {value}")


def _normalize_decision_time(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AgentContractViolationError("decision clock must be timezone-aware")
    return value.astimezone(UTC)
