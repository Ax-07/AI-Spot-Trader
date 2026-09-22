from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from ai_spot_trader.core.clock import Clock
from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.market.research import MarketResearchService
from ai_spot_trader.tools.read_only import (
    ReadOnlyFunctionTool,
    ReadOnlyToolRegistry,
    ToolHandler,
)


class _ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ListMarketsArguments(_ToolArguments):
    market_type: Literal["ALL", "SPOT", "PERPETUAL", "FUTURE"]
    cursor: int = Field(ge=0)
    limit: int = Field(gt=0)


class GetMarketSnapshotArguments(_ToolArguments):
    symbol: str = Field(min_length=3, max_length=64)
    market_type: Literal["SPOT", "PERPETUAL"]


def build_market_research_tool_registry(
    service: MarketResearchService,
    *,
    timeout_seconds: float,
    max_result_bytes: int,
    clock: Clock | None = None,
) -> ReadOnlyToolRegistry:
    """Build the only Agent-visible Batch 18.1 registry: factual public market reads."""

    class _BoundedListMarketsArguments(_ToolArguments):
        market_type: Literal["ALL", "SPOT", "PERPETUAL", "FUTURE"]
        cursor: int = Field(ge=0)
        limit: int = Field(gt=0, le=service.max_list_limit)

    async def list_markets(raw: BaseModel) -> JsonValue:
        args = cast(ListMarketsArguments, raw)
        market_type = (
            None if args.market_type == "ALL" else MarketType(args.market_type)
        )
        page = await service.list_markets(
            market_type=market_type,
            cursor=args.cursor,
            limit=args.limit,
        )
        return cast(JsonValue, page.model_dump(mode="json"))

    async def get_market_snapshot(raw: BaseModel) -> JsonValue:
        args = cast(GetMarketSnapshotArguments, raw)
        snapshot = await service.get_market_snapshot(
            symbol=args.symbol,
            market_type=MarketType(args.market_type),
        )
        return cast(JsonValue, snapshot.model_dump(mode="json"))

    list_schema = {
        "type": "object",
        "properties": {
            "market_type": {
                "type": "string",
                "enum": ["ALL", "SPOT", "PERPETUAL", "FUTURE"],
                "description": (
                    "Factual product-family filter; ALL performs no strategic selection."
                ),
            },
            "cursor": {"type": "integer", "minimum": 0},
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": service.max_list_limit,
            },
        },
        "required": ["market_type", "cursor", "limit"],
        "additionalProperties": False,
    }
    snapshot_schema = {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "minLength": 3,
                "maxLength": 64,
                "description": "Canonical BASE/QUOTE symbol chosen by the Agent for research.",
            },
            "market_type": {
                "type": "string",
                "enum": ["SPOT", "PERPETUAL"],
            },
        },
        "required": ["symbol", "market_type"],
        "additionalProperties": False,
    }
    return ReadOnlyToolRegistry(
        (
            ReadOnlyFunctionTool(
                name="list_markets",
                description=(
                    "List public Kraken markets and factual metadata with deterministic "
                    "alphabetical pagination. No opportunity score, ranking or momentum filter."
                ),
                parameters=list_schema,
                arguments_model=_BoundedListMarketsArguments,
                handler=cast(ToolHandler, list_markets),
            ),
            ReadOnlyFunctionTool(
                name="get_market_snapshot",
                description=(
                    "Read one bounded normalized market snapshot using the canonical market-state "
                    "calculations. This is read-only and cannot place or authorize an order."
                ),
                parameters=snapshot_schema,
                arguments_model=GetMarketSnapshotArguments,
                handler=cast(ToolHandler, get_market_snapshot),
            ),
        ),
        timeout_seconds=timeout_seconds,
        max_result_bytes=max_result_bytes,
        clock=clock,
    )
