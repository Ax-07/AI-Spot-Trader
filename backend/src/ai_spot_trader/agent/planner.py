from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Annotated, Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ai_spot_trader.agent.errors import (
    AgentContractViolationError,
    LLMOutputValidationError,
    RecoverableLLMContractViolationError,
)
from ai_spot_trader.agent.llm_audit import current_llm_audit_context
from ai_spot_trader.agent.prompt import AGENT_SYSTEM_PROMPT
from ai_spot_trader.agent.provider import OpenAIDecisionProvider, ToolStructuredDecisionClient
from ai_spot_trader.domain.enums import LLMModel, MarketType, TradingAction
from ai_spot_trader.domain.models import AgentToolTrace, DecisionCandidate
from ai_spot_trader.domain.planning import (
    CycleDecisionPlan,
    CycleDecisionPlanInput,
    MAX_DECISIONS_PER_CYCLE_HARD_LIMIT,
)
from ai_spot_trader.domain.strategic_thesis import (
    MAX_INVALIDATION_CONDITIONS,
    MAX_SUPPORTING_FACTS,
    StrategicThesisStatus,
    StrategicThesisUpdate,
)

logger = logging.getLogger("ai_spot_trader.agent.planner")

PositiveDecimal = Annotated[Decimal, Field(gt=0)]
StrategicAction = Literal["BUY", "SELL", "HOLD"]
SelectionMarketType = Literal["SPOT", "PERPETUAL"]
StrategicThesisStatusLiteral = Literal[
    "NEW",
    "CONFIRMED",
    "WEAKENING",
    "INVALIDATED",
    "COMPLETED",
]

_OLLAMA_CONTRACT_REGENERATION_ATTEMPTS = 1

_THESIS_UPDATE_OBJECT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["NEW", "CONFIRMED", "WEAKENING", "INVALIDATED", "COMPLETED"],
        },
        "horizon": {"type": "string", "minLength": 1, "maxLength": 64},
        "thesis_summary": {"type": "string", "minLength": 1, "maxLength": 1200},
        "supporting_facts": {
            "type": "array",
            "maxItems": MAX_SUPPORTING_FACTS,
            "items": {"type": "string", "minLength": 1, "maxLength": 500},
        },
        "invalidation_conditions": {
            "type": "array",
            "maxItems": MAX_INVALIDATION_CONDITIONS,
            "items": {"type": "string", "minLength": 1, "maxLength": 500},
        },
        "review_summary": {"type": "string", "minLength": 1, "maxLength": 800},
    },
    "required": [
        "status",
        "horizon",
        "thesis_summary",
        "supporting_facts",
        "invalidation_conditions",
        "review_summary",
    ],
    "additionalProperties": False,
}

_THESIS_UPDATE_SCHEMA: dict[str, Any] = {
    "anyOf": [_THESIS_UPDATE_OBJECT_SCHEMA, {"type": "null"}]
}


def _decision_item_variant(
    action: StrategicAction,
    *,
    proposed_quantity_schema: dict[str, Any],
    symbol: str | None = None,
    market_type: SelectionMarketType | None = None,
) -> dict[str, Any]:
    """Build one strict Structured Outputs variant without weakening Pydantic validation."""

    symbol_schema: dict[str, Any] = {"type": "string", "minLength": 1}
    market_type_schema: dict[str, Any] = {
        "type": "string",
        "enum": ["SPOT", "PERPETUAL"],
    }
    if symbol is not None:
        symbol_schema = {"type": "string", "enum": [symbol]}
    if market_type is not None:
        market_type_schema = {"type": "string", "enum": [market_type]}

    return {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": [action]},
            "symbol": symbol_schema,
            "market_type": market_type_schema,
            "proposed_quantity": proposed_quantity_schema,
            "rationale": {"type": ["string", "null"]},
            "thesis_update": _THESIS_UPDATE_SCHEMA,
        },
        "required": [
            "action",
            "symbol",
            "market_type",
            "proposed_quantity",
            "rationale",
            "thesis_update",
        ],
        "additionalProperties": False,
    }


def _decision_variants(
    allowed_markets: tuple[tuple[str, SelectionMarketType], ...] | None,
) -> list[dict[str, Any]]:
    actions: tuple[tuple[StrategicAction, dict[str, Any]], ...] = (
        ("BUY", {"type": "number", "exclusiveMinimum": 0}),
        ("SELL", {"type": "number", "exclusiveMinimum": 0}),
        ("HOLD", {"type": "null"}),
    )
    if allowed_markets is None:
        return [
            _decision_item_variant(action, proposed_quantity_schema=quantity_schema)
            for action, quantity_schema in actions
        ]
    return [
        _decision_item_variant(
            action,
            proposed_quantity_schema=quantity_schema,
            symbol=symbol,
            market_type=market_type,
        )
        for action, quantity_schema in actions
        for symbol, market_type in allowed_markets
    ]


def _strategic_plan_schema(
    allowed_markets: tuple[tuple[str, SelectionMarketType], ...] | None,
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "decisions": {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_DECISIONS_PER_CYCLE_HARD_LIMIT,
                "items": {"anyOf": _decision_variants(allowed_markets)},
            },
            "rationale": {"type": ["string", "null"]},
        },
        "required": ["decisions", "rationale"],
        "additionalProperties": False,
    }


# Compatibility/reference schema used by existing tests and singleton tooling. The actual
# multi-market plan call now receives a causal schema built from CycleDecisionPlanInput.
STRATEGIC_PLAN_SCHEMA: dict[str, Any] = _strategic_plan_schema(None)


def build_strategic_plan_schema(plan_input: CycleDecisionPlanInput) -> dict[str, Any]:
    """Bind Structured Outputs to the exact causal ``symbol + market_type`` universe.

    The schema is a transport guard only. It does not rank, select or otherwise make a strategic
    choice for the Agent. Pydantic and the post-LLM business validation below remain authoritative
    fail-closed checks even if a provider ignores or misapplies the JSON Schema.
    """

    allowed_markets: list[tuple[str, SelectionMarketType]] = []
    for item in plan_input.market_states:
        if item.market_type is MarketType.SPOT:
            market_type: SelectionMarketType = "SPOT"
        elif item.market_type is MarketType.PERPETUAL:
            market_type = "PERPETUAL"
        else:
            raise AgentContractViolationError(
                "strategic plan causal universe contains a non-executable market type"
            )
        allowed_markets.append((item.symbol, market_type))
    return _strategic_plan_schema(tuple(allowed_markets))


class _StrategicThesisUpdatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: StrategicThesisStatusLiteral
    horizon: Annotated[str, Field(min_length=1, max_length=64)]
    thesis_summary: Annotated[str, Field(min_length=1, max_length=1200)]
    supporting_facts: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=500)]],
        Field(max_length=MAX_SUPPORTING_FACTS),
    ]
    invalidation_conditions: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=500)]],
        Field(max_length=MAX_INVALIDATION_CONDITIONS),
    ]
    review_summary: Annotated[str, Field(min_length=1, max_length=800)]

    def to_domain(self) -> StrategicThesisUpdate:
        return StrategicThesisUpdate(
            status=StrategicThesisStatus(self.status),
            horizon=self.horizon,
            thesis_summary=self.thesis_summary,
            supporting_facts=tuple(self.supporting_facts),
            invalidation_conditions=tuple(self.invalidation_conditions),
            review_summary=self.review_summary,
        )


class _StrategicPlanEntryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    action: StrategicAction
    symbol: Annotated[str, Field(min_length=1)]
    market_type: SelectionMarketType
    proposed_quantity: PositiveDecimal | None
    rationale: str | None
    thesis_update: _StrategicThesisUpdatePayload | None = None

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
        strategic_context_enabled = plan_input.strategic_position_context is not None
        managed = {
            (item.symbol, item.market_type)
            for item in (
                plan_input.strategic_position_context.positions
                if strategic_context_enabled
                else ()
            )
        }
        self._last_tool_traces = ()
        input_text = _plan_input_text(plan_input)
        plan_schema = build_strategic_plan_schema(plan_input)
        allow_tools = not plan_input.management_mode

        raw_output, traces = await self._generate_plan_output(
            input_text=input_text,
            plan_schema=plan_schema,
            allow_tools=allow_tools,
        )
        self._last_tool_traces = traces
        try:
            payload = _parse_plan_output(raw_output)
            _validate_recoverable_plan_contract(
                payload,
                plan_input=plan_input,
                allowed=allowed,
                managed=managed,
                strategic_context_enabled=strategic_context_enabled,
            )
        except (LLMOutputValidationError, RecoverableLLMContractViolationError) as exc:
            if _contract_regeneration_budget(self._model) <= 0:
                raise
            category = _recoverable_error_category(exc)
            _log_contract_regeneration_started(
                plan_input=plan_input,
                category=category,
            )
            corrective_input = _contract_regeneration_input_text(
                plan_input,
                category=category,
            )
            try:
                raw_output, traces = await self._generate_plan_output(
                    input_text=corrective_input,
                    plan_schema=plan_schema,
                    allow_tools=allow_tools,
                )
                self._last_tool_traces = traces
                payload = _parse_plan_output(raw_output)
                _validate_recoverable_plan_contract(
                    payload,
                    plan_input=plan_input,
                    allowed=allowed,
                    managed=managed,
                    strategic_context_enabled=strategic_context_enabled,
                )
            except (LLMOutputValidationError, RecoverableLLMContractViolationError) as retry_exc:
                _log_contract_regeneration_failed(
                    plan_input=plan_input,
                    category=_recoverable_error_category(retry_exc),
                )
                raise
            except Exception as retry_exc:
                _log_contract_regeneration_failed(
                    plan_input=plan_input,
                    category=type(retry_exc).__name__,
                )
                raise
            _log_contract_regeneration_succeeded(plan_input=plan_input)

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

        decisions: list[DecisionCandidate] = []
        thesis_updates: list[StrategicThesisUpdate | None] = []
        for entry in payload.decisions:
            market_type = MarketType(entry.market_type)
            thesis_update = (
                None if entry.thesis_update is None else entry.thesis_update.to_domain()
            )
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
            thesis_updates.append(thesis_update)

        self._last_tool_traces = traces
        retained_thesis_updates = (
            tuple(thesis_updates)
            if strategic_context_enabled or any(item is not None for item in thesis_updates)
            else ()
        )
        return CycleDecisionPlan(
            cycle_id=plan_input.cycle_id,
            created_at=created_at,
            decisions=tuple(decisions),
            thesis_updates=retained_thesis_updates,
            rationale=payload.rationale,
            tool_traces=traces,
        )

    async def _generate_plan_output(
        self,
        *,
        input_text: str,
        plan_schema: dict[str, Any],
        allow_tools: bool,
    ) -> tuple[str, tuple[AgentToolTrace, ...]]:
        traces: tuple[AgentToolTrace, ...] = ()
        if allow_tools and self._tool_registry is not None and self._max_tool_calls > 0:
            tool_client = cast(ToolStructuredDecisionClient, self._client)
            try:
                loop_result = await tool_client.generate_structured_decision_with_tools(
                    model=self._model,
                    instructions=AGENT_SYSTEM_PROMPT,
                    input_text=input_text,
                    schema=plan_schema,
                    tool_registry=self._tool_registry,
                    max_tool_calls=self._max_tool_calls,
                )
            except Exception:
                self._capture_partial_traces(tool_client)
                raise
            return loop_result.output_text, loop_result.traces
        raw_output = await self._client.generate_structured_decision(
            model=self._model,
            instructions=AGENT_SYSTEM_PROMPT,
            input_text=input_text,
            schema=plan_schema,
        )
        return raw_output, traces


def _validate_recoverable_plan_contract(
    payload: _StrategicPlanPayload,
    *,
    plan_input: CycleDecisionPlanInput,
    allowed: set[tuple[str, MarketType]],
    managed: set[tuple[str, MarketType]],
    strategic_context_enabled: bool,
) -> None:
    if len(payload.decisions) > plan_input.max_decisions_per_cycle:
        raise RecoverableLLMContractViolationError(
            "LLM decision plan exceeds max_decisions_per_cycle",
            category="MAX_DECISIONS_PER_CYCLE",
        )

    seen: set[tuple[str, MarketType]] = set()
    for entry in payload.decisions:
        market_type = MarketType(entry.market_type)
        key = (entry.symbol, market_type)
        if key not in allowed:
            raise RecoverableLLMContractViolationError(
                "LLM decision targets a market outside the causal plan universe",
                category="MARKET_OUTSIDE_CAUSAL_UNIVERSE",
            )
        if key in seen:
            raise RecoverableLLMContractViolationError(
                "LLM decision plan contains a duplicate symbol + market_type",
                category="DUPLICATE_MARKET",
            )
        if strategic_context_enabled:
            if entry.action != "HOLD" and entry.thesis_update is None:
                raise RecoverableLLMContractViolationError(
                    "BUY and SELL decisions require a structured strategic thesis update",
                    category="MISSING_STRATEGIC_THESIS_UPDATE",
                )
            if entry.action == "HOLD" and key in managed and entry.thesis_update is None:
                raise RecoverableLLMContractViolationError(
                    "HOLD on an open position requires a structured strategic thesis review",
                    category="MISSING_STRATEGIC_THESIS_REVIEW",
                )
        seen.add(key)


def _contract_regeneration_budget(model: LLMModel | str) -> int:
    """Enable one corrective generation only for the canonical Ollama model representation."""

    # ``client_factory.ConfiguredModel`` is intentionally ``LLMModel | str``: OpenAI uses the
    # explicit LLMModel enum while Ollama carries its local model name as a plain string. Keep the
    # retry Ollama-only so OpenAI gains no extra call/cost from this batch.
    if isinstance(model, LLMModel):
        return 0
    if isinstance(model, str) and model.strip():
        return _OLLAMA_CONTRACT_REGENERATION_ATTEMPTS
    return 0


def _recoverable_error_category(
    error: LLMOutputValidationError | RecoverableLLMContractViolationError,
) -> str:
    if isinstance(error, RecoverableLLMContractViolationError):
        return error.category
    message = str(error)
    if "not valid JSON" in message or "output is empty" in message:
        return "INVALID_JSON"
    if "invalid action/quantity" in message:
        return "INVALID_ACTION_OR_QUANTITY"
    if "invalid action" in message:
        return "INVALID_ACTION"
    if "invalid strategic thesis update" in message:
        return "INVALID_STRATEGIC_THESIS_UPDATE"
    if "invalid decision list" in message:
        return "INVALID_DECISION_LIST"
    return "STRUCTURED_OUTPUT_SCHEMA"


def _contract_regeneration_input_text(
    plan_input: CycleDecisionPlanInput,
    *,
    category: str,
) -> str:
    payload = json.loads(_plan_input_text(plan_input))
    payload["contract_regeneration"] = {
        "protocol_version": "strategic-output-regeneration-v1",
        "attempt": 1,
        "reason": category,
        "instruction": (
            "La réponse précédente a été rejetée par le contrat de sortie. Régénérez intégralement "
            "le plan à partir des mêmes faits causaux; ne tentez pas de corriger partiellement la "
            "réponse précédente et n'inventez aucune décision attendue."
        ),
        "constraints": _contract_regeneration_constraints(category),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _contract_regeneration_constraints(category: str) -> list[str]:
    constraints = [
        "Respecter strictement le JSON Schema fourni.",
        "BUY et SELL utilisent proposed_quantity strictement positive; HOLD utilise null.",
        "Chaque couple symbol + market_type est unique et appartient à l'univers causal fourni.",
        "Ne jamais dépasser max_decisions_per_cycle.",
        "Produire une réponse concise sans chaîne de pensée détaillée.",
    ]
    if category in {
        "INVALID_STRATEGIC_THESIS_UPDATE",
        "MISSING_STRATEGIC_THESIS_UPDATE",
        "MISSING_STRATEGIC_THESIS_REVIEW",
    }:
        constraints.append(
            "Respecter intégralement les exigences thesis_update/review du contexte stratégique."
        )
    return constraints


def _log_contract_regeneration_started(
    *,
    plan_input: CycleDecisionPlanInput,
    category: str,
) -> None:
    try:
        context = current_llm_audit_context()
        logger.warning(
            "agent_contract_regeneration_started provider=OLLAMA session_id=%s cycle_id=%s "
            "attempt=1 max_attempts=1 reason=%s",
            "-" if context.session_id is None else str(context.session_id),
            str(context.cycle_id or plan_input.cycle_id),
            category,
        )
    except Exception:
        pass


def _log_contract_regeneration_succeeded(*, plan_input: CycleDecisionPlanInput) -> None:
    try:
        context = current_llm_audit_context()
        logger.info(
            "agent_contract_regeneration_succeeded provider=OLLAMA session_id=%s cycle_id=%s "
            "attempt=1",
            "-" if context.session_id is None else str(context.session_id),
            str(context.cycle_id or plan_input.cycle_id),
        )
    except Exception:
        pass


def _log_contract_regeneration_failed(
    *,
    plan_input: CycleDecisionPlanInput,
    category: str,
) -> None:
    try:
        context = current_llm_audit_context()
        logger.error(
            "agent_contract_regeneration_failed provider=OLLAMA session_id=%s cycle_id=%s "
            "attempt=1 reason=%s",
            "-" if context.session_id is None else str(context.session_id),
            str(context.cycle_id or plan_input.cycle_id),
            category,
        )
    except Exception:
        pass


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
    payload["strategic_thesis_contract"] = {
        "protocol_version": "strategic-position-thesis-v1",
        "role": (
            "Dans ce même appel stratégique, produisez aussi la création ou la réévaluation "
            "structurée de la thèse associée à chaque position concernée."
        ),
        "continuity": (
            "Lorsqu'une position figure dans strategic_position_context, partez de sa mémoire de "
            "thèse, comparez les faits actuels aux faits de support et aux conditions "
            "d'invalidation, puis qualifiez la thèse NEW, CONFIRMED, WEAKENING, INVALIDATED ou "
            "COMPLETED avant de comparer maintien, réduction, fermeture, augmentation et "
            "alternatives. Une position UNAVAILABLE_LEGACY n'a aucune motivation historique "
            "connue : ne l'inventez pas; créez seulement une thèse de gestion fondée sur les "
            "faits disponibles à partir de ce cycle."
        ),
        "output": (
            "BUY et SELL exigent thesis_update. HOLD exige thesis_update lorsqu'une position "
            "ouverte correspondante est fournie; HOLD sans position peut utiliser null. Les "
            "champs de thèse doivent rester concis, factuels, bornés et auditables."
        ),
        "activation": (
            "Une thèse proposée avec une entrée n'est pas encore une thèse active. Le backend ne "
            "l'activera qu'après autorisation Risk et fill économique réel. Un REJECT Risk ou une "
            "absence de fill ne crée aucune thèse active."
        ),
        "non_automatic": (
            "INVALIDATED et COMPLETED sont des états stratégiques descriptifs, jamais des ordres "
            "SELL automatiques. La décision reste BUY / SELL / HOLD et le Risk Engine conserve "
            "l'autorité finale."
        ),
        "privacy": (
            "N'émettez ni chaîne de pensée cachée ni transcript de raisonnement. Utilisez "
            "uniquement le résumé de thèse, les faits, conditions d'invalidation et la revue "
            "structurée demandés."
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
        if "thesis_update" in location:
            return "LLM strategic plan contains an invalid strategic thesis update"
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


__all__ = [
    "OpenAIMultiMarketDecisionProvider",
    "STRATEGIC_PLAN_SCHEMA",
    "build_strategic_plan_schema",
]
