"""PAPER broker implementation behind the canonical Broker port."""

from ai_spot_trader.broker.errors import (
    FuturePricingContextError,
    InvalidCanonicalSymbolError,
    InvalidExecutionTimeError,
    InvalidPaperCostModelError,
    PaperBrokerError,
    PricingContextError,
    PricingSymbolMismatchError,
)
from ai_spot_trader.broker.paper import PaperBroker
from ai_spot_trader.broker.pricing import (
    PaperExecutionCostModel,
    PaperExecutionEstimate,
    estimate_paper_execution,
)

__all__ = [
    "FuturePricingContextError",
    "InvalidCanonicalSymbolError",
    "InvalidExecutionTimeError",
    "InvalidPaperCostModelError",
    "PaperBroker",
    "PaperBrokerError",
    "PaperExecutionCostModel",
    "PaperExecutionEstimate",
    "PricingContextError",
    "PricingSymbolMismatchError",
    "estimate_paper_execution",
]
