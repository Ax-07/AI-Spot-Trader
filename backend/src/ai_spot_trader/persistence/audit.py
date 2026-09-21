from typing import Protocol

from ai_spot_trader.trading.engine import TradingCycleResult


class CycleAuditWriter(Protocol):
    """Durable boundary receiving complete canonical cycle results."""

    async def ensure_available(self) -> None: ...

    async def record(self, result: TradingCycleResult) -> bool: ...


class CycleRunner(Protocol):
    """Minimal orchestration surface required by the audited wrapper."""

    async def run_cycle(self) -> TradingCycleResult: ...


class CycleAuditUnavailableError(RuntimeError):
    """Raised once an audit failure has latched the runner fail-closed."""


class AuditedTradingCycleRunner:
    """Preflight audit availability, persist every result, and fail closed on audit errors."""

    def __init__(self, *, delegate: CycleRunner, audit_writer: CycleAuditWriter) -> None:
        self._delegate = delegate
        self._audit_writer = audit_writer
        self._audit_failed = False

    async def run_cycle(self) -> TradingCycleResult:
        if self._audit_failed:
            raise CycleAuditUnavailableError(
                "cycle audit is unavailable; restart after resolving persistence"
            )

        try:
            await self._audit_writer.ensure_available()
        except Exception:
            self._audit_failed = True
            raise

        result = await self._delegate.run_cycle()
        try:
            await self._audit_writer.record(result)
        except Exception:
            self._audit_failed = True
            raise
        return result
