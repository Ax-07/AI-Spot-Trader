import json
from typing import Protocol

from ai_spot_trader.agent.errors import LLMProviderError, LLMTransportError
from ai_spot_trader.chat.errors import ChatProviderError, ChatTransportError
from ai_spot_trader.chat.models import ChatContextSnapshot, ChatMessage
from ai_spot_trader.chat.prompt import OPERATOR_CHAT_SYSTEM_PROMPT
from ai_spot_trader.domain.enums import LLMModel


class TextResponseClient(Protocol):
    """Minimal LLM transport required by the conversational provider."""

    async def generate_text_response(
        self,
        *,
        model: LLMModel,
        instructions: str,
        input_text: str,
    ) -> str: ...


class OpenAIChatProvider:
    """Conversation-only interface to the configured Agent model."""

    def __init__(self, *, client: TextResponseClient, model: LLMModel) -> None:
        self._client = client
        self._model = model

    @property
    def model(self) -> LLMModel:
        return self._model

    async def reply(
        self,
        *,
        history: tuple[ChatMessage, ...],
        context: ChatContextSnapshot,
    ) -> str:
        payload = {
            "chat_history": [message.model_dump(mode="json") for message in history],
            "canonical_context": context.model_dump(mode="json"),
        }
        try:
            response = await self._client.generate_text_response(
                model=self._model,
                instructions=OPERATOR_CHAT_SYSTEM_PROMPT,
                input_text=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            )
        except LLMTransportError as exc:
            raise ChatTransportError("chat provider transport failed") from exc
        except LLMProviderError as exc:
            raise ChatProviderError("chat provider returned an invalid response") from exc

        normalized = response.strip()
        if not normalized:
            raise ChatProviderError("chat provider returned an empty response")
        if len(normalized) > 12000:
            raise ChatProviderError("chat provider response exceeds the allowed size")
        return normalized
