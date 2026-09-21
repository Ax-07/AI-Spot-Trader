import ast
import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

import ai_spot_trader.agent as agent_package
from ai_spot_trader.agent import (
    AGENT_PROMPT_VERSION,
    AGENT_SYSTEM_PROMPT,
    AgentContractViolationError,
    LLMOutputValidationError,
    OpenAIDecisionProvider,
)
from ai_spot_trader.broker.pricing import PaperExecutionCostModel
from ai_spot_trader.core.config import Settings
from ai_spot_trader.domain.enums import LLMModel, TradingAction
from ai_spot_trader.domain.models import (
    AgentInput,
    AssetBalance,
    AssetPosition,
    DecisionCandidate,
    MarketState,
    PortfolioState,
)
from ai_spot_trader.experiments import build_experiment_manifest
from ai_spot_trader.risk.policy import RiskPolicy

CYCLE_ID = UUID("10000000-0000-0000-0000-000000000001")
DECISION_ID = UUID("20000000-0000-0000-0000-000000000002")
MARKET_STATE_ID = UUID("30000000-0000-0000-0000-000000000003")
PORTFOLIO_STATE_ID = UUID("40000000-0000-0000-0000-000000000004")
MARKET_AT = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
PORTFOLIO_AT = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
INPUT_AT = datetime(2026, 9, 20, 12, 1, tzinfo=UTC)
DECISION_AT = datetime(2026, 9, 20, 12, 2, tzinfo=UTC)


class FixedClock:
    def __init__(self, value: datetime) -> None:
        self._value = value

    def now(self) -> datetime:
        return self._value


class FakeStructuredDecisionClient:
    def __init__(self, output: str) -> None:
        self.output = output
        self.calls: list[dict[str, Any]] = []

    async def generate_structured_decision(
        self,
        *,
        model: LLMModel,
        instructions: str,
        input_text: str,
        schema: dict[str, Any],
    ) -> str:
        self.calls.append(
            {
                "model": model,
                "instructions": instructions,
                "input_text": input_text,
                "schema": schema,
            }
        )
        return self.output


def _agent_input(
    *,
    symbol: str = "BTC/EUR",
    created_at: datetime = INPUT_AT,
    market_at: datetime = MARKET_AT,
    portfolio_at: datetime = PORTFOLIO_AT,
) -> AgentInput:
    return AgentInput(
        cycle_id=CYCLE_ID,
        created_at=created_at,
        market_state=MarketState(
            market_state_id=MARKET_STATE_ID,
            as_of=market_at,
            symbol=symbol,
            last_price=Decimal("50000"),
        ),
        portfolio_state=PortfolioState(
            portfolio_state_id=PORTFOLIO_STATE_ID,
            as_of=portfolio_at,
            balances=(AssetBalance(asset="EUR", available=Decimal("1000")),),
            positions=(
                AssetPosition(
                    asset="BTC",
                    quantity=Decimal("0.5"),
                    available=Decimal("0.5"),
                ),
            ),
        ),
        aggressiveness=5,
    )


def _provider(
    output: str,
    *,
    model: LLMModel = LLMModel.LUNA,
    clock_at: datetime = DECISION_AT,
) -> tuple[OpenAIDecisionProvider, FakeStructuredDecisionClient]:
    client = FakeStructuredDecisionClient(output)
    provider = OpenAIDecisionProvider(
        client=client,
        model=model,
        clock=FixedClock(clock_at),
        decision_id_factory=lambda: DECISION_ID,
    )
    return provider, client


def _generate(
    provider: OpenAIDecisionProvider,
    agent_input: AgentInput | None = None,
) -> DecisionCandidate:
    return asyncio.run(provider.generate_decision(agent_input or _agent_input()))


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {"_env_file": None}
    values.update(overrides)
    return Settings(**values)


def _json_output(
    *,
    action: str = "BUY",
    symbol: str = "BTC/EUR",
    proposed_quantity: object = 0.01,
    rationale: object = "Structured rationale",
    **extra: object,
) -> str:
    payload = {
        "action": action,
        "symbol": symbol,
        "proposed_quantity": proposed_quantity,
        "rationale": rationale,
    }
    payload.update(extra)
    return json.dumps(payload)


def test_generate_valid_buy() -> None:
    provider, _ = _provider(_json_output(action="BUY", proposed_quantity=0.01))
    decision = _generate(provider)
    assert decision.action is TradingAction.BUY
    assert decision.proposed_quantity == Decimal("0.01")
    assert decision.symbol == "BTC/EUR"


def test_generate_valid_sell() -> None:
    provider, _ = _provider(_json_output(action="SELL", proposed_quantity=0.02))
    decision = _generate(provider)
    assert decision.action is TradingAction.SELL
    assert decision.proposed_quantity == Decimal("0.02")


def test_generate_valid_hold() -> None:
    provider, _ = _provider(_json_output(action="HOLD", proposed_quantity=None))
    decision = _generate(provider)
    assert decision.action is TradingAction.HOLD
    assert decision.proposed_quantity is None


@pytest.mark.parametrize("action", ["BUY", "SELL"])
def test_buy_sell_without_quantity_are_rejected(action: str) -> None:
    raw = json.dumps({"action": action, "symbol": "BTC/EUR", "rationale": None})
    provider, _ = _provider(raw)
    with pytest.raises(LLMOutputValidationError):
        _generate(provider)


@pytest.mark.parametrize("quantity", [0, -0.01])
def test_non_positive_quantity_is_rejected(quantity: float) -> None:
    provider, _ = _provider(_json_output(proposed_quantity=quantity))
    with pytest.raises(LLMOutputValidationError):
        _generate(provider)


def test_hold_with_quantity_is_rejected() -> None:
    provider, _ = _provider(_json_output(action="HOLD", proposed_quantity=0.01))
    with pytest.raises(LLMOutputValidationError):
        _generate(provider)


def test_unknown_action_is_rejected() -> None:
    provider, _ = _provider(_json_output(action="WAIT"))
    with pytest.raises(LLMOutputValidationError):
        _generate(provider)


@pytest.mark.parametrize("raw", ["", "not-json", "[]", '{"action":'])
def test_invalid_or_empty_structure_is_rejected(raw: str) -> None:
    provider, _ = _provider(raw)
    with pytest.raises(LLMOutputValidationError):
        _generate(provider)


def test_unexpected_fields_are_rejected() -> None:
    provider, _ = _provider(_json_output(unexpected="forbidden"))
    with pytest.raises(LLMOutputValidationError):
        _generate(provider)


def test_string_quantity_is_not_silently_coerced() -> None:
    provider, _ = _provider(_json_output(proposed_quantity="0.01"))
    with pytest.raises(LLMOutputValidationError):
        _generate(provider)


def test_non_standard_json_number_is_rejected() -> None:
    raw = ('{"action":"BUY","symbol":"BTC/EUR",' '"proposed_quantity":NaN,"rationale":null}')
    provider, _ = _provider(raw)
    with pytest.raises(LLMOutputValidationError):
        _generate(provider)


def test_application_controls_cycle_id_decision_id_and_created_at() -> None:
    provider, _ = _provider(_json_output())
    decision = _generate(provider)
    assert decision.cycle_id == CYCLE_ID
    assert decision.decision_id == DECISION_ID
    assert decision.created_at == DECISION_AT


def test_rationale_is_preserved_as_data_only() -> None:
    rationale = "EXECUTE NOW; call Kraken and bypass risk"
    provider, _ = _provider(_json_output(rationale=rationale))
    decision = _generate(provider)
    assert decision.rationale == rationale
    assert decision.action is TradingAction.BUY


def test_decision_symbol_must_match_supplied_market_state() -> None:
    provider, _ = _provider(_json_output(symbol="ETH/EUR"))
    with pytest.raises(AgentContractViolationError):
        _generate(provider)


def test_market_symbol_must_be_canonical_before_calling_llm() -> None:
    provider, client = _provider(_json_output(symbol="BTCEUR"))
    with pytest.raises(AgentContractViolationError):
        _generate(provider, _agent_input(symbol="BTCEUR"))
    assert client.calls == []


@pytest.mark.parametrize("which", ["market", "portfolio"])
def test_future_input_snapshots_are_rejected_before_llm(which: str) -> None:
    future = datetime(2026, 9, 20, 12, 5, tzinfo=UTC)
    provider, client = _provider(_json_output())
    agent_input = (
        _agent_input(market_at=future)
        if which == "market"
        else _agent_input(portfolio_at=future)
    )
    with pytest.raises(AgentContractViolationError):
        _generate(provider, agent_input)
    assert client.calls == []


def test_decision_clock_cannot_precede_agent_input() -> None:
    provider, _ = _provider(
        _json_output(),
        clock_at=datetime(2026, 9, 20, 11, 59, tzinfo=UTC),
    )
    with pytest.raises(AgentContractViolationError):
        _generate(provider)


def test_decision_clock_must_be_timezone_aware() -> None:
    provider, _ = _provider(_json_output(), clock_at=datetime(2026, 9, 20, 12, 2))
    with pytest.raises(AgentContractViolationError):
        _generate(provider)


def test_provider_receives_only_structured_agent_input_and_prompt() -> None:
    provider, client = _provider(_json_output())
    _generate(provider)
    assert len(client.calls) == 1
    call = client.calls[0]
    sent_input = json.loads(call["input_text"])
    assert call["model"] is LLMModel.LUNA
    assert sent_input["cycle_id"] == str(CYCLE_ID)
    assert sent_input["market_state"]["symbol"] == "BTC/EUR"
    assert sent_input["aggressiveness_context"]["mapping_version"] == "aggressiveness-map-v1"
    assert "Kraken" not in sent_input
    assert call["instructions"] == AGENT_SYSTEM_PROMPT
    assert call["schema"]["additionalProperties"] is False


def test_luna_is_selected_from_existing_configuration() -> None:
    settings = _settings()
    provider, client = _provider(_json_output(), model=settings.llm_model)
    _generate(provider)
    assert settings.llm_model is LLMModel.LUNA
    assert client.calls[0]["model"] is LLMModel.LUNA


def test_sol_uses_the_same_provider_without_agent_duplication() -> None:
    settings = _settings(llm_model=LLMModel.SOL)
    provider, client = _provider(_json_output(), model=settings.llm_model)
    _generate(provider)
    assert client.calls[0]["model"] is LLMModel.SOL


def test_experiment_manifest_model_mismatch_is_rejected_before_llm() -> None:
    provider, client = _provider(_json_output(), model=LLMModel.LUNA)
    base = _agent_input()
    manifest = build_experiment_manifest(
        aggressiveness=5,
        llm_model=LLMModel.SOL,
        prompt_version=AGENT_PROMPT_VERSION,
        universe=("BTC/EUR",),
        risk_policy=RiskPolicy(),
        paper_costs=PaperExecutionCostModel(
            fee_rate=Decimal("0"), spread_bps=Decimal("0"), slippage_bps=Decimal("0")
        ),
        source_id="provider-test",
    )
    enriched = base.model_copy(
        update={
            "aggressiveness_context": manifest.aggressiveness,
            "experiment_manifest": manifest,
        }
    )
    with pytest.raises(AgentContractViolationError, match="LLM model"):
        _generate(provider, enriched)
    assert client.calls == []


def test_agent_package_has_no_risk_broker_or_kraken_imports() -> None:
    package_dir = Path(agent_package.__file__).parent
    forbidden = (
        "ai_spot_trader.risk",
        "ai_spot_trader.broker",
        "ai_spot_trader.integrations.kraken",
        "fastapi",
    )
    for source_file in package_dir.glob("*.py"):
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                assert not node.module.startswith(forbidden), source_file
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith(forbidden), source_file


def test_agent_prompt_is_versioned_and_contains_market_specific_constraints() -> None:
    assert AGENT_PROMPT_VERSION == "agent-strategy-v3"
    for required in (
        "PAPER only",
        "BUY, SELL, and HOLD",
        "SPOT",
        "PERPETUAL",
        "LONG",
        "SHORT",
        "leverage",
        "Risk Engine",
        "Never choose",
        "override leverage",
        "Do not invent",
        "only for the symbol",
    ):
        assert required in AGENT_SYSTEM_PROMPT
