from typing import Protocol

from ai_spot_trader.trading.engine import TradingCycleResult


class CycleAuditWriter(Protocol):
    """Durable boundary receiving complete canonical cycle results."""

    async def record(self, result: TradingCycleResult) -> bool: ...


class CycleRunner(Protocol):
    """Minimal orchestration surface required by the audited wrapper."""

    async def run_cycle(self) -> TradingCycleResult: ...


class AuditedTradingCycleRunner:
    """Persist each canonical cycle result without changing trading semantics."""

    def __init__(self, *, delegate: CycleRunner, audit_writer: CycleAuditWriter) -> None:
        self._delegate = delegate
        self._audit_writer = audit_writer

    async def run_cycle(self) -> TradingCycleResult:
        result = await self._delegate.run_cycle()
        await self._audit_writer.record(result)
        return result
