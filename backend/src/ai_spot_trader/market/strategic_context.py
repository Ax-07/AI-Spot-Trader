from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

from ai_spot_trader.domain.models import (
    ExecutableMarket,
    StrategicCandleSnapshot,
    StrategicMarketTimeframes,
    StrategicMultiTimeframeContext,
    StrategicTimeframeContext,
    TradingStyleContext,
)
from ai_spot_trader.market.candles import Candle, CandleKey, CandleStreamService, CandleTimeframe

STRATEGIC_MULTI_TIMEFRAME_CONTEXT_VERSION = "strategic-mtf-v1"
MAX_STRATEGIC_CONTEXT_MARKETS = 32
MAX_STRATEGIC_CONTEXT_BYTES = 131_072
MAX_STRATEGIC_CONTEXT_CONCURRENCY = 4

# Historical depth is a data-volume bound, not a strategic preference. The style-to-timeframe
# mapping remains canonical in domain.experiments / TradingStyleContext.
STRATEGIC_HISTORY_DEPTH: dict[CandleTimeframe, int] = {
    CandleTimeframe.M1: 12,
    CandleTimeframe.M5: 12,
    CandleTimeframe.M15: 10,
    CandleTimeframe.M30: 8,
    CandleTimeframe.H1: 16,
    CandleTimeframe.H4: 12,
    CandleTimeframe.D1: 10,
}


class StrategicContextCapacityError(RuntimeError):
    """Raised when the bounded strategic context would exceed its explicit limits."""


class StrategicMultiTimeframeContextService:
    """Build compact causal summaries from the backend-owned canonical candle service."""

    def __init__(
        self,
        candle_service: CandleStreamService,
        *,
        max_markets: int = MAX_STRATEGIC_CONTEXT_MARKETS,
        max_serialized_bytes: int = MAX_STRATEGIC_CONTEXT_BYTES,
        max_concurrency: int = MAX_STRATEGIC_CONTEXT_CONCURRENCY,
    ) -> None:
        if isinstance(max_markets, bool) or max_markets <= 0:
            raise ValueError("max_markets must be a positive integer")
        if isinstance(max_serialized_bytes, bool) or max_serialized_bytes <= 0:
            raise ValueError("max_serialized_bytes must be a positive integer")
        if isinstance(max_concurrency, bool) or max_concurrency <= 0:
            raise ValueError("max_concurrency must be a positive integer")
        self._candles = candle_service
        self._max_markets = max_markets
        self._max_serialized_bytes = max_serialized_bytes
        self._max_concurrency = max_concurrency

    async def build(
        self,
        *,
        markets: tuple[ExecutableMarket, ...],
        trading_style_context: TradingStyleContext,
        as_of: datetime,
    ) -> StrategicMultiTimeframeContext:
        as_of = _utc(as_of)
        ordered_markets = tuple(
            sorted(markets, key=lambda market: (market.market_type.value, market.symbol))
        )
        if ordered_markets != markets:
            raise ValueError("strategic context markets must use deterministic sorted order")
        if not markets:
            raise ValueError("strategic context requires at least one market")
        if len(markets) > self._max_markets:
            raise StrategicContextCapacityError(
                f"strategic context supports at most {self._max_markets} markets"
            )

        requested_timeframes = tuple(
            CandleTimeframe(value) for value in trading_style_context.preferred_timeframes
        )
        for timeframe in requested_timeframes:
            if timeframe not in STRATEGIC_HISTORY_DEPTH:
                raise ValueError(f"unsupported strategic timeframe: {timeframe.value}")

        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def build_market(market: ExecutableMarket) -> StrategicMarketTimeframes:
            async def build_timeframe(timeframe: CandleTimeframe) -> StrategicTimeframeContext:
                async with semaphore:
                    depth = STRATEGIC_HISTORY_DEPTH[timeframe]
                    rows = await self._candles.history_as_of(
                        CandleKey(
                            symbol=market.symbol,
                            market_type=market.market_type,
                            timeframe=timeframe,
                        ),
                        as_of=as_of,
                        limit=depth,
                    )
                return _summarize_timeframe(
                    timeframe=timeframe,
                    requested_depth=depth,
                    rows=rows,
                    as_of=as_of,
                )

            series = tuple(
                await asyncio.gather(
                    *(build_timeframe(timeframe) for timeframe in requested_timeframes)
                )
            )
            return StrategicMarketTimeframes(
                symbol=market.symbol,
                market_type=market.market_type,
                timeframes=series,
            )

        market_contexts = tuple(await asyncio.gather(*(build_market(m) for m in markets)))
        total_candle_count = sum(
            timeframe.candle_count
            for market in market_contexts
            for timeframe in market.timeframes
        )
        context = StrategicMultiTimeframeContext(
            context_version=STRATEGIC_MULTI_TIMEFRAME_CONTEXT_VERSION,
            as_of=as_of,
            style=trading_style_context.style,
            style_mapping_version=trading_style_context.mapping_version,
            markets=market_contexts,
            total_candle_count=total_candle_count,
        )
        payload_size = len(context.model_dump_json().encode("utf-8"))
        if payload_size > self._max_serialized_bytes:
            raise StrategicContextCapacityError(
                "serialized strategic context exceeds "
                f"{self._max_serialized_bytes} bytes ({payload_size} bytes)"
            )
        return context


def _summarize_timeframe(
    *,
    timeframe: CandleTimeframe,
    requested_depth: int,
    rows: tuple[Candle, ...],
    as_of: datetime,
) -> StrategicTimeframeContext:
    if not rows:
        return StrategicTimeframeContext(
            timeframe=timeframe.value,
            availability="MISSING",
            requested_depth=requested_depth,
            candle_count=0,
            has_gaps=False,
            gap_count=0,
        )

    gap_count = 0
    for previous, current in zip(rows, rows[1:]):
        delta = current.open_time.astimezone(UTC) - previous.open_time.astimezone(UTC)
        if delta > timeframe.duration:
            gap_count += max(0, int(delta / timeframe.duration) - 1)

    latest = rows[-1]
    freshness_at = (
        latest.close_time.astimezone(UTC)
        if latest.is_final
        else latest.updated_at.astimezone(UTC)
    )
    is_stale = as_of - freshness_at > timeframe.duration * 2
    availability = (
        "AVAILABLE"
        if len(rows) >= requested_depth and gap_count == 0
        else "PARTIAL"
    )
    window_open = rows[0].open
    window_close = latest.close
    return StrategicTimeframeContext(
        timeframe=timeframe.value,
        availability=availability,
        requested_depth=requested_depth,
        candle_count=len(rows),
        covered_from=rows[0].open_time,
        covered_to=(
            latest.close_time
            if latest.is_final
            else min(latest.updated_at, latest.close_time)
        ),
        has_gaps=gap_count > 0,
        gap_count=gap_count,
        is_stale=is_stale,
        latest_candle=StrategicCandleSnapshot(
            open_time=latest.open_time,
            close_time=latest.close_time,
            open=latest.open,
            high=latest.high,
            low=latest.low,
            close=latest.close,
            volume=latest.volume,
            is_final=latest.is_final,
            updated_at=latest.updated_at,
        ),
        window_open=window_open,
        window_high=max(row.high for row in rows),
        window_low=min(row.low for row in rows),
        window_close=window_close,
        window_volume=sum((row.volume for row in rows), Decimal(0)),
        return_fraction=window_close / window_open - Decimal(1),
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("strategic context as_of must be timezone-aware")
    return value.astimezone(UTC)


__all__ = [
    "MAX_STRATEGIC_CONTEXT_BYTES",
    "MAX_STRATEGIC_CONTEXT_CONCURRENCY",
    "MAX_STRATEGIC_CONTEXT_MARKETS",
    "STRATEGIC_HISTORY_DEPTH",
    "STRATEGIC_MULTI_TIMEFRAME_CONTEXT_VERSION",
    "StrategicContextCapacityError",
    "StrategicMultiTimeframeContextService",
]
