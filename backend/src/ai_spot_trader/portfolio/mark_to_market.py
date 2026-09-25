import asyncio
import math
from collections.abc import Iterable

from ai_spot_trader.domain.ports import MarketDataSource, MarketObservationSource
from ai_spot_trader.domain.symbols import parse_canonical_symbol
from ai_spot_trader.portfolio.ledger import PaperPortfolioLedger


class PaperSpotMarkToMarketMonitor:
    """Refresh held SPOT positions from public market observations without invoking the Agent."""

    def __init__(
        self,
        *,
        market_data: MarketObservationSource,
        portfolio: PaperPortfolioLedger,
        settlement_asset: str,
        executable_symbols: Iterable[str],
        cadence_seconds: float,
        timeout_seconds: float,
        allow_dynamic_markets: bool = False,
    ) -> None:
        for name, value in (
            ("cadence_seconds", cadence_seconds),
            ("timeout_seconds", timeout_seconds),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a positive finite number")
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a positive finite number")

        normalized_settlement = settlement_asset.strip().upper()
        if not normalized_settlement:
            raise ValueError("settlement_asset cannot be empty")
        by_asset: dict[str, str] = {}
        for symbol in executable_symbols:
            base_asset, quote_asset = parse_canonical_symbol(symbol)
            if quote_asset != normalized_settlement:
                raise ValueError("mark-to-market symbols must use the settlement asset")
            existing = by_asset.get(base_asset)
            if existing is not None and existing != symbol:
                raise ValueError("mark-to-market SPOT universe is ambiguous by base asset")
            by_asset[base_asset] = symbol

        self._market_data = market_data
        self._portfolio = portfolio
        self._settlement_asset = normalized_settlement
        self._symbols_by_asset = by_asset
        self._allow_dynamic_markets = allow_dynamic_markets
        self._cadence_seconds = float(cadence_seconds)
        self._timeout_seconds = float(timeout_seconds)
        self._task: asyncio.Task[None] | None = None
        self._last_error_type: str | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def last_error_type(self) -> str | None:
        return self._last_error_type

    async def start(self) -> None:
        """Start the process-local refresh loop; repeated starts are idempotent."""

        if self.is_running:
            return
        self._task = asyncio.create_task(self._run(), name="paper-spot-mark-to-market")
        await asyncio.sleep(0)

    async def refresh_once(self) -> int:
        """Refresh every currently held executable SPOT position once."""

        snapshot = self._portfolio.snapshot()
        refreshed = 0
        saw_error = False
        for position in snapshot.positions:
            symbol = self._symbols_by_asset.get(position.asset)
            if symbol is None and self._allow_dynamic_markets:
                symbol = f"{position.asset}/{self._settlement_asset}"
                try:
                    parse_canonical_symbol(symbol)
                except ValueError:
                    symbol = None
            if symbol is None:
                self._portfolio.clear_spot_mark(position.asset)
                saw_error = True
                self._last_error_type = "MarkMarketUnavailable"
                continue
            try:
                async with asyncio.timeout(self._timeout_seconds):
                    observation = await self._market_data.observation(symbol)
                if observation.symbol != symbol:
                    raise ValueError("mark-to-market source returned a different symbol")
                self._portfolio.mark_spot_observation(observation)
                refreshed += 1
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                saw_error = True
                self._last_error_type = type(exc).__name__
        if not saw_error:
            self._last_error_type = None
        return refreshed

    async def aclose(self) -> None:
        """Stop the refresh loop cooperatively."""

        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _run(self) -> None:
        while True:
            try:
                await self.refresh_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._last_error_type = type(exc).__name__
            await asyncio.sleep(self._cadence_seconds)


class PaperDerivativeMarkToMarketMonitor:
    """Refresh held derivatives from the canonical public source without invoking the Agent."""

    def __init__(
        self,
        *,
        market_data: MarketDataSource,
        portfolio: PaperPortfolioLedger,
        executable_symbols: Iterable[str],
        cadence_seconds: float,
        timeout_seconds: float,
        allow_dynamic_markets: bool = False,
    ) -> None:
        for name, value in (
            ("cadence_seconds", cadence_seconds),
            ("timeout_seconds", timeout_seconds),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a positive finite number")
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a positive finite number")
        self._market_data = market_data
        self._portfolio = portfolio
        self._symbols = frozenset(executable_symbols)
        self._allow_dynamic_markets = allow_dynamic_markets
        self._cadence_seconds = float(cadence_seconds)
        self._timeout_seconds = float(timeout_seconds)
        self._task: asyncio.Task[None] | None = None
        self._last_error_type: str | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def last_error_type(self) -> str | None:
        return self._last_error_type

    async def start(self) -> None:
        if self.is_running:
            return
        self._task = asyncio.create_task(
            self._run(), name="paper-derivative-mark-to-market"
        )
        await asyncio.sleep(0)

    async def refresh_once(self) -> int:
        snapshot = self._portfolio.snapshot()
        refreshed = 0
        saw_error = False
        for position in snapshot.derivative_positions:
            if position.symbol not in self._symbols and not self._allow_dynamic_markets:
                saw_error = True
                self._last_error_type = "MarkMarketUnavailable"
                continue
            try:
                parse_canonical_symbol(position.symbol)
                async with asyncio.timeout(self._timeout_seconds):
                    market_state = await self._market_data.snapshot(position.symbol)
                if market_state.symbol != position.symbol:
                    raise ValueError("mark-to-market source returned a different symbol")
                self._portfolio.mark_derivative_market(market_state)
                refreshed += 1
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                saw_error = True
                self._last_error_type = type(exc).__name__
        if not saw_error:
            self._last_error_type = None
        return refreshed

    async def aclose(self) -> None:
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _run(self) -> None:
        while True:
            try:
                await self.refresh_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._last_error_type = type(exc).__name__
            await asyncio.sleep(self._cadence_seconds)
