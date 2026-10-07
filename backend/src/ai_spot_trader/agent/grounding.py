from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation, localcontext

FACTUAL_GROUNDING_GUARDRAIL = (
    "Rationale/these : n'affirmez que des faits presents dans l'input causal ou les tools "
    "read-only du meme appel. Memoire du modele et nom du symbole ne sont pas des sources. "
    "Un prix seul ne prouve ni tendance, momentum, volatilite, consolidation/breakout, ratio, "
    "classification (layer-1, altcoin, leader) ou fait fondamental. Fait absent = inconnu."
)

STRATEGIC_SIZING_GUARDRAIL = (
    "`proposed_quantity` = quantite d'actif de base. BUY SPOT : "
    "`gross_notional = proposed_quantity * last_price`. Si la rationale cite X %, nommez la "
    "reference fournie et verifiez `X = 100 * gross_notional / reference`. SELL SPOT <= "
    "`base_available`. `SIZING_FACTS` = arithmetique descriptive, pas cible d'allocation ni "
    "limite Risk. Si incoherent, HOLD est valide ; Risk garde l'autorite finale."
)


def build_strategic_sizing_facts(payload: Mapping[str, object]) -> dict[str, object] | None:
    """Build compact arithmetic references from the causal plan payload only."""

    raw_portfolio = payload.get("portfolio_state")
    raw_markets = payload.get("market_states")
    if not isinstance(raw_portfolio, Mapping) or not isinstance(raw_markets, list):
        return None

    balances = _available_by_asset(raw_portfolio.get("balances"))
    positions = _spot_available_by_asset(raw_portfolio.get("positions"))
    markets: list[dict[str, str]] = []

    for raw_market in raw_markets:
        if not isinstance(raw_market, Mapping):
            continue
        symbol = raw_market.get("symbol")
        market_type = raw_market.get("market_type")
        last_price = _decimal(raw_market.get("last_price"))
        if (
            not isinstance(symbol, str)
            or not symbol.strip()
            or not isinstance(market_type, str)
            or last_price is None
            or last_price <= 0
        ):
            continue
        parsed = _parse_symbol(symbol)
        if parsed is None:
            continue
        base_asset, quote_asset = parsed
        item = {
            "symbol": symbol,
            "market_type": market_type,
            "last_price": _decimal_text(last_price),
        }

        if market_type == "SPOT":
            available_quote = balances.get(quote_asset, Decimal(0))
            available_base = positions.get(base_asset, Decimal(0))
            with localcontext() as context:
                context.prec = 34
                one_percent_notional = available_quote / Decimal(100)
                one_percent_quantity = one_percent_notional / last_price
            item.update(
                {
                    "quote_available": _decimal_text(available_quote),
                    "quote_one_percent_notional": _decimal_text(one_percent_notional),
                    "base_quantity_at_quote_one_percent": _compact_decimal_text(
                        one_percent_quantity
                    ),
                    "base_available": _decimal_text(available_base),
                }
            )
        markets.append(item)

    if not markets:
        return None

    facts: dict[str, object] = {"markets": markets}
    settlement_asset = raw_portfolio.get("settlement_asset")
    if isinstance(settlement_asset, str) and settlement_asset.strip():
        facts["settlement_asset"] = settlement_asset
    cash_available = _decimal(raw_portfolio.get("cash_available"))
    if cash_available is not None:
        facts["cash_available_if_provided"] = _decimal_text(cash_available)
        facts["cash_one_percent_if_provided"] = _decimal_text(cash_available / Decimal(100))
    equity = _decimal(raw_portfolio.get("equity"))
    if equity is not None:
        facts["equity_if_provided"] = _decimal_text(equity)
        facts["equity_one_percent_if_provided"] = _decimal_text(equity / Decimal(100))
    return facts


def render_strategic_sizing_facts(payload: Mapping[str, object]) -> str | None:
    facts = build_strategic_sizing_facts(payload)
    if facts is None:
        return None

    lines = ["SIZING_FACTS arithmetic only; not allocation advice/Risk limits:"]
    portfolio_parts: list[str] = []
    for key in (
        "settlement_asset",
        "cash_available_if_provided",
        "cash_one_percent_if_provided",
        "equity_if_provided",
        "equity_one_percent_if_provided",
    ):
        value = facts.get(key)
        if value is not None:
            label = {
                "settlement_asset": "settlement",
                "cash_available_if_provided": "cash",
                "cash_one_percent_if_provided": "cash_1pct",
                "equity_if_provided": "equity",
                "equity_one_percent_if_provided": "equity_1pct",
            }[key]
            portfolio_parts.append(f"{label}={value}")
    if portfolio_parts:
        lines.append("portfolio " + " ".join(portfolio_parts))

    raw_markets = facts["markets"]
    assert isinstance(raw_markets, list)
    for item in raw_markets:
        assert isinstance(item, dict)
        labels = {
            "symbol": "symbol",
            "market_type": "type",
            "last_price": "price",
            "quote_available": "quote_avail",
            "quote_one_percent_notional": "quote_1pct",
            "base_quantity_at_quote_one_percent": "base_qty_for_quote_1pct",
            "base_available": "base_avail",
        }
        fields = " ".join(f"{labels[key]}={value}" for key, value in item.items())
        lines.append(fields)
    return "\n".join(lines)


def _available_by_asset(raw_balances: object) -> dict[str, Decimal]:
    result: dict[str, Decimal] = {}
    if not isinstance(raw_balances, list):
        return result
    for item in raw_balances:
        if not isinstance(item, Mapping):
            continue
        asset = item.get("asset")
        available = _decimal(item.get("available"))
        if isinstance(asset, str) and asset.strip() and available is not None and available >= 0:
            result[asset] = available
    return result


def _spot_available_by_asset(raw_positions: object) -> dict[str, Decimal]:
    result: dict[str, Decimal] = {}
    if not isinstance(raw_positions, list):
        return result
    for item in raw_positions:
        if not isinstance(item, Mapping):
            continue
        asset = item.get("asset")
        available = _decimal(item.get("available"))
        if isinstance(asset, str) and asset.strip() and available is not None and available >= 0:
            result[asset] = available
    return result


def _parse_symbol(symbol: str) -> tuple[str, str] | None:
    parts = symbol.split("/")
    if len(parts) != 2:
        return None
    base_asset, quote_asset = (part.strip() for part in parts)
    if not base_asset or not quote_asset or base_asset == quote_asset:
        return None
    return base_asset, quote_asset


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite():
        return None
    return parsed


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _compact_decimal_text(value: Decimal) -> str:
    return format(value, ".18g")


__all__ = [
    "FACTUAL_GROUNDING_GUARDRAIL",
    "STRATEGIC_SIZING_GUARDRAIL",
    "build_strategic_sizing_facts",
    "render_strategic_sizing_facts",
]
