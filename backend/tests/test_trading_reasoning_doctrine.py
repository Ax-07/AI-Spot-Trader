from ai_spot_trader.agent.prompt import (
    AGENT_SYSTEM_PROMPT,
    NET_ECONOMIC_OBJECTIVE_GUARDRAIL,
    TRADING_REASONING_DOCTRINE,
)
from ai_spot_trader.agent.strategy_client import (
    _compose_market_discovery_instructions,
    _compose_multi_market_plan_instructions,
)
from ai_spot_trader.domain.experiments import aggressiveness_context


def test_multi_market_plan_contains_doctrine_once_and_keeps_core_contracts() -> None:
    instructions = _compose_multi_market_plan_instructions(
        strategy_prompt="Priorise les opportunites defendables apres couts.",
        context=aggressiveness_context(5),
        trading_style_context=None,
        execution_cost_context=None,
    )

    assert instructions.count(TRADING_REASONING_DOCTRINE.rstrip()) == 1
    assert "strategic-multi-market-plan-v1" in instructions
    assert "`SPOT` et `PERPETUAL`" in instructions
    assert "`FUTURE` date n'est pas executable" in instructions
    assert "`HOLD` doit toujours proposer `proposed_quantity=null`" in instructions
    assert "SELL` exprime ou augmente une exposition `SHORT`" in instructions
    assert "`BUY` exprime ou augmente une exposition `LONG`" in instructions
    assert NET_ECONOMIC_OBJECTIVE_GUARDRAIL in instructions
    assert "Risk Engine" in instructions
    assert "L'IA propose ; le Risk Engine autorise" in instructions


def test_market_discovery_does_not_receive_decision_doctrine() -> None:
    instructions = _compose_market_discovery_instructions(
        strategy_prompt="Surveille les meilleurs candidats factuels.",
        context=aggressiveness_context(5),
        trading_style_context=None,
        execution_cost_context=None,
    )

    assert "market-discovery-v1" in instructions
    assert TRADING_REASONING_DOCTRINE not in instructions
    assert "La watchlist ne declenche aucun ordre et ne constitue ni BUY, ni SELL, ni HOLD" in instructions


def test_historical_prompt_does_not_gain_current_doctrine() -> None:
    assert TRADING_REASONING_DOCTRINE not in AGENT_SYSTEM_PROMPT
    assert "Version du contrat : agent-strategy-v4." in AGENT_SYSTEM_PROMPT
    assert "L'objectif expérimental de +4 % par jour" in AGENT_SYSTEM_PROMPT
