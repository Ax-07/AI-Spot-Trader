from __future__ import annotations

import io
import logging

from ai_spot_trader.core.logging import configure_runtime_logging


LOGGER_NAMES = (
    "ai_spot_trader",
    "ai_spot_trader.agent.ollama",
    "ai_spot_trader.agent.planner",
    "ai_spot_trader.trading.cadence",
    "ai_spot_trader.integrations.kraken",
    "ai_spot_trader.integrations.kraken.rest",
    "httpx",
    "httpcore",
)


def _snapshot_logging_state():
    return {
        name: (
            logging.getLogger(name).level,
            logging.getLogger(name).propagate,
            list(logging.getLogger(name).handlers),
            {
                handler: getattr(handler, "stream", None)
                for handler in logging.getLogger(name).handlers
                if isinstance(handler, logging.StreamHandler)
            },
        )
        for name in LOGGER_NAMES
    }


def _restore_logging_state(snapshots) -> None:
    for name, (level, propagate, handlers, streams) in snapshots.items():
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.propagate = propagate
        logger.handlers[:] = handlers
        for handler, original_stream in streams.items():
            if original_stream is not None and handler.stream is not original_stream:
                handler.setStream(original_stream)


def test_runtime_logging_exposes_agent_and_scheduler_info_but_keeps_network_noise_quiet() -> None:
    snapshots = _snapshot_logging_state()
    stream = io.StringIO()
    try:
        configure_runtime_logging("INFO", stream=stream)
        configure_runtime_logging("INFO", stream=stream)

        logging.getLogger("ai_spot_trader.agent.ollama").info("OLLAMA_VISIBLE")
        logging.getLogger("ai_spot_trader.agent.planner").info("PLANNER_VISIBLE")
        logging.getLogger("ai_spot_trader.trading.cadence").info("CADENCE_VISIBLE")
        logging.getLogger("httpx").info("HTTPX_HIDDEN")
        logging.getLogger("httpcore").info("HTTPCORE_HIDDEN")
        logging.getLogger("ai_spot_trader.integrations.kraken.rest").info("KRAKEN_INFO_HIDDEN")
        logging.getLogger("ai_spot_trader.integrations.kraken.rest").warning(
            "KRAKEN_WARNING_VISIBLE"
        )

        output = stream.getvalue()
        assert output.count("OLLAMA_VISIBLE") == 1
        assert output.count("PLANNER_VISIBLE") == 1
        assert output.count("CADENCE_VISIBLE") == 1
        assert "HTTPX_HIDDEN" not in output
        assert "HTTPCORE_HIDDEN" not in output
        assert "KRAKEN_INFO_HIDDEN" not in output
        assert output.count("KRAKEN_WARNING_VISIBLE") == 1
    finally:
        _restore_logging_state(snapshots)


def test_runtime_logging_preserves_external_handler_propagation() -> None:
    snapshots = _snapshot_logging_state()
    records: list[logging.LogRecord] = []

    class CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    root = logging.getLogger()
    handler = CaptureHandler()
    original_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    try:
        configure_runtime_logging("INFO", stream=io.StringIO())
        logging.getLogger("ai_spot_trader.agent.ollama").info("EXTERNAL_VISIBLE")
        assert any(record.getMessage() == "EXTERNAL_VISIBLE" for record in records)
    finally:
        root.removeHandler(handler)
        root.setLevel(original_level)
        _restore_logging_state(snapshots)
