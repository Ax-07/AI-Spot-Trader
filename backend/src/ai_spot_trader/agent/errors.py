class AgentError(Exception):
    """Base error raised by the strategic agent boundary."""


class LLMTransportError(AgentError):
    """The LLM provider could not be reached or returned an HTTP failure."""


class LLMProviderError(AgentError):
    """The LLM provider returned an unusable or incomplete response envelope."""


class LLMOutputValidationError(AgentError):
    """The model output failed strict structured-output validation."""


class AgentContractViolationError(AgentError):
    """A validated strategic output violates an application-owned invariant."""
