from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import DerivativeInstrument, ExecutableMarket
from ai_spot_trader.integrations.kraken.derivatives import (
    KrakenDerivativesPublicClient,
    build_kraken_linear_perpetual_instrument_map,
)
from ai_spot_trader.integrations.kraken.errors import KrakenPayloadError
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

    async def volume_24h_usd_by_market(self) -> dict[ExecutableMarket, Decimal]:
        """Return Kraken's public rolling 24h quote turnover for USD linear perpetuals.

        Kraken Futures exposes ``volumeQuote`` in its bulk public ticker response. Because the
        value is already denominated in the instrument quote asset, USD-quoted linear perpetuals
        require no candle-volume unit assumption and no synthetic price conversion.
        """

        if not self._perpetual_instruments:
            instruments = await self._derivatives.fetch_instruments()
            self._perpetual_instruments = build_kraken_linear_perpetual_instrument_map(instruments)

        # The canonical derivatives client owns the public transport. A single bulk request keeps
        # this read path bounded; it deliberately avoids one ticker request per market.
        payload = await self._derivatives._get_json(  # noqa: SLF001
            "/tickers",
            "Kraken Derivatives tickers",
        )
        quote_volumes = parse_kraken_derivatives_quote_volumes(payload)
        result: dict[ExecutableMarket, Decimal] = {}
        for instrument in self._perpetual_instruments.values():
            if instrument.quote_asset.upper() != "USD":
                continue
            value = quote_volumes.get(instrument.venue_symbol.upper())
            if value is None:
                continue
            result[
                ExecutableMarket(
                    symbol=instrument.symbol,
                    market_type=MarketType.PERPETUAL,
                )
            ] = value
        return result

    async def aclose(self) -> None:
        await self._spot.aclose()
        await self._derivatives.aclose()


def parse_kraken_derivatives_quote_volumes(payload: object) -> dict[str, Decimal]:
    """Parse public Futures ``/tickers`` into venue-symbol -> rolling quote volume."""

    if not isinstance(payload, Mapping):
        raise KrakenPayloadError("Kraken Derivatives tickers payload must be an object")
    result = payload.get("result")
    if result is not None and result != "success":
        raise KrakenPayloadError("Kraken Derivatives tickers returned an API error")
    rows = payload.get("tickers")
    if not isinstance(rows, list):
        raise KrakenPayloadError("Kraken Derivatives tickers must contain an array")

    parsed: dict[str, Decimal] = {}
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise KrakenPayloadError("Kraken Derivatives tickers contain an invalid entry")
        symbol = raw.get("symbol")
        if not isinstance(symbol, str) or not symbol.strip():
            raise KrakenPayloadError("Kraken Derivatives ticker symbol is invalid")
        if raw.get("suspended") is True:
            continue
        value = raw.get("volumeQuote")
        if value is None:
            continue
        number = _non_negative_decimal(value, "ticker volumeQuote")
        parsed[symbol.strip().upper()] = number
    return parsed


def _non_negative_decimal(value: Any, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise KrakenPayloadError(f"Kraken {label} is invalid")
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise KrakenPayloadError(f"Kraken {label} is invalid") from exc
    if not number.is_finite() or number < 0:
        raise KrakenPayloadError(f"Kraken {label} must be a finite non-negative number")
    return number
