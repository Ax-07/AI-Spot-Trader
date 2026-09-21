from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from ai_spot_trader.core.clock import Clock, SystemClock
from ai_spot_trader.domain.models import (
    MarketContext,
    MarketObservation,
    MarketState,
    MarketWindowStats,
)
from ai_spot_trader.market.errors import (
    DuplicateObservationError,
    EmptyMarketHistoryError,
    OutOfOrderObservationError,
    SymbolMismatchError,
)

DEFAULT_MARKET_HORIZONS: tuple[timedelta, ...] = (
    timedelta(minutes=5),
    timedelta(minutes=30),
)
DEFAULT_MAX_OBSERVATIONS = 10_000
MarketStateIdFactory = Callable[[], UUID]


class MarketStateBuilder:
    """Bounded in-memory aggregator for one canonical market symbol."""

    def __init__(
        self,
        *,
        horizons: Sequence[timedelta] = DEFAULT_MARKET_HORIZONS,
        max_observations: int = DEFAULT_MAX_OBSERVATIONS,
        stale_after: timedelta | None = None,
        clock: Clock | None = None,
        market_state_id_factory: MarketStateIdFactory = uuid4,
    ) -> None:
        if max_observations <= 0:
            raise ValueError("max_observations must be positive")
        if not horizons:
            raise ValueError("at least one market horizon is required")

        normalized_horizons = tuple(sorted(horizons))
        if len(set(normalized_horizons)) != len(normalized_horizons):
            raise ValueError("market horizons must be unique")
        if any(horizon <= timedelta(0) for horizon in normalized_horizons):
            raise ValueError("market horizons must be positive")
        if stale_after is not None and stale_after <= timedelta(0):
            raise ValueError("stale_after must be positive when configured")

        self._horizons = normalized_horizons
        self._max_observations = max_observations
        self._stale_after = stale_after
        self._clock = clock or SystemClock()
        self._market_state_id_factory = market_state_id_factory
        self._observations: list[MarketObservation] = []
        self._symbol: str | None = None

    @property
    def retained_observations(self) -> tuple[MarketObservation, ...]:
        """Return statistical history retained for deterministic window calculations."""

        return tuple(self._observations)

    def add_observation(self, observation: MarketObservation) -> None:
        """Append one statistical observation in strictly increasing timestamp order."""

        if self._symbol is None:
            self._symbol = observation.symbol
        elif observation.symbol != self._symbol:
            raise SymbolMismatchError(
                f"expected observation for {self._symbol}, received {observation.symbol}"
            )

        if self._observations:
            latest = self._observations[-1]
            if observation.observed_at == latest.observed_at:
                raise DuplicateObservationError(
                    f"duplicate observation timestamp: {observation.observed_at.isoformat()}"
                )
            if observation.observed_at < latest.observed_at:
                raise OutOfOrderObservationError(
                    "observations must be added in strictly increasing timestamp order"
                )

        self._observations.append(observation)
        overflow = len(self._observations) - self._max_observations
        if overflow > 0:
            del self._observations[:overflow]

    def extend(self, observations: Iterable[MarketObservation]) -> None:
        """Append several statistical observations using the same ordering checks."""

        for observation in observations:
            self.add_observation(observation)

    def build(
        self,
        *,
        as_of: datetime | None = None,
        current_observation: MarketObservation | None = None,
        statistics_as_of: datetime | None = None,
    ) -> MarketState:
        """Build one snapshot while keeping current price and statistics independent.

        Retained observations are the deterministic statistical series used by every
        descriptive window. ``current_observation`` is snapshot-only: when eligible it
        supplies the current ``last_price`` and freshness metadata, but it never changes
        observation counts, returns, ranges or realized volatility. ``statistics_as_of``
        can anchor those windows to the causal time of the fixed-granularity statistical
        series instead of the engine invocation time.
        """

        cutoff = _normalize_utc(as_of if as_of is not None else self._clock.now())
        statistics_cutoff = (
            _normalize_utc(statistics_as_of) if statistics_as_of is not None else cutoff
        )
        if statistics_cutoff > cutoff:
            raise ValueError("statistics_as_of cannot be newer than the snapshot time")

        snapshot_eligible = [
            observation
            for observation in self._observations
            if observation.observed_at <= cutoff
        ]
        statistical_eligible = [
            observation
            for observation in snapshot_eligible
            if observation.observed_at <= statistics_cutoff
        ]
        current = self._eligible_current_observation(
            current_observation,
            cutoff=cutoff,
            retained_eligible=snapshot_eligible,
        )
        if current is None and not snapshot_eligible:
            raise EmptyMarketHistoryError("no observation exists at or before the snapshot time")

        latest = current if current is not None else snapshot_eligible[-1]
        age = cutoff - latest.observed_at
        age_seconds = _timedelta_seconds(age)
        stale_after_seconds = (
            _timedelta_seconds(self._stale_after) if self._stale_after is not None else None
        )
        is_stale = (
            age_seconds > stale_after_seconds
            if stale_after_seconds is not None
            else None
        )
        windows = tuple(
            self._build_window(
                cutoff=statistics_cutoff,
                horizon=horizon,
                eligible=statistical_eligible,
            )
            for horizon in self._horizons
        )

        return MarketState(
            market_state_id=self._market_state_id_factory(),
            as_of=cutoff,
            symbol=latest.symbol,
            last_price=latest.last_price,
            context=MarketContext(
                last_observed_at=latest.observed_at,
                data_age_seconds=age_seconds,
                stale_after_seconds=stale_after_seconds,
                is_stale=is_stale,
                windows=windows,
            ),
        )

    def _eligible_current_observation(
        self,
        observation: MarketObservation | None,
        *,
        cutoff: datetime,
        retained_eligible: list[MarketObservation],
    ) -> MarketObservation | None:
        if observation is None or observation.observed_at > cutoff:
            return None
        if self._symbol is not None and observation.symbol != self._symbol:
            raise SymbolMismatchError(
                f"expected observation for {self._symbol}, received {observation.symbol}"
            )
        if not retained_eligible:
            return observation

        latest_history = retained_eligible[-1]
        if observation.observed_at == latest_history.observed_at:
            raise DuplicateObservationError(
                "current observation must be strictly newer than statistical history"
            )
        if observation.observed_at < latest_history.observed_at:
            raise OutOfOrderObservationError(
                "current observation must be newer than statistical history"
            )
        return observation

    def _build_window(
        self,
        *,
        cutoff: datetime,
        horizon: timedelta,
        eligible: list[MarketObservation],
    ) -> MarketWindowStats:
        window_start = cutoff - horizon
        observations = [
            observation
            for observation in eligible
            if observation.observed_at >= window_start
        ]
        history_spans_window = bool(eligible) and eligible[0].observed_at <= window_start
        horizon_seconds = _timedelta_seconds(horizon)

        if not observations:
            return MarketWindowStats(
                horizon_seconds=horizon_seconds,
                window_start=window_start,
                observation_count=0,
                is_complete=False,
            )

        prices = [observation.last_price for observation in observations]
        first = observations[0]
        last = observations[-1]
        min_price = min(prices)
        max_price = max(prices)
        return_fraction = (
            last.last_price / first.last_price - Decimal(1)
            if len(observations) >= 2
            else None
        )
        realized_volatility = (
            _realized_volatility(prices) if len(observations) >= 3 else None
        )

        return MarketWindowStats(
            horizon_seconds=horizon_seconds,
            window_start=window_start,
            observation_count=len(observations),
            is_complete=history_spans_window,
            first_observed_at=first.observed_at,
            last_observed_at=last.observed_at,
            first_price=first.last_price,
            last_price=last.last_price,
            min_price=min_price,
            max_price=max_price,
            price_range=max_price - min_price,
            return_fraction=return_fraction,
            realized_volatility=realized_volatility,
        )


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("snapshot time must be timezone-aware")
    return value.astimezone(UTC)


def _timedelta_seconds(value: timedelta) -> Decimal:
    if value < timedelta(0):
        raise ValueError("duration cannot be negative")
    whole_seconds = value.days * 86_400 + value.seconds
    return Decimal(whole_seconds) + Decimal(value.microseconds) / Decimal(1_000_000)


def _realized_volatility(prices: Sequence[Decimal]) -> Decimal:
    returns = [
        current / previous - Decimal(1)
        for previous, current in zip(prices, prices[1:], strict=False)
    ]
    mean = sum(returns, start=Decimal(0)) / Decimal(len(returns))
    variance = (
        sum(((value - mean) ** 2 for value in returns), start=Decimal(0))
        / Decimal(len(returns))
    )
    return variance.sqrt()
