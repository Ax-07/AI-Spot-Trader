from __future__ import annotations

import json
from typing import Any, Protocol, cast

from ai_spot_trader.agent.position_management import build_position_management_context
from ai_spot_trader.agent.prompt import (
    compose_agent_instructions,
    compose_trading_context_sections,
    normalize_strategy_prompt,
)
from ai_spot_trader.domain.enums import LLMModel
from ai_spot_trader.domain.models import (
    AggressivenessContext,
    ExecutionCostContext,
    ExecutableMarket,
    MarketState,
    PortfolioState,
    TradingStyleContext,
)
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
        trading_style = _trading_style_context_from_payload(payload)
        execution_costs = _execution_cost_context_from_payload(payload)
        if "market_discovery_context" in payload:
            return _compose_market_discovery_instructions(
                strategy_prompt=self._strategy_prompt,
                context=context,
                trading_style_context=trading_style,
                execution_cost_context=execution_costs,
            )
        instructions = compose_agent_instructions(
            strategy_prompt=self._strategy_prompt,
            aggressiveness_context=context,
            trading_style_context=trading_style,
            execution_cost_context=execution_costs,
        ).instructions
        position_section = _position_management_section_from_payload(
            payload,
            execution_cost_context=execution_costs,
        )
        if position_section is None:
            return instructions
        return f"{instructions}\n\n{position_section}"

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


def _trading_style_context_from_payload(
    payload: dict[str, object],
) -> TradingStyleContext | None:
    raw = payload.get("trading_style_context")
    if raw is None:
        return None
    try:
        return TradingStyleContext.model_validate_json(json.dumps(raw, ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "campaign Agent input contains an invalid trading_style_context"
        ) from exc


def _execution_cost_context_from_payload(
    payload: dict[str, object],
) -> ExecutionCostContext | None:
    raw = payload.get("execution_cost_context")
    if raw is None:
        return None
    try:
        return ExecutionCostContext.model_validate_json(json.dumps(raw, ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "campaign Agent input contains an invalid execution_cost_context"
        ) from exc


def _position_management_section_from_payload(
    payload: dict[str, object],
    *,
    execution_cost_context: ExecutionCostContext | None,
) -> str | None:
    # Preserve the exact historical Campaign prompt for legacy inputs without the paired
    # TradingStyleContext + ExecutionCostContext introduced in Batch 19.9A.
    if execution_cost_context is None:
        return None

    raw_portfolio = payload.get("portfolio_state")
    if raw_portfolio is None:
        return None
    try:
        portfolio = PortfolioState.model_validate_json(
            json.dumps(raw_portfolio, ensure_ascii=False)
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("campaign Agent input contains an invalid portfolio_state") from exc

    raw_markets = payload.get("executable_markets")
    markets: tuple[ExecutableMarket, ...]
    if isinstance(raw_markets, list):
        try:
            markets = tuple(
                ExecutableMarket.model_validate_json(
                    json.dumps(item, ensure_ascii=False)
                )
                for item in raw_markets
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "campaign Agent input contains invalid executable_markets"
            ) from exc
    else:
        raw_market_state = payload.get("market_state")
        if raw_market_state is None:
            return None
        try:
            market_state = MarketState.model_validate_json(
                json.dumps(raw_market_state, ensure_ascii=False)
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("campaign Agent input contains an invalid market_state") from exc
        markets = (
            ExecutableMarket(
                symbol=market_state.symbol,
                market_type=market_state.market_type,
            ),
        )

    context = build_position_management_context(
        portfolio_state=portfolio,
        executable_markets=markets,
        execution_cost_context=execution_cost_context,
    )
    if not context["management_markets"]:
        return None

    encoded = json.dumps(
        context,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        "CONTEXTE FACTUEL DE GESTION DES POSITIONS OUVERTES :\n"
        f"{encoded}\n"
        "Les marches de `management_markets` correspondent a du capital deja engage. "
        "Ils restent des opportunites strategiques meme quand une nouvelle ouverture est possible. "
        "Les estimations de sortie sont descriptives et utilisent les couts PAPER canoniques : "
        "elles ne constituent jamais un signal automatique de vente."
    )


def _compose_market_discovery_instructions(
    *,
    strategy_prompt: str,
    context: AggressivenessContext,
    trading_style_context: TradingStyleContext | None,
    execution_cost_context: ExecutionCostContext | None,
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
    sections = [protected.rstrip(), strategy_section, aggression_section]
    sections.extend(
        compose_trading_context_sections(
            trading_style_context=trading_style_context,
            execution_cost_context=execution_cost_context,
        )
    )
    return "\n\n".join(sections)
