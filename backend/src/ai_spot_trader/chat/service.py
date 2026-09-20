import asyncio
import re
from collections import OrderedDict, deque
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Literal, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel

from ai_spot_trader.chat.errors import (
    ChatContextNotFoundError,
    ChatSessionNotFoundError,
)
from ai_spot_trader.chat.models import (
    ChatContextSnapshot,
    ChatExchangeResponse,
    ChatHistoryResponse,
    ChatMessage,
    ChatRole,
)
from ai_spot_trader.core.clock import Clock, SystemClock
from ai_spot_trader.core.runtime import AppRuntime
from ai_spot_trader.domain.enums import LLMModel
from ai_spot_trader.persistence.query import (
    AuditDataIntegrityError,
    AuditSortOrder,
    AuditStoreUnavailableError,
)

_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(
        r"(?i)\b(api[_ -]?key|token|secret|password)\s*[:=]\s*([^\s,;]{6,})"
    ),
)
_CYCLE_ID_PATTERN = re.compile(
    r"(?i)\bcycle(?:_id)?\s*(?:[:=#-]\s*)?"
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b"
)


class ChatProvider(Protocol):
    @property
    def model(self) -> LLMModel: ...

    async def reply(
        self,
        *,
        history: tuple[ChatMessage, ...],
        context: ChatContextSnapshot,
    ) -> str: ...


class RuntimeChatContextSource:
    """Build chat context only from canonical runtime and durable read surfaces."""

    def __init__(self, runtime: AppRuntime, *, clock: Clock | None = None) -> None:
        self._runtime = runtime
        self._clock = clock or SystemClock()

    async def load(self, *, context_cycle_id: UUID | None) -> ChatContextSnapshot:
        engine = _json_object(self._runtime.engine_snapshot())
        portfolio = _portfolio_snapshot(self._runtime)

        current_market: dict[str, object] | None = None
        recent_cycles: tuple[dict[str, object], ...] = ()
        historical_cycle: dict[str, object] | None = None
        historical_cycle_id: UUID | None = None
        audit_status: Literal["AVAILABLE", "UNCONFIGURED", "UNAVAILABLE", "INVALID"] = (
            "UNCONFIGURED"
        )
        reader = self._runtime.audit_reader
        if reader is not None:
            try:
                market_payload = await reader.latest_market_state()
                current_market = (
                    None if market_payload is None else _json_object(market_payload)
                )
                if context_cycle_id is None:
                    detail = await reader.latest_cycle()
                    page = await reader.list_cycles(
                        limit=8,
                        offset=0,
                        order=AuditSortOrder.DESC,
                    )
                    recent_cycles = tuple(_json_object(item) for item in page.items)
                else:
                    detail = await reader.get_cycle(context_cycle_id)
                    if detail is None:
                        raise ChatContextNotFoundError("historical cycle not found")
                if detail is not None:
                    historical_cycle = _json_object(detail)
                    historical_cycle_id = detail.cycle_id
                audit_status = "AVAILABLE"
            except AuditStoreUnavailableError:
                audit_status = "UNAVAILABLE"
            except AuditDataIntegrityError:
                audit_status = "INVALID"

        analytics_summary: dict[str, object] | None = None
        analytics_status: Literal[
            "AVAILABLE", "UNCONFIGURED", "UNAVAILABLE", "INVALID"
        ] = "UNCONFIGURED"
        analytics_reader = self._runtime.analytics_reader
        if analytics_reader is not None:
            try:
                report = await analytics_reader.paper_analytics()
                analytics_summary = _json_object(report.summary)
                analytics_status = "AVAILABLE"
            except AuditStoreUnavailableError:
                analytics_status = "UNAVAILABLE"
            except AuditDataIntegrityError:
                analytics_status = "INVALID"

        return ChatContextSnapshot(
            generated_at=self._clock.now(),
            engine=engine,
            current_market=current_market,
            current_portfolio=portfolio,
            recent_cycles=recent_cycles,
            historical_cycle=historical_cycle,
            historical_cycle_id=historical_cycle_id,
            analytics_summary=analytics_summary,
            audit_status=audit_status,
            analytics_status=analytics_status,
        )


class OperatorChatService:
    """Process-local bounded conversation service with no trading mutation surface."""

    def __init__(
        self,
        *,
        provider: ChatProvider,
        context_source: RuntimeChatContextSource,
        clock: Clock | None = None,
        max_messages: int = 20,
        max_sessions: int = 32,
    ) -> None:
        if max_messages < 2:
            raise ValueError("max_messages must be at least 2")
        if max_sessions < 1:
            raise ValueError("max_sessions must be positive")
        self._provider = provider
        self._context_source = context_source
        self._clock = clock or SystemClock()
        self._max_messages = max_messages
        self._max_sessions = max_sessions
        self._sessions: OrderedDict[UUID, deque[ChatMessage]] = OrderedDict()
        self._lock = asyncio.Lock()

    @property
    def model(self) -> LLMModel:
        return self._provider.model

    async def send_message(
        self,
        *,
        message: str,
        session_id: UUID | None = None,
        context_cycle_id: UUID | None = None,
    ) -> ChatExchangeResponse:
        safe_message = _redact_secrets(message)
        resolved_cycle_id = context_cycle_id or _extract_context_cycle_id(safe_message)
        context = await self._context_source.load(context_cycle_id=resolved_cycle_id)

        async with self._lock:
            resolved_session_id = session_id or uuid4()
            history = self._sessions.get(resolved_session_id)
            created_session = False
            if history is None:
                if session_id is not None:
                    raise ChatSessionNotFoundError("chat session not found")
                self._evict_session_if_needed()
                history = deque(maxlen=self._max_messages)
                self._sessions[resolved_session_id] = history
                created_session = True
            else:
                self._sessions.move_to_end(resolved_session_id)

            operator_message = ChatMessage(
                message_id=uuid4(),
                created_at=self._clock.now(),
                role=ChatRole.OPERATOR,
                content=safe_message,
            )
            prospective_history = (*history, operator_message)
            try:
                reply_text = await self._provider.reply(
                    history=prospective_history,
                    context=context,
                )
            except Exception:
                if created_session:
                    self._sessions.pop(resolved_session_id, None)
                raise
            agent_message = ChatMessage(
                message_id=uuid4(),
                created_at=self._clock.now(),
                role=ChatRole.AGENT,
                content=reply_text,
            )
            history.append(operator_message)
            history.append(agent_message)
            return ChatExchangeResponse(
                session_id=resolved_session_id,
                model=self._provider.model,
                historical_cycle_id=context.historical_cycle_id,
                operator_message=operator_message,
                agent_message=agent_message,
                history_size=len(history),
            )

    async def history(self, session_id: UUID) -> ChatHistoryResponse:
        async with self._lock:
            history = self._sessions.get(session_id)
            if history is None:
                raise ChatSessionNotFoundError("chat session not found")
            self._sessions.move_to_end(session_id)
            return ChatHistoryResponse(
                session_id=session_id,
                model=self._provider.model,
                messages=tuple(history),
                max_messages=self._max_messages,
            )

    def _evict_session_if_needed(self) -> None:
        while len(self._sessions) >= self._max_sessions:
            self._sessions.popitem(last=False)


def _extract_context_cycle_id(message: str) -> UUID | None:
    match = _CYCLE_ID_PATTERN.search(message)
    if match is None:
        return None
    try:
        return UUID(match.group(1))
    except ValueError:
        return None


def _redact_secrets(message: str) -> str:
    redacted = message.strip()
    for pattern in _SECRET_PATTERNS:
        if pattern.pattern.startswith("(?i)\\b(api"):
            redacted = pattern.sub(lambda match: f"{match.group(1)}=[REDACTED]", redacted)
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def _portfolio_snapshot(runtime: AppRuntime) -> dict[str, object] | None:
    portfolio = runtime.portfolio
    if portfolio is None:
        return None
    snapshot = portfolio.snapshot()
    if isinstance(snapshot, BaseModel):
        return _json_object(snapshot)
    if isinstance(snapshot, Mapping):
        return _json_object(dict(snapshot))
    return None


def _json_object(value: object) -> dict[str, object]:
    converted = _json_ready(value)
    if not isinstance(converted, dict):
        raise TypeError("chat context value must serialize to an object")
    return converted


def _json_ready(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        normalized = value.astimezone(UTC)
        return normalized.isoformat().replace("+00:00", "Z")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, BaseModel):
        return _json_ready(value.model_dump(mode="python"))
    if is_dataclass(value) and not isinstance(value, type):
        return _json_ready(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_json_ready(item) for item in value]
    raise TypeError(f"unsupported chat context value: {type(value).__name__}")
