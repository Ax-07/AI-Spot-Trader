import inspect
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

import ai_spot_trader.market.state as market_state_module
from ai_spot_trader.domain.models import MarketObservation
from ai_spot_trader.market import (
    DuplicateObservationError,
    EmptyMarketHistoryError,
    MarketStateBuilder,
    OutOfOrderObservationError,
    SymbolMismatchError,
)

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
FIXED_ID = UUID("11111111-1111-1111-1111-111111111111")


@dataclass
class FixedClock:
    current: datetime

    def now(self) -> datetime:
        return self.current


def observation(minutes: int, price: str, *, symbol: str = "BTC/EUR") -> MarketObservation:
    return MarketObservation(
        observed_at=NOW + timedelta(minutes=minutes),
        symbol=symbol,
        last_price=Decimal(price),
    )


def test_build_market_state_with_default_horizons_and_fixed_clock() -> None:
    builder = MarketStateBuilder(
        clock=FixedClock(NOW),
        market_state_id_factory=lambda: FIXED_ID,
    )
    builder.extend(
        [
            observation(-31, "100"),
            observation(-5, "101"),
            observation(-1, "102"),
        ]
    )

    state = builder.build()

    assert state.market_state_id == FIXED_ID
    assert state.as_of == NOW
    assert state.symbol == "BTC/EUR"
    assert state.last_price == Decimal("102")
    assert state.context is not None
    assert state.context.last_observed_at == NOW - timedelta(minutes=1)
    assert state.context.data_age_seconds == Decimal("60")
    assert state.context.is_stale is None
    assert [window.horizon_seconds for window in state.context.windows] == [
        Decimal("300"),
        Decimal("1800"),
    ]


def test_no_look_ahead_excludes_observations_after_snapshot_cutoff() -> None:
    builder = MarketStateBuilder(horizons=(timedelta(minutes=30),))
    builder.extend([observation(0, "100"), observation(10, "200")])

    state = builder.build(as_of=NOW + timedelta(minutes=5))

    assert state.last_price == Decimal("100")
    assert state.context is not None
    window = state.context.windows[0]
    assert window.observation_count == 1
    assert window.max_price == Decimal("100")
    assert window.last_observed_at == NOW


def test_empty_history_and_future_only_history_are_explicit_errors() -> None:
    builder = MarketStateBuilder(horizons=(timedelta(minutes=5),))
    with pytest.raises(EmptyMarketHistoryError):
        builder.build(as_of=NOW)

    builder.add_observation(observation(1, "100"))
    with pytest.raises(EmptyMarketHistoryError):
        builder.build(as_of=NOW)


def test_one_observation_creates_partial_window_without_fake_derived_values() -> None:
    builder = MarketStateBuilder(horizons=(timedelta(minutes=5),))
    builder.add_observation(observation(-2, "100"))

    state = builder.build(as_of=NOW)

    assert state.context is not None
    window = state.context.windows[0]
    assert window.observation_count == 1
    assert not window.is_complete
    assert window.first_price == Decimal("100")
    assert window.last_price == Decimal("100")
    assert window.return_fraction is None
    assert window.realized_volatility is None


def test_window_can_be_complete_when_retained_history_spans_its_start() -> None:
    builder = MarketStateBuilder(horizons=(timedelta(minutes=5),))
    builder.extend(
        [
            observation(-6, "99"),
            observation(-5, "100"),
            observation(-1, "101"),
        ]
    )

    state = builder.build(as_of=NOW)

    assert state.context is not None
    window = state.context.windows[0]
    assert window.is_complete
    assert window.observation_count == 2


def test_window_statistics_use_decimal_return_range_and_realized_volatility() -> None:
    builder = MarketStateBuilder(horizons=(timedelta(minutes=5),))
    builder.extend(
        [
            observation(-6, "95"),
            observation(-3, "100"),
            observation(-2, "110"),
            observation(-1, "99"),
        ]
    )

    state = builder.build(as_of=NOW)

    assert state.context is not None
    window = state.context.windows[0]
    assert window.observation_count == 3
    assert window.min_price == Decimal("99")
    assert window.max_price == Decimal("110")
    assert window.price_range == Decimal("11")
    assert window.return_fraction == Decimal("-0.01")
    assert window.realized_volatility == Decimal("0.1")


def test_window_without_recent_observation_is_explicitly_empty() -> None:
    builder = MarketStateBuilder(horizons=(timedelta(minutes=5),))
    builder.add_observation(observation(-10, "100"))

    state = builder.build(as_of=NOW)

    assert state.context is not None
    window = state.context.windows[0]
    assert window.observation_count == 0
    assert not window.is_complete
    assert window.first_price is None
    assert window.return_fraction is None


def test_builder_marks_stale_data_only_when_threshold_is_supplied() -> None:
    builder = MarketStateBuilder(
        horizons=(timedelta(minutes=5),),
        stale_after=timedelta(seconds=10),
    )
    builder.add_observation(
        MarketObservation(
            observed_at=NOW - timedelta(seconds=11),
            symbol="BTC/EUR",
            last_price=Decimal("100"),
        )
    )

    state = builder.build(as_of=NOW)

    assert state.context is not None
    assert state.context.data_age_seconds == Decimal("11")
    assert state.context.stale_after_seconds == Decimal("10")
    assert state.context.is_stale is True


def test_history_is_bounded_and_oldest_observations_are_purged() -> None:
    builder = MarketStateBuilder(
        horizons=(timedelta(minutes=30),),
        max_observations=3,
    )
    builder.extend(
        [
            observation(-3, "97"),
            observation(-2, "98"),
            observation(-1, "99"),
            observation(0, "100"),
        ]
    )

    retained = builder.retained_observations
    assert len(retained) == 3
    assert retained[0].last_price == Decimal("98")
    assert retained[-1].last_price == Decimal("100")


def test_out_of_order_and_duplicate_observations_are_rejected() -> None:
    builder = MarketStateBuilder(horizons=(timedelta(minutes=5),))
    builder.add_observation(observation(-1, "100"))

    with pytest.raises(DuplicateObservationError):
        builder.add_observation(observation(-1, "101"))
    with pytest.raises(OutOfOrderObservationError):
        builder.add_observation(observation(-2, "99"))


def test_symbol_mismatch_is_rejected() -> None:
    builder = MarketStateBuilder(horizons=(timedelta(minutes=5),))
    builder.add_observation(observation(-1, "100"))

    with pytest.raises(SymbolMismatchError):
        builder.add_observation(observation(0, "200", symbol="ETH/EUR"))


def test_snapshot_cutoff_must_be_timezone_aware_and_is_normalized_to_utc() -> None:
    builder = MarketStateBuilder(horizons=(timedelta(minutes=5),))
    builder.add_observation(observation(-1, "100"))

    with pytest.raises(ValueError, match="timezone-aware"):
        builder.build(as_of=datetime(2026, 9, 20, 12, 0))

    paris = timezone(timedelta(hours=2))
    state = builder.build(as_of=datetime(2026, 9, 20, 14, 0, tzinfo=paris))
    assert state.as_of == NOW
    assert state.as_of.tzinfo is UTC


def test_horizons_and_limits_must_be_valid() -> None:
    with pytest.raises(ValueError, match="at least one"):
        MarketStateBuilder(horizons=())
    with pytest.raises(ValueError, match="unique"):
        MarketStateBuilder(horizons=(timedelta(minutes=5), timedelta(minutes=5)))
    with pytest.raises(ValueError, match="positive"):
        MarketStateBuilder(horizons=(timedelta(0),))
    with pytest.raises(ValueError, match="max_observations"):
        MarketStateBuilder(max_observations=0)
    with pytest.raises(ValueError, match="stale_after"):
        MarketStateBuilder(stale_after=timedelta(0))


def test_market_layer_has_no_kraken_dependency_or_trading_action_output() -> None:
    source = inspect.getsource(market_state_module)
    assert "integrations.kraken" not in source
    assert "Kraken" not in source

    builder = MarketStateBuilder(horizons=(timedelta(minutes=5),))
    builder.add_observation(observation(0, "100"))
    state = builder.build(as_of=NOW)
    payload = state.model_dump()
    assert "action" not in payload
    assert "signal" not in payload
