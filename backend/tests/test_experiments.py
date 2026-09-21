import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from ai_spot_trader.agent.prompt import AGENT_PROMPT_VERSION
from ai_spot_trader.analytics.paper import (
    ANALYTICS_VERSION,
    PaperAnalyticsCycleFact,
    PaperAnalyticsReport,
    PaperAnalyticsSummary,
    build_paper_analytics_report,
)
from ai_spot_trader.broker.pricing import PaperExecutionCostModel
from ai_spot_trader.domain.enums import (
    ExperimentVariable,
    LLMModel,
    RiskDecision,
    RiskReason,
    TradingAction,
)
from ai_spot_trader.domain.models import (
    AgentInput,
    AssetBalance,
    AssetPosition,
    DecisionCandidate,
    ExperimentManifest,
    MarketState,
    PortfolioState,
    RiskAssessment,
)
from ai_spot_trader.experiments import (
    AGGRESSIVENESS_MAPPING_VERSION,
    MODEL_EXPERIMENT_PROTOCOL_VERSION,
    ExperimentComparisonError,
    ExperimentRun,
    aggressiveness_context,
    build_experiment_manifest,
    build_model_experiment_manifest,
    compare_aggressiveness_runs,
    compare_model_runs,
    validate_experiment_manifest_digest,
)
from ai_spot_trader.risk.engine import RiskEngine, RiskResult
from ai_spot_trader.risk.policy import RiskPolicy

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
END = datetime(2026, 9, 20, 13, 0, tzinfo=UTC)
CYCLE_ID = UUID("10000000-0000-0000-0000-000000000001")
DECISION_ID = UUID("20000000-0000-0000-0000-000000000002")
RISK_ID = UUID("30000000-0000-0000-0000-000000000003")
MARKET_ID = UUID("40000000-0000-0000-0000-000000000004")
PORTFOLIO_ID = UUID("50000000-0000-0000-0000-000000000005")


class FixedClock:
    def now(self) -> datetime:
        return NOW


def costs(
    *,
    fee_rate: str = "0.001",
    spread_bps: str = "2",
    slippage_bps: str = "3",
) -> PaperExecutionCostModel:
    return PaperExecutionCostModel(
        fee_rate=Decimal(fee_rate),
        spread_bps=Decimal(spread_bps),
        slippage_bps=Decimal(slippage_bps),
    )


def policy(*, reduction: bool = False, max_notional: str | None = None) -> RiskPolicy:
    return RiskPolicy(
        max_order_notional=(Decimal(max_notional) if max_notional is not None else None),
        allowed_pairs=frozenset({"BTC/EUR"}),
        allow_quantity_reduction=reduction,
    )


def manifest(level: int, *, risk_policy: RiskPolicy | None = None) -> ExperimentManifest:
    return build_experiment_manifest(
        aggressiveness=level,
        llm_model=LLMModel.LUNA,
        prompt_version=AGENT_PROMPT_VERSION,
        universe=("BTC/EUR",),
        risk_policy=risk_policy or policy(),
        paper_costs=costs(),
        source_id="fixture-market-v1",
        source_digest="a" * 64,
        window_start=NOW,
        window_end=END,
    )


def model_manifest(
    model: LLMModel,
    *,
    replicate_index: int = 1,
    replicate_count: int = 1,
    aggressiveness: int = 5,
    prompt_version: str = AGENT_PROMPT_VERSION,
    risk_policy: RiskPolicy | None = None,
    paper_costs: PaperExecutionCostModel | None = None,
    source_id: str = "frozen-replay-v1",
    source_digest: str = "d" * 64,
    universe: tuple[str, ...] = ("BTC/EUR",),
    window_start: datetime | None = NOW,
    window_end: datetime | None = END,
    analytics_version: str = ANALYTICS_VERSION,
) -> ExperimentManifest:
    return build_model_experiment_manifest(
        aggressiveness=aggressiveness,
        llm_model=model,
        prompt_version=prompt_version,
        universe=universe,
        risk_policy=risk_policy or policy(),
        paper_costs=paper_costs or costs(),
        source_id=source_id,
        source_digest=source_digest,
        replicate_index=replicate_index,
        replicate_count=replicate_count,
        window_start=window_start,
        window_end=window_end,
        analytics_version=analytics_version,
    )


def portfolio() -> PortfolioState:
    return PortfolioState(
        portfolio_state_id=PORTFOLIO_ID,
        as_of=NOW,
        balances=(AssetBalance(asset="EUR", available=Decimal("1000")),),
        positions=(
            AssetPosition(asset="BTC", quantity=Decimal("2"), available=Decimal("2")),
        ),
    )


def market() -> MarketState:
    return MarketState(
        market_state_id=MARKET_ID,
        as_of=NOW,
        symbol="BTC/EUR",
        last_price=Decimal("100"),
    )


def summary(*, net_pnl: str, holds: int = 0) -> PaperAnalyticsSummary:
    net = Decimal(net_pnl)
    return PaperAnalyticsSummary(
        initial_equity=Decimal("1200"),
        ending_equity=Decimal("1200") + net,
        gross_pnl=net + Decimal("1"),
        net_pnl=net,
        fees=Decimal("0.4"),
        spread_cost=Decimal("0.3"),
        slippage_cost=Decimal("0.3"),
        max_drawdown_value=Decimal("10"),
        max_drawdown_fraction=Decimal("0.01"),
        current_drawdown_value=Decimal("5"),
        current_drawdown_fraction=Decimal("0.005"),
        current_exposure_value=Decimal("200"),
        current_exposure_fraction=Decimal("0.1666666667"),
        trade_count=2,
        buy_trade_count=1,
        sell_trade_count=1,
        hold_count=holds,
        reject_count=1,
        modify_count=1,
        completed_cycle_count=4,
        failed_cycle_count=1,
        valued_cycle_count=4,
        first_at=NOW,
        last_at=NOW,
    )


def report(*, net_pnl: str, source_digest: str) -> PaperAnalyticsReport:
    return PaperAnalyticsReport(
        calculation_version=ANALYTICS_VERSION,
        timezone="UTC",
        source_digest=source_digest,
        summary=summary(net_pnl=net_pnl),
        points=(),
        daily=(),
    )


@pytest.mark.parametrize("level", [0, 11, -1, True])
def test_aggressiveness_rejects_values_outside_integer_1_to_10(level: object) -> None:
    with pytest.raises(ValueError):
        aggressiveness_context(level)  # type: ignore[arg-type]


def test_aggressiveness_mapping_is_discrete_versioned_and_deterministic() -> None:
    first = tuple(aggressiveness_context(level) for level in range(1, 11))
    second = tuple(aggressiveness_context(level) for level in range(1, 11))

    assert first == second
    assert {item.mapping_version for item in first} == {AGGRESSIVENESS_MAPPING_VERSION}
    assert [item.level for item in first] == list(range(1, 11))
    assert len({item.posture for item in first}) == 10
    assert len({item.strategic_instruction for item in first}) == 10


def test_agent_input_rejects_mismatched_aggressiveness_context() -> None:
    with pytest.raises(ValidationError):
        AgentInput(
            cycle_id=CYCLE_ID,
            created_at=NOW,
            market_state=market(),
            portfolio_state=portfolio(),
            aggressiveness=5,
            aggressiveness_context=aggressiveness_context(6),
        )


def test_same_configuration_produces_same_manifest_digest() -> None:
    left = manifest(5)
    right = manifest(5)

    assert left == right
    assert left.experiment_digest == right.experiment_digest
    assert (
        left.experiment_digest
        == "e458683918bdafa7300a3e5984cee8df52336bce2c3543802ad990495ee364f6"
    )
    validate_experiment_manifest_digest(left)


def test_different_aggressiveness_levels_produce_distinct_manifest_digests() -> None:
    low = manifest(2)
    high = manifest(9)

    assert low.experiment_digest != high.experiment_digest
    assert low.aggressiveness.level == 2
    assert high.aggressiveness.level == 9


def test_tampered_manifest_digest_is_rejected() -> None:
    original = manifest(5)
    tampered = original.model_copy(update={"source_id": "changed-after-digest"})

    with pytest.raises(ValueError, match="digest"):
        validate_experiment_manifest_digest(tampered)


def test_comparison_reuses_batch_12_reports_without_ranking() -> None:
    comparison = compare_aggressiveness_runs(
        (
            ExperimentRun(
                manifest=manifest(8),
                analytics=report(net_pnl="12", source_digest="8" * 64),
            ),
            ExperimentRun(
                manifest=manifest(3),
                analytics=report(net_pnl="5", source_digest="3" * 64),
            ),
        )
    )

    assert comparison.analytics_version == ANALYTICS_VERSION
    assert [row.aggressiveness for row in comparison.rows] == [3, 8]
    assert [row.net_pnl for row in comparison.rows] == [Decimal("5"), Decimal("12")]
    assert [row.analytics_source_digest for row in comparison.rows] == ["3" * 64, "8" * 64]


def test_comparison_rejects_changed_risk_policy() -> None:
    with pytest.raises(ExperimentComparisonError, match="controlled fields"):
        compare_aggressiveness_runs(
            (
                ExperimentRun(
                    manifest=manifest(3),
                    analytics=report(net_pnl="1", source_digest="1" * 64),
                ),
                ExperimentRun(
                    manifest=manifest(8, risk_policy=policy(max_notional="50")),
                    analytics=report(net_pnl="2", source_digest="2" * 64),
                ),
            )
        )


def test_risk_outcomes_are_independent_of_aggressiveness() -> None:
    sell_too_much = DecisionCandidate(
        decision_id=DECISION_ID,
        cycle_id=CYCLE_ID,
        created_at=NOW,
        action=TradingAction.SELL,
        symbol="BTC/EUR",
        proposed_quantity=Decimal("3"),
    )

    results = []
    for level in (1, 10):
        assert aggressiveness_context(level).level == level
        engine = RiskEngine(
            policy=policy(),
            cost_model=costs(),
            clock=FixedClock(),
            risk_assessment_id_factory=lambda: RISK_ID,
            execution_id_factory=lambda: UUID("60000000-0000-0000-0000-000000000006"),
        )
        results.append(
            engine.evaluate(
                decision=sell_too_much,
                market_state=market(),
                portfolio_state=portfolio(),
            )
        )

    assert all(item.assessment.status is RiskDecision.REJECT for item in results)
    assert all(item.execution_intent is None for item in results)
    assert all(item.assessment.reasons == (RiskReason.INSUFFICIENT_POSITION,) for item in results)


def test_risk_preserves_hold_allow_modify_and_reject_semantics() -> None:
    def evaluate(
        action: TradingAction,
        quantity: Decimal | None,
        *,
        reduction: bool = False,
    ) -> RiskResult:
        engine = RiskEngine(
            policy=policy(reduction=reduction),
            cost_model=costs(),
            clock=FixedClock(),
            risk_assessment_id_factory=lambda: RISK_ID,
            execution_id_factory=lambda: UUID("60000000-0000-0000-0000-000000000006"),
        )
        return engine.evaluate(
            decision=DecisionCandidate(
                decision_id=DECISION_ID,
                cycle_id=CYCLE_ID,
                created_at=NOW,
                action=action,
                symbol="BTC/EUR",
                proposed_quantity=quantity,
            ),
            market_state=market(),
            portfolio_state=portfolio(),
        )

    hold = evaluate(TradingAction.HOLD, None)
    allow = evaluate(TradingAction.BUY, Decimal("1"))
    modify = evaluate(TradingAction.SELL, Decimal("3"), reduction=True)
    reject = evaluate(TradingAction.SELL, Decimal("3"))

    assert hold.assessment.status is RiskDecision.ALLOW and hold.execution_intent is None
    assert allow.assessment.status is RiskDecision.ALLOW and allow.execution_intent is not None
    assert modify.assessment.status is RiskDecision.MODIFY and modify.execution_intent is not None
    assert modify.execution_intent.quantity == Decimal("2")
    assert reject.assessment.status is RiskDecision.REJECT and reject.execution_intent is None


def test_batch_12_analytics_accepts_persisted_experiment_manifest() -> None:
    experiment = manifest(5)
    agent_input = AgentInput(
        cycle_id=CYCLE_ID,
        created_at=NOW,
        market_state=market(),
        portfolio_state=portfolio(),
        aggressiveness=5,
        aggressiveness_context=experiment.aggressiveness,
        experiment_manifest=experiment,
    )
    decision = DecisionCandidate(
        decision_id=DECISION_ID,
        cycle_id=CYCLE_ID,
        created_at=NOW,
        action=TradingAction.HOLD,
        symbol="BTC/EUR",
        proposed_quantity=None,
    )
    risk = RiskAssessment(
        risk_assessment_id=RISK_ID,
        cycle_id=CYCLE_ID,
        decision_id=DECISION_ID,
        assessed_at=NOW,
        status=RiskDecision.ALLOW,
        requested_quantity=None,
        authorized_quantity=None,
        reasons=(RiskReason.HOLD_NO_EXECUTION,),
    )
    fact = PaperAnalyticsCycleFact(
        cycle_id=CYCLE_ID,
        status="COMPLETED",
        recorded_at=NOW,
        result_digest="f" * 64,
        agent_input_payload=agent_input.model_dump(mode="json"),
        decision_payload=decision.model_dump(mode="json"),
        risk_assessment_payload=risk.model_dump(mode="json"),
        fill_payloads=(),
        portfolio_after_payload=None,
    )

    analytics = build_paper_analytics_report((fact,))

    assert analytics.calculation_version == ANALYTICS_VERSION
    assert analytics.summary.hold_count == 1
    assert analytics.summary.trade_count == 0


def test_durable_agent_input_payload_distinguishes_levels_and_round_trips() -> None:
    low_manifest = manifest(2)
    high_manifest = manifest(9)
    payloads = []
    for experiment in (low_manifest, high_manifest):
        value = AgentInput(
            cycle_id=CYCLE_ID,
            created_at=NOW,
            market_state=market(),
            portfolio_state=portfolio(),
            aggressiveness=experiment.aggressiveness.level,
            aggressiveness_context=experiment.aggressiveness,
            experiment_manifest=experiment,
        )
        payload = value.model_dump(mode="json")
        restored = AgentInput.model_validate_json(json.dumps(payload))
        assert restored == value
        payloads.append(payload)

    assert payloads[0]["aggressiveness"] == 2
    assert payloads[1]["aggressiveness"] == 9
    assert (
        payloads[0]["experiment_manifest"]["experiment_digest"]
        != payloads[1]["experiment_manifest"]["experiment_digest"]
    )


def test_comparison_rejects_different_source_facts() -> None:
    left = manifest(3)
    right = build_experiment_manifest(
        aggressiveness=8,
        llm_model=LLMModel.LUNA,
        prompt_version=AGENT_PROMPT_VERSION,
        universe=("BTC/EUR",),
        risk_policy=policy(),
        paper_costs=costs(),
        source_id="other-fixture",
        source_digest="b" * 64,
        window_start=NOW,
        window_end=END,
    )

    with pytest.raises(ExperimentComparisonError, match="controlled fields"):
        compare_aggressiveness_runs(
            (
                ExperimentRun(
                    manifest=left,
                    analytics=report(net_pnl="1", source_digest="1" * 64),
                ),
                ExperimentRun(
                    manifest=right,
                    analytics=report(net_pnl="2", source_digest="2" * 64),
                ),
            )
        )


def test_manifest_digest_is_based_on_normalized_values() -> None:
    start_local = datetime.fromisoformat("2026-09-20T14:00:00+02:00")
    end_local = datetime.fromisoformat("2026-09-20T15:00:00+02:00")
    value = build_experiment_manifest(
        aggressiveness=5,
        llm_model=LLMModel.LUNA,
        prompt_version=f"  {AGENT_PROMPT_VERSION}  ",
        universe=("BTC/EUR",),
        risk_policy=policy(),
        paper_costs=costs(),
        source_id="  normalized-fixture  ",
        window_start=start_local,
        window_end=end_local,
    )

    validate_experiment_manifest_digest(value)
    assert value.prompt_version == AGENT_PROMPT_VERSION
    assert value.source_id == "normalized-fixture"
    assert value.window_start == NOW
    assert value.window_end == END


# Batch 14 — controlled Luna/Sol comparison.


def test_luna_and_sol_are_representable_in_same_model_protocol() -> None:
    luna = model_manifest(LLMModel.LUNA)
    sol = model_manifest(LLMModel.SOL)

    assert luna.protocol_version == MODEL_EXPERIMENT_PROTOCOL_VERSION
    assert sol.protocol_version == MODEL_EXPERIMENT_PROTOCOL_VERSION
    assert luna.comparison_variable is ExperimentVariable.LLM_MODEL
    assert luna.experiment_group_digest == sol.experiment_group_digest
    assert luna.experiment_digest != sol.experiment_digest
    validate_experiment_manifest_digest(luna)
    validate_experiment_manifest_digest(sol)


def test_identical_runs_outside_model_are_comparable_factually() -> None:
    comparison = compare_model_runs(
        (
            ExperimentRun(
                manifest=model_manifest(LLMModel.SOL),
                analytics=report(net_pnl="7", source_digest="7" * 64),
            ),
            ExperimentRun(
                manifest=model_manifest(LLMModel.LUNA),
                analytics=report(net_pnl="5", source_digest="5" * 64),
            ),
        )
    )

    assert comparison.replicate_count == 1
    assert comparison.analytics_version == ANALYTICS_VERSION
    assert {row.llm_model for row in comparison.rows} == {LLMModel.LUNA, LLMModel.SOL}
    assert {row.net_pnl for row in comparison.rows} == {Decimal("5"), Decimal("7")}
    assert all(row.trade_count == 2 for row in comparison.rows)
    assert all(row.hold_count == 0 for row in comparison.rows)
    assert all(row.reject_count == 1 for row in comparison.rows)
    assert all(row.modify_count == 1 for row in comparison.rows)
    assert all(row.failed_cycle_count == 1 for row in comparison.rows)


def _assert_model_comparison_rejected(left: ExperimentManifest, right: ExperimentManifest) -> None:
    with pytest.raises(ExperimentComparisonError, match="controlled fields"):
        compare_model_runs(
            (
                ExperimentRun(left, report(net_pnl="1", source_digest="1" * 64)),
                ExperimentRun(right, report(net_pnl="2", source_digest="2" * 64)),
            )
        )


def test_model_comparison_rejects_changed_aggressiveness() -> None:
    _assert_model_comparison_rejected(
        model_manifest(LLMModel.LUNA, aggressiveness=5),
        model_manifest(LLMModel.SOL, aggressiveness=6),
    )


def test_model_comparison_rejects_changed_prompt() -> None:
    _assert_model_comparison_rejected(
        model_manifest(LLMModel.LUNA),
        model_manifest(LLMModel.SOL, prompt_version="agent-strategy-other"),
    )


def test_model_comparison_rejects_changed_risk_policy() -> None:
    _assert_model_comparison_rejected(
        model_manifest(LLMModel.LUNA),
        model_manifest(LLMModel.SOL, risk_policy=policy(max_notional="50")),
    )


def test_model_comparison_rejects_changed_paper_costs() -> None:
    _assert_model_comparison_rejected(
        model_manifest(LLMModel.LUNA),
        model_manifest(LLMModel.SOL, paper_costs=costs(fee_rate="0.002")),
    )


def test_model_comparison_rejects_changed_dataset_source() -> None:
    _assert_model_comparison_rejected(
        model_manifest(LLMModel.LUNA),
        model_manifest(LLMModel.SOL, source_digest="e" * 64),
    )


@pytest.mark.parametrize(
    "sol",
    [
        {"universe": ("ETH/EUR",)},
        {
            "window_start": datetime(2026, 9, 20, 12, 30, tzinfo=UTC),
            "window_end": END,
        },
        {"analytics_version": "paper-analytics-v2"},
    ],
)
def test_model_comparison_rejects_changed_universe_window_or_analytics_version(
    sol: dict[str, object],
) -> None:
    _assert_model_comparison_rejected(
        model_manifest(LLMModel.LUNA),
        model_manifest(LLMModel.SOL, **sol),  # type: ignore[arg-type]
    )


def test_model_protocol_requires_frozen_source_digest() -> None:
    with pytest.raises(ValueError, match="frozen source_digest"):
        build_model_experiment_manifest(
            aggressiveness=5,
            llm_model=LLMModel.LUNA,
            prompt_version=AGENT_PROMPT_VERSION,
            universe=("BTC/EUR",),
            risk_policy=policy(),
            paper_costs=costs(),
            source_id="unfrozen",
            source_digest=None,  # type: ignore[arg-type]
        )


def test_model_repetitions_are_complete_paired_and_not_post_hoc_subset() -> None:
    runs = tuple(
        ExperimentRun(
            manifest=model_manifest(model, replicate_index=index, replicate_count=2),
            analytics=report(
                net_pnl=str(index + (0 if model is LLMModel.LUNA else 1)),
                source_digest=f"{index + (0 if model is LLMModel.LUNA else 2):064x}",
            ),
        )
        for index in (1, 2)
        for model in (LLMModel.LUNA, LLMModel.SOL)
    )

    comparison = compare_model_runs(runs)
    assert comparison.replicate_count == 2
    assert [(row.replicate_index, row.llm_model) for row in comparison.rows] == [
        (1, LLMModel.LUNA),
        (1, LLMModel.SOL),
        (2, LLMModel.LUNA),
        (2, LLMModel.SOL),
    ]

    with pytest.raises(ExperimentComparisonError, match="every declared replicate"):
        compare_model_runs(runs[:-1])


def test_model_run_and_group_digests_are_deterministic() -> None:
    left = model_manifest(LLMModel.LUNA, replicate_index=2, replicate_count=3)
    right = model_manifest(LLMModel.LUNA, replicate_index=2, replicate_count=3)
    other_replicate = model_manifest(LLMModel.LUNA, replicate_index=3, replicate_count=3)
    sol_same_group = model_manifest(LLMModel.SOL, replicate_index=2, replicate_count=3)

    assert left == right
    assert left.experiment_digest == right.experiment_digest
    assert left.experiment_group_digest == right.experiment_group_digest
    assert left.experiment_digest != other_replicate.experiment_digest
    assert left.experiment_group_digest == other_replicate.experiment_group_digest
    assert left.experiment_group_digest == sol_same_group.experiment_group_digest


def test_model_experiment_identity_round_trips_through_durable_agent_input() -> None:
    experiment = model_manifest(LLMModel.SOL, replicate_index=2, replicate_count=3)
    value = AgentInput(
        cycle_id=CYCLE_ID,
        created_at=NOW,
        market_state=market(),
        portfolio_state=portfolio(),
        aggressiveness=experiment.aggressiveness.level,
        aggressiveness_context=experiment.aggressiveness,
        experiment_manifest=experiment,
    )

    restored = AgentInput.model_validate_json(value.model_dump_json())

    assert restored == value
    assert restored.experiment_manifest is not None
    assert restored.experiment_manifest.experiment_digest == experiment.experiment_digest
    assert (
        restored.experiment_manifest.experiment_group_digest
        == experiment.experiment_group_digest
    )
    assert restored.experiment_manifest.replicate_index == 2
    assert restored.experiment_manifest.replicate_count == 3


def test_old_batch_13_manifest_payload_without_batch_14_fields_remains_readable() -> None:
    original = manifest(5)
    old_payload = original.model_dump(
        mode="json",
        exclude={
            "comparison_variable",
            "experiment_group_digest",
            "replicate_index",
            "replicate_count",
        },
    )

    restored = ExperimentManifest.model_validate_json(json.dumps(old_payload))

    assert restored.experiment_digest == original.experiment_digest
    assert restored.comparison_variable is None
    validate_experiment_manifest_digest(restored)


def test_batch_12_analytics_accepts_persisted_model_experiment_manifest() -> None:
    experiment = model_manifest(LLMModel.LUNA)
    agent_input = AgentInput(
        cycle_id=CYCLE_ID,
        created_at=NOW,
        market_state=market(),
        portfolio_state=portfolio(),
        aggressiveness=5,
        aggressiveness_context=experiment.aggressiveness,
        experiment_manifest=experiment,
    )
    decision = DecisionCandidate(
        decision_id=DECISION_ID,
        cycle_id=CYCLE_ID,
        created_at=NOW,
        action=TradingAction.HOLD,
        symbol="BTC/EUR",
        proposed_quantity=None,
    )
    risk = RiskAssessment(
        risk_assessment_id=RISK_ID,
        cycle_id=CYCLE_ID,
        decision_id=DECISION_ID,
        assessed_at=NOW,
        status=RiskDecision.ALLOW,
        requested_quantity=None,
        authorized_quantity=None,
        reasons=(RiskReason.HOLD_NO_EXECUTION,),
    )
    fact = PaperAnalyticsCycleFact(
        cycle_id=CYCLE_ID,
        status="COMPLETED",
        recorded_at=NOW,
        result_digest="9" * 64,
        agent_input_payload=agent_input.model_dump(mode="json"),
        decision_payload=decision.model_dump(mode="json"),
        risk_assessment_payload=risk.model_dump(mode="json"),
        fill_payloads=(),
        portfolio_after_payload=None,
    )

    analytics = build_paper_analytics_report((fact,))

    assert analytics.calculation_version == ANALYTICS_VERSION
    assert analytics.summary.hold_count == 1
    assert analytics.summary.failed_cycle_count == 0


def test_risk_result_is_identical_regardless_of_manifest_model_identity() -> None:
    sell_too_much = DecisionCandidate(
        decision_id=DECISION_ID,
        cycle_id=CYCLE_ID,
        created_at=NOW,
        action=TradingAction.SELL,
        symbol="BTC/EUR",
        proposed_quantity=Decimal("3"),
    )
    outcomes = []

    for model in (LLMModel.LUNA, LLMModel.SOL):
        experiment = model_manifest(model)
        validate_experiment_manifest_digest(experiment)
        engine = RiskEngine(
            policy=policy(),
            cost_model=costs(),
            clock=FixedClock(),
            risk_assessment_id_factory=lambda: RISK_ID,
            execution_id_factory=lambda: UUID("60000000-0000-0000-0000-000000000006"),
        )
        outcomes.append(
            engine.evaluate(
                decision=sell_too_much,
                market_state=market(),
                portfolio_state=portfolio(),
            )
        )

    assert outcomes[0] == outcomes[1]
    assert outcomes[0].assessment.status is RiskDecision.REJECT
    assert outcomes[0].execution_intent is None
