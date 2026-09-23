from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from decimal import Decimal
from typing import Protocol

import httpx

from ai_spot_trader.core.retry import (
    KRAKEN_PUBLIC_READ_RETRY_POLICY,
    RetryPolicy,
    Sleep,
    retry_async,
)
from ai_spot_trader.domain.models import DerivativeInstrument, MarketObservation
from ai_spot_trader.integrations.kraken.errors import (
    KrakenConnectionError,
    KrakenHTTPError,
    KrakenNetworkError,
    KrakenRateLimitError,
    KrakenServerError,
    KrakenTimeoutError,
    KrakenTransientError,
)
from ai_spot_trader.integrations.kraken.models import KrakenOhlcCandle
from ai_spot_trader.integrations.kraken.symbols import KrakenPairRegistry


class SpotRestSource(Protocol):
    async def fetch_pair_registry(self) -> KrakenPairRegistry: ...

    async def fetch_ohlc_history(
        self,
        symbol: str,
        *,
        interval_minutes: int,
        since: datetime,
    ) -> tuple[KrakenOhlcCandle, ...]: ...

    async def aclose(self) -> None: ...


class DerivativesRestSource(Protocol):
    async def fetch_instruments(self) -> tuple[DerivativeInstrument, ...]: ...

    async def fetch_ticker(
        self,
        instrument: DerivativeInstrument,
    ) -> tuple[datetime, Decimal, Decimal | None, Decimal | None]: ...

    async def fetch_mark_history(
        self,
        instrument: DerivativeInstrument,
        *,
        since: datetime,
        until: datetime,
    ) -> tuple[MarketObservation, ...]: ...

    async def aclose(self) -> None: ...


class RetryingKrakenSpotRestSource:
    """Retry only public read-only Spot REST calls; payload failures remain fail-closed."""

    def __init__(
        self,
        delegate: SpotRestSource,
        *,
        retry_policy: RetryPolicy = KRAKEN_PUBLIC_READ_RETRY_POLICY,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._delegate = delegate
        self._retry_policy = retry_policy
        self._sleep = sleep

    async def fetch_pair_registry(self) -> KrakenPairRegistry:
        return await self._call(
            "kraken_spot_asset_pairs",
            self._delegate.fetch_pair_registry,
        )

    async def fetch_ohlc_history(
        self,
        symbol: str,
        *,
        interval_minutes: int,
        since: datetime,
    ) -> tuple[KrakenOhlcCandle, ...]:
        async def operation() -> tuple[KrakenOhlcCandle, ...]:
            return await self._delegate.fetch_ohlc_history(
                symbol,
                interval_minutes=interval_minutes,
                since=since,
            )

        return await self._call("kraken_spot_ohlc", operation)

    async def aclose(self) -> None:
        await self._delegate.aclose()

    async def _call[T](self, operation_name: str, operation: AwaitableFactory[T]) -> T:
        return await _retry_kraken_read(
            operation,
            retry_policy=self._retry_policy,
            operation_name=operation_name,
            sleep=self._sleep,
        )


class RetryingKrakenDerivativesRestSource:
    """Retry only public read-only Derivatives REST calls before any ledger-side effect."""

    def __init__(
        self,
        delegate: DerivativesRestSource,
        *,
        retry_policy: RetryPolicy = KRAKEN_PUBLIC_READ_RETRY_POLICY,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._delegate = delegate
        self._retry_policy = retry_policy
        self._sleep = sleep

    async def fetch_instruments(self) -> tuple[DerivativeInstrument, ...]:
        return await self._call(
            "kraken_derivatives_instruments",
            self._delegate.fetch_instruments,
        )

    async def fetch_ticker(
        self,
        instrument: DerivativeInstrument,
    ) -> tuple[datetime, Decimal, Decimal | None, Decimal | None]:
        async def operation() -> tuple[datetime, Decimal, Decimal | None, Decimal | None]:
            return await self._delegate.fetch_ticker(instrument)

        return await self._call("kraken_derivatives_ticker", operation)

    async def fetch_mark_history(
        self,
        instrument: DerivativeInstrument,
        *,
        since: datetime,
        until: datetime,
    ) -> tuple[MarketObservation, ...]:
        async def operation() -> tuple[MarketObservation, ...]:
            return await self._delegate.fetch_mark_history(
                instrument,
                since=since,
                until=until,
            )

        return await self._call("kraken_derivatives_mark_history", operation)

    async def aclose(self) -> None:
        await self._delegate.aclose()

    async def _call[T](self, operation_name: str, operation: AwaitableFactory[T]) -> T:
        return await _retry_kraken_read(
            operation,
            retry_policy=self._retry_policy,
            operation_name=operation_name,
            sleep=self._sleep,
        )


type AwaitableFactory[T] = Callable[[], Awaitable[T]]


async def _retry_kraken_read[T](
    operation: AwaitableFactory[T],
    *,
    retry_policy: RetryPolicy,
    operation_name: str,
    sleep: Sleep,
) -> T:
    async def classified_operation() -> T:
        try:
            return await operation()
        except KrakenConnectionError as exc:
            classified = _classify_connection_error(exc)
            if classified is exc:
                raise
            raise classified from exc

    return await retry_async(
        classified_operation,
        policy=retry_policy,
        operation_name=operation_name,
        is_retryable=lambda exc: isinstance(exc, KrakenTransientError),
        sleep=sleep,
    )


def _classify_connection_error(exc: KrakenConnectionError) -> KrakenConnectionError:
    cause = _httpx_cause(exc)
    if isinstance(cause, httpx.TimeoutException):
        return KrakenTimeoutError("Kraken public request timed out")
    if isinstance(cause, httpx.HTTPStatusError):
        status_code = cause.response.status_code
        if status_code == 408:
            return KrakenTimeoutError(
                "Kraken public request timed out",
                status_code=status_code,
            )
        if status_code == 429:
            return KrakenRateLimitError(
                "Kraken public request was rate limited",
                status_code=status_code,
            )
        if 500 <= status_code <= 599:
            return KrakenServerError(
                "Kraken public request returned a server error",
                status_code=status_code,
            )
        return KrakenHTTPError(
            "Kraken public request returned a permanent HTTP error",
            status_code=status_code,
        )
    if isinstance(cause, httpx.TransportError):
        return KrakenNetworkError("Kraken public network request failed")
    return exc


def _httpx_cause(exc: BaseException) -> httpx.HTTPError | None:
    current: BaseException | None = exc.__cause__
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, httpx.HTTPError):
            return current
        current = current.__cause__ or current.__context__
    return None
