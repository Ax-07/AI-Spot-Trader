from __future__ import annotations

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.integrations.kraken.derivatives import (
    KrakenDerivativesPublicClient,
    build_kraken_linear_perpetual_instrument_map,
)
from ai_spot_trader.integrations.kraken.rest import KrakenPublicRestClient


class KrakenAttentionCatalogue:
    """Read-only Kraken catalogue for the observation-only Market Attention Radar."""

    def __init__(
        self,
        *,
        spot_rest_url: str,
        derivatives_rest_url: str,
        timeout_seconds: float,
    ) -> None:
        self._spot = KrakenPublicRestClient(
            spot_rest_url,
            timeout_seconds=timeout_seconds,
        )
        self._derivatives = KrakenDerivativesPublicClient(
            derivatives_rest_url,
            timeout_seconds=timeout_seconds,
        )

    async def list_markets(self) -> tuple[ExecutableMarket, ...]:
        markets: set[ExecutableMarket] = set()
        spot_registry = await self._spot.fetch_pair_registry()
        allowed_statuses = {"online", "open", "active", "tradeable", "tradable"}
        for pair in spot_registry.pairs:
            if pair.status is not None and pair.status.strip().lower() not in allowed_statuses:
                continue
            markets.add(ExecutableMarket(symbol=pair.symbol, market_type=MarketType.SPOT))

        instruments = await self._derivatives.fetch_instruments()
        perpetuals = build_kraken_linear_perpetual_instrument_map(instruments)
        for instrument in perpetuals.values():
            markets.add(
                ExecutableMarket(
                    symbol=instrument.symbol,
                    market_type=MarketType.PERPETUAL,
                )
            )
        return tuple(sorted(markets, key=lambda item: (item.market_type.value, item.symbol)))

    async def aclose(self) -> None:
        await self._spot.aclose()
        await self._derivatives.aclose()
