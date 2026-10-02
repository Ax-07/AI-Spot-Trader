from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

import httpx

from ai_spot_trader.market.attention_filters import MarketMetadataSnapshot

COINPAPRIKA_API_URL = "https://api.coinpaprika.com/v1"
COINPAPRIKA_PROVIDER_NAME = "COINPAPRIKA"
COINPAPRIKA_METADATA_TTL = timedelta(hours=6)


class CoinPaprikaMarketMetadataProvider:
    """Read-only, keyless CoinPaprika metadata source with a long fail-soft cache."""

    def __init__(
        self,
        *,
        base_url: str = COINPAPRIKA_API_URL,
        timeout_seconds: float = 10.0,
        cache_ttl: timedelta = COINPAPRIKA_METADATA_TTL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if cache_ttl.total_seconds() <= 0:
            raise ValueError("market metadata cache_ttl must be positive")
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds)
        self._owns_client = client is None
        self._cache_ttl = cache_ttl
        self._cache: dict[str, MarketMetadataSnapshot] = {}
        self._cache_at: datetime | None = None
        self._lock = asyncio.Lock()

    async def metadata_by_symbol(self) -> dict[str, MarketMetadataSnapshot]:
        now = datetime.now(UTC)
        if self._cache_fresh(now):
            return dict(self._cache)

        async with self._lock:
            now = datetime.now(UTC)
            if self._cache_fresh(now):
                return dict(self._cache)
            try:
                response = await self._client.get("/tickers", params={"quotes": "USD"})
                response.raise_for_status()
                payload = response.json()
                parsed = parse_coinpaprika_tickers(payload, observed_at=now)
                if not parsed:
                    raise ValueError("CoinPaprika returned no usable market metadata")
            except (httpx.HTTPError, ValueError, TypeError):
                # Fail-soft: stale metadata remains usable for an informative filter. If no
                # successful snapshot has ever been cached, the Radar receives an empty map.
                return dict(self._cache)

            self._cache = parsed
            self._cache_at = now
            return dict(self._cache)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _cache_fresh(self, now: datetime) -> bool:
        return (
            bool(self._cache)
            and self._cache_at is not None
            and now - self._cache_at < self._cache_ttl
        )


def parse_coinpaprika_tickers(
    payload: object,
    *,
    observed_at: datetime,
) -> dict[str, MarketMetadataSnapshot]:
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("CoinPaprika observed_at must be timezone-aware")
    if not isinstance(payload, list):
        raise ValueError("CoinPaprika tickers payload must be an array")

    selected: dict[str, MarketMetadataSnapshot] = {}
    ambiguous_symbols: set[str] = set()
    for raw in payload:
        if not isinstance(raw, Mapping):
            continue
        symbol = raw.get("symbol")
        if not isinstance(symbol, str) or not symbol.strip():
            continue
        symbol = symbol.strip().upper()
        quotes = raw.get("quotes")
        if not isinstance(quotes, Mapping):
            continue
        usd = quotes.get("USD")
        if not isinstance(usd, Mapping):
            continue

        market_cap = _optional_non_negative_decimal(usd.get("market_cap"))
        if market_cap is not None and market_cap == 0:
            market_cap = None
        circulating_supply = _optional_non_negative_decimal(raw.get("circulating_supply"))
        rank = _optional_positive_int(raw.get("rank"))
        snapshot = MarketMetadataSnapshot(
            asset_symbol=symbol,
            circulating_supply=circulating_supply,
            market_cap_usd=market_cap,
            market_cap_rank=rank,
            observed_at=_provider_timestamp(raw.get("last_updated"), fallback=observed_at),
            provider=COINPAPRIKA_PROVIDER_NAME,
        )
        if symbol in ambiguous_symbols:
            continue
        if symbol in selected:
            # A ticker symbol is not a globally unique asset identifier. Failing closed on
            # duplicates is safer than silently attaching another asset's market cap to a
            # Kraken base symbol.
            selected.pop(symbol, None)
            ambiguous_symbols.add(symbol)
            continue
        selected[symbol] = snapshot
    return selected


def _optional_non_negative_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not parsed.is_finite() or parsed < 0:
        return None
    return parsed


def _optional_positive_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (ValueError, TypeError):
        return None
    return parsed if parsed > 0 else None


def _provider_timestamp(value: object, *, fallback: datetime) -> datetime:
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            parsed = None
        if parsed is not None and parsed.tzinfo is not None and parsed.utcoffset() is not None:
            return parsed.astimezone(UTC)
    return fallback.astimezone(UTC)
