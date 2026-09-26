from __future__ import annotations

from ai_spot_trader.agent.provider import OpenAIDecisionProvider
from ai_spot_trader.domain.models import (
    AgentInput,
    AgentToolTrace,
    DecisionCandidate,
    ExecutableMarket,
    MarketSelection,
    MarketSelectionInput,
    StrategicMultiTimeframeContext,
)
from ai_spot_trader.market.strategic_context import StrategicMultiTimeframeContextService


class MultiTimeframeDecisionProvider:
    """Decorate the strategic Agent with one coherent causal candle snapshot per cycle.

    Discovery intentionally keeps using the undecorated provider. The rich candle context is built
    only for Market Selection (or the legacy one-market final decision) and the exact same snapshot
    is then reused by the final BUY/SELL/HOLD decision.
    """

    def __init__(
        self,
        delegate: OpenAIDecisionProvider,
        context_service: StrategicMultiTimeframeContextService,
    ) -> None:
        self._delegate = delegate
        self._context_service = context_service
        self._snapshots: dict[object, StrategicMultiTimeframeContext] = {}

    @property
    def last_tool_traces(self) -> tuple[AgentToolTrace, ...]:
        return self._delegate.last_tool_traces

    async def select_market(self, selection_input: MarketSelectionInput) -> MarketSelection:
        await self._attach_selection_context(selection_input)
        try:
            return await self._delegate.select_market(selection_input)
        except Exception:
            self._snapshots.pop(selection_input.cycle_id, None)
            raise

    async def select_management_market(
        self,
        selection_input: MarketSelectionInput,
        *,
        capacity_reason: str,
        management_markets: tuple[ExecutableMarket, ...],
    ) -> MarketSelection:
        await self._attach_selection_context(selection_input)
        try:
            return await self._delegate.select_management_market(
                selection_input,
                capacity_reason=capacity_reason,
                management_markets=management_markets,
            )
        except Exception:
            self._snapshots.pop(selection_input.cycle_id, None)
            raise

    async def generate_decision(self, agent_input: AgentInput) -> DecisionCandidate:
        await self._attach_final_context(agent_input)
        try:
            return await self._delegate.generate_decision(agent_input)
        finally:
            self._snapshots.pop(agent_input.cycle_id, None)

    async def generate_management_decision(
        self,
        agent_input: AgentInput,
        *,
        capacity_reason: str,
    ) -> DecisionCandidate:
        await self._attach_final_context(agent_input)
        try:
            return await self._delegate.generate_management_decision(
                agent_input,
                capacity_reason=capacity_reason,
            )
        finally:
            self._snapshots.pop(agent_input.cycle_id, None)

    async def _attach_selection_context(self, selection_input: MarketSelectionInput) -> None:
        style = selection_input.trading_style_context
        if style is None:
            return
        # TradingCycleRunner serializes cycles. Clearing here bounds retained failed-cycle state.
        self._snapshots.clear()
        context = await self._context_service.build(
            markets=selection_input.executable_markets,
            trading_style_context=style,
            as_of=selection_input.created_at,
        )
        selection_input.multi_timeframe_context = context
        # Validate after assignment because DomainModel intentionally does not enable
        # validate_assignment globally.
        MarketSelectionInput.model_validate(selection_input.model_dump(mode="python"))
        self._snapshots[selection_input.cycle_id] = context

    async def _attach_final_context(self, agent_input: AgentInput) -> None:
        style = agent_input.trading_style_context
        if style is None:
            return
        context = self._snapshots.get(agent_input.cycle_id)
        if context is None:
            context = await self._context_service.build(
                markets=(
                    ExecutableMarket(
                        symbol=agent_input.market_state.symbol,
                        market_type=agent_input.market_state.market_type,
                    ),
                ),
                trading_style_context=style,
                as_of=agent_input.created_at,
            )
        agent_input.multi_timeframe_context = context
        AgentInput.model_validate(agent_input.model_dump(mode="python"))


__all__ = ["MultiTimeframeDecisionProvider"]
