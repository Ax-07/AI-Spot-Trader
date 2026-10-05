from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from ai_spot_trader.market import attention_analytics_observability as observability_module
from ai_spot_trader.market.attention_analytics_observability import (
    build_analytics_ranking_observability,
)

NOW = datetime(2026, 10, 5, 10, 0, tzinfo=UTC)
SERIES = (
    ("OPEN_INTEREST", "open-interest"),
    ("FUNDING", "funding"),
    ("LIQUIDATION_VOLUME", "liquidation-volume"),
    ("ORDER_FLOW", "cvd"),
    ("ORDER_FLOW", "aggressor-differential"),
)


def _ranking(
    score: int,
    *,
    component_contributions: dict[str, int] | None = None,
    statuses: dict[str, str] | None = None,
    applied: bool = True,
    rank_change: int | None = 0,
    deduplicated: bool = False,
    conflict: bool = False,
    duplicate_open_interest_component: bool = False,
):
    component_contributions = component_contributions or {}
    statuses = statuses or {}
    components: list[SimpleNamespace] = []
    for component_name in ("OPEN_INTEREST", "FUNDING", "LIQUIDATION_VOLUME", "ORDER_FLOW"):
        diagnostics = tuple(
            SimpleNamespace(series=series, status=statuses.get(series, "AVAILABLE"), used=False)
            for family, series in SERIES
            if family == component_name
        )
        components.append(
            SimpleNamespace(
                name=component_name,
                contribution=component_contributions.get(component_name, 0),
                series=diagnostics,
            )
        )
    if duplicate_open_interest_component:
        components.append(
            SimpleNamespace(
                name="OPEN_INTEREST",
                contribution=1,
                series=(SimpleNamespace(series="open-interest", status="AVAILABLE", used=True),),
            )
        )
    return SimpleNamespace(
        score=score,
        components=tuple(components),
        applied_to_ranking=applied,
        rank_change=rank_change,
        order_flow_deduplicated=deduplicated,
        order_flow_conflict=conflict,
    )


def _candidate(
    symbol: str,
    *,
    score: int | None = 0,
    market_type: str = "PERPETUAL",
    interest_level: str = "HIGH",
    **ranking_kwargs,
):
    return SimpleNamespace(
        market=SimpleNamespace(symbol=symbol, market_type=market_type),
        interest_level=interest_level,
        analytics_ranking=(
            None if score is None else _ranking(score, **ranking_kwargs)
        ),
    )


def _overview(
    *candidates,
    scope: str = "PERPETUAL",
    observed_at: datetime = NOW,
    analytics_capable: bool = True,
):
    values = {
        "market_scope": scope,
        "observed_at": observed_at,
        "shortlist": tuple(candidates),
    }
    if analytics_capable:
        values["perpetual_analytics_coverage"] = SimpleNamespace(status="COVERED")
    return SimpleNamespace(**values)


def _score_dict(report):
    return report.score_distribution.model_dump()


def test_score_distribution_covers_zero_through_four_and_output_is_deterministic() -> None:
    history = (
        _overview(
            *(_candidate(f"SCORE{score}/USD", score=score) for score in range(5)),
        ),
    )
    first = build_analytics_ranking_observability(history)
    second = build_analytics_ranking_observability(history)
    assert _score_dict(first) == {
        "score_0": 1,
        "score_1": 1,
        "score_2": 1,
        "score_3": 1,
        "score_4": 1,
    }
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_components_and_series_are_counted_once_per_candidate() -> None:
    report = build_analytics_ranking_observability(
        (
            _overview(
                _candidate(
                    "BTC/USD",
                    score=1,
                    component_contributions={"OPEN_INTEREST": 1},
                    duplicate_open_interest_component=True,
                )
            ),
        )
    )
    assert report.component_contributions.OPEN_INTEREST == 1
    open_interest = next(item for item in report.series_health if item.series == "open-interest")
    assert open_interest.observations == 1
    assert open_interest.statuses.AVAILABLE == 1


def test_order_flow_deduplication_and_conflict_are_observed_not_double_weighted() -> None:
    report = build_analytics_ranking_observability(
        (
            _overview(
                _candidate(
                    "BTC/USD",
                    score=1,
                    component_contributions={"ORDER_FLOW": 1},
                    deduplicated=True,
                ),
                _candidate("ETH/USD", score=0, conflict=True),
            ),
        )
    )
    assert report.component_contributions.ORDER_FLOW == 1
    assert report.order_flow_deduplications == 1
    assert report.order_flow_conflicts == 1
    assert report.order_flow_deduplication_ratio == 0.5
    assert report.order_flow_conflict_ratio == 0.5


def test_degraded_and_missing_series_statuses_are_counted_explicitly() -> None:
    statuses = {
        "open-interest": "PARTIAL",
        "funding": "INSUFFICIENT_HISTORY",
        "liquidation-volume": "STALE",
        "cvd": "TECHNICAL_ERROR",
        "aggressor-differential": "UNAVAILABLE",
    }
    report = build_analytics_ranking_observability(
        (_overview(_candidate("BTC/USD", score=0, statuses=statuses)),)
    )
    assert report.series_status_totals.PARTIAL == 1
    assert report.series_status_totals.INSUFFICIENT_HISTORY == 1
    assert report.series_status_totals.STALE == 1
    assert report.series_status_totals.TECHNICAL_ERROR == 1
    assert report.series_status_totals.UNAVAILABLE == 1
    open_interest = next(item for item in report.series_health if item.series == "open-interest")
    funding = next(item for item in report.series_health if item.series == "funding")
    liquidations = next(
        item for item in report.series_health if item.series == "liquidation-volume"
    )
    cvd = next(item for item in report.series_health if item.series == "cvd")
    assert open_interest.partial_ratio == 1.0
    assert funding.insufficient_history_ratio == 1.0
    assert liquidations.stale_ratio == 1.0
    assert cvd.technical_error_ratio == 1.0
    assert report.perpetual_candidates_without_usable_analytics == 1
    assert report.perpetual_candidates_without_usable_analytics_ratio == 1.0


def test_rank_change_zero_is_distinct_from_ranking_not_applicable_or_missing() -> None:
    applicable_unchanged = _overview(
        _candidate("BTC/USD", score=2, applied=True, rank_change=0),
        _candidate("ETH/USD", score=1, applied=True, rank_change=0),
        observed_at=NOW,
    )
    not_applicable = _overview(
        _candidate("SOL/USD", score=3, applied=False, rank_change=0),
        observed_at=NOW + timedelta(minutes=5),
    )
    missing_rank = _overview(
        _candidate("XRP/USD", score=1, applied=True, rank_change=None),
        observed_at=NOW + timedelta(minutes=10),
    )
    report = build_analytics_ranking_observability(
        (applicable_unchanged, not_applicable, missing_rank)
    )
    assert report.reranking_applicable_snapshots == 2
    assert report.effective_reranking_snapshots == 0
    assert report.analytics_applicable_but_no_rank_change_snapshots == 2
    assert report.candidates_unchanged == 2
    assert report.rank_change_missing_candidates == 1
    assert report.rank_change_observation_count == 2
    assert [(item.rank_change, item.count) for item in report.rank_change_distribution] == [(0, 2)]
    assert report.mean_absolute_rank_change == 0.0
    assert report.max_absolute_rank_change == 0


def test_effective_reranking_amplitude_and_direction_counts() -> None:
    report = build_analytics_ranking_observability(
        (
            _overview(
                _candidate("BTC/USD", score=4, rank_change=2),
                _candidate("ETH/USD", score=1, rank_change=-2),
                _candidate("SOL/USD", score=1, rank_change=0),
            ),
        )
    )
    assert report.reranking_applicable_snapshots == 1
    assert report.effective_reranking_snapshots == 1
    assert report.reranking_effective_ratio == 1.0
    assert report.candidates_moved_up == 1
    assert report.candidates_moved_down == 1
    assert report.candidates_unchanged == 1
    assert [(item.rank_change, item.count) for item in report.rank_change_distribution] == [
        (-2, 1),
        (0, 1),
        (2, 1),
    ]
    assert report.mean_absolute_rank_change == 4 / 3
    assert report.max_absolute_rank_change == 2


def test_scope_breakdown_keeps_spot_perpetual_and_all_descriptive_only() -> None:
    report = build_analytics_ranking_observability(
        (
            _overview(_candidate("BTC/USD", score=2), scope="PERPETUAL"),
            _overview(
                _candidate("ETH/USD", score=3),
                _candidate("ETH/USD", market_type="SPOT", score=None),
                scope="ALL",
                observed_at=NOW + timedelta(minutes=5),
            ),
            _overview(
                _candidate("BTC/USD", market_type="SPOT", score=None),
                scope="SPOT",
                observed_at=NOW + timedelta(minutes=10),
            ),
        )
    )
    by_scope = {item.scope: item for item in report.scope_breakdown}
    assert by_scope["SPOT"].snapshots_observed == 1
    assert by_scope["SPOT"].perpetual_candidates_observed == 0
    assert by_scope["PERPETUAL"].perpetual_candidates_observed == 1
    assert by_scope["ALL"].perpetual_candidates_observed == 1
    assert by_scope["PERPETUAL"].mean_score == 2.0
    assert by_scope["ALL"].mean_score == 3.0


def test_market_coverage_is_sorted_and_tracks_availability_over_time() -> None:
    history = (
        _overview(
            _candidate("ETH/USD", score=1),
            _candidate("BTC/USD", score=2),
        ),
        _overview(
            _candidate(
                "BTC/USD",
                score=0,
                statuses={series: "STALE" for _, series in SERIES},
            ),
            observed_at=NOW + timedelta(minutes=5),
        ),
    )
    report = build_analytics_ranking_observability(history)
    assert [item.symbol for item in report.market_coverage] == ["BTC/USD", "ETH/USD"]
    btc = report.market_coverage[0]
    assert btc.candidate_observations == 2
    assert btc.observations_with_any_available_series == 1
    assert btc.analytics_available_ratio == 0.5
    assert btc.mean_score == 1.0
    assert report.window_started_at == NOW
    assert report.window_ended_at == NOW + timedelta(minutes=5)


def test_legacy_payload_is_ignored_and_missing_ranking_is_not_invented() -> None:
    report = build_analytics_ranking_observability(
        (
            _overview(_candidate("OLD/USD"), analytics_capable=False),
            _overview(_candidate("BTC/USD", score=None)),
        )
    )
    assert report.source_snapshot_count == 2
    assert report.snapshots_observed == 1
    assert report.legacy_snapshots_ignored == 1
    assert report.perpetual_candidates_observed == 1
    assert report.ranking_candidates_observed == 0
    assert report.perpetual_candidates_missing_ranking == 1
    assert report.perpetual_candidates_without_usable_analytics == 1


def test_aggregation_is_self_bounded_to_requested_history_limit() -> None:
    history = tuple(
        _overview(
            _candidate(f"M{index:03}/USD", score=index % 5),
            observed_at=NOW + timedelta(minutes=index),
        )
        for index in range(200)
    )
    report = build_analytics_ranking_observability(history, requested_limit=96)
    assert report.source_snapshot_count == 96
    assert report.snapshots_observed == 96
    assert report.perpetual_candidates_observed == 96
    assert report.window_started_at == NOW + timedelta(minutes=104)
    assert report.window_ended_at == NOW + timedelta(minutes=199)


def test_observability_does_not_mutate_candidate_population_or_interest_level() -> None:
    first = _candidate("BTC/USD", score=4, interest_level="VERY_HIGH", rank_change=1)
    second = _candidate("ETH/USD", score=0, interest_level="LOW", rank_change=-1)
    overview = _overview(first, second)
    original_shortlist = overview.shortlist
    original_levels = tuple(item.interest_level for item in overview.shortlist)
    build_analytics_ranking_observability((overview,))
    assert overview.shortlist is original_shortlist
    assert tuple(item.interest_level for item in overview.shortlist) == original_levels


def test_observability_has_no_agent_risk_broker_or_pnl_dependency() -> None:
    source = inspect.getsource(observability_module)
    assert "ai_spot_trader.agent" not in source
    assert "ai_spot_trader.risk" not in source
    assert "ai_spot_trader.broker" not in source
    assert "pnl" not in source.lower()
