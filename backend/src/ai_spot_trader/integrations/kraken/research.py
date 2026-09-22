from typing import Protocol

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import DerivativeInstrument, MarketState
from ai_spot_trader.domain.symbols import parse_canonical_symbol
from ai_spot_trader.integrations.kraken.derivatives import KrakenDerivativesMarketDataSource
from ai_spot_trader.integrations.kraken.errors import UnknownKrakenSymbolError
from ai_spot_trader.integrations.kraken.market_data import KrakenMarketDataSource
from ai_spot_trader.market.research import MarketResearchMarket


class KrakenDerivativesCatalog(Protocol):
    """Raw normalized public instrument catalogue without executable-symbol collapsing."""

    async def fetch_instruments(self) -> tuple[DerivativeInstrument, ...]: ...


class KrakenMarketResearchBackend:
    """Public Kraken facts reused by the provider-agnostic market research service."""

    def __init__(
        self,
        *,
        spot: KrakenMarketDataSource,
        derivatives: KrakenDerivativesMarketDataSource,
        derivatives_catalog: KrakenDerivativesCatalog,
    ) -> None:
        self._spot = spot
        self._derivatives = derivatives
        self._derivatives_catalog = derivatives_catalog

    async def list_markets(
        self,
        market_type: MarketType | None,
    ) -> tuple[MarketResearchMarket, ...]:
        markets: list[MarketResearchMarket] = []
        if market_type in (None, MarketType.SPOT):
            registry = await self._spot.refresh_pairs()
            for pair in registry.pairs:
                base_asset, quote_asset = parse_canonical_symbol(pair.symbol)
                markets.append(
                    MarketResearchMarket(
                        symbol=pair.symbol,
                        market_type=MarketType.SPOT,
                        venue_symbol=pair.wsname or pair.altname or pair.symbol,
                        status=pair.status,
                        underlying_asset=base_asset,
                        quote_asset=quote_asset,
                    )
                )

        if market_type is not MarketType.SPOT:
            instruments = await self._derivatives_catalog.fetch_instruments()
            for instrument in instruments:
                if market_type is not None and instrument.market_type is not market_type:
                    continue
                markets.append(
                    MarketResearchMarket(
                        symbol=instrument.symbol,
                        market_type=instrument.market_type,
                        venue_symbol=instrument.venue_symbol,
                        status="tradeable",
                        contract_kind=instrument.contract_kind,
                        underlying_asset=instrument.underlying_asset,
                        quote_asset=instrument.quote_asset,
                        expires_at=instrument.expires_at,
                    )
                )
        return tuple(markets)

    async def snapshot(self, symbol: str, market_type: MarketType) -> MarketState:
        if market_type is MarketType.SPOT:
            return await self._spot.snapshot(symbol)
        if market_type is not MarketType.PERPETUAL:
            raise UnknownKrakenSymbolError(
                "dated FUTURE snapshots are not exposed by the Batch 18.1 research tool"
            )

        state = await self._derivatives.snapshot(symbol)
        if state.market_type is not market_type:
            raise UnknownKrakenSymbolError(
                f"no Kraken {market_type.value} instrument mapped to {symbol}"
            )
        return state
