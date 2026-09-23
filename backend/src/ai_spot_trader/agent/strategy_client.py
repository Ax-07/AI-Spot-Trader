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
        context = _aggressiveness_context_from_input(input_text)
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


def _aggressiveness_context_from_input(input_text: str) -> AggressivenessContext:
    try:
        payload = json.loads(input_text)
        raw = payload["aggressiveness_context"]
        return AggressivenessContext.model_validate(raw)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "campaign Agent input requires canonical aggressiveness_context before prompting"
        ) from exc
