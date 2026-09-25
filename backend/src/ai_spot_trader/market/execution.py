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
    """Route a validated typed Agent selection to the canonical execution data source.

    Static campaigns use the immutable allowed_markets set. Batch 19.4 dynamic campaigns can
    additionally authorize Kraken markets by deterministic type + settlement-asset constraints;
    the strategic watchlist remains responsible for deciding which of those addresses enters a
    cycle, and the provider snapshot still proves the market exists on Kraken.
    """

    def __init__(
        self,
        *,
        spot: MarketDataSource,
        derivatives: MarketDataSource,
        allowed_markets: tuple[ExecutableMarket, ...],
        allow_dynamic_markets: bool = False,
        settlement_asset: str | None = None,
        dynamic_market_types: tuple[MarketType, ...] = (),
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
        self._allow_dynamic_markets = allow_dynamic_markets
        self._settlement_asset = (
            None if settlement_asset is None else settlement_asset.strip().upper()
        )
        self._dynamic_market_types = frozenset(dynamic_market_types)
        if allow_dynamic_markets:
            if not self._settlement_asset:
                raise ValueError("dynamic executable markets require settlement_asset")
            if not self._dynamic_market_types:
                raise ValueError("dynamic executable markets require market types")
            if MarketType.FUTURE in self._dynamic_market_types:
                raise ValueError("dated FUTURE markets cannot be dynamically executable")

    @property
    def allowed_markets(self) -> frozenset[ExecutableMarket]:
        return self._allowed_markets

    async def snapshot(self, symbol: str, market_type: MarketType) -> MarketState:
        try:
            _, quote_asset = parse_canonical_symbol(symbol)
        except ValueError as exc:
            raise MarketOutsideExecutableUniverseError("selected symbol is not canonical") from exc

        if market_type is MarketType.FUTURE:
            raise UnsupportedExecutableMarketError("dated FUTURE execution is not supported")

        selected = ExecutableMarket(symbol=symbol, market_type=market_type)
        if selected not in self._allowed_markets and not self._dynamic_address_allowed(
            market_type=market_type,
            quote_asset=quote_asset,
        ):
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

    def _dynamic_address_allowed(self, *, market_type: MarketType, quote_asset: str) -> bool:
        return (
            self._allow_dynamic_markets
            and market_type in self._dynamic_market_types
            and quote_asset == self._settlement_asset
        )
