class RiskEngineError(Exception):
    """Base exception for technically invalid Risk Engine operation."""


class InvalidRiskTimeError(RiskEngineError, ValueError):
    """Raised when the injected assessment clock precedes the decision."""
