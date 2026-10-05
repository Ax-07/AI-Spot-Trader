from __future__ import annotations

import json
from decimal import Decimal
from typing import Annotated, Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ai_spot_trader.agent.errors import AgentContractViolationError, LLMOutputValidationError
from ai_spot_trader.agent.prompt import AGENT_SYSTEM_PROMPT
from ai_spot_trader.agent.provider import OpenAIDecisionProvider, ToolStructuredDecisionClient
from ai_spot_trader.domain.enums import MarketType, TradingAction
from ai_spot_trader.domain.models import AgentToolTrace, DecisionCandidate
from ai_spot_trader.domain.planning import (
    CycleDecisionPlan,
    CycleDecisionPlanInput,
    MAX_DECISIONS_PER_CYCLE_HARD_LIMIT,
)

PositiveDecimal = Annotated[Decimal, Field(gt=0)]
StrategicAction = Literal["BUY", "SELL", "HOLD"]
SelectionMarketType = Literal["SPOT", "PERPETUAL"]


def _decision_item_variant(
    action: StrategicAction,
    *,
    proposed_quantity_schema: dict[str, Any],
) -> dict[str, Any]:
    """Build one strict Structured Outputs variant without weakening Pydantic validation."""

    return {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": [action]},
            "symbol": {"type": "string", "minLength": 1},
            "market_type": {"type": "string", "enum": ["SPOT", "PERPETUAL"]},
            "proposed_quantity": proposed_quantity_schema,
            "rationale": {"type": ["string", "null"]},
        },
        "required": [
            "action",
            "symbol",
            "market_type",
            "proposed_quantity",
            "rationale",
        ],
        "additionalProperties": False,
    }


# Nested anyOf is supported by OpenAI Structured Outputs. Keeping the root an object also
# preserves the strict adapter contract. The quantity constraints now match the Pydantic model:
# BUY/SELL require a strictly positive number, while HOLD requires null.
_DECISION_ITEM_SCHEMA: dict[str, Any] = {
    "anyOf": [
        _decision_item_variant(
            "BUY",
            proposed_quantity_schema={"type": "number", "exclusiveMinimum": 0},
        ),
        _decision_item_variant(
            "SELL",
            proposed_quantity_schema={"type": "number", "exclusiveMinimum": 0},
        ),
        _decision_item_variant(
            "HOLD",
            proposed_quantity_schema={"type": "null"},
        ),
    ]
}

STRATEGIC_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "decisions": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_DECISIONS_PER_CYCLE_HARD_LIMIT,
            "items": _DECISION_ITEM_SCHEMA,
        },
        "rationale": {"type": ["string", "null"]},
    },
    "required": ["decisions", "rationale"],
    "additionalProperties": False,
}


class _StrategicPlanEntryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    action: StrategicAction
    symbol: Annotated[str, Field(min_length=1)]
    market_type: SelectionMarketType
    proposed_quantity: PositiveDecimal | None
    rationale: str | None

    @model_validator(mode="after")
    def validate_quantity(self) -> "_StrategicPlanEntryPayload":
        if self.action == "HOLD":
            if self.proposed_quantity is not None:
                raise ValueError("HOLD cannot propose a quantity")
        elif self.proposed_quantity is None:
            raise ValueError("BUY and SELL require proposed_quantity")
        return self


class _StrategicPlanPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    # JSON arrays arrive as Python lists. With strict=True Pydantic must not be asked
    # to coerce that transport-native list into a tuple before validating entries.
    # The canonical domain plan is converted to an immutable tuple below.
    decisions: Annotated[
        list[_StrategicPlanEntryPayload],
        Field(min_length=1, max_length=MAX_DECISIONS_PER_CYCLE_HARD_LIMIT),
    ]
    rationale: str | None


class OpenAIMultiMarketDecisionProvider(OpenAIDecisionProvider):
    """Extend the existing single Agent with one bounded ordered multi-market plan call."""

    async def generate_decision_plan(
        self,
        plan_input: CycleDecisionPlanInput,
    ) -> CycleDecisionPlan:
        allowed = {(item.symbol, item.market_type) for item in plan_input.market_states}
        self._last_tool_traces = ()
        input_text = _plan_input_text(plan_input)
        traces: tuple[AgentToolTrace, ...] = ()

        allow_tools = not plan_input.management_mode
        if allow_tools and self._tool_registry is not None and self._max_tool_calls > 0:
            tool_client = cast(ToolStructuredDecisionClient, self._client)
            try:
                loop_result = await tool_client.generate_structured_decision_with_tools(
                    model=self._model,
                    instructions=AGENT_SYSTEM_PROMPT,
                    input_text=input_text,
                    schema=STRATEGIC_PLAN_SCHEMA,
                    tool_registry=self._tool_registry,
                    max_tool_calls=self._max_tool_calls,
                )
            except Exception:
                self._capture_partial_traces(tool_client)
                raise
            raw_output = loop_result.output_text
            traces = loop_result.traces
        else:
            raw_output = await self._client.generate_structured_decision(
                model=self._model,
                instructions=AGENT_SYSTEM_PROMPT,
                input_text=input_text,
                schema=STRATEGIC_PLAN_SCHEMA,
            )

        payload = _parse_plan_output(raw_output)
        if len(payload.decisions) > plan_input.max_decisions_per_cycle:
            raise AgentContractViolationError(
                "LLM decision plan exceeds max_decisions_per_cycle"
            )

        created_at = self._clock.now()
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise AgentContractViolationError("decision clock must be timezone-aware")
        created_at = created_at.astimezone(plan_input.created_at.tzinfo)
        if created_at < plan_input.created_at:
            raise AgentContractViolationError(
                "decision plan clock cannot precede CycleDecisionPlanInput.created_at"
            )
        if any(trace.completed_at > created_at for trace in traces):
            raise AgentContractViolationError(
                "tool trace cannot contain data completed after the decision plan"
            )

        seen: set[tuple[str, MarketType]] = set()
        decisions: list[DecisionCandidate] = []
        for entry in payload.decisions:
            market_type = MarketType(entry.market_type)
            key = (entry.symbol, market_type)
            if key not in allowed:
                raise AgentContractViolationError(
                    "LLM decision targets a market outside the causal plan universe"
                )
            if key in seen:
                raise AgentContractViolationError(
                    "LLM decision plan contains a duplicate symbol + market_type"
                )
            seen.add(key)
            decisions.append(
                DecisionCandidate(
                    decision_id=self._decision_id_factory(),
                    cycle_id=plan_input.cycle_id,
                    created_at=created_at,
                    action=TradingAction(entry.action),
                    symbol=entry.symbol,
                    proposed_quantity=entry.proposed_quantity,
                    rationale=entry.rationale,
                    market_type=market_type,
                    tool_traces=traces,
                )
            )

        self._last_tool_traces = traces
        return CycleDecisionPlan(
            cycle_id=plan_input.cycle_id,
            created_at=created_at,
            decisions=tuple(decisions),
            rationale=payload.rationale,
            tool_traces=traces,
        )


def _plan_input_text(plan_input: CycleDecisionPlanInput) -> str:
    payload = plan_input.model_dump(mode="json")
    payload["strategic_plan_contract"] = {
        "protocol_version": "strategic-multi-market-plan-v1",
        "instruction": (
            "Produisez un plan ordonné de BUY / SELL / HOLD sur des marchés distincts. "
            "Chaque décision doit viser exclusivement un market_state fourni. L'ordre du tableau "
            "est l'ordre stratégique d'évaluation et d'exécution. Ne supposez jamais que les "
            "limites Risk sont assouplies et ne dépassez pas max_decisions_per_cycle."
        ),
        "sequential_risk_notice": (
            "Risk réévaluera chaque décision dans cet ordre contre le portefeuille effectivement "
            "mis à jour par les décisions précédentes."
        ),
    }
    if plan_input.radar_analytics_context is not None:
        payload["radar_analytics_context_contract"] = {
            "protocol_version": "radar-analytics-strategic-v1",
            "role": (
                "Contexte descriptif causal figé provenant du Radar/Analytics pour les marchés "
                "déjà admis dans l'univers Agent."
            ),
            "instruction": (
                "Interprétez ces faits comme du contexte, jamais comme une action automatique. "
                "Le score analytics_ranking est un indice d'attention descriptif 0..4 et non une "
                "probabilité de hausse/baisse, une conviction, ni une instruction BUY/SELL. "
                "Les statuts UNAVAILABLE, PARTIAL, STALE, INSUFFICIENT_HISTORY, "
                "TECHNICAL_ERROR et NOT_APPLICABLE signifient absence ou dégradation de donnée, "
                "pas un signal de marché. Vous restez seul responsable du choix BUY/SELL/HOLD; "
                "Risk reste l'autorité finale d'autorisation/modification/refus."
            ),
        }
    if plan_input.management_mode:
        payload["capacity_context"] = {
            "mode": "MANAGEMENT",
            "reason": plan_input.capacity_reason,
            "new_opening_research_skipped": True,
            "instruction": (
                "Aucune nouvelle exposition ne peut être ouverte. Utilisez seulement HOLD ou une "
                "action destinée à réduire/clôturer une position déjà ouverte."
            ),
        }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _parse_plan_output(raw_output: str) -> _StrategicPlanPayload:
    if not raw_output or not raw_output.strip():
        raise LLMOutputValidationError("LLM strategic plan output is empty")
    try:
        parsed = json.loads(
            raw_output,
            parse_float=Decimal,
            parse_int=Decimal,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise LLMOutputValidationError("LLM strategic plan output is not valid JSON") from exc
    try:
        return _StrategicPlanPayload.model_validate(parsed)
    except ValidationError as exc:
        raise LLMOutputValidationError(_validation_error_message(exc)) from exc


def _validation_error_message(exc: ValidationError) -> str:
    """Return a safe category without embedding the raw LLM payload or validation input."""

    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    for error in errors:
        location = tuple(str(item) for item in error.get("loc", ()))
        error_type = str(error.get("type", ""))
        message = str(error.get("msg", ""))
        if "action" in location and error_type == "literal_error":
            return "LLM strategic plan contains an invalid action"
        if "proposed_quantity" in location or "quantity" in message.lower():
            return "LLM strategic plan contains an invalid action/quantity combination"
        if "decisions" in location and error_type in {
            "too_long",
            "too_short",
            "tuple_type",
            "list_type",
        }:
            return "LLM strategic plan contains an invalid decision list"
    return "LLM structured output violates the strategic plan schema"


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant is forbidden: {value}")


__all__ = ["OpenAIMultiMarketDecisionProvider", "STRATEGIC_PLAN_SCHEMA"]
