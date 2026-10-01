from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_spot_trader.market.candles import Candle, CandleTimeframe


STRUCTURE_TIMEFRAMES: tuple[CandleTimeframe, ...] = (
    CandleTimeframe.M5,
    CandleTimeframe.M15,
    CandleTimeframe.H1,
    CandleTimeframe.H4,
)


class StructureModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SwingKind(StrEnum):
    HIGH = "HIGH"
    LOW = "LOW"


class SwingClassification(StrEnum):
    HH = "HH"
    HL = "HL"
    LH = "LH"
    LL = "LL"


class MarketStructureState(StrEnum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    RANGE = "RANGE"
    TRANSITION = "TRANSITION"
    UNKNOWN = "UNKNOWN"


class MultiTimeframeStructureState(StrEnum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    RANGE = "RANGE"
    TRANSITION = "TRANSITION"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


class StructureEvent(StrEnum):
    BOS_UP = "BOS_UP"
    BOS_DOWN = "BOS_DOWN"
    CHOCH_UP = "CHOCH_UP"
    CHOCH_DOWN = "CHOCH_DOWN"


class MarketStructurePolicy(StructureModel):
    """Bounded and causal policy for deterministic swing geometry."""

    history_limit: int = Field(default=100, ge=40, le=300)
    min_history_candles: int = Field(default=20, ge=7, le=100)
    pivot_left_bars: int = Field(default=2, ge=1, le=10)
    pivot_right_bars: int = Field(default=2, ge=1, le=10)
    equality_tolerance_bps: Decimal = Field(default=Decimal("2"), ge=0, le=100)
    swing_display_limit: int = Field(default=8, ge=4, le=20)
    fetch_concurrency: int = Field(default=8, ge=1, le=16)

    @model_validator(mode="after")
    def validate_policy(self) -> "MarketStructurePolicy":
        minimum = self.pivot_left_bars + self.pivot_right_bars + 3
        if self.min_history_candles < minimum:
            raise ValueError("min_history_candles is too small for the pivot confirmation window")
        if self.history_limit < self.min_history_candles:
            raise ValueError("history_limit must be >= min_history_candles")
        return self


class SwingPoint(StructureModel):
    kind: SwingKind
    price: Decimal = Field(gt=0)
    open_time: datetime
    confirmed_at: datetime
    classification: SwingClassification | None = None

    @model_validator(mode="after")
    def validate_times(self) -> "SwingPoint":
        for value, label in (
            (self.open_time, "open_time"),
            (self.confirmed_at, "confirmed_at"),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{label} must be timezone-aware")
        if self.confirmed_at.astimezone(UTC) <= self.open_time.astimezone(UTC):
            raise ValueError("a swing cannot be confirmed before or at its pivot open_time")
        return self


class TimeframeMarketStructure(StructureModel):
    timeframe: CandleTimeframe
    state: MarketStructureState = MarketStructureState.UNKNOWN
    event: StructureEvent | None = None
    history_count: int = Field(default=0, ge=0)
    latest_final_close: datetime | None = None
    confirmed_swing_highs: tuple[SwingPoint, ...] = ()
    confirmed_swing_lows: tuple[SwingPoint, ...] = ()
    swings: tuple[SwingPoint, ...] = ()
    sequence: tuple[SwingClassification, ...] = ()
    error_type: str | None = None


class MultiTimeframeMarketStructure(StructureModel):
    observed_at: datetime
    global_state: MultiTimeframeStructureState = MultiTimeframeStructureState.UNKNOWN
    timeframes: tuple[TimeframeMarketStructure, ...] = ()

    @model_validator(mode="after")
    def validate_observed_at(self) -> "MultiTimeframeMarketStructure":
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("market structure observed_at must be timezone-aware")
        return self

    def timeframe(self, timeframe: CandleTimeframe) -> TimeframeMarketStructure | None:
        return next((item for item in self.timeframes if item.timeframe is timeframe), None)


class MarketStructureAnalyzer:
    """Causal swing detector using finalized candles from one native timeframe."""

    def __init__(self, *, policy: MarketStructurePolicy | None = None) -> None:
        self.policy = policy or MarketStructurePolicy()

    def analyze(
        self,
        *,
        timeframe: CandleTimeframe,
        candles: tuple[Candle, ...],
        observed_at: datetime,
    ) -> TimeframeMarketStructure:
        observed_at = _utc(observed_at)
        final = tuple(
            sorted(
                (
                    candle
                    for candle in candles
                    if candle.timeframe is timeframe
                    and candle.is_final
                    and candle.close_time.astimezone(UTC) <= observed_at
                    and candle.updated_at.astimezone(UTC) <= observed_at
                ),
                key=lambda item: item.open_time,
            )
        )[-self.policy.history_limit :]

        latest_close = final[-1].close_time.astimezone(UTC) if final else None
        if len(final) < self.policy.min_history_candles:
            return TimeframeMarketStructure(
                timeframe=timeframe,
                history_count=len(final),
                latest_final_close=latest_close,
            )

        pivots = self._confirmed_pivots(final)
        classified = self._classify(pivots)
        highs = tuple(item for item in classified if item.kind is SwingKind.HIGH)
        lows = tuple(item for item in classified if item.kind is SwingKind.LOW)
        state = _structure_state(classified)
        event = _structure_event(classified, state)
        display = tuple(
            item for item in classified if item.classification is not None
        )[-self.policy.swing_display_limit :]
        sequence = tuple(
            item.classification for item in display if item.classification is not None
        )
        return TimeframeMarketStructure(
            timeframe=timeframe,
            state=state,
            event=event,
            history_count=len(final),
            latest_final_close=latest_close,
            confirmed_swing_highs=highs[-self.policy.swing_display_limit :],
            confirmed_swing_lows=lows[-self.policy.swing_display_limit :],
            swings=display,
            sequence=sequence,
        )

    def unknown(
        self,
        *,
        timeframe: CandleTimeframe,
        error_type: str | None = None,
    ) -> TimeframeMarketStructure:
        return TimeframeMarketStructure(timeframe=timeframe, error_type=error_type)

    def _confirmed_pivots(self, candles: tuple[Candle, ...]) -> tuple[SwingPoint, ...]:
        left = self.policy.pivot_left_bars
        right = self.policy.pivot_right_bars
        tolerance = self.policy.equality_tolerance_bps / Decimal("10000")
        found: list[tuple[int, SwingPoint]] = []

        # The upper bound intentionally excludes the most recent `right` finalized bars.
        # A pivot therefore exists only after its confirmation bars have themselves closed.
        for index in range(left, len(candles) - right):
            pivot = candles[index]
            neighbours = candles[index - left : index] + candles[index + 1 : index + right + 1]
            max_neighbour_high = max(item.high for item in neighbours)
            min_neighbour_low = min(item.low for item in neighbours)
            confirmation = candles[index + right].close_time.astimezone(UTC)

            if pivot.high > max_neighbour_high * (Decimal(1) + tolerance):
                found.append(
                    (
                        index,
                        SwingPoint(
                            kind=SwingKind.HIGH,
                            price=pivot.high,
                            open_time=pivot.open_time.astimezone(UTC),
                            confirmed_at=confirmation,
                        ),
                    )
                )
            if pivot.low < min_neighbour_low * (Decimal(1) - tolerance):
                found.append(
                    (
                        index,
                        SwingPoint(
                            kind=SwingKind.LOW,
                            price=pivot.low,
                            open_time=pivot.open_time.astimezone(UTC),
                            confirmed_at=confirmation,
                        ),
                    )
                )

        found.sort(key=lambda item: (item[0], 0 if item[1].kind is SwingKind.LOW else 1))
        return tuple(item for _index, item in found)

    def _classify(self, pivots: tuple[SwingPoint, ...]) -> tuple[SwingPoint, ...]:
        tolerance = self.policy.equality_tolerance_bps / Decimal("10000")
        previous: dict[SwingKind, SwingPoint] = {}
        result: list[SwingPoint] = []
        for pivot in pivots:
            prior = previous.get(pivot.kind)
            classification: SwingClassification | None = None
            if prior is not None:
                delta = (pivot.price - prior.price) / prior.price
                if abs(delta) > tolerance:
                    if pivot.kind is SwingKind.HIGH:
                        classification = (
                            SwingClassification.HH if delta > 0 else SwingClassification.LH
                        )
                    else:
                        classification = (
                            SwingClassification.HL if delta > 0 else SwingClassification.LL
                        )
            classified = pivot.model_copy(update={"classification": classification})
            result.append(classified)
            previous[pivot.kind] = classified
        return tuple(result)


def summarize_market_structures(
    *,
    observed_at: datetime,
    timeframes: Iterable[TimeframeMarketStructure],
) -> MultiTimeframeMarketStructure:
    ordered = tuple(timeframes)
    states = tuple(item.state for item in ordered if item.state is not MarketStructureState.UNKNOWN)
    if len(states) < 2:
        global_state = MultiTimeframeStructureState.UNKNOWN
    else:
        unique = set(states)
        if unique == {MarketStructureState.BULLISH}:
            global_state = MultiTimeframeStructureState.BULLISH
        elif unique == {MarketStructureState.BEARISH}:
            global_state = MultiTimeframeStructureState.BEARISH
        elif unique == {MarketStructureState.RANGE}:
            global_state = MultiTimeframeStructureState.RANGE
        elif unique == {MarketStructureState.TRANSITION}:
            global_state = MultiTimeframeStructureState.TRANSITION
        else:
            global_state = MultiTimeframeStructureState.MIXED
    return MultiTimeframeMarketStructure(
        observed_at=_utc(observed_at),
        global_state=global_state,
        timeframes=ordered,
    )


def _structure_state(pivots: tuple[SwingPoint, ...]) -> MarketStructureState:
    highs = tuple(
        item.classification
        for item in pivots
        if item.kind is SwingKind.HIGH and item.classification is not None
    )
    lows = tuple(
        item.classification
        for item in pivots
        if item.kind is SwingKind.LOW and item.classification is not None
    )

    if (
        len(highs) >= 2
        and len(lows) >= 2
        and highs[-2:] == (SwingClassification.HH, SwingClassification.HH)
        and lows[-2:] == (SwingClassification.HL, SwingClassification.HL)
    ):
        return MarketStructureState.BULLISH
    if (
        len(highs) >= 2
        and len(lows) >= 2
        and highs[-2:] == (SwingClassification.LH, SwingClassification.LH)
        and lows[-2:] == (SwingClassification.LL, SwingClassification.LL)
    ):
        return MarketStructureState.BEARISH

    recent = tuple(
        item.classification for item in pivots if item.classification is not None
    )[-6:]
    has_high_shift = SwingClassification.HH in recent and SwingClassification.LH in recent
    has_low_shift = SwingClassification.HL in recent and SwingClassification.LL in recent
    latest_high = highs[-1] if highs else None
    latest_low = lows[-1] if lows else None
    opposed_latest = (
        (latest_high is SwingClassification.HH and latest_low is SwingClassification.LL)
        or (latest_high is SwingClassification.LH and latest_low is SwingClassification.HL)
    )
    if has_high_shift or has_low_shift or opposed_latest:
        return MarketStructureState.TRANSITION

    # Repeated confirmed pivots that remain within the equality tolerance are descriptive range
    # evidence. They deliberately do not become HH/HL/LH/LL.
    if len(pivots) >= 6 and len(recent) <= 1:
        return MarketStructureState.RANGE
    return MarketStructureState.UNKNOWN


def _structure_event(
    pivots: tuple[SwingPoint, ...],
    state: MarketStructureState,
) -> StructureEvent | None:
    highs = tuple(
        item.classification
        for item in pivots
        if item.kind is SwingKind.HIGH and item.classification is not None
    )
    lows = tuple(
        item.classification
        for item in pivots
        if item.kind is SwingKind.LOW and item.classification is not None
    )
    if state is MarketStructureState.TRANSITION:
        if (
            highs
            and lows
            and highs[-1] is SwingClassification.LH
            and lows[-1] is SwingClassification.LL
            and (SwingClassification.HH in highs[:-1] or SwingClassification.HL in lows[:-1])
        ):
            return StructureEvent.CHOCH_DOWN
        if (
            highs
            and lows
            and highs[-1] is SwingClassification.HH
            and lows[-1] is SwingClassification.HL
            and (SwingClassification.LH in highs[:-1] or SwingClassification.LL in lows[:-1])
        ):
            return StructureEvent.CHOCH_UP
    if state is MarketStructureState.BULLISH and highs and highs[-1] is SwingClassification.HH:
        return StructureEvent.BOS_UP
    if state is MarketStructureState.BEARISH and lows and lows[-1] is SwingClassification.LL:
        return StructureEvent.BOS_DOWN
    return None


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("market structure timestamps must be timezone-aware")
    return value.astimezone(UTC)
