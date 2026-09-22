import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from pydantic import BaseModel, ConfigDict, JsonValue

from ai_spot_trader.agent.errors import AgentContractViolationError
from ai_spot_trader.agent.prompt import AGENT_PROMPT_VERSION
from ai_spot_trader.agent.provider import OpenAIDecisionProvider
from ai_spot_trader.analytics.paper import (
    MULTI_MARKET_ANALYTICS_VERSION,
    PaperAnalyticsReport,
    PaperAnalyticsSummary,
)
from ai_spot_trader.broker.pricing import PaperExecutionCostModel
from ai_spot_trader.domain.enums import LLMModel, MarketType
from ai_spot_trader.domain.models import (
    AgentInput,
    AssetBalance,
    ExecutableMarket,
    ExperimentManifest,
    MarketSelection,
    MarketSelectionInput,
    MarketState,
    PortfolioState,
    market_selection_digest,
)
from ai_spot_trader.experiments import (
    EXPERIMENT_PROTOCOL_VERSION,
    MODEL_EXPERIMENT_PROTOCOL_VERSION,
    MULTI_MARKET_MODEL_EXPERIMENT_PROTOCOL_VERSION,
    ExperimentComparisonError,
    ExperimentRun,
    build_experiment_manifest,
    build_model_experiment_manifest,
    build_multi_market_model_experiment_manifest,
    compare_model_runs,
    validate_experiment_manifest_digest,
)
from ai_spot_trader.risk.policy import RiskPolicy
from ai_spot_trader.tools.read_only import ReadOnlyFunctionTool, ReadOnlyToolRegistry
from ai_spot_trader.trading.engine import TradingCycleRunner, TradingCycleTimeouts

NOW = datetime(2026, 9, 23, 0, 0, tzinfo=UTC)
END = datetime(2026, 9, 23, 1, 0, tzinfo=UTC)
CYCLE = UUID("10000000-0000-0000-0000-000000000001")
SELECTION = UUID("20000000-0000-0000-0000-000000000002")
PORTFOLIO = UUID("30000000-0000-0000-0000-000000000003")
MARKET = UUID("40000000-0000-0000-0000-000000000004")


class EmptyArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ListArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    limit: int = 20


async def _empty_handler(_: BaseModel) -> JsonValue:
    return {"ok": True}


def _registry(*, list_limit: int = 50, description_suffix: str = "") -> ReadOnlyToolRegistry:
    return ReadOnlyToolRegistry(
        (
            ReadOnlyFunctionTool(
                name="get_market_snapshot",
                description="Return factual market data." + description_suffix,
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                arguments_model=EmptyArgs,
                handler=_empty_handler,
            ),
            ReadOnlyFunctionTool(
                name="list_markets",
                description="List discoverable markets without ranking." + description_suffix,
                parameters={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": list_limit,
                        }
                    },
                    "required": [],
                    "additionalProperties": False,
                },
                arguments_model=ListArgs,
                handler=_empty_handler,
            ),
        ),
        timeout_seconds=5.0,
        max_result_bytes=32768,
    )


def _markets(*, btc_type: MarketType = MarketType.SPOT) -> tuple[ExecutableMarket, ...]:
    return tuple(
        sorted(
            (
                ExecutableMarket(symbol="BTC/USD", market_type=btc_type),
                ExecutableMarket(symbol="ETH/USD", market_type=MarketType.PERPETUAL),
            ),
            key=lambda item: (item.market_type.value, item.symbol),
        )
    )


def _costs() -> PaperExecutionCostModel:
    return PaperExecutionCostModel(
        fee_rate=Decimal("0.001"),
        spread_bps=Decimal("2"),
        slippage_bps=Decimal("3"),
    )


def _policy() -> RiskPolicy:
    return RiskPolicy(allowed_pairs=frozenset({"BTC/USD", "ETH/USD"}))


def _v3(
    model: LLMModel = LLMModel.LUNA,
    *,
    executable_markets: tuple[ExecutableMarket, ...] | None = None,
    registry: ReadOnlyToolRegistry | None = None,
    max_tool_calls: int = 6,
    replicate_index: int = 1,
    market_selection_protocol_version: str = "agent-market-selection-v1",
) -> ExperimentManifest:
    active_registry = registry if registry is not None else _registry()
    return build_multi_market_model_experiment_manifest(
        aggressiveness=5,
        llm_model=model,
        prompt_version=AGENT_PROMPT_VERSION,
        executable_markets=executable_markets or _markets(),
        risk_policy=_policy(),
        paper_costs=_costs(),
        source_id="frozen-multi-market-v1",
        source_digest="d" * 64,
        tool_registry=active_registry,
        max_tool_calls=max_tool_calls,
        replicate_index=replicate_index,
        replicate_count=2,
        window_start=NOW,
        window_end=END,
        market_selection_protocol_version=market_selection_protocol_version,
    )


def _report(net_pnl: str) -> PaperAnalyticsReport:
    net = Decimal(net_pnl)
    return PaperAnalyticsReport(
        calculation_version=MULTI_MARKET_ANALYTICS_VERSION,
        timezone="UTC",
        source_digest="a" * 64,
        summary=PaperAnalyticsSummary(
            initial_equity=Decimal("1000"),
            ending_equity=Decimal("1000") + net,
            gross_pnl=net,
            net_pnl=net,
            fees=Decimal("0"),
            spread_cost=Decimal("0"),
            slippage_cost=Decimal("0"),
            max_drawdown_value=Decimal("0"),
            max_drawdown_fraction=Decimal("0"),
            current_drawdown_value=Decimal("0"),
            current_drawdown_fraction=Decimal("0"),
            current_exposure_value=Decimal("0"),
            current_exposure_fraction=Decimal("0"),
            trade_count=0,
            buy_trade_count=0,
            sell_trade_count=0,
            hold_count=1,
            reject_count=0,
            modify_count=0,
            completed_cycle_count=1,
            failed_cycle_count=0,
            valued_cycle_count=1,
            first_at=NOW,
            last_at=NOW,
        ),
        points=(),
        daily=(),
    )


def test_v3_digest_and_group_are_deterministic() -> None:
    left = _v3()
    right = _v3()

    assert left.protocol_version == MULTI_MARKET_MODEL_EXPERIMENT_PROTOCOL_VERSION
    assert left == right
    assert left.experiment_digest == right.experiment_digest
    assert left.experiment_group_digest == right.experiment_group_digest
    validate_experiment_manifest_digest(left)


def test_v3_typed_executable_universe_changes_run_and_group_identity() -> None:
    spot = _v3(executable_markets=_markets(btc_type=MarketType.SPOT))
    perpetual = _v3(executable_markets=_markets(btc_type=MarketType.PERPETUAL))

    assert spot.universe == perpetual.universe
    assert spot.agent_protocol is not None
    assert perpetual.agent_protocol is not None
    assert spot.agent_protocol.executable_markets != perpetual.agent_protocol.executable_markets
    assert spot.experiment_digest != perpetual.experiment_digest
    assert spot.experiment_group_digest != perpetual.experiment_group_digest


def test_v3_selection_policy_or_effective_tool_capability_changes_group() -> None:
    baseline = _v3()
    policy_changed = _v3(market_selection_protocol_version="agent-market-selection-v2")
    definitions_changed = _v3(registry=_registry(description_suffix=" Revised."))
    list_limit_changed = _v3(registry=_registry(list_limit=25))

    assert baseline.experiment_group_digest != policy_changed.experiment_group_digest
    assert baseline.experiment_group_digest != definitions_changed.experiment_group_digest
    assert baseline.experiment_group_digest != list_limit_changed.experiment_group_digest


def test_v3_group_is_stable_when_only_model_or_replicate_changes() -> None:
    luna_one = _v3(LLMModel.LUNA, replicate_index=1)
    sol_one = _v3(LLMModel.SOL, replicate_index=1)
    luna_two = _v3(LLMModel.LUNA, replicate_index=2)

    assert luna_one.experiment_group_digest == sol_one.experiment_group_digest
    assert luna_one.experiment_group_digest == luna_two.experiment_group_digest
    assert luna_one.experiment_digest != sol_one.experiment_digest
    assert luna_one.experiment_digest != luna_two.experiment_digest


def test_v3_model_comparison_rejects_changed_controlled_tool_capacity() -> None:
    left = _v3(LLMModel.LUNA, registry=_registry(list_limit=50))
    right = _v3(LLMModel.SOL, registry=_registry(list_limit=25))

    with pytest.raises(ExperimentComparisonError, match="controlled fields"):
        compare_model_runs(
            (
                ExperimentRun(left, _report("1")),
                ExperimentRun(right, _report("2")),
            )
        )


def test_v1_v2_payloads_keep_historical_shape_and_round_trip() -> None:
    v1 = build_experiment_manifest(
        aggressiveness=5,
        llm_model=LLMModel.LUNA,
        prompt_version=AGENT_PROMPT_VERSION,
        universe=("BTC/USD",),
        risk_policy=RiskPolicy(allowed_pairs=frozenset({"BTC/USD"})),
        paper_costs=_costs(),
        source_id="legacy-v1",
    )
    v2 = build_model_experiment_manifest(
        aggressiveness=5,
        llm_model=LLMModel.LUNA,
        prompt_version=AGENT_PROMPT_VERSION,
        universe=("BTC/USD",),
        risk_policy=RiskPolicy(allowed_pairs=frozenset({"BTC/USD"})),
        paper_costs=_costs(),
        source_id="legacy-v2",
        source_digest="e" * 64,
    )

    assert v1.protocol_version == EXPERIMENT_PROTOCOL_VERSION
    assert v2.protocol_version == MODEL_EXPERIMENT_PROTOCOL_VERSION
    for original in (v1, v2):
        payload = original.model_dump(mode="json")
        assert "agent_protocol" not in payload
        restored = ExperimentManifest.model_validate_json(json.dumps(payload))
        assert restored == original
        assert restored.experiment_digest == original.experiment_digest
        validate_experiment_manifest_digest(restored)


def test_v3_agent_input_persisted_payload_round_trips() -> None:
    experiment = _v3()
    selected = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT)
    selection = MarketSelection(
        selection_id=SELECTION,
        cycle_id=CYCLE,
        selected_at=NOW,
        symbol=selected.symbol,
        market_type=selected.market_type,
        rationale="test",
        selection_digest=market_selection_digest(
            selection_id=SELECTION,
            cycle_id=CYCLE,
            selected_at=NOW,
            symbol=selected.symbol,
            market_type=selected.market_type,
            tool_traces=(),
            rationale="test",
        ),
    )
    value = AgentInput(
        cycle_id=CYCLE,
        created_at=NOW,
        market_state=MarketState(
            market_state_id=MARKET,
            as_of=NOW,
            symbol="BTC/USD",
            last_price=Decimal("50000"),
        ),
        portfolio_state=PortfolioState(
            portfolio_state_id=PORTFOLIO,
            as_of=NOW,
            balances=(AssetBalance(asset="USD", available=Decimal("1000")),),
        ),
        aggressiveness=5,
        aggressiveness_context=experiment.aggressiveness,
        experiment_manifest=experiment,
        market_selection=selection,
    )

    restored = AgentInput.model_validate_json(value.model_dump_json())
    assert restored == value
    assert restored.experiment_manifest is not None
    assert restored.experiment_manifest.agent_protocol == experiment.agent_protocol


class NeverCalledClient:
    def __init__(self) -> None:
        self.calls = 0

    async def generate_structured_decision(
        self,
        *,
        model: LLMModel,
        instructions: str,
        input_text: str,
        schema: dict[str, Any],
    ) -> str:
        self.calls += 1
        return '{"symbol":"BTC/USD","market_type":"SPOT","rationale":null}'

    async def generate_structured_decision_with_tools(self, **_: Any) -> Any:
        self.calls += 1
        raise AssertionError("LLM must not be called for an incoherent v3 manifest")


def _selection_input(experiment: ExperimentManifest) -> MarketSelectionInput:
    assert experiment.agent_protocol is not None
    return MarketSelectionInput(
        cycle_id=CYCLE,
        created_at=NOW,
        portfolio_state=PortfolioState(
            portfolio_state_id=PORTFOLIO,
            as_of=NOW,
            balances=(AssetBalance(asset="USD", available=Decimal("1000")),),
        ),
        executable_markets=experiment.agent_protocol.executable_markets,
        aggressiveness=5,
        aggressiveness_context=experiment.aggressiveness,
        experiment_manifest=experiment,
    )


def test_provider_rejects_v3_selection_policy_mismatch_before_llm() -> None:
    registry = _registry()
    experiment = _v3(
        registry=registry,
        market_selection_protocol_version="agent-market-selection-other",
    )
    client = NeverCalledClient()
    provider = OpenAIDecisionProvider(
        client=client,
        model=LLMModel.LUNA,
        tool_registry=registry,
        max_tool_calls=6,
    )

    with pytest.raises(AgentContractViolationError, match="market-selection protocol"):
        asyncio.run(provider.select_market(_selection_input(experiment)))
    assert client.calls == 0


def test_provider_rejects_changed_effective_tool_definitions_before_llm() -> None:
    manifest_registry = _registry()
    active_registry = _registry(description_suffix=" Active drift.")
    experiment = _v3(registry=manifest_registry)
    client = NeverCalledClient()
    provider = OpenAIDecisionProvider(
        client=client,
        model=LLMModel.LUNA,
        tool_registry=active_registry,
        max_tool_calls=6,
    )

    with pytest.raises(AgentContractViolationError, match="tool definitions"):
        asyncio.run(provider.select_market(_selection_input(experiment)))
    assert client.calls == 0


class SelectingAgent:
    async def select_market(self, value: MarketSelectionInput) -> MarketSelection:
        raise AssertionError("runner construction should fail before Agent invocation")

    async def generate_decision(self, value: AgentInput) -> Any:
        raise AssertionError("runner construction should fail before Agent invocation")


class DummyExecutionMarkets:
    async def snapshot(self, symbol: str, market_type: MarketType) -> MarketState:
        raise AssertionError("runner construction should fail before market acquisition")


class DummyPortfolio:
    def snapshot(self, *, as_of: datetime | None = None) -> PortfolioState:
        raise AssertionError("runner construction should fail before portfolio access")


class DummyRisk:
    pass


class DummyBroker:
    pass


def test_runner_rejects_typed_universe_mismatch_before_agent_call() -> None:
    experiment = build_multi_market_model_experiment_manifest(
        aggressiveness=5,
        llm_model=LLMModel.LUNA,
        prompt_version=AGENT_PROMPT_VERSION,
        executable_markets=(
            ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),
        ),
        risk_policy=RiskPolicy(allowed_pairs=frozenset({"BTC/USD"})),
        paper_costs=_costs(),
        source_id="runner-v3",
        source_digest="f" * 64,
        tool_registry=None,
        max_tool_calls=0,
    )

    with pytest.raises(ValueError, match="typed experiment universe"):
        TradingCycleRunner(
            executable_market_data=DummyExecutionMarkets(),
            executable_markets=(
                ExecutableMarket(symbol="BTC/USD", market_type=MarketType.PERPETUAL),
            ),
            portfolio=DummyPortfolio(),  # type: ignore[arg-type]
            agent=SelectingAgent(),
            risk_engine=DummyRisk(),  # type: ignore[arg-type]
            broker=DummyBroker(),  # type: ignore[arg-type]
            aggressiveness=5,
            timeouts=TradingCycleTimeouts(1, 1, 1),
            experiment_manifest=experiment,
        )


def test_historical_v2_digest_fixture_is_unchanged() -> None:
    historical = build_model_experiment_manifest(
        aggressiveness=5,
        llm_model=LLMModel.LUNA,
        prompt_version=AGENT_PROMPT_VERSION,
        universe=("BTC/EUR",),
        risk_policy=RiskPolicy(allowed_pairs=frozenset({"BTC/EUR"})),
        paper_costs=_costs(),
        source_id="frozen-replay-v1",
        source_digest="d" * 64,
        window_start=datetime(2026, 9, 20, 12, 0, tzinfo=UTC),
        window_end=datetime(2026, 9, 20, 13, 0, tzinfo=UTC),
    )

    assert historical.experiment_digest == (
        "4a2bca5b9dfbbfb9b9ba6f7f766a64d3bdc0ba42f602e40646eb2baa8362e5f6"
    )
    assert historical.experiment_group_digest == (
        "3bb36a16ea642f080b4127536c44c20b253275e0c208acdcd057d16741297df2"
    )
