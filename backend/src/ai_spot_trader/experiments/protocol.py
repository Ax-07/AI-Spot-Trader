from datetime import datetime
from decimal import Decimal

from ai_spot_trader.analytics.paper import ANALYTICS_VERSION
from ai_spot_trader.broker.pricing import PaperExecutionCostModel
from ai_spot_trader.domain.enums import ExperimentVariable, LLMModel
from ai_spot_trader.domain.experiments import (
    AGGRESSIVENESS_MAPPING_VERSION,
    EXPERIMENT_PROTOCOL_VERSION,
    MODEL_EXPERIMENT_PROTOCOL_VERSION,
    aggressiveness_context,
    canonical_experiment_digest,
    comparison_identity,
    manifest_digest_payload,
    model_comparison_group_digest,
    model_comparison_identity,
    validate_experiment_manifest_digest,
)
from ai_spot_trader.domain.models import (
    ExperimentManifest,
    ExperimentPaperCostSnapshot,
    ExperimentRiskPolicySnapshot,
)
from ai_spot_trader.domain.symbols import parse_canonical_symbol
from ai_spot_trader.risk.policy import RiskPolicy


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
    """Build one durable run in a strictly controlled Luna/Sol comparison group."""

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
    )


__all__ = [
    "AGGRESSIVENESS_MAPPING_VERSION",
    "EXPERIMENT_PROTOCOL_VERSION",
    "MODEL_EXPERIMENT_PROTOCOL_VERSION",
    "aggressiveness_context",
    "build_experiment_manifest",
    "build_model_experiment_manifest",
    "comparison_identity",
    "model_comparison_identity",
    "paper_cost_snapshot",
    "risk_policy_snapshot",
    "validate_experiment_manifest_digest",
]
