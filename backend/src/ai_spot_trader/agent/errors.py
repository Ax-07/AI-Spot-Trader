class AgentError(Exception):
    """Base error raised by the strategic agent boundary."""


class LLMTransportError(AgentError):
    """The LLM provider could not be reached or returned an HTTP failure."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        provider_error_type: str | None = None,
        provider_error_code: str | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.provider_error_type = provider_error_type
        self.provider_error_code = provider_error_code
        self.retry_after_seconds = retry_after_seconds


class LLMTransientError(LLMTransportError):
    """Retryable LLM transport failure before a durable decision exists."""


class LLMTimeoutError(LLMTransientError, TimeoutError):
    """Retryable LLM timeout, including an HTTP 408 response."""


class LLMNetworkError(LLMTransientError):
    """Retryable LLM DNS/connectivity/transport failure."""


class LLMRateLimitError(LLMTransientError):
    """Retryable provider throughput/rate-limit failure."""


class LLMQuotaError(LLMTransportError):
    """Non-retryable provider quota, credit, usage or spend-limit failure."""


class LLMProviderLimitError(LLMTransportError):
    """Provider limit failure that cannot be safely classified as transient."""


class LLMServerError(LLMTransientError):
    """Retryable LLM HTTP 5xx response."""


class LLMHTTPError(LLMTransportError):
    """Permanent LLM HTTP failure that must not be retried automatically."""


class LLMProviderError(AgentError):
    """The LLM provider returned an unusable or incomplete response envelope."""


class LLMOutputValidationError(AgentError):
    """The model output failed strict structured-output validation."""


class AgentContractViolationError(AgentError):
    """A validated strategic output violates an application-owned invariant."""
