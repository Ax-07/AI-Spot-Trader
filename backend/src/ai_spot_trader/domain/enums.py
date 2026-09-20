from enum import StrEnum


class TradingAction(StrEnum):
    """Strategic action emitted by the trading agent."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class ExecutionMode(StrEnum):
    """Execution modes currently allowed by the application."""

    PAPER = "PAPER"


class RiskDecision(StrEnum):
    """Deterministic Risk Engine outcome."""

    ALLOW = "ALLOW"
    MODIFY = "MODIFY"
    REJECT = "REJECT"


class LLMModel(StrEnum):
    """LLM selections supported by configuration."""

    LUNA = "gpt-5.6-luna"
    SOL = "gpt-5.6-sol"
