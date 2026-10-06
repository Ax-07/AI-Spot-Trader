from __future__ import annotations

import copy
import json
import math
import re
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Iterator, Literal
from uuid import UUID, uuid4

JsonObject = dict[str, object]
LLMCallCategory = Literal[
    "MARKET_DISCOVERY",
    "STRATEGIC_MULTI_MARKET_PLAN",
    "STRATEGIC_SINGLETON",
    "OPERATOR_CHAT",
    "UNKNOWN",
]
LLMAuditProvider = Literal["OPENAI", "OLLAMA"]
LLMAuditStatus = Literal["SUCCESS", "ERROR"]

_MAX_RECORDS = 200
_MAX_RECORD_BYTES = 512_000
_SECRET_VALUE_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)\b(api[_ -]?key|token|secret|password)\s*[:=]\s*([^\s,;]{6,})"),
    re.compile(r"(?i)postgres(?:ql)?(?:\+asyncpg)?://[^\s]+"),
)


@dataclass(frozen=True, slots=True)
class LLMAuditContext:
    session_id: UUID | None = None
    cycle_id: UUID | None = None
    discovery_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class LLMAuditRecord:
    audit_id: UUID
    recorded_at: datetime
    sequence: int
    category: LLMCallCategory
    provider: LLMAuditProvider
    model: str
    # SUCCESS means that the LLM transport/provider call completed successfully. It does not mean
    # that Pydantic, Agent business validation, Risk or Broker subsequently accepted the decision.
    status: LLMAuditStatus
    error_type: str | None
    latency_ms: float | None
    session_id: UUID | None
    cycle_id: UUID | None
    discovery_id: UUID | None
    request: JsonObject
    response_output: tuple[JsonObject, ...]
    response_text: str | None


_context: ContextVar[LLMAuditContext] = ContextVar(
    "llm_audit_context", default=LLMAuditContext()
)


@contextmanager
def llm_audit_context(
    *,
    session_id: UUID | None = None,
    cycle_id: UUID | None = None,
    discovery_id: UUID | None = None,
) -> Iterator[None]:
    current = _context.get()
    token = _context.set(
        LLMAuditContext(
            session_id=session_id or current.session_id,
            cycle_id=cycle_id or current.cycle_id,
            discovery_id=discovery_id or current.discovery_id,
        )
    )
    try:
        yield
    finally:
        _context.reset(token)


def current_llm_audit_context() -> LLMAuditContext:
    return _context.get()


class InMemoryLLMAuditStore:
    """Best-effort bounded process-local trace of payloads sent to an LLM provider."""

    def __init__(
        self,
        *,
        max_records: int = _MAX_RECORDS,
        max_record_bytes: int = _MAX_RECORD_BYTES,
    ) -> None:
        if max_records < 1 or max_record_bytes < 1:
            raise ValueError("LLM audit bounds must be positive")
        self._records: deque[LLMAuditRecord] = deque(maxlen=max_records)
        self._max_record_bytes = max_record_bytes
        self._lock = Lock()
        self._sequence = 0

    def append(
        self,
        *,
        request: JsonObject,
        response: JsonObject,
        provider: LLMAuditProvider = "OPENAI",
        status: LLMAuditStatus = "SUCCESS",
        error_type: str | None = None,
        latency_ms: float | None = None,
    ) -> None:
        if latency_ms is not None and (
            isinstance(latency_ms, bool)
            or not isinstance(latency_ms, (int, float))
            or not math.isfinite(latency_ms)
            or latency_ms < 0
        ):
            raise ValueError("latency_ms must be a finite non-negative number")
        sanitized_request = _sanitize_request(request)
        output = _response_output(response)
        response_text = _response_text(output)
        category, inferred = _classify_request(sanitized_request)
        explicit = current_llm_audit_context()
        record = LLMAuditRecord(
            audit_id=uuid4(),
            recorded_at=datetime.now(UTC),
            sequence=0,
            category=category,
            provider=provider,
            model=str(sanitized_request.get("model", "")),
            status=status,
            error_type=error_type,
            latency_ms=None if latency_ms is None else float(latency_ms),
            session_id=explicit.session_id,
            cycle_id=explicit.cycle_id or inferred.cycle_id,
            discovery_id=explicit.discovery_id or inferred.discovery_id,
            request=sanitized_request,
            response_output=output,
            response_text=response_text,
        )
        if _encoded_size(record) > self._max_record_bytes:
            return
        with self._lock:
            self._sequence += 1
            self._records.append(
                LLMAuditRecord(
                    audit_id=record.audit_id,
                    recorded_at=record.recorded_at,
                    sequence=self._sequence,
                    category=record.category,
                    provider=record.provider,
                    model=record.model,
                    status=record.status,
                    error_type=record.error_type,
                    latency_ms=record.latency_ms,
                    session_id=record.session_id,
                    cycle_id=record.cycle_id,
                    discovery_id=record.discovery_id,
                    request=record.request,
                    response_output=record.response_output,
                    response_text=record.response_text,
                )
            )

    def list_records(
        self,
        *,
        limit: int = 100,
        category: str | None = None,
        cycle_id: UUID | None = None,
        session_id: UUID | None = None,
        discovery_id: UUID | None = None,
    ) -> tuple[LLMAuditRecord, ...]:
        with self._lock:
            values = tuple(self._records)
        filtered = (
            item
            for item in reversed(values)
            if (category is None or item.category == category)
            and (cycle_id is None or item.cycle_id == cycle_id)
            and (session_id is None or item.session_id == session_id)
            and (discovery_id is None or item.discovery_id == discovery_id)
        )
        return tuple(list(filtered)[:limit])

    def clear_for_tests(self) -> None:
        with self._lock:
            self._records.clear()
            self._sequence = 0


GLOBAL_LLM_AUDIT_STORE = InMemoryLLMAuditStore()


def _sanitize_request(request: JsonObject) -> JsonObject:
    # Transport payloads contain no credentials by design. Defensive filtering prevents a future
    # caller from accidentally making transport/database secrets visible in the cockpit.
    copied = copy.deepcopy(request)
    for forbidden in (
        "authorization",
        "api_key",
        "openai_api_key",
        "database_url",
        "connection_string",
    ):
        _drop_key_recursive(copied, forbidden)
    _redact_values_recursive(copied)
    return copied


def _drop_key_recursive(value: object, forbidden: str) -> None:
    if isinstance(value, dict):
        for key in tuple(value):
            if str(key).lower() == forbidden:
                value.pop(key, None)
            else:
                _drop_key_recursive(value[key], forbidden)
    elif isinstance(value, list):
        for item in value:
            _drop_key_recursive(item, forbidden)


def _redact_values_recursive(value: object) -> object:
    if isinstance(value, dict):
        for key, item in tuple(value.items()):
            value[key] = _redact_values_recursive(item)
        return value
    if isinstance(value, list):
        for index, item in enumerate(value):
            value[index] = _redact_values_recursive(item)
        return value
    if isinstance(value, str):
        redacted = value
        for pattern in _SECRET_VALUE_PATTERNS:
            redacted = pattern.sub("[REDACTED]", redacted)
        return redacted
    return value


def _classify_request(request: JsonObject) -> tuple[LLMCallCategory, LLMAuditContext]:
    payload = _initial_input_payload(_request_input(request))
    if payload is None:
        return "UNKNOWN", LLMAuditContext()
    cycle_id = _uuid(payload.get("cycle_id"))
    discovery_id = _uuid(payload.get("discovery_id"))
    if "chat_history" in payload and "canonical_context" in payload:
        return "OPERATOR_CHAT", LLMAuditContext(
            cycle_id=_nested_uuid(payload, "canonical_context", "historical_cycle_id")
        )
    if "market_discovery_context" in payload or (
        discovery_id is not None and "candidates" in payload
    ):
        return "MARKET_DISCOVERY", LLMAuditContext(discovery_id=discovery_id)
    if "strategic_plan_contract" in payload:
        return "STRATEGIC_MULTI_MARKET_PLAN", LLMAuditContext(cycle_id=cycle_id)
    if cycle_id is not None:
        return "STRATEGIC_SINGLETON", LLMAuditContext(cycle_id=cycle_id)
    return "UNKNOWN", LLMAuditContext()


def _request_input(request: JsonObject) -> object:
    if "input" in request:
        return request.get("input")
    messages = request.get("messages")
    if not isinstance(messages, list):
        return None
    for item in messages:
        if isinstance(item, dict) and item.get("role") == "user":
            return item.get("content")
    return None


def _initial_input_payload(value: object) -> JsonObject | None:
    candidate: object = value
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, dict) and first.get("role") == "user":
            candidate = first.get("content")
    if not isinstance(candidate, str):
        return None
    try:
        decoded = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


def _nested_uuid(payload: JsonObject, parent: str, key: str) -> UUID | None:
    nested = payload.get(parent)
    return _uuid(nested.get(key)) if isinstance(nested, dict) else None


def _uuid(value: object) -> UUID | None:
    try:
        return UUID(str(value)) if value is not None else None
    except ValueError:
        return None


def _response_output(response: JsonObject) -> tuple[JsonObject, ...]:
    raw = response.get("output")
    if isinstance(raw, list):
        return tuple(
            _sanitize_response_item(item) for item in raw if isinstance(item, dict)
        )
    message = response.get("message")
    if isinstance(message, dict):
        return (_sanitize_response_item(message),)
    return ()


def _sanitize_response_item(item: dict[str, object]) -> JsonObject:
    """Return public/auditable provider output without hidden reasoning payloads."""

    copied = copy.deepcopy(item)
    _drop_key_recursive(copied, "thinking")
    return copied


def _response_text(output: tuple[JsonObject, ...]) -> str | None:
    texts: list[str] = []
    for item in output:
        # Ollama native /api/chat message. `thinking` has already been removed above.
        direct_content = item.get("content")
        if isinstance(direct_content, str) and direct_content.strip():
            texts.append(direct_content)
            continue

        # OpenAI Responses API message.
        if item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if (
                isinstance(part, dict)
                and part.get("type") == "output_text"
                and isinstance(part.get("text"), str)
            ):
                texts.append(str(part["text"]))
    return texts[0] if len(texts) == 1 else None


def _encoded_size(record: LLMAuditRecord) -> int:
    payload = {
        "provider": record.provider,
        "model": record.model,
        "status": record.status,
        "error_type": record.error_type,
        "latency_ms": record.latency_ms,
        "request": record.request,
        "response_output": record.response_output,
        "response_text": record.response_text,
    }
    return len(json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"))
