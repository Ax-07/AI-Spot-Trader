from __future__ import annotations

from dataclasses import dataclass

from ai_spot_trader.agent.ollama_client import OllamaStructuredDecisionClient
from ai_spot_trader.agent.openai_client import OpenAIResponsesClient
from ai_spot_trader.control_plane import CampaignConfiguration
from ai_spot_trader.core.config import PaperRuntimeConfigurationError, Settings
from ai_spot_trader.domain.enums import LLMModel, LLMProviderKind

StructuredTransportClient = OpenAIResponsesClient | OllamaStructuredDecisionClient
ConfiguredModel = LLMModel | str


@dataclass(frozen=True, slots=True)
class ResolvedLLMConfiguration:
    """Provider/model/transport budget effectively selected for one strategic Agent."""

    provider: LLMProviderKind
    model: ConfiguredModel
    ollama_timeout_seconds: float | None = None


def resolve_llm_configuration(
    settings: Settings,
    *,
    campaign_configuration: CampaignConfiguration | None = None,
    openai_model: LLMModel | None = None,
) -> ResolvedLLMConfiguration:
    """Resolve Campaign overrides against process-level infrastructure and legacy defaults.

    A Campaign with an explicit provider always wins over `Settings.llm_provider`. A legacy
    Campaign keeps its historical behavior by inheriting the process provider/model/timeout.
    Provider resolution never performs fallback from one transport to the other.
    """

    if campaign_configuration is None:
        provider = settings.llm_provider
        effective_openai_model = openai_model or settings.llm_model
        campaign_ollama_model: str | None = None
        campaign_ollama_timeout: float | None = None
        agent_timeout: float | None = None
    else:
        provider = campaign_configuration.llm_provider or settings.llm_provider
        effective_openai_model = campaign_configuration.llm_model
        campaign_ollama_model = campaign_configuration.ollama_model
        campaign_ollama_timeout = campaign_configuration.ollama_timeout_seconds
        agent_timeout = campaign_configuration.cycle_agent_timeout_seconds

    if provider is LLMProviderKind.OPENAI:
        secret = settings.openai_api_key
        if secret is None or not secret.get_secret_value().strip():
            raise PaperRuntimeConfigurationError(
                "OPENAI_API_KEY is required when the effective llm_provider is OPENAI"
            )
        return ResolvedLLMConfiguration(
            provider=provider,
            model=effective_openai_model,
        )

    if campaign_configuration is not None and campaign_configuration.llm_provider is not None:
        model = (campaign_ollama_model or "").strip()
    else:
        model = settings.ollama_model.strip()
    if not model:
        raise PaperRuntimeConfigurationError(
            "OLLAMA model cannot be empty when the effective llm_provider is OLLAMA"
        )

    timeout_seconds = (
        campaign_ollama_timeout
        if campaign_ollama_timeout is not None
        else settings.ollama_timeout_seconds
    )
    if timeout_seconds <= 0:
        raise PaperRuntimeConfigurationError("effective Ollama timeout must be strictly positive")
    if agent_timeout is not None and agent_timeout <= timeout_seconds:
        raise PaperRuntimeConfigurationError(
            "cycle_agent_timeout_seconds must be greater than the effective Ollama "
            "transport timeout; this check does not guarantee the budget of a multi-call tool loop"
        )
    return ResolvedLLMConfiguration(
        provider=provider,
        model=model,
        ollama_timeout_seconds=timeout_seconds,
    )


def build_structured_decision_client(
    settings: Settings,
    *,
    openai_model: LLMModel | None = None,
    campaign_configuration: CampaignConfiguration | None = None,
    resolved: ResolvedLLMConfiguration | None = None,
) -> tuple[StructuredTransportClient, ConfiguredModel]:
    """Build exactly one transport for the canonical Agent, with no provider fallback."""

    effective = resolved or resolve_llm_configuration(
        settings,
        campaign_configuration=campaign_configuration,
        openai_model=openai_model,
    )

    if effective.provider is LLMProviderKind.OPENAI:
        secret = settings.openai_api_key
        if secret is None or not secret.get_secret_value().strip():
            raise PaperRuntimeConfigurationError(
                "OPENAI_API_KEY is required when the effective llm_provider is OPENAI"
            )
        return (
            OpenAIResponsesClient(
                api_key=secret,
                base_url=settings.openai_base_url,
                timeout_seconds=settings.openai_timeout_seconds,
            ),
            effective.model,
        )

    timeout_seconds = effective.ollama_timeout_seconds
    assert timeout_seconds is not None
    return (
        OllamaStructuredDecisionClient(
            base_url=settings.ollama_base_url,
            timeout_seconds=timeout_seconds,
        ),
        effective.model,
    )


__all__ = [
    "ConfiguredModel",
    "ResolvedLLMConfiguration",
    "StructuredTransportClient",
    "build_structured_decision_client",
    "resolve_llm_configuration",
]
