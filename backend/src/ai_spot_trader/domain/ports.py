from typing import Protocol, runtime_checkable

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import (
    AgentInput,
    DecisionCandidate,
    ExecutionIntent,
    Fill,
    MarketObservation,
    MarketSelection,
    MarketSelectionInput,
    MarketState,
)


class MarketObservationSource(Protocol):
    """Boundary implemented by providers that emit normalized market observations."""

    async def observation(self, symbol: str) -> MarketObservation: ...


class MarketDataSource(Protocol):
    """Legacy/single-market boundary exposing canonical market snapshots by symbol."""

    async def snapshot(self, symbol: str) -> MarketState: ...


class ExecutableMarketDataSource(Protocol):
    """Typed execution-market router used after the Agent has selected a market."""

    async def snapshot(self, symbol: str, market_type: MarketType) -> MarketState: ...


class LLMProvider(Protocol):
    """Boundary implemented by the configured Luna/Sol strategic provider."""

    async def generate_decision(self, agent_input: AgentInput) -> DecisionCandidate: ...


@runtime_checkable
class MarketSelectingLLMProvider(LLMProvider, Protocol):
    """Same strategic Agent extended with an explicit executable-market selection phase."""

    async def select_market(self, selection_input: MarketSelectionInput) -> MarketSelection: ...


class Broker(Protocol):
    """Execution boundary; PAPER pricing context is explicit and provider-agnostic."""

    async def execute(
        self,
        intent: ExecutionIntent,
        market_state: MarketState,
    ) -> tuple[Fill, ...]: ...
