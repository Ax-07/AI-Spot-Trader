from collections.abc import Mapping
from typing import Any

from ai_spot_trader.integrations.kraken.errors import KrakenPayloadError, UnknownKrakenSymbolError
from ai_spot_trader.integrations.kraken.models import KrakenPairMetadata


class KrakenPairRegistry:
    """Translate Kraken pair aliases to one canonical slash-separated display symbol."""

    def __init__(self, pairs: tuple[KrakenPairMetadata, ...]) -> None:
        self._pairs = pairs
        aliases: dict[str, str] = {}
        for pair in pairs:
            for alias in (pair.symbol, pair.altname, pair.wsname):
                if alias:
                    aliases[alias.strip().upper()] = pair.symbol
        self._aliases = aliases

    @property
    def pairs(self) -> tuple[KrakenPairMetadata, ...]:
        return self._pairs

    def normalize(self, symbol: str) -> str:
        normalized = symbol.strip().upper()
        canonical = self._aliases.get(normalized)
        if canonical is None:
            raise UnknownKrakenSymbolError(f"unknown Kraken Spot symbol: {symbol!r}")
        return canonical


def parse_asset_pairs_payload(payload: object) -> KrakenPairRegistry:
    """Parse `/0/public/AssetPairs?assetVersion=1` without leaking Kraken payloads upstream."""

    if not isinstance(payload, Mapping):
        raise KrakenPayloadError("Kraken AssetPairs payload must be an object")

    errors = payload.get("error")
    if not isinstance(errors, list):
        raise KrakenPayloadError("Kraken AssetPairs payload has an invalid error field")
    if errors:
        raise KrakenPayloadError("Kraken AssetPairs returned an API error")

    result = payload.get("result")
    if not isinstance(result, Mapping):
        raise KrakenPayloadError("Kraken AssetPairs payload has no result object")

    pairs: list[KrakenPairMetadata] = []
    for raw_symbol, raw_info in result.items():
        if not isinstance(raw_symbol, str) or not isinstance(raw_info, Mapping):
            raise KrakenPayloadError("Kraken AssetPairs contains an invalid pair entry")
        symbol = raw_symbol.strip().upper()
        if "/" not in symbol:
            raise KrakenPayloadError(
                "Kraken AssetPairs assetVersion=1 returned a non-display symbol"
            )
        pairs.append(
            KrakenPairMetadata(
                symbol=symbol,
                altname=_optional_text(raw_info.get("altname")),
                wsname=_optional_text(raw_info.get("wsname")),
                status=_optional_text(raw_info.get("status")),
            )
        )

    if not pairs:
        raise KrakenPayloadError("Kraken AssetPairs returned no Spot pairs")
    return KrakenPairRegistry(tuple(pairs))


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise KrakenPayloadError("Kraken pair metadata contains an invalid text field")
    return value.strip().upper()
