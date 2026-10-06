from __future__ import annotations

import logging
import sys
from typing import TextIO

_RUNTIME_HANDLER_MARKER = "_ai_spot_trader_runtime_handler"
_OPERATIONAL_LOGGERS = (
    "ai_spot_trader.agent.ollama",
    "ai_spot_trader.agent.planner",
    "ai_spot_trader.trading.cadence",
)
_QUIET_LOGGERS = (
    "httpx",
    "httpcore",
)


class _RuntimeLogFilter(logging.Filter):
    """Keep application INFO intentionally narrow while preserving every warning/error."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.WARNING:
            return True
        return record.name in _OPERATIONAL_LOGGERS


def configure_runtime_logging(
    level: str | int = "INFO",
    *,
    stream: TextIO | None = None,
) -> None:
    """Configure safe backend runtime logs without relying on a custom launch command.

    The application namespace stays WARNING by default. Only the Agent/Ollama/cadence loggers are
    explicitly enabled at the configured level, and one filtered application handler makes those
    records visible. ``httpx``/``httpcore`` stay at WARNING. Kraken therefore keeps warnings/errors
    while normal request chatter stays quiet.

    Propagation intentionally remains enabled so pytest ``caplog`` and external observability
    handlers can still observe records. The application handler is idempotent and filtered, so it
    does not turn the rest of the package into INFO noise.
    """

    resolved_level = _resolve_level(level)
    handler = _runtime_handler(stream=stream)
    handler.setLevel(logging.DEBUG)

    app_logger = logging.getLogger("ai_spot_trader")
    app_logger.setLevel(logging.WARNING)
    app_logger.propagate = True
    _ensure_handler(app_logger, handler)

    for name in _OPERATIONAL_LOGGERS:
        logger = logging.getLogger(name)
        logger.setLevel(resolved_level)
        logger.propagate = True

    kraken_logger = logging.getLogger("ai_spot_trader.integrations.kraken")
    kraken_logger.setLevel(logging.WARNING)
    kraken_logger.propagate = True

    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def _resolve_level(level: str | int) -> int:
    if isinstance(level, bool):
        raise ValueError("log level must be a logging level name or integer")
    if isinstance(level, int):
        return level
    candidate = logging.getLevelName(level.upper())
    if not isinstance(candidate, int):
        raise ValueError(f"unsupported log level: {level}")
    return candidate


def _runtime_handler(*, stream: TextIO | None) -> logging.StreamHandler[TextIO]:
    app_logger = logging.getLogger("ai_spot_trader")
    for handler in app_logger.handlers:
        if getattr(handler, _RUNTIME_HANDLER_MARKER, False):
            if stream is not None and handler.stream is not stream:
                handler.setStream(stream)
            return handler  # type: ignore[return-value]

    handler = logging.StreamHandler(stream or sys.stdout)
    setattr(handler, _RUNTIME_HANDLER_MARKER, True)
    handler.addFilter(_RuntimeLogFilter())
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    return handler


def _ensure_handler(
    logger: logging.Logger,
    handler: logging.Handler,
) -> None:
    if handler not in logger.handlers:
        logger.addHandler(handler)


__all__ = ["configure_runtime_logging"]
