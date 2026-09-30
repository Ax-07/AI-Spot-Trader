from collections.abc import Mapping
from typing import Any

from ai_spot_trader.integrations.kraken.errors import (
    KrakenPayloadError,
    KrakenPayloadStage,
    UnknownKrakenSymbolError,
)
from ai_spot_trader.integrations.kraken.models import KrakenPairMetadata


_DISPLAY_ASSET_ALIASES = {
    "XBT": "BTC",
    "XDG": "DOGE",
}

# Conservative exact mappings for legacy REST asset identifiers. Do not strip X/Z
# generically: legitimate assets such as XTZ or ZRX must stay untouched.
_REST_ASSET_ALIASES = {
    "XXBT": "BTC",
    "XBT": "BTC",
    "XXDG": "DOGE",
    "XDG": "DOGE",
    "XETH": "ETH",
    "XLTC": "LTC",
    "XXLM": "XLM",
    "XXMR": "XMR",
    "XXRP": "XRP",
    "XZEC": "ZEC",
    "XETC": "ETC",
    "XMLN": "MLN",
    "XREP": "REP",
    "ZUSD": "USD",
    "ZEUR": "EUR",
    "ZGBP": "GBP",
    "ZJPY": "JPY",
    "ZCAD": "CAD",
    "ZAUD": "AUD",
    "ZCHF": "CHF",
}


class KrakenPairRegistry:
    """Translate Kraken pair aliases to one canonical slash-separated display symbol."""

    def __init__(
        self,
        pairs: tuple[KrakenPairMetadata, ...],
        *,
        provider_aliases: Mapping[str, str] | None = None,
    ) -> None:
        self._pairs = pairs
        aliases: dict[str, str] = {}
        for pair in pairs:
            for alias in (pair.symbol, pair.altname, pair.wsname):
                if alias:
                    _register_alias(aliases, alias, pair.symbol)
        if provider_aliases is not None:
            for alias, canonical in provider_aliases.items():
                _register_alias(aliases, alias, canonical)
        self._aliases = aliases

    @property
    def pairs(self) -> tuple[KrakenPairMetadata, ...]:
        return self._pairs

    def normalize(self, symbol: str) -> str:
        normalized = symbol.strip().upper()
        canonical = self._aliases.get(normalized)
        if canonical is None:
            # Canonical display input can use the project alias BTC while Kraken's
            # wsname uses XBT. Canonicalize only slash-separated display symbols.
            display = _try_canonical_display_symbol(normalized)
            if display is not None:
                canonical = self._aliases.get(display)
        if canonical is None:
            raise UnknownKrakenSymbolError(f"unknown Kraken Spot symbol: {symbol!r}")
        return canonical


def parse_asset_pairs_payload(payload: object) -> KrakenPairRegistry:
    """Parse Kraken AssetPairs without treating REST result keys as display symbols."""

    if not isinstance(payload, Mapping):
        raise KrakenPayloadError(
            "Kraken AssetPairs payload must be an object",
            stage=KrakenPayloadStage.ASSET_PAIRS_PAYLOAD,
        )

    errors = payload.get("error")
    if not isinstance(errors, list):
        raise KrakenPayloadError(
            "Kraken AssetPairs payload has an invalid error field",
            stage=KrakenPayloadStage.ASSET_PAIRS_PAYLOAD,
        )
    if errors:
        raise KrakenPayloadError(
            "Kraken AssetPairs returned an API error",
            stage=KrakenPayloadStage.ASSET_PAIRS_PAYLOAD,
        )

    result = payload.get("result")
    if not isinstance(result, Mapping):
        raise KrakenPayloadError(
            "Kraken AssetPairs payload has no result object",
            stage=KrakenPayloadStage.ASSET_PAIRS_PAYLOAD,
        )

    pairs: list[KrakenPairMetadata] = []
    provider_aliases: dict[str, str] = {}
    seen_symbols: set[str] = set()
    for raw_symbol, raw_info in result.items():
        if not isinstance(raw_symbol, str) or not raw_symbol.strip():
            raise KrakenPayloadError(
                "Kraken AssetPairs contains an invalid pair key",
                stage=KrakenPayloadStage.ASSET_PAIRS_ENTRY,
            )
        if not isinstance(raw_info, Mapping):
            raise KrakenPayloadError(
                "Kraken AssetPairs contains an invalid pair entry",
                stage=KrakenPayloadStage.ASSET_PAIRS_ENTRY,
            )

        provider_key = raw_symbol.strip().upper()
        altname = _optional_text(raw_info.get("altname"), field="altname")
        wsname = _optional_text(raw_info.get("wsname"), field="wsname")
        status = _optional_text(raw_info.get("status"), field="status")
        symbol = _canonical_pair_symbol(
            provider_key=provider_key,
            wsname=wsname,
            base=raw_info.get("base"),
            quote=raw_info.get("quote"),
        )

        existing = provider_aliases.get(provider_key)
        if existing is not None and existing != symbol:
            raise KrakenPayloadError(
                "Kraken AssetPairs contains a conflicting provider pair key",
                stage=KrakenPayloadStage.ASSET_PAIRS_SYMBOL,
            )
        provider_aliases[provider_key] = symbol

        if symbol not in seen_symbols:
            pairs.append(
                KrakenPairMetadata(
                    symbol=symbol,
                    altname=altname,
                    wsname=wsname,
                    status=status,
                )
            )
            seen_symbols.add(symbol)
        else:
            # Preserve all aliases even if Kraken exposes more than one provider-local
            # entry for the same canonical display pair. The canonical pair itself is
            # represented once in the registry.
            for alias in (altname, wsname):
                if alias:
                    existing = provider_aliases.get(alias)
                    if existing is not None and existing != symbol:
                        raise KrakenPayloadError(
                            "Kraken AssetPairs contains conflicting pair aliases",
                            stage=KrakenPayloadStage.ASSET_PAIRS_SYMBOL,
                        )
                    provider_aliases[alias] = symbol

    if not pairs:
        raise KrakenPayloadError(
            "Kraken AssetPairs returned no Spot pairs",
            stage=KrakenPayloadStage.ASSET_PAIRS_PAYLOAD,
        )
    return KrakenPairRegistry(tuple(pairs), provider_aliases=provider_aliases)


def _canonical_pair_symbol(
    *,
    provider_key: str,
    wsname: str | None,
    base: Any,
    quote: Any,
) -> str:
    candidates: list[str] = []

    if wsname is not None:
        display = _try_canonical_display_symbol(wsname)
        if display is not None:
            candidates.append(display)

    provider_display = _try_canonical_display_symbol(provider_key)
    if provider_display is not None:
        candidates.append(provider_display)

    if isinstance(base, str) and isinstance(quote, str) and base.strip() and quote.strip():
        canonical_base = _canonical_rest_asset(base)
        canonical_quote = _canonical_rest_asset(quote)
        if canonical_base == canonical_quote:
            raise KrakenPayloadError(
                "Kraken AssetPairs entry has an invalid asset pair",
                stage=KrakenPayloadStage.ASSET_PAIRS_SYMBOL,
            )
        candidates.append(f"{canonical_base}/{canonical_quote}")

    if not candidates:
        raise KrakenPayloadError(
            "Kraken AssetPairs entry has no usable display symbol",
            stage=KrakenPayloadStage.ASSET_PAIRS_SYMBOL,
        )

    canonical = candidates[0]
    if any(candidate != canonical for candidate in candidates[1:]):
        raise KrakenPayloadError(
            "Kraken AssetPairs entry contains inconsistent symbol metadata",
            stage=KrakenPayloadStage.ASSET_PAIRS_SYMBOL,
        )
    return canonical


def kraken_pair_key_matches(raw_symbol: str, expected_symbol: str) -> bool:
    """Match one OHLC result key to the requested canonical pair without raw-key guessing."""

    expected = _try_canonical_display_symbol(expected_symbol)
    if expected is None:
        return False

    raw_display = _try_canonical_display_symbol(raw_symbol)
    if raw_display is not None:
        return raw_display == expected

    base, quote = expected.split("/", 1)
    base_aliases = _asset_aliases_for_canonical(base)
    quote_aliases = _asset_aliases_for_canonical(quote)
    accepted = {
        f"{base_alias}{quote_alias}"
        for base_alias in base_aliases
        for quote_alias in quote_aliases
    }
    return raw_symbol.strip().upper() in accepted


def _asset_aliases_for_canonical(asset: str) -> frozenset[str]:
    normalized = asset.strip().upper()
    aliases = {normalized}
    aliases.update(alias for alias, target in _DISPLAY_ASSET_ALIASES.items() if target == normalized)
    aliases.update(alias for alias, target in _REST_ASSET_ALIASES.items() if target == normalized)
    return frozenset(aliases)


def _try_canonical_display_symbol(value: str) -> str | None:
    normalized = value.strip().upper()
    parts = normalized.split("/")
    if len(parts) != 2 or not all(parts) or parts[0] == parts[1]:
        return None
    base, quote = (_DISPLAY_ASSET_ALIASES.get(part, part) for part in parts)
    return f"{base}/{quote}"


def _canonical_rest_asset(value: str) -> str:
    normalized = value.strip().upper()
    if not normalized:
        raise KrakenPayloadError(
            "Kraken AssetPairs contains an invalid asset identifier",
            stage=KrakenPayloadStage.ASSET_PAIRS_SYMBOL,
        )
    return _REST_ASSET_ALIASES.get(normalized, normalized)


def _register_alias(aliases: dict[str, str], alias: str, canonical: str) -> None:
    normalized = alias.strip().upper()
    if not normalized:
        raise KrakenPayloadError(
            "Kraken pair metadata contains an empty alias",
            stage=KrakenPayloadStage.ASSET_PAIRS_SYMBOL,
        )
    existing = aliases.get(normalized)
    if existing is not None and existing != canonical:
        raise KrakenPayloadError(
            "Kraken pair metadata contains a conflicting alias",
            stage=KrakenPayloadStage.ASSET_PAIRS_SYMBOL,
        )
    aliases[normalized] = canonical


def _optional_text(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise KrakenPayloadError(
            f"Kraken pair metadata contains an invalid {field} field",
            stage=KrakenPayloadStage.ASSET_PAIRS_ENTRY,
        )
    return value.strip().upper()
