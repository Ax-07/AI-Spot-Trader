import asyncio
import json
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast

from pydantic import BaseModel, JsonValue, ValidationError

from ai_spot_trader.core.clock import Clock, SystemClock
from ai_spot_trader.domain.models import AgentToolTrace, canonical_json_digest


class ReadOnlyToolError(RuntimeError):
    """Base error for the non-executable function-tool layer."""


class UnknownToolError(ReadOnlyToolError):
    """Raised when the model requests a function that is not registered."""


class MalformedToolArgumentsError(ReadOnlyToolError):
    """Raised when model-provided JSON arguments violate the strict contract."""


class ToolCallBudgetExceededError(ReadOnlyToolError):
    """Raised when the model exceeds the configured non-strategic tool budget."""


class ToolResultTooLargeError(ReadOnlyToolError):
    """Sanitized result used when a tool output exceeds the configured byte budget."""


ToolHandler = Callable[[BaseModel], Awaitable[JsonValue]]


@dataclass(frozen=True, slots=True)
class ReadOnlyFunctionTool:
    name: str
    description: str
    parameters: dict[str, Any]
    arguments_model: type[BaseModel]
    handler: ToolHandler

    def openai_definition(self) -> dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "strict": True,
        }


@dataclass(frozen=True, slots=True)
class ToolExecution:
    function_output: str
    trace: AgentToolTrace


@dataclass(frozen=True, slots=True)
class ToolLoopResult:
    output_text: str
    traces: tuple[AgentToolTrace, ...]


class ReadOnlyToolRegistry:
    """Strict bounded registry. It exposes facts only and owns no Risk/Broker dependency."""

    def __init__(
        self,
        tools: tuple[ReadOnlyFunctionTool, ...],
        *,
        timeout_seconds: float,
        max_result_bytes: int,
        clock: Clock | None = None,
    ) -> None:
        if not tools:
            raise ValueError("at least one read-only tool is required")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be a positive finite number")
        if (
            isinstance(max_result_bytes, bool)
            or not isinstance(max_result_bytes, int)
            or max_result_bytes < 128
        ):
            raise ValueError("max_result_bytes must be an integer of at least 128 bytes")
        by_name: dict[str, ReadOnlyFunctionTool] = {}
        for tool in tools:
            if not tool.name or tool.name in by_name:
                raise ValueError("read-only tool names must be non-empty and unique")
            by_name[tool.name] = tool
        self._tools = by_name
        self._timeout_seconds = float(timeout_seconds)
        self._max_result_bytes = max_result_bytes
        self._clock = clock or SystemClock()

    @property
    def registered_names(self) -> frozenset[str]:
        return frozenset(self._tools)

    @property
    def openai_tools(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._tools[name].openai_definition() for name in sorted(self._tools))

    async def execute(
        self,
        *,
        call_id: str,
        name: str,
        arguments_json: str,
    ) -> ToolExecution:
        if not call_id.strip():
            raise MalformedToolArgumentsError("tool call_id cannot be empty")
        tool = self._tools.get(name)
        if tool is None:
            raise UnknownToolError(f"unregistered tool: {name}")
        validated = self._validate_arguments(tool, arguments_json)
        arguments = cast(
            dict[str, JsonValue],
            validated.model_dump(mode="json", exclude_none=False),
        )
        started_at = self._now()
        status: Literal["SUCCESS", "ERROR"] = "SUCCESS"
        error_type: str | None = None
        try:
            async with asyncio.timeout(self._timeout_seconds):
                data = await tool.handler(validated)
            result: dict[str, JsonValue] = {"ok": True, "data": data}
            encoded = _canonical_json(result)
            if len(encoded.encode("utf-8")) > self._max_result_bytes:
                raise ToolResultTooLargeError("tool result exceeded configured byte budget")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            status = "ERROR"
            error_type = type(exc).__name__
            result = {"ok": False, "error": {"type": error_type}}
            encoded = _canonical_json(result)

        completed_at = self._now()
        digest = canonical_json_digest(result)
        trace = AgentToolTrace(
            call_id=call_id,
            tool_name=name,
            arguments=arguments,
            started_at=started_at,
            completed_at=completed_at,
            status=status,
            error_type=error_type,
            result=result,
            result_digest=digest,
        )
        return ToolExecution(function_output=encoded, trace=trace)

    def _validate_arguments(
        self,
        tool: ReadOnlyFunctionTool,
        arguments_json: str,
    ) -> BaseModel:
        try:
            parsed = json.loads(arguments_json)
        except (json.JSONDecodeError, TypeError) as exc:
            raise MalformedToolArgumentsError("tool arguments must be valid JSON") from exc
        if not isinstance(parsed, dict):
            raise MalformedToolArgumentsError("tool arguments must be a JSON object")
        try:
            return tool.arguments_model.model_validate(parsed)
        except ValidationError as exc:
            raise MalformedToolArgumentsError(
                "tool arguments violate the registered strict schema"
            ) from exc

    def _now(self) -> datetime:
        value = self._clock.now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ReadOnlyToolError("read-only tool clock must be timezone-aware")
        return value.astimezone(UTC)


def _canonical_json(value: JsonValue) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

