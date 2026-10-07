import json
from decimal import Decimal
from typing import Any, cast

from ai_spot_trader.agent.grounding import (
    FACTUAL_GROUNDING_GUARDRAIL,
    STRATEGIC_SIZING_GUARDRAIL,
    build_strategic_sizing_facts,
)
from ai_spot_trader.agent.strategy_client import StrategyInstructionsClient
from ai_spot_trader.domain.enums import LLMModel
from ai_spot_trader.domain.experiments import aggressiveness_context


class _UnusedDelegate:
    async def generate_structured_decision(
        self,
        *,
        model: LLMModel,
        instructions: str,
        input_text: str,
        schema: dict[str, Any],
    ) -> str:
        del model, instructions, input_text, schema
        raise AssertionError("transport must not be called while inspecting instructions")


def _benchmark_payload() -> dict[str, object]:
    return {
        "aggressiveness_context": aggressiveness_context(5).model_dump(mode="json"),
        "portfolio_state": {
            "settlement_asset": "EUR",
            "balances": [{"asset": "EUR", "available": "10000"}],
            "positions": [],
            "cash_available": "10000",
            "equity": "10000",
        },
        "market_states": [
            {"symbol": "BTC/EUR", "market_type": "SPOT", "last_price": "98250"},
            {"symbol": "ETH/EUR", "market_type": "SPOT", "last_price": "3245"},
            {"symbol": "SOL/EUR", "market_type": "SPOT", "last_price": "184.20"},
        ],
        "strategic_plan_contract": {"protocol_version": "strategic-multi-market-plan-v1"},
    }


def test_benchmark_sizing_facts_make_one_percent_arithmetic_explicit() -> None:
    facts = build_strategic_sizing_facts(_benchmark_payload())
    assert facts is not None
    markets = cast(list[dict[str, str]], facts["markets"])
    btc = next(item for item in markets if item["symbol"] == "BTC/EUR")

    assert Decimal(btc["quote_available"]) == Decimal("10000")
    assert Decimal(btc["quote_one_percent_notional"]) == Decimal("100")
    one_percent_quantity = Decimal(btc["base_quantity_at_quote_one_percent"])
    assert abs(one_percent_quantity * Decimal("98250") - Decimal("100")) < Decimal("1e-15")
    assert Decimal(btc["base_available"]) == Decimal("0")
    assert facts["cash_one_percent_if_provided"] == "100"
    assert facts["equity_one_percent_if_provided"] == "100"


def test_benchmark_quantity_point_one_is_explicitly_about_98_percent_of_cash() -> None:
    quantity = Decimal("0.1")
    price = Decimal("98250")
    cash = Decimal("10000")

    gross_notional = quantity * price
    allocation_percent = gross_notional / cash * Decimal("100")

    assert gross_notional == Decimal("9825")
    assert allocation_percent == Decimal("98.2500")
    assert allocation_percent != Decimal("1")


def test_grounding_contract_forbids_unprovided_market_narratives_and_general_knowledge() -> None:
    assert "Memoire du modele" in FACTUAL_GROUNDING_GUARDRAIL
    assert "nom du symbole" in FACTUAL_GROUNDING_GUARDRAIL
    assert "Un prix seul" in FACTUAL_GROUNDING_GUARDRAIL
    for unsupported_claim in (
        "tendance",
        "momentum",
        "volatilite",
        "consolidation/breakout",
        "ratio",
        "layer-1",
        "altcoin",
        "leader",
        "fait fondamental",
    ):
        assert unsupported_claim in FACTUAL_GROUNDING_GUARDRAIL


def test_sizing_contract_requires_quantity_notional_percentage_consistency() -> None:
    assert "gross_notional = proposed_quantity * last_price" in STRATEGIC_SIZING_GUARDRAIL
    assert "X = 100 * gross_notional / reference" in STRATEGIC_SIZING_GUARDRAIL
    assert "Risk garde l'autorite finale" in STRATEGIC_SIZING_GUARDRAIL


def test_strategy_instructions_append_compact_sizing_facts_for_multi_market_plan() -> None:
    client = StrategyInstructionsClient(
        _UnusedDelegate(),
        strategy_prompt="Priorise uniquement les theses defendables apres couts.",
    )
    instructions = client.effective_instructions(json.dumps(_benchmark_payload()))

    assert "SIZING_FACTS arithmetic only" in instructions
    assert "quote_avail=10000" in instructions
    assert "quote_1pct=100" in instructions
    assert "cash_1pct=100" in instructions
    assert "Un prix seul ne prouve ni tendance" in instructions
    assert "`proposed_quantity` = quantite d'actif de base" in instructions


def test_non_plan_prompt_does_not_receive_multi_market_sizing_section() -> None:
    payload = {
        "aggressiveness_context": aggressiveness_context(5).model_dump(mode="json"),
    }
    client = StrategyInstructionsClient(
        _UnusedDelegate(),
        strategy_prompt="Conserve le cash sans opportunite defendable.",
    )

    instructions = client.effective_instructions(json.dumps(payload))

    assert "SIZING_FACTS arithmetic only" not in instructions
