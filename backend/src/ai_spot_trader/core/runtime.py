import asyncio
from dataclasses import dataclass, field
from typing import Protocol


class StoppableTradingEngine(Protocol):
    """Narrow runtime dependency needed for cooperative application shutdown."""

    async def stop(self) -> None: ...


@dataclass(slots=True)
class AppRuntime:
    """Async runtime state owning the optional autonomous trading engine lifecycle."""

    shutdown_requested: asyncio.Event = field(default_factory=asyncio.Event)
    trading_engine: StoppableTradingEngine | None = None

    async def close(self) -> None:
        """Signal shutdown and await a configured engine without cancelling its active cycle."""

        self.shutdown_requested.set()
        if self.trading_engine is not None:
            await self.trading_engine.stop()
        await asyncio.sleep(0)
