class ChatError(Exception):
    """Base error for the operator-chat boundary."""


class ChatTransportError(ChatError):
    """The chat LLM transport failed without exposing provider details."""


class ChatProviderError(ChatError):
    """The chat LLM response was unusable or incomplete."""


class ChatContextNotFoundError(ChatError):
    """A specifically requested historical cycle was not found."""


class ChatSessionNotFoundError(ChatError):
    """The requested process-local chat session no longer exists."""
