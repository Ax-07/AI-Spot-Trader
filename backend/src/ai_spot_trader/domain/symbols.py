def parse_canonical_symbol(symbol: str) -> tuple[str, str]:
    """Parse the provider-agnostic canonical ``BASE/QUOTE`` representation."""

    parts = symbol.split("/")
    if len(parts) != 2:
        raise ValueError("symbol must use canonical BASE/QUOTE form")
    base_asset, quote_asset = (part.strip() for part in parts)
    if not base_asset or not quote_asset or base_asset == quote_asset:
        raise ValueError("symbol must contain distinct BASE and QUOTE assets")
    return base_asset, quote_asset
