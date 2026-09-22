from ai_spot_trader.domain.enums import DerivativeContractKind, MarketType
from ai_spot_trader.domain.models import ExecutableMarket, MarketState
from ai_spot_trader.domain.ports import MarketDataSource
from ai_spot_trader.domain.symbols import parse_canonical_symbol


class ExecutableMarketError(RuntimeError):
    """Base error for deterministic validation of an Agent-selected execution market."""


class MarketOutsideExecutableUniverseError(ExecutableMarketError):
    """The Agent selected a typed market outside the configured PAPER execution universe."""


class UnsupportedExecutableMarketError(ExecutableMarketError):
    """The selected market exists conceptually but is not executable by this runtime."""


class ExecutableMarketSnapshotMismatchError(ExecutableMarketError):
    """An execution source returned facts for a different market than requested."""


class RoutedExecutableMarketDataSource:
    """Route a validated typed Agent selection to the canonical execution data source."""

    def __init__(
        self,
        *,
        spot: MarketDataSource,
        derivatives: MarketDataSource,
        allowed_markets: tuple[ExecutableMarket, ...],
    ) -> None:
        if not allowed_markets:
            raise ValueError("allowed_markets cannot be empty")
        ordered = tuple(
            sorted(allowed_markets, key=lambda market: (market.market_type.value, market.symbol))
        )
        if ordered != allowed_markets:
            raise ValueError("allowed_markets must use deterministic sorted order")
        if len(set(allowed_markets)) != len(allowed_markets):
            raise ValueError("allowed_markets must be unique")
        self._spot = spot
        self._derivatives = derivatives
        self._allowed_markets = frozenset(allowed_markets)

    @property
    def allowed_markets(self) -> frozenset[ExecutableMarket]:
        return self._allowed_markets

    async def snapshot(self, symbol: str, market_type: MarketType) -> MarketState:
        try:
            parse_canonical_symbol(symbol)
        except ValueError as exc:
            raise MarketOutsideExecutableUniverseError("selected symbol is not canonical") from exc

        if market_type is MarketType.FUTURE:
            raise UnsupportedExecutableMarketError("dated FUTURE execution is not supported")

        selected = ExecutableMarket(symbol=symbol, market_type=market_type)
        if selected not in self._allowed_markets:
            raise MarketOutsideExecutableUniverseError(
                "selected symbol + market_type is outside the executable universe"
            )

        if market_type is MarketType.SPOT:
            state = await self._spot.snapshot(symbol)
        elif market_type is MarketType.PERPETUAL:
            state = await self._derivatives.snapshot(symbol)
        else:
            raise UnsupportedExecutableMarketError(
                f"market type {market_type.value} is not executable"
            )

        if state.symbol != symbol or state.market_type is not market_type:
            raise ExecutableMarketSnapshotMismatchError(
                "execution market source returned a different symbol or market_type"
            )
        if market_type is MarketType.PERPETUAL:
            context = state.derivative
            if context is None:
                raise UnsupportedExecutableMarketError(
                    "PERPETUAL execution requires derivative market context"
                )
            if context.instrument.market_type is not MarketType.PERPETUAL:
                raise UnsupportedExecutableMarketError(
                    "selected derivative instrument is not PERPETUAL"
                )
            if context.instrument.contract_kind is not DerivativeContractKind.LINEAR:
                raise UnsupportedExecutableMarketError(
                    "only linear PERPETUAL instruments are executable"
                )
        return state
