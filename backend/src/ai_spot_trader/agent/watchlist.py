from __future__ import annotations

import json
from datetime import UTC
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai_spot_trader.agent.errors import AgentContractViolationError, LLMOutputValidationError
from ai_spot_trader.agent.provider import OpenAIDecisionProvider
from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.discovery import (
    MarketDiscoveryInput,
    WatchlistEntry,
    WatchlistSelection,
)

WATCHLIST_SELECTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "markets": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "minLength": 1},
                    "market_type": {"type": "string", "enum": ["SPOT", "PERPETUAL"]},
                    "rationale": {"type": "string", "minLength": 1},
                },
                "required": ["symbol", "market_type", "rationale"],
                "additionalProperties": False,
            },
        },
        "rationale": {"type": "string", "minLength": 1},
    },
    "required": ["markets", "rationale"],
    "additionalProperties": False,
}


class _EntryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    symbol: Annotated[str, Field(min_length=1)]
    market_type: str
    rationale: Annotated[str, Field(min_length=1)]


class _WatchlistPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    markets: list[_EntryPayload]
    rationale: Annotated[str, Field(min_length=1)]


class OpenAIWatchlistSelector:
    """Batch 19.4 adapter over the *same* OpenAIDecisionProvider instance.

    It intentionally reuses the provider's configured model, protected strategy client and clock;
    no second strategic agent or alternate model client is created.
    """

    def __init__(self, agent: OpenAIDecisionProvider) -> None:
        self._agent = agent

    async def select_watchlist(
        self,
        discovery_input: MarketDiscoveryInput,
    ) -> WatchlistSelection:
        # The provider already owns the canonical campaign client/model/clock. This adapter only
        # adds one structured-output phase to the same strategic Agent.
        raw_output = await self._agent._client.generate_structured_decision(  # noqa: SLF001
            model=self._agent._model,  # noqa: SLF001
            instructions="",
            input_text=discovery_input.model_dump_json(),
            schema=WATCHLIST_SELECTION_SCHEMA,
        )
        payload = _parse(raw_output)
        if not payload.markets:
            raise AgentContractViolationError("LLM watchlist cannot be empty")
        if not payload.rationale.strip():
            raise AgentContractViolationError("LLM watchlist requires a non-empty rationale")
        if len(payload.markets) > discovery_input.watchlist_limit:
            raise AgentContractViolationError("LLM watchlist exceeds configured limit")

        candidates = {candidate.market for candidate in discovery_input.candidates}
        entries: list[WatchlistEntry] = []
        seen: set[ExecutableMarket] = set()
        for item in payload.markets:
            if not item.rationale.strip():
                raise AgentContractViolationError(
                    "LLM watchlist entries require a non-empty rationale"
                )
            try:
                market_type = MarketType(item.market_type)
                market = ExecutableMarket(symbol=item.symbol, market_type=market_type)
            except ValueError as exc:
                raise AgentContractViolationError(
                    "LLM watchlist contains an invalid market"
                ) from exc
            if market not in candidates:
                raise AgentContractViolationError(
                    "LLM watchlist contains a market outside the candidate universe"
                )
            if market in seen:
                raise AgentContractViolationError("LLM watchlist contains duplicate markets")
            seen.add(market)
            entries.append(WatchlistEntry(market=market, rationale=item.rationale.strip()))

        selected_at = self._agent._clock.now()  # noqa: SLF001
        if selected_at.tzinfo is None or selected_at.utcoffset() is None:
            raise AgentContractViolationError("watchlist Agent clock must be timezone-aware")
        selected_at = selected_at.astimezone(UTC)
        if selected_at < discovery_input.created_at:
            raise AgentContractViolationError("watchlist selection predates discovery input")
        entries.sort(key=lambda entry: (entry.market.market_type.value, entry.market.symbol))
        return WatchlistSelection(
            discovery_id=discovery_input.discovery_id,
            selected_at=selected_at,
            entries=tuple(entries),
            rationale=payload.rationale.strip(),
        )


def _parse(raw_output: str) -> _WatchlistPayload:
    if not raw_output or not raw_output.strip():
        raise LLMOutputValidationError("LLM watchlist output is empty")
    try:
        decoded = json.loads(raw_output)
        return _WatchlistPayload.model_validate(decoded)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise LLMOutputValidationError("LLM watchlist output violates the schema") from exc
