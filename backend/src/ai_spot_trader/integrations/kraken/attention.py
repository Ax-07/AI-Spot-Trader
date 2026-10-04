from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import DerivativeInstrument, ExecutableMarket
from ai_spot_trader.integrations.kraken.derivatives import (
    KrakenDerivativesPublicClient,
    KrakenDerivativesTickerSnapshot,
    build_kraken_linear_perpetual_instrument_map,
    parse_kraken_derivatives_tickers,
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
        self._perpetual_instruments: dict[str, DerivativeInstrument] = {}

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
        self._perpetual_instruments = perpetuals
        for instrument in perpetuals.values():
            markets.add(
                ExecutableMarket(
                    symbol=instrument.symbol,
                    market_type=MarketType.PERPETUAL,
                )
            )
        return tuple(sorted(markets, key=lambda item: (item.market_type.value, item.symbol)))

    async def perpetual_ticker_snapshot_by_market(
        self,
    ) -> dict[ExecutableMarket, KrakenDerivativesTickerSnapshot]:
        """Return one shared public bulk-ticker snapshot keyed by canonical PERPETUAL market."""

        if not self._perpetual_instruments:
            instruments = await self._derivatives.fetch_instruments()
            self._perpetual_instruments = build_kraken_linear_perpetual_instrument_map(instruments)

        tickers = await self._derivatives.fetch_tickers()
        by_venue_symbol = {ticker.venue_symbol.upper(): ticker for ticker in tickers}
        result: dict[ExecutableMarket, KrakenDerivativesTickerSnapshot] = {}
        for instrument in self._perpetual_instruments.values():
            ticker = by_venue_symbol.get(instrument.venue_symbol.upper())
            if ticker is None:
                continue
            ticker = replace(
                ticker,
                funding_rate_relative=ticker.normalized_funding_rate(
                    contract_size=instrument.contract_size
                ),
            )
            result[
                ExecutableMarket(
                    symbol=instrument.symbol,
                    market_type=MarketType.PERPETUAL,
                )
            ] = ticker
        return result

    async def volume_24h_usd_by_market(self) -> dict[ExecutableMarket, Decimal]:
        """Return rolling USD quote turnover using the same canonical bulk ticker parser."""

        snapshots = await self.perpetual_ticker_snapshot_by_market()
        result: dict[ExecutableMarket, Decimal] = {}
        for market, ticker in snapshots.items():
            instrument = self._perpetual_instruments.get(market.symbol)
            if instrument is None or instrument.quote_asset.upper() != "USD":
                continue
            if ticker.suspended is True or ticker.volume_quote is None:
                continue
            result[market] = ticker.volume_quote
        return result

    async def aclose(self) -> None:
        await self._spot.aclose()
        await self._derivatives.aclose()


def parse_kraken_derivatives_quote_volumes(payload: object) -> dict[str, Decimal]:
    """Compatibility view over the canonical bulk parser: venue symbol -> quote volume."""

    return {
        ticker.venue_symbol: ticker.volume_quote
        for ticker in parse_kraken_derivatives_tickers(payload)
        if ticker.suspended is not True and ticker.volume_quote is not None
    }
