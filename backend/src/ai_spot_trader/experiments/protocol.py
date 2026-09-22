from datetime import datetime
from decimal import Decimal

from ai_spot_trader.analytics.paper import ANALYTICS_VERSION, MULTI_MARKET_ANALYTICS_VERSION
from ai_spot_trader.broker.pricing import PaperExecutionCostModel
from ai_spot_trader.domain.enums import ExperimentVariable, LLMModel
from ai_spot_trader.domain.experiments import (
    AGGRESSIVENESS_MAPPING_VERSION,
    EXPERIMENT_PROTOCOL_VERSION,
    MARKET_SELECTION_PROTOCOL_VERSION,
    MODEL_EXPERIMENT_PROTOCOL_VERSION,
    MULTI_MARKET_MODEL_EXPERIMENT_PROTOCOL_VERSION,
    aggressiveness_context,
    canonical_experiment_digest,
    comparison_identity,
    manifest_digest_payload,
    model_comparison_group_digest,
    model_comparison_identity,
    validate_experiment_manifest_digest,
)
from ai_spot_trader.domain.models import (
    ExecutableMarket,
    ExperimentAgentPhaseSnapshot,
    ExperimentAgentProtocolSnapshot,
    ExperimentManifest,
    ExperimentPaperCostSnapshot,
    ExperimentRiskPolicySnapshot,
)
from ai_spot_trader.domain.symbols import parse_canonical_symbol
from ai_spot_trader.risk.policy import RiskPolicy
from ai_spot_trader.tools.read_only import ReadOnlyToolRegistry


def risk_policy_snapshot(policy: RiskPolicy) -> ExperimentRiskPolicySnapshot:
    """Convert an injected RiskPolicy into a canonical immutable experiment identity."""

    allowed_pairs = None
    if policy.allowed_pairs is not None:
        allowed_pairs = tuple(sorted(policy.allowed_pairs))
    stale_after_seconds = None
    if policy.stale_after is not None:
        stale_after_seconds = Decimal(str(policy.stale_after.total_seconds()))
    return ExperimentRiskPolicySnapshot(
        max_order_notional=policy.max_order_notional,
        allowed_pairs=allowed_pairs,
        stale_after_seconds=stale_after_seconds,
        allow_quantity_reduction=policy.allow_quantity_reduction,
    )


def paper_cost_snapshot(cost_model: PaperExecutionCostModel) -> ExperimentPaperCostSnapshot:
    """Convert the injected PAPER cost model into a canonical experiment identity."""

    return ExperimentPaperCostSnapshot(
        fee_rate=cost_model.fee_rate,
        spread_bps=cost_model.spread_bps,
        slippage_bps=cost_model.slippage_bps,
    )


def build_experiment_manifest(
    *,
    aggressiveness: int,
    llm_model: LLMModel,
    prompt_version: str,
    universe: tuple[str, ...],
    risk_policy: RiskPolicy,
    paper_costs: PaperExecutionCostModel,
    source_id: str,
    source_digest: str | None = None,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    analytics_version: str = ANALYTICS_VERSION,
) -> ExperimentManifest:
    """Build a Batch 13 manifest whose digest preserves the original v1 wire identity."""

    provisional = _provisional_manifest(
        protocol_version=EXPERIMENT_PROTOCOL_VERSION,
        aggressiveness=aggressiveness,
        llm_model=llm_model,
        prompt_version=prompt_version,
        universe=universe,
        risk_policy=risk_policy,
        paper_costs=paper_costs,
        source_id=source_id,
        source_digest=source_digest,
        window_start=window_start,
        window_end=window_end,
        analytics_version=analytics_version,
    )
    digest = canonical_experiment_digest(manifest_digest_payload(provisional))
    return provisional.model_copy(update={"experiment_digest": digest})


def build_model_experiment_manifest(
    *,
    aggressiveness: int,
    llm_model: LLMModel,
    prompt_version: str,
    universe: tuple[str, ...],
    risk_policy: RiskPolicy,
    paper_costs: PaperExecutionCostModel,
    source_id: str,
    source_digest: str,
    replicate_index: int = 1,
    replicate_count: int = 1,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    analytics_version: str = ANALYTICS_VERSION,
) -> ExperimentManifest:
    """Build one durable run in a strictly controlled historical Luna/Sol v2 group."""

    provisional = _provisional_manifest(
        protocol_version=MODEL_EXPERIMENT_PROTOCOL_VERSION,
        aggressiveness=aggressiveness,
        llm_model=llm_model,
        prompt_version=prompt_version,
        universe=universe,
        risk_policy=risk_policy,
        paper_costs=paper_costs,
        source_id=source_id,
        source_digest=source_digest,
        window_start=window_start,
        window_end=window_end,
        analytics_version=analytics_version,
        comparison_variable=ExperimentVariable.LLM_MODEL,
        experiment_group_digest="0" * 64,
        replicate_index=replicate_index,
        replicate_count=replicate_count,
    )
    return _finalize_model_manifest(provisional)


def build_multi_market_model_experiment_manifest(
    *,
    aggressiveness: int,
    llm_model: LLMModel,
    prompt_version: str,
    executable_markets: tuple[ExecutableMarket, ...],
    risk_policy: RiskPolicy,
    paper_costs: PaperExecutionCostModel,
    source_id: str,
    source_digest: str,
    tool_registry: ReadOnlyToolRegistry | None,
    max_tool_calls: int,
    replicate_index: int = 1,
    replicate_count: int = 1,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    analytics_version: str = MULTI_MARKET_ANALYTICS_VERSION,
    market_selection_protocol_version: str = MARKET_SELECTION_PROTOCOL_VERSION,
) -> ExperimentManifest:
    """Build the v3 identity for the existing causal two-phase multi-market Agent path."""

    agent_protocol = multi_market_agent_protocol_snapshot(
        executable_markets=executable_markets,
        tool_registry=tool_registry,
        max_tool_calls=max_tool_calls,
        market_selection_protocol_version=market_selection_protocol_version,
    )
    universe = tuple(sorted({market.symbol for market in agent_protocol.executable_markets}))
    provisional = _provisional_manifest(
        protocol_version=MULTI_MARKET_MODEL_EXPERIMENT_PROTOCOL_VERSION,
        aggressiveness=aggressiveness,
        llm_model=llm_model,
        prompt_version=prompt_version,
        universe=universe,
        risk_policy=risk_policy,
        paper_costs=paper_costs,
        source_id=source_id,
        source_digest=source_digest,
        window_start=window_start,
        window_end=window_end,
        analytics_version=analytics_version,
        comparison_variable=ExperimentVariable.LLM_MODEL,
        experiment_group_digest="0" * 64,
        replicate_index=replicate_index,
        replicate_count=replicate_count,
        agent_protocol=agent_protocol,
    )
    return _finalize_model_manifest(provisional)


def multi_market_agent_protocol_snapshot(
    *,
    executable_markets: tuple[ExecutableMarket, ...],
    tool_registry: ReadOnlyToolRegistry | None,
    max_tool_calls: int,
    market_selection_protocol_version: str = MARKET_SELECTION_PROTOCOL_VERSION,
) -> ExperimentAgentProtocolSnapshot:
    """Snapshot the effective v3 Agent selection/tool environment without changing behavior."""

    if (
        isinstance(max_tool_calls, bool)
        or not isinstance(max_tool_calls, int)
        or max_tool_calls < 0
    ):
        raise ValueError("max_tool_calls must be a non-negative integer")
    ordered_markets = tuple(
        sorted(
            executable_markets,
            key=lambda market: (market.market_type.value, market.symbol),
        )
    )
    if not ordered_markets:
        raise ValueError("multi-market experiments require at least one executable market")
    if len(set(ordered_markets)) != len(ordered_markets):
        raise ValueError("multi-market experiment executable_markets must be unique")

    tools_enabled = tool_registry is not None and max_tool_calls > 0
    if tool_registry is None and max_tool_calls > 0:
        raise ValueError("max_tool_calls requires a read-only tool registry")

    definitions_digest: str | None = None
    timeout_seconds: Decimal | None = None
    max_result_bytes: int | None = None
    list_markets_max_limit: int | None = None
    if tools_enabled:
        assert tool_registry is not None
        list_markets_max_limit = tool_registry.integer_parameter_maximum("list_markets", "limit")
        if list_markets_max_limit is None:
            raise ValueError("v3 market research tools require a bounded list_markets limit")
        definitions_digest = tool_registry.openai_tools_digest
        timeout_seconds = Decimal(str(tool_registry.timeout_seconds)).normalize()
        max_result_bytes = tool_registry.max_result_bytes

    return ExperimentAgentProtocolSnapshot(
        executable_markets=ordered_markets,
        market_selection_protocol_version=market_selection_protocol_version,
        selection_phase=ExperimentAgentPhaseSnapshot(
            tools_enabled=tools_enabled,
            max_tool_calls=max_tool_calls if tools_enabled else 0,
        ),
        final_decision_phase=ExperimentAgentPhaseSnapshot(
            tools_enabled=False,
            max_tool_calls=0,
        ),
        tool_definitions_digest=definitions_digest,
        tool_timeout_seconds=timeout_seconds,
        tool_max_result_bytes=max_result_bytes,
        list_markets_max_limit=list_markets_max_limit,
    )


def _finalize_model_manifest(provisional: ExperimentManifest) -> ExperimentManifest:
    group_digest = model_comparison_group_digest(provisional)
    grouped = provisional.model_copy(update={"experiment_group_digest": group_digest})
    digest = canonical_experiment_digest(manifest_digest_payload(grouped))
    result = grouped.model_copy(update={"experiment_digest": digest})
    validate_experiment_manifest_digest(result)
    return result


def _provisional_manifest(
    *,
    protocol_version: str,
    aggressiveness: int,
    llm_model: LLMModel,
    prompt_version: str,
    universe: tuple[str, ...],
    risk_policy: RiskPolicy,
    paper_costs: PaperExecutionCostModel,
    source_id: str,
    source_digest: str | None,
    window_start: datetime | None,
    window_end: datetime | None,
    analytics_version: str,
    comparison_variable: ExperimentVariable | None = None,
    experiment_group_digest: str | None = None,
    replicate_index: int | None = None,
    replicate_count: int | None = None,
    agent_protocol: ExperimentAgentProtocolSnapshot | None = None,
) -> ExperimentManifest:
    normalized_universe = tuple(sorted(universe))
    for symbol in normalized_universe:
        parse_canonical_symbol(symbol)
    return ExperimentManifest(
        protocol_version=protocol_version,
        experiment_digest="0" * 64,
        aggressiveness=aggressiveness_context(aggressiveness),
        llm_model=llm_model,
        prompt_version=prompt_version,
        universe=normalized_universe,
        risk_policy=risk_policy_snapshot(risk_policy),
        paper_costs=paper_cost_snapshot(paper_costs),
        analytics_version=analytics_version,
        source_id=source_id,
        source_digest=source_digest,
        window_start=window_start,
        window_end=window_end,
        comparison_variable=comparison_variable,
        experiment_group_digest=experiment_group_digest,
        replicate_index=replicate_index,
        replicate_count=replicate_count,
        agent_protocol=agent_protocol,
    )


__all__ = [
    "AGGRESSIVENESS_MAPPING_VERSION",
    "EXPERIMENT_PROTOCOL_VERSION",
    "MARKET_SELECTION_PROTOCOL_VERSION",
    "MODEL_EXPERIMENT_PROTOCOL_VERSION",
    "MULTI_MARKET_MODEL_EXPERIMENT_PROTOCOL_VERSION",
    "aggressiveness_context",
    "build_experiment_manifest",
    "build_model_experiment_manifest",
    "build_multi_market_model_experiment_manifest",
    "comparison_identity",
    "model_comparison_identity",
    "multi_market_agent_protocol_snapshot",
    "paper_cost_snapshot",
    "risk_policy_snapshot",
    "validate_experiment_manifest_digest",
]
