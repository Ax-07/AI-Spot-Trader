"""Single-agent strategic LLM boundary for PAPER SPOT and Derivatives decisions."""

from ai_spot_trader.agent.errors import (
    AgentContractViolationError,
    AgentError,
    LLMOutputValidationError,
    LLMProviderError,
    LLMTransportError,
)
from ai_spot_trader.agent.openai_client import OpenAIResponsesClient
from ai_spot_trader.agent.prompt import AGENT_PROMPT_VERSION, AGENT_SYSTEM_PROMPT
from ai_spot_trader.agent.provider import (
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
    "LLMOutputValidationError",
    "LLMProviderError",
    "LLMTransportError",
    "OpenAIDecisionProvider",
    "OpenAIResponsesClient",
    "STRATEGIC_DECISION_SCHEMA",
    "StructuredDecisionClient",
    "ToolStructuredDecisionClient",
]
