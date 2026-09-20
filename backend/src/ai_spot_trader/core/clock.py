from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Injectable source of timezone-aware technical timestamps."""

    def now(self) -> datetime: ...


class SystemClock:
    """Production clock returning current UTC time."""

    def now(self) -> datetime:
        return datetime.now(UTC)
