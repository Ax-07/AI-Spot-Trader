from typing import Protocol, runtime_checkable
from uuid import UUID

from ai_spot_trader.domain.models import PortfolioState
from ai_spot_trader.trading.engine import TradingCycleResult, TradingCycleStatus


@runtime_checkable
class CycleAuditWriter(Protocol):
    """Durable boundary receiving complete canonical cycle results."""

    async def ensure_available(self) -> None: ...

    async def record(self, result: TradingCycleResult) -> bool: ...


@runtime_checkable
class RunScopedCycleAuditWriter(Protocol):
    """Durable writer requiring an explicit PAPER run identity."""

    async def ensure_available_for_run(self, paper_run_id: UUID) -> None: ...

    async def record_for_run(
        self,
        paper_run_id: UUID,
        result: TradingCycleResult,
    ) -> bool: ...


class CurrentPaperRunProvider(Protocol):
    @property
    def current_run_id(self) -> UUID | None: ...


class MutablePaperPortfolio(Protocol):
    def snapshot(self) -> PortfolioState: ...

    def restore(self, state: PortfolioState) -> None: ...


class RunBoundCycleAuditWriter:
    """Bind the canonical audit writer to the run owned by the current backend lifetime."""

    def __init__(
        self,
        *,
        delegate: RunScopedCycleAuditWriter,
        run_provider: CurrentPaperRunProvider,
    ) -> None:
        self._delegate = delegate
        self._run_provider = run_provider

    @property
    def paper_run_id(self) -> UUID | None:
        return self._run_provider.current_run_id

    async def ensure_available(self) -> None:
        await self._delegate.ensure_available_for_run(self._require_run_id())

    async def record(self, result: TradingCycleResult) -> bool:
        return await self._delegate.record_for_run(self._require_run_id(), result)

    def _require_run_id(self) -> UUID:
        paper_run_id = self._run_provider.current_run_id
        if paper_run_id is None:
            raise RuntimeError("PAPER run is not initialized")
        return paper_run_id


class CycleRunner(Protocol):
    """Minimal orchestration surface required by the audited wrapper."""

    async def run_cycle(self) -> TradingCycleResult: ...


class CycleAuditUnavailableError(RuntimeError):
    """Raised once an audit failure has latched the runner fail-closed."""


class AuditedTradingCycleRunner:
    """Persist each cycle atomically with respect to the process-local PAPER ledger."""

    def __init__(
        self,
        *,
        delegate: CycleRunner,
        audit_writer: CycleAuditWriter | RunScopedCycleAuditWriter,
        paper_run_id: UUID | None = None,
        portfolio: MutablePaperPortfolio | None = None,
    ) -> None:
        if paper_run_id is not None and not isinstance(
            audit_writer, RunScopedCycleAuditWriter
        ):
            raise TypeError("paper_run_id requires a run-scoped audit writer")
        if paper_run_id is None and not isinstance(audit_writer, CycleAuditWriter):
            raise TypeError("audit writer requires an explicit paper_run_id")
        self._delegate = delegate
        self._audit_writer = audit_writer
        self._paper_run_id = paper_run_id
        self._portfolio = portfolio
        self._audit_failed = False

    @property
    def paper_run_id(self) -> UUID | None:
        return self._paper_run_id

    async def run_cycle(self) -> TradingCycleResult:
        if self._audit_failed:
            raise CycleAuditUnavailableError(
                "cycle audit is unavailable; restart after resolving persistence"
            )

        try:
            await self._ensure_available()
        except Exception:
            self._audit_failed = True
            raise

        checkpoint = self._portfolio.snapshot() if self._portfolio is not None else None
        try:
            result = await self._delegate.run_cycle()
        except Exception:
            self._restore(checkpoint)
            self._audit_failed = True
            raise

        # A FAILED cycle is audit evidence, not a committed ledger transition. This also rolls
        # back derivative mark/funding side effects produced before a later Agent/Risk failure.
        if result.status is TradingCycleStatus.FAILED:
            self._restore(checkpoint)

        try:
            inserted = await self._record(result)
        except Exception:
            self._restore(checkpoint)
            self._audit_failed = True
            raise
        if not inserted:
            # Exact audit replay is idempotent. It must not apply the same in-memory transition
            # twice if a deterministic test or caller reuses a cycle identity.
            self._restore(checkpoint)
        return result

    def _restore(self, checkpoint: PortfolioState | None) -> None:
        portfolio = self._portfolio
        if portfolio is not None and checkpoint is not None:
            portfolio.restore(checkpoint)

    async def _ensure_available(self) -> None:
        writer = self._audit_writer
        if self._paper_run_id is None:
            assert isinstance(writer, CycleAuditWriter)
            await writer.ensure_available()
            return
        assert isinstance(writer, RunScopedCycleAuditWriter)
        await writer.ensure_available_for_run(self._paper_run_id)

    async def _record(self, result: TradingCycleResult) -> bool:
        writer = self._audit_writer
        if self._paper_run_id is None:
            assert isinstance(writer, CycleAuditWriter)
            return await writer.record(result)
        assert isinstance(writer, RunScopedCycleAuditWriter)
        return await writer.record_for_run(self._paper_run_id, result)
