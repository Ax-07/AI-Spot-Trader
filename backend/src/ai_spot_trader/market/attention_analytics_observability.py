from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


_COMPONENT_NAMES = (
    "OPEN_INTEREST",
    "FUNDING",
    "LIQUIDATION_VOLUME",
    "ORDER_FLOW",
)
_SERIES_NAMES = (
    "open-interest",
    "funding",
    "liquidation-volume",
    "cvd",
    "aggressor-differential",
)
_STATUS_NAMES = (
    "AVAILABLE",
    "PARTIAL",
    "INSUFFICIENT_HISTORY",
    "STALE",
    "TECHNICAL_ERROR",
    "NOT_APPLICABLE",
    "UNAVAILABLE",
)
_SCOPE_NAMES = ("SPOT", "PERPETUAL", "ALL")


class _ObservationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AnalyticsScoreDistribution(_ObservationModel):
    score_0: int = Field(default=0, ge=0)
    score_1: int = Field(default=0, ge=0)
    score_2: int = Field(default=0, ge=0)
    score_3: int = Field(default=0, ge=0)
    score_4: int = Field(default=0, ge=0)


class AnalyticsComponentContributions(_ObservationModel):
    OPEN_INTEREST: int = Field(default=0, ge=0)
    FUNDING: int = Field(default=0, ge=0)
    LIQUIDATION_VOLUME: int = Field(default=0, ge=0)
    ORDER_FLOW: int = Field(default=0, ge=0)


class AnalyticsSeriesStatusCounts(_ObservationModel):
    AVAILABLE: int = Field(default=0, ge=0)
    PARTIAL: int = Field(default=0, ge=0)
    INSUFFICIENT_HISTORY: int = Field(default=0, ge=0)
    STALE: int = Field(default=0, ge=0)
    TECHNICAL_ERROR: int = Field(default=0, ge=0)
    NOT_APPLICABLE: int = Field(default=0, ge=0)
    UNAVAILABLE: int = Field(default=0, ge=0)


class AnalyticsSeriesHealth(_ObservationModel):
    series: str
    observations: int = Field(default=0, ge=0)
    statuses: AnalyticsSeriesStatusCounts = Field(default_factory=AnalyticsSeriesStatusCounts)
    available_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    partial_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    insufficient_history_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    stale_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    technical_error_ratio: float | None = Field(default=None, ge=0.0, le=1.0)


class AnalyticsRankChangeBucket(_ObservationModel):
    rank_change: int
    count: int = Field(default=0, ge=0)


class AnalyticsScopeObservability(_ObservationModel):
    scope: str
    snapshots_observed: int = Field(default=0, ge=0)
    perpetual_candidates_observed: int = Field(default=0, ge=0)
    ranking_candidates_observed: int = Field(default=0, ge=0)
    mean_score: float | None = Field(default=None, ge=0.0, le=4.0)
    reranking_applicable_snapshots: int = Field(default=0, ge=0)
    effective_reranking_snapshots: int = Field(default=0, ge=0)


class AnalyticsMarketCoverage(_ObservationModel):
    market_type: str
    symbol: str
    candidate_observations: int = Field(default=0, ge=0)
    ranking_observations: int = Field(default=0, ge=0)
    observations_with_any_available_series: int = Field(default=0, ge=0)
    analytics_available_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    mean_score: float | None = Field(default=None, ge=0.0, le=4.0)
    effective_rank_changes: int = Field(default=0, ge=0)


class AnalyticsRankingObservability(_ObservationModel):
    schema_version: str = "analytics-ranking-observability-v1"
    source: str = "bounded-market-attention-history"
    requested_history_limit: int = Field(default=96, ge=1, le=96)
    source_snapshot_count: int = Field(default=0, ge=0)
    snapshots_observed: int = Field(default=0, ge=0)
    legacy_snapshots_ignored: int = Field(default=0, ge=0)
    window_started_at: datetime | None = None
    window_ended_at: datetime | None = None
    score_distribution: AnalyticsScoreDistribution = Field(
        default_factory=AnalyticsScoreDistribution
    )
    component_contributions: AnalyticsComponentContributions = Field(
        default_factory=AnalyticsComponentContributions
    )
    series_status_totals: AnalyticsSeriesStatusCounts = Field(
        default_factory=AnalyticsSeriesStatusCounts
    )
    series_health: tuple[AnalyticsSeriesHealth, ...] = ()
    perpetual_candidates_observed: int = Field(default=0, ge=0)
    ranking_candidates_observed: int = Field(default=0, ge=0)
    perpetual_candidates_missing_ranking: int = Field(default=0, ge=0)
    perpetual_candidates_without_usable_analytics: int = Field(default=0, ge=0)
    perpetual_candidates_without_usable_analytics_ratio: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    reranking_applicable_snapshots: int = Field(default=0, ge=0)
    effective_reranking_snapshots: int = Field(default=0, ge=0)
    reranking_effective_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    analytics_applicable_but_no_rank_change_snapshots: int = Field(default=0, ge=0)
    candidates_moved_up: int = Field(default=0, ge=0)
    candidates_moved_down: int = Field(default=0, ge=0)
    candidates_unchanged: int = Field(default=0, ge=0)
    rank_change_missing_candidates: int = Field(default=0, ge=0)
    rank_change_observation_count: int = Field(default=0, ge=0)
    rank_change_distribution: tuple[AnalyticsRankChangeBucket, ...] = ()
    mean_absolute_rank_change: float | None = Field(default=None, ge=0.0)
    max_absolute_rank_change: int | None = Field(default=None, ge=0)
    order_flow_deduplications: int = Field(default=0, ge=0)
    order_flow_deduplication_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    order_flow_conflicts: int = Field(default=0, ge=0)
    order_flow_conflict_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    scope_breakdown: tuple[AnalyticsScopeObservability, ...] = ()
    market_coverage: tuple[AnalyticsMarketCoverage, ...] = ()


class _ScopeAccumulator:
    __slots__ = (
        "snapshots",
        "perpetual_candidates",
        "ranking_candidates",
        "score_total",
        "reranking_applicable",
        "effective_reranking",
    )

    def __init__(self) -> None:
        self.snapshots = 0
        self.perpetual_candidates = 0
        self.ranking_candidates = 0
        self.score_total = 0
        self.reranking_applicable = 0
        self.effective_reranking = 0


class _MarketAccumulator:
    __slots__ = (
        "candidate_observations",
        "ranking_observations",
        "any_available",
        "score_total",
        "effective_rank_changes",
    )

    def __init__(self) -> None:
        self.candidate_observations = 0
        self.ranking_observations = 0
        self.any_available = 0
        self.score_total = 0
        self.effective_rank_changes = 0


def _value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw)


def _safe_score(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        score = int(value)
    except (TypeError, ValueError):
        return None
    return score if 0 <= score <= 4 else None


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def build_analytics_ranking_observability(
    history: Iterable[object],
    *,
    requested_limit: int = 96,
) -> AnalyticsRankingObservability:
    """Aggregate only already-observed Radar facts, with no future outcome or P&L input.

    The caller normally supplies ``MarketAttentionReader.history``. The function also slices its
    own input to the requested bound so it cannot accidentally turn an unbounded iterable of
    historical snapshots into an unbounded in-memory aggregation.
    """

    if isinstance(requested_limit, bool) or requested_limit < 1 or requested_limit > 96:
        raise ValueError("requested_limit must be between 1 and 96")

    source = tuple(history)[-requested_limit:]
    score_counts = [0, 0, 0, 0, 0]
    component_counts = {name: 0 for name in _COMPONENT_NAMES}
    status_totals = {name: 0 for name in _STATUS_NAMES}
    series_counts = {
        series: {name: 0 for name in _STATUS_NAMES} for series in _SERIES_NAMES
    }
    scopes = {name: _ScopeAccumulator() for name in _SCOPE_NAMES}
    markets: dict[tuple[str, str], _MarketAccumulator] = {}

    snapshots_observed = 0
    legacy_snapshots_ignored = 0
    observed_times: list[datetime] = []
    perpetual_candidates = 0
    ranking_candidates = 0
    missing_ranking = 0
    without_usable = 0
    reranking_applicable = 0
    effective_reranking = 0
    applicable_without_change = 0
    moved_up = 0
    moved_down = 0
    unchanged = 0
    rank_change_missing = 0
    absolute_rank_changes: list[int] = []
    rank_change_counts: dict[int, int] = {}
    order_flow_deduplications = 0
    order_flow_conflicts = 0

    for overview in source:
        # Batch 47.5+ Analytics overviews expose this field even for SPOT scope. Older payloads
        # are intentionally ignored rather than guessed into the new diagnostic contract.
        if not hasattr(overview, "perpetual_analytics_coverage"):
            legacy_snapshots_ignored += 1
            continue

        snapshots_observed += 1
        observed_at = getattr(overview, "observed_at", None)
        if isinstance(observed_at, datetime):
            observed_times.append(observed_at)

        scope_name = _value(getattr(overview, "market_scope", "UNKNOWN"))
        scope_acc = scopes.get(scope_name)
        if scope_acc is None:
            scope_acc = _ScopeAccumulator()
            scopes[scope_name] = scope_acc
        scope_acc.snapshots += 1

        snapshot_applicable = False
        snapshot_changed = False
        shortlist = tuple(getattr(overview, "shortlist", ()) or ())

        for candidate in shortlist:
            market = getattr(candidate, "market", None)
            market_type = _value(getattr(market, "market_type", "UNKNOWN"))
            if market_type != "PERPETUAL":
                continue
            symbol = str(getattr(market, "symbol", "UNKNOWN"))
            market_key = (market_type, symbol)
            market_acc = markets.setdefault(market_key, _MarketAccumulator())
            market_acc.candidate_observations += 1
            perpetual_candidates += 1
            scope_acc.perpetual_candidates += 1

            ranking = getattr(candidate, "analytics_ranking", None)
            if ranking is None:
                missing_ranking += 1
                without_usable += 1
                continue

            ranking_candidates += 1
            scope_acc.ranking_candidates += 1
            market_acc.ranking_observations += 1

            score = _safe_score(getattr(ranking, "score", None))
            if score is not None:
                score_counts[score] += 1
                scope_acc.score_total += score
                market_acc.score_total += score

            seen_components: set[str] = set()
            seen_series: set[str] = set()
            any_available = False
            for component in tuple(getattr(ranking, "components", ()) or ()):
                component_name = _value(getattr(component, "name", ""))
                if component_name in component_counts and component_name not in seen_components:
                    seen_components.add(component_name)
                    contribution = getattr(component, "contribution", 0)
                    if contribution == 1:
                        component_counts[component_name] += 1

                for diagnostic in tuple(getattr(component, "series", ()) or ()):
                    series_name = str(getattr(diagnostic, "series", ""))
                    if series_name not in series_counts or series_name in seen_series:
                        continue
                    seen_series.add(series_name)
                    status_name = _value(getattr(diagnostic, "status", "UNAVAILABLE"))
                    if status_name not in status_totals:
                        status_name = "UNAVAILABLE"
                    status_totals[status_name] += 1
                    series_counts[series_name][status_name] += 1
                    any_available = any_available or status_name == "AVAILABLE"

            if any_available:
                market_acc.any_available += 1
            else:
                without_usable += 1

            if bool(getattr(ranking, "order_flow_deduplicated", False)):
                order_flow_deduplications += 1
            if bool(getattr(ranking, "order_flow_conflict", False)):
                order_flow_conflicts += 1

            applied = bool(getattr(ranking, "applied_to_ranking", False))
            if not applied:
                continue
            snapshot_applicable = True
            rank_change = getattr(ranking, "rank_change", None)
            if isinstance(rank_change, bool) or not isinstance(rank_change, int):
                rank_change_missing += 1
                continue

            absolute_rank_changes.append(abs(rank_change))
            rank_change_counts[rank_change] = rank_change_counts.get(rank_change, 0) + 1
            if rank_change > 0:
                moved_up += 1
                snapshot_changed = True
                market_acc.effective_rank_changes += 1
            elif rank_change < 0:
                moved_down += 1
                snapshot_changed = True
                market_acc.effective_rank_changes += 1
            else:
                unchanged += 1

        if snapshot_applicable:
            reranking_applicable += 1
            scope_acc.reranking_applicable += 1
            if snapshot_changed:
                effective_reranking += 1
                scope_acc.effective_reranking += 1
            else:
                applicable_without_change += 1

    series_health = tuple(
        AnalyticsSeriesHealth(
            series=series,
            observations=sum(series_counts[series].values()),
            statuses=AnalyticsSeriesStatusCounts(**series_counts[series]),
            available_ratio=_ratio(
                series_counts[series]["AVAILABLE"],
                sum(series_counts[series].values()),
            ),
            partial_ratio=_ratio(
                series_counts[series]["PARTIAL"],
                sum(series_counts[series].values()),
            ),
            insufficient_history_ratio=_ratio(
                series_counts[series]["INSUFFICIENT_HISTORY"],
                sum(series_counts[series].values()),
            ),
            stale_ratio=_ratio(
                series_counts[series]["STALE"],
                sum(series_counts[series].values()),
            ),
            technical_error_ratio=_ratio(
                series_counts[series]["TECHNICAL_ERROR"],
                sum(series_counts[series].values()),
            ),
        )
        for series in _SERIES_NAMES
    )

    ordered_scope_names = [*(_SCOPE_NAMES), *sorted(set(scopes) - set(_SCOPE_NAMES))]
    scope_breakdown = tuple(
        AnalyticsScopeObservability(
            scope=name,
            snapshots_observed=scopes[name].snapshots,
            perpetual_candidates_observed=scopes[name].perpetual_candidates,
            ranking_candidates_observed=scopes[name].ranking_candidates,
            mean_score=(
                scopes[name].score_total / scopes[name].ranking_candidates
                if scopes[name].ranking_candidates
                else None
            ),
            reranking_applicable_snapshots=scopes[name].reranking_applicable,
            effective_reranking_snapshots=scopes[name].effective_reranking,
        )
        for name in ordered_scope_names
    )

    market_coverage = tuple(
        AnalyticsMarketCoverage(
            market_type=market_type,
            symbol=symbol,
            candidate_observations=acc.candidate_observations,
            ranking_observations=acc.ranking_observations,
            observations_with_any_available_series=acc.any_available,
            analytics_available_ratio=_ratio(acc.any_available, acc.candidate_observations),
            mean_score=(
                acc.score_total / acc.ranking_observations
                if acc.ranking_observations
                else None
            ),
            effective_rank_changes=acc.effective_rank_changes,
        )
        for (market_type, symbol), acc in sorted(markets.items())
    )

    return AnalyticsRankingObservability(
        requested_history_limit=requested_limit,
        source_snapshot_count=len(source),
        snapshots_observed=snapshots_observed,
        legacy_snapshots_ignored=legacy_snapshots_ignored,
        window_started_at=min(observed_times) if observed_times else None,
        window_ended_at=max(observed_times) if observed_times else None,
        score_distribution=AnalyticsScoreDistribution(
            score_0=score_counts[0],
            score_1=score_counts[1],
            score_2=score_counts[2],
            score_3=score_counts[3],
            score_4=score_counts[4],
        ),
        component_contributions=AnalyticsComponentContributions(**component_counts),
        series_status_totals=AnalyticsSeriesStatusCounts(**status_totals),
        series_health=series_health,
        perpetual_candidates_observed=perpetual_candidates,
        ranking_candidates_observed=ranking_candidates,
        perpetual_candidates_missing_ranking=missing_ranking,
        perpetual_candidates_without_usable_analytics=without_usable,
        perpetual_candidates_without_usable_analytics_ratio=_ratio(
            without_usable, perpetual_candidates
        ),
        reranking_applicable_snapshots=reranking_applicable,
        effective_reranking_snapshots=effective_reranking,
        reranking_effective_ratio=_ratio(effective_reranking, reranking_applicable),
        analytics_applicable_but_no_rank_change_snapshots=applicable_without_change,
        candidates_moved_up=moved_up,
        candidates_moved_down=moved_down,
        candidates_unchanged=unchanged,
        rank_change_missing_candidates=rank_change_missing,
        rank_change_observation_count=len(absolute_rank_changes),
        rank_change_distribution=tuple(
            AnalyticsRankChangeBucket(rank_change=value, count=count)
            for value, count in sorted(rank_change_counts.items())
        ),
        mean_absolute_rank_change=(
            sum(absolute_rank_changes) / len(absolute_rank_changes)
            if absolute_rank_changes
            else None
        ),
        max_absolute_rank_change=max(absolute_rank_changes) if absolute_rank_changes else None,
        order_flow_deduplications=order_flow_deduplications,
        order_flow_deduplication_ratio=_ratio(order_flow_deduplications, ranking_candidates),
        order_flow_conflicts=order_flow_conflicts,
        order_flow_conflict_ratio=_ratio(order_flow_conflicts, ranking_candidates),
        scope_breakdown=scope_breakdown,
        market_coverage=market_coverage,
    )
