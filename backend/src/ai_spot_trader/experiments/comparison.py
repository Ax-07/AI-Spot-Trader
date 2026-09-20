from dataclasses import dataclass
from decimal import Decimal

from ai_spot_trader.analytics.paper import PaperAnalyticsReport, PaperDailyPerformance
from ai_spot_trader.domain.experiments import (
    comparison_identity,
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
        identity = comparison_identity(manifest)
        if protocol_identity is None:
            protocol_identity = identity
        elif protocol_identity != identity:
            raise ExperimentComparisonError(
                "runs differ on controlled fields other than aggressiveness"
            )

        if report.calculation_version != manifest.analytics_version:
            raise ExperimentComparisonError(
                "analytics calculation version does not match the experiment manifest"
            )
        if analytics_version is None:
            analytics_version = report.calculation_version
        elif analytics_version != report.calculation_version:
            raise ExperimentComparisonError("runs use different analytics calculation versions")

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
