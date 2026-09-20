from datetime import UTC

from ai_spot_trader.core.clock import SystemClock


def test_system_clock_returns_utc_aware_timestamp() -> None:
    now = SystemClock().now()

    assert now.tzinfo is UTC
    assert now.utcoffset() is not None
