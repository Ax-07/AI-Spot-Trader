from typing import Protocol

from ai_spot_trader.domain.models import (
    AgentInput,
    DecisionCandidate,
    ExecutionIntent,
    Fill,
    MarketObservation,
    MarketState,
)


class MarketObservationSource(Protocol):
    """Boundary implemented by providers that emit normalized market observations."""

    async def observation(self, symbol: str) -> MarketObservation: ...


class MarketDataSource(Protocol):
    """Boundary implemented by components exposing canonical market snapshots."""

    async def snapshot(self, symbol: str) -> MarketState: ...


class LLMProvider(Protocol):
    """Boundary implemented later by the configured Luna/Sol provider."""

    async def generate_decision(self, agent_input: AgentInput) -> DecisionCandidate: ...


class Broker(Protocol):
    """Execution boundary; only a PAPER implementation is allowed initially."""

    async def execute(self, intent: ExecutionIntent) -> tuple[Fill, ...]: ...
