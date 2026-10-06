from __future__ import annotations

from ai_spot_trader.agent.ollama_client import OllamaStructuredDecisionClient
from ai_spot_trader.agent.openai_client import OpenAIResponsesClient
from ai_spot_trader.core.config import PaperRuntimeConfigurationError, Settings
from ai_spot_trader.domain.enums import LLMModel, LLMProviderKind

StructuredTransportClient = OpenAIResponsesClient | OllamaStructuredDecisionClient
ConfiguredModel = LLMModel | str


def build_structured_decision_client(
    settings: Settings,
    *,
    openai_model: LLMModel,
) -> tuple[StructuredTransportClient, ConfiguredModel]:
    """Resolve exactly one LLM transport for the canonical Agent.

    LOCAL/OLLAMA never falls back to OpenAI. The Campaign's historical `llm_model` field keeps
    its Luna/Sol semantics; the local model is process configuration in Batch 51.1.
    """

    if settings.llm_provider is LLMProviderKind.OPENAI:
        secret = settings.openai_api_key
        if secret is None or not secret.get_secret_value().strip():
            raise PaperRuntimeConfigurationError(
                "OPENAI_API_KEY is required when llm_provider=OPENAI"
            )
        return (
            OpenAIResponsesClient(
                api_key=secret,
                base_url=settings.openai_base_url,
                timeout_seconds=settings.openai_timeout_seconds,
            ),
            openai_model,
        )

    model = settings.ollama_model.strip()
    if not model:
        raise PaperRuntimeConfigurationError(
            "OLLAMA_MODEL cannot be empty when llm_provider=OLLAMA"
        )
    return (
        OllamaStructuredDecisionClient(
            base_url=settings.ollama_base_url,
            timeout_seconds=settings.ollama_timeout_seconds,
        ),
        model,
    )
