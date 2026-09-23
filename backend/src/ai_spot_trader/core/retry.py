import asyncio
import logging
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

Sleep = Callable[[float], Awaitable[None]]
RetryPredicate = Callable[[Exception], bool]

logger = logging.getLogger("ai_spot_trader.retry")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Bounded retry policy for operations proven safe to repeat."""

    max_attempts: int
    base_delay_seconds: float
    max_delay_seconds: float

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_attempts, bool)
            or not isinstance(self.max_attempts, int)
            or self.max_attempts <= 0
        ):
            raise ValueError("max_attempts must be a positive integer")
        for name, value in (
            ("base_delay_seconds", self.base_delay_seconds),
            ("max_delay_seconds", self.max_delay_seconds),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a finite non-negative number")
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be a finite non-negative number")
        if self.base_delay_seconds > self.max_delay_seconds:
            raise ValueError("base_delay_seconds cannot exceed max_delay_seconds")

    def delay_after(self, failed_attempt: int) -> float:
        """Return the bounded exponential delay after one failed 1-based attempt."""

        if (
            isinstance(failed_attempt, bool)
            or not isinstance(failed_attempt, int)
            or failed_attempt <= 0
        ):
            raise ValueError("failed_attempt must be a positive integer")
        delay = self.base_delay_seconds * (2.0 ** (failed_attempt - 1))
        return float(min(delay, self.max_delay_seconds))


KRAKEN_PUBLIC_READ_RETRY_POLICY = RetryPolicy(
    max_attempts=3,
    base_delay_seconds=0.25,
    max_delay_seconds=1.0,
)

LLM_PRE_DECISION_RETRY_POLICY = RetryPolicy(
    max_attempts=2,
    base_delay_seconds=0.5,
    max_delay_seconds=1.0,
)


async def retry_async[T](
    operation: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy,
    operation_name: str,
    is_retryable: RetryPredicate,
    sleep: Sleep = asyncio.sleep,
) -> T:
    """Retry one operation within a bounded budget, logging only sanitized metadata."""

    if not operation_name.strip():
        raise ValueError("operation_name cannot be empty")

    for attempt in range(1, policy.max_attempts + 1):
        try:
            return await operation()
        except Exception as exc:
            retryable = is_retryable(exc)
            status_code = _status_code(exc)
            if not retryable:
                logger.error(
                    "network_operation_failed operation=%s attempt=%d max_attempts=%d "
                    "error_type=%s http_status=%s retryable=false",
                    operation_name,
                    attempt,
                    policy.max_attempts,
                    type(exc).__name__,
                    status_code,
                )
                raise
            if attempt >= policy.max_attempts:
                logger.error(
                    "network_retry_exhausted operation=%s attempts=%d error_type=%s "
                    "http_status=%s",
                    operation_name,
                    attempt,
                    type(exc).__name__,
                    status_code,
                )
                raise
            delay = policy.delay_after(attempt)
            logger.warning(
                "network_retry operation=%s attempt=%d max_attempts=%d error_type=%s "
                "http_status=%s delay_seconds=%.3f",
                operation_name,
                attempt,
                policy.max_attempts,
                type(exc).__name__,
                status_code,
                delay,
            )
            await sleep(delay)

    raise AssertionError("retry loop exhausted without returning or raising")


def _status_code(exc: Exception) -> str:
    value = getattr(exc, "status_code", None)
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return "-"
