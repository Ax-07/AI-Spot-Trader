from dataclasses import dataclass
from decimal import Decimal

from ai_spot_trader.analytics.paper import (
    PaperAnalyticsPoint,
    PaperAnalyticsReport,
    PaperDailyPerformance,
)
from ai_spot_trader.domain.enums import LLMModel
from ai_spot_trader.domain.experiments import (
    EXPERIMENT_PROTOCOL_VERSION,
    MODEL_EXPERIMENT_PROTOCOL_VERSION,
    comparison_identity,
    model_comparison_identity,
    validate_experiment_manifest_digest,
)
from ai_spot_trader.domain.models import ExperimentManifest


class ExperimentComparisonError(ValueError):
    """Raised when experiment runs are not comparable under one controlled protocol."""


@dataclass(frozen=True, slots=True)
class ExperimentRun:
    manifest: ExperimentManifest
    analytics: PaperAnalyticsReport


@dataclass(frozen=True, slots=True)
class AggressivenessComparisonRow:
    aggressiveness: int
    experiment_digest: str
    analytics_source_digest: str
    gross_pnl: Decimal
    net_pnl: Decimal
    fees: Decimal
    spread_cost: Decimal
    slippage_cost: Decimal
    max_drawdown_value: Decimal
    max_drawdown_fraction: Decimal | None
    current_exposure_value: Decimal
    current_exposure_fraction: Decimal | None
    trade_count: int
    hold_count: int
    reject_count: int
    modify_count: int
    completed_cycle_count: int
    failed_cycle_count: int
    daily: tuple[PaperDailyPerformance, ...]


@dataclass(frozen=True, slots=True)
class AggressivenessComparison:
    protocol_identity: str
    analytics_version: str
    rows: tuple[AggressivenessComparisonRow, ...]


@dataclass(frozen=True, slots=True)
class ModelComparisonRow:
    llm_model: LLMModel
    replicate_index: int
    experiment_digest: str
    experiment_group_digest: str
    analytics_source_digest: str
    gross_pnl: Decimal
    net_pnl: Decimal
    fees: Decimal
    spread_cost: Decimal
    slippage_cost: Decimal
    max_drawdown_value: Decimal
    max_drawdown_fraction: Decimal | None
    current_exposure_value: Decimal
    current_exposure_fraction: Decimal | None
    trade_count: int
    buy_trade_count: int
    sell_trade_count: int
    hold_count: int
    reject_count: int
    modify_count: int
    completed_cycle_count: int
    failed_cycle_count: int
    points: tuple[PaperAnalyticsPoint, ...]
    daily: tuple[PaperDailyPerformance, ...]


@dataclass(frozen=True, slots=True)
class ModelComparison:
    protocol_identity: str
    analytics_version: str
    replicate_count: int
    rows: tuple[ModelComparisonRow, ...]


def compare_aggressiveness_runs(
    runs: tuple[ExperimentRun, ...],
) -> AggressivenessComparison:
    """Compare existing Batch 12 reports without recalculating or ranking them."""

    if len(runs) < 2:
        raise ExperimentComparisonError("at least two experiment runs are required")

    protocol_identity: str | None = None
    analytics_version: str | None = None
    seen_levels: set[int] = set()
    rows: list[AggressivenessComparisonRow] = []

    for run in runs:
        manifest = run.manifest
        report = run.analytics
        validate_experiment_manifest_digest(manifest)
        if manifest.protocol_version != EXPERIMENT_PROTOCOL_VERSION:
            raise ExperimentComparisonError(
                "aggressiveness comparison requires paper-experiment-v1 manifests"
            )
        identity = comparison_identity(manifest)
        if protocol_identity is None:
            protocol_identity = identity
        elif protocol_identity != identity:
            raise ExperimentComparisonError(
                "runs differ on controlled fields other than aggressiveness"
            )

        analytics_version = _validated_analytics_version(
            manifest=manifest,
            report=report,
            expected=analytics_version,
        )

        level = manifest.aggressiveness.level
        if level in seen_levels:
            raise ExperimentComparisonError("duplicate aggressiveness level in comparison")
        seen_levels.add(level)
        summary = report.summary
        rows.append(
            AggressivenessComparisonRow(
                aggressiveness=level,
                experiment_digest=manifest.experiment_digest,
                analytics_source_digest=report.source_digest,
                gross_pnl=summary.gross_pnl,
                net_pnl=summary.net_pnl,
                fees=summary.fees,
                spread_cost=summary.spread_cost,
                slippage_cost=summary.slippage_cost,
                max_drawdown_value=summary.max_drawdown_value,
                max_drawdown_fraction=summary.max_drawdown_fraction,
                current_exposure_value=summary.current_exposure_value,
                current_exposure_fraction=summary.current_exposure_fraction,
                trade_count=summary.trade_count,
                hold_count=summary.hold_count,
                reject_count=summary.reject_count,
                modify_count=summary.modify_count,
                completed_cycle_count=summary.completed_cycle_count,
                failed_cycle_count=summary.failed_cycle_count,
                daily=report.daily,
            )
        )

    assert protocol_identity is not None
    assert analytics_version is not None
    return AggressivenessComparison(
        protocol_identity=protocol_identity,
        analytics_version=analytics_version,
        rows=tuple(sorted(rows, key=lambda item: item.aggressiveness)),
    )


def compare_model_runs(runs: tuple[ExperimentRun, ...]) -> ModelComparison:
    """Compare complete paired Luna/Sol repetitions using canonical Batch 12 metrics only."""

    if len(runs) < 2:
        raise ExperimentComparisonError("at least two experiment runs are required")

    protocol_identity: str | None = None
    analytics_version: str | None = None
    replicate_count: int | None = None
    seen_runs: set[tuple[LLMModel, int]] = set()
    indices_by_model: dict[LLMModel, set[int]] = {
        LLMModel.LUNA: set(),
        LLMModel.SOL: set(),
    }
    rows: list[ModelComparisonRow] = []

    for run in runs:
        manifest = run.manifest
        report = run.analytics
        validate_experiment_manifest_digest(manifest)
        if manifest.protocol_version != MODEL_EXPERIMENT_PROTOCOL_VERSION:
            raise ExperimentComparisonError(
                "model comparison requires paper-experiment-v2 manifests"
            )
        identity = model_comparison_identity(manifest)
        if protocol_identity is None:
            protocol_identity = identity
        elif protocol_identity != identity:
            raise ExperimentComparisonError(
                "runs differ on controlled fields other than llm_model and replicate_index"
            )

        analytics_version = _validated_analytics_version(
            manifest=manifest,
            report=report,
            expected=analytics_version,
        )

        assert manifest.replicate_index is not None
        assert manifest.replicate_count is not None
        assert manifest.experiment_group_digest is not None
        if replicate_count is None:
            replicate_count = manifest.replicate_count
        elif replicate_count != manifest.replicate_count:
            raise ExperimentComparisonError("runs use different declared replicate counts")

        key = (manifest.llm_model, manifest.replicate_index)
        if key in seen_runs:
            raise ExperimentComparisonError("duplicate model replicate in comparison")
        seen_runs.add(key)
        indices_by_model[manifest.llm_model].add(manifest.replicate_index)

        summary = report.summary
        rows.append(
            ModelComparisonRow(
                llm_model=manifest.llm_model,
                replicate_index=manifest.replicate_index,
                experiment_digest=manifest.experiment_digest,
                experiment_group_digest=manifest.experiment_group_digest,
                analytics_source_digest=report.source_digest,
                gross_pnl=summary.gross_pnl,
                net_pnl=summary.net_pnl,
                fees=summary.fees,
                spread_cost=summary.spread_cost,
                slippage_cost=summary.slippage_cost,
                max_drawdown_value=summary.max_drawdown_value,
                max_drawdown_fraction=summary.max_drawdown_fraction,
                current_exposure_value=summary.current_exposure_value,
                current_exposure_fraction=summary.current_exposure_fraction,
                trade_count=summary.trade_count,
                buy_trade_count=summary.buy_trade_count,
                sell_trade_count=summary.sell_trade_count,
                hold_count=summary.hold_count,
                reject_count=summary.reject_count,
                modify_count=summary.modify_count,
                completed_cycle_count=summary.completed_cycle_count,
                failed_cycle_count=summary.failed_cycle_count,
                points=report.points,
                daily=report.daily,
            )
        )

    assert protocol_identity is not None
    assert analytics_version is not None
    assert replicate_count is not None
    expected_indices = set(range(1, replicate_count + 1))
    for model in (LLMModel.LUNA, LLMModel.SOL):
        if indices_by_model[model] != expected_indices:
            raise ExperimentComparisonError(
                "model comparison requires every declared replicate for both Luna and Sol"
            )

    return ModelComparison(
        protocol_identity=protocol_identity,
        analytics_version=analytics_version,
        replicate_count=replicate_count,
        rows=tuple(sorted(rows, key=lambda item: (item.replicate_index, item.llm_model.value))),
    )


def _validated_analytics_version(
    *,
    manifest: ExperimentManifest,
    report: PaperAnalyticsReport,
    expected: str | None,
) -> str:
    if report.calculation_version != manifest.analytics_version:
        raise ExperimentComparisonError(
            "analytics calculation version does not match the experiment manifest"
        )
    if expected is not None and expected != report.calculation_version:
        raise ExperimentComparisonError("runs use different analytics calculation versions")
    return report.calculation_version
