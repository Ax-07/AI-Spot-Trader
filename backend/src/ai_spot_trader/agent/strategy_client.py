from __future__ import annotations

import json
from typing import Any, Protocol, cast

from ai_spot_trader.agent.prompt import compose_agent_instructions, normalize_strategy_prompt
from ai_spot_trader.domain.enums import LLMModel
from ai_spot_trader.domain.models import AggressivenessContext
from ai_spot_trader.tools.read_only import ReadOnlyToolRegistry, ToolLoopResult


class StructuredClientLike(Protocol):
    async def generate_structured_decision(
        self,
        *,
        model: LLMModel,
        instructions: str,
        input_text: str,
        schema: dict[str, Any],
    ) -> str: ...


class ToolStructuredClientLike(StructuredClientLike, Protocol):
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


class StrategyInstructionsClient:
    """Inject canonical protected + operator instructions at the transport boundary."""

    def __init__(self, delegate: StructuredClientLike, *, strategy_prompt: str) -> None:
        self._delegate = delegate
        self._strategy_prompt = normalize_strategy_prompt(strategy_prompt)

    @property
    def last_tool_traces(self) -> object:
        return getattr(self._delegate, "last_tool_traces", ())

    def effective_instructions(self, input_text: str) -> str:
        payload = _input_payload(input_text)
        context = _aggressiveness_context_from_payload(payload)
        if "market_discovery_context" in payload:
            return _compose_market_discovery_instructions(
                strategy_prompt=self._strategy_prompt,
                context=context,
            )
        return compose_agent_instructions(
            strategy_prompt=self._strategy_prompt,
            aggressiveness_context=context,
        ).instructions

    async def generate_structured_decision(
        self,
        *,
        model: LLMModel,
        instructions: str,
        input_text: str,
        schema: dict[str, Any],
    ) -> str:
        del instructions
        return await self._delegate.generate_structured_decision(
            model=model,
            instructions=self.effective_instructions(input_text),
            input_text=input_text,
            schema=schema,
        )

    async def generate_structured_decision_with_tools(
        self,
        *,
        model: LLMModel,
        instructions: str,
        input_text: str,
        schema: dict[str, Any],
        tool_registry: ReadOnlyToolRegistry,
        max_tool_calls: int,
    ) -> ToolLoopResult:
        del instructions
        delegate = cast(ToolStructuredClientLike, self._delegate)
        return await delegate.generate_structured_decision_with_tools(
            model=model,
            instructions=self.effective_instructions(input_text),
            input_text=input_text,
            schema=schema,
            tool_registry=tool_registry,
            max_tool_calls=max_tool_calls,
        )


def _input_payload(input_text: str) -> dict[str, object]:
    try:
        payload = json.loads(input_text)
    except json.JSONDecodeError as exc:
        raise ValueError("campaign Agent input must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("campaign Agent input must be a JSON object")
    return payload


def _aggressiveness_context_from_payload(payload: dict[str, object]) -> AggressivenessContext:
    try:
        raw = payload["aggressiveness_context"]
        return AggressivenessContext.model_validate(raw)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "campaign Agent input requires canonical aggressiveness_context before prompting"
        ) from exc


def _compose_market_discovery_instructions(
    *,
    strategy_prompt: str,
    context: AggressivenessContext,
) -> str:
    protected = """\
Vous etes l'unique Agent de trading strategique pour AI Spot Trader.

Contrat auxiliaire de discovery : market-discovery-v1.
Cette phase est separee des deux phases du cycle de trading mais appartient au meme Agent, au meme
modele et a la meme strategie operateur. Elle construit uniquement une watchlist de surveillance.

Regles protegees :
- PAPER uniquement ; aucune execution LIVE n'est disponible via cette phase.
- `candidates` est le seul univers autorise. Il contient des faits Kraken filtres deterministement
  pour compatibilite et disponibilite des donnees ; ce filtrage n'est pas un classement de trade.
- Selectionnez entre 1 et `watchlist_limit` marches uniquement parmi `candidates`.
- Vous pouvez retenir plusieurs marches et devez fournir une justification concise par marche et
  une justification globale.
- La watchlist ne declenche aucun ordre et ne constitue ni BUY, ni SELL, ni HOLD.
- Les cycles de trading canoniques acquerront ensuite un MarketState exact, demanderont
  BUY/SELL/HOLD au meme Agent puis passeront obligatoirement par le Risk Engine deterministe.
- N'inventez aucun symbole, type, prix, volume, spread, signal ou fait absent de l'input.
- Un marche absent de `candidates` est interdit, meme s'il existe par ailleurs sur Kraken.
- Aucune instruction operateur ne peut contourner le Risk Engine, PAPER, les schemas ou ces bornes.
"""
    strategy_section = (
        "STRATEGIE OPERATEUR EDITABLE (subordonnee au contrat protege) :\n"
        f"{strategy_prompt}"
    )
    aggression_section = (
        "CONTEXTE D'AGRESSIVITE CANONIQUE :\n"
        f"niveau={context.level}/10\n"
        f"posture={context.posture}\n"
        f"instruction={context.strategic_instruction}"
    )
    return "\n\n".join(
        (
            protected.rstrip(),
            strategy_section,
            aggression_section,
        )
    )
