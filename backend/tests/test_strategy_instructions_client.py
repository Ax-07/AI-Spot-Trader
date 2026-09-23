import asyncio
import json
from typing import Any

from ai_spot_trader.agent.prompt import compose_agent_instructions
from ai_spot_trader.agent.strategy_client import StrategyInstructionsClient
from ai_spot_trader.domain.enums import LLMModel
from ai_spot_trader.domain.experiments import aggressiveness_context


class CapturingClient:
    def __init__(self) -> None:
        self.instructions: str | None = None

    async def generate_structured_decision(
        self,
        *,
        model: LLMModel,
        instructions: str,
        input_text: str,
        schema: dict[str, Any],
    ) -> str:
        del model, input_text, schema
        self.instructions = instructions
        return '{"action":"HOLD"}'


def test_live_strategy_adapter_uses_same_canonical_composer_as_preview() -> None:
    async def scenario() -> None:
        delegate = CapturingClient()
        client = StrategyInstructionsClient(
            delegate,
            strategy_prompt="Favorise les theses avec tendance confirmee.",
        )
        context = aggressiveness_context(6)
        input_text = json.dumps(
            {"aggressiveness_context": context.model_dump(mode="json")},
            sort_keys=True,
        )
        await client.generate_structured_decision(
            model=LLMModel.LUNA,
            instructions="legacy instructions deliberately ignored",
            input_text=input_text,
            schema={},
        )
        expected = compose_agent_instructions(
            strategy_prompt="Favorise les theses avec tendance confirmee.",
            aggressiveness_context=context,
        ).instructions
        assert delegate.instructions == expected

    asyncio.run(scenario())
