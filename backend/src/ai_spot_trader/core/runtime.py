import asyncio
from dataclasses import dataclass, field


@dataclass(slots=True)
class AppRuntime:
    """Minimal async runtime state shared by future backend tasks."""

    shutdown_requested: asyncio.Event = field(default_factory=asyncio.Event)

    async def close(self) -> None:
        """Signal cooperative async tasks to stop during application shutdown."""

        self.shutdown_requested.set()
        await asyncio.sleep(0)
