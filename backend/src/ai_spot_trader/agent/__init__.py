"""Single-agent strategic LLM boundary for causal PAPER market selection and decisions."""

from ai_spot_trader.agent.errors import (
    AgentContractViolationError,
    AgentError,
    LLMHTTPError,
    LLMNetworkError,
    LLMOutputValidationError,
    LLMProviderError,
    LLMRateLimitError,
    LLMServerError,
    LLMTimeoutError,
    LLMTransientError,
    LLMTransportError,
)
from ai_spot_trader.agent.openai_client import OpenAIResponsesClient
from ai_spot_trader.agent.prompt import AGENT_PROMPT_VERSION, AGENT_SYSTEM_PROMPT
from ai_spot_trader.agent.provider import (
    MARKET_SELECTION_SCHEMA,
    STRATEGIC_DECISION_SCHEMA,
    OpenAIDecisionProvider,
    StructuredDecisionClient,
    ToolStructuredDecisionClient,
)

__all__ = [
    "AGENT_PROMPT_VERSION",
    "AGENT_SYSTEM_PROMPT",
    "AgentContractViolationError",
    "AgentError",
    "LLMHTTPError",
    "LLMNetworkError",
    "LLMOutputValidationError",
    "LLMProviderError",
    "LLMRateLimitError",
    "LLMServerError",
    "LLMTimeoutError",
    "LLMTransientError",
    "LLMTransportError",
    "MARKET_SELECTION_SCHEMA",
    "OpenAIDecisionProvider",
    "OpenAIResponsesClient",
    "STRATEGIC_DECISION_SCHEMA",
    "StructuredDecisionClient",
    "ToolStructuredDecisionClient",
]
