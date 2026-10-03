from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.attention import (
    MarketActivityState,
    MarketAttentionPolicy,
    RadarInterestLevel,
    RadarStatus,
)
from ai_spot_trader.market.attention_filters import MarketAttentionSnapshotV6
from ai_spot_trader.market.attention_scope_trend import (
    MarketActivitySnapshotV4,
    MarketScope,
    TrendDirection,
)
from ai_spot_trader.market.attention_structure_prefilter import (
    MarketAttentionOverviewV6Structure,
    MarketStructureCoverageDiagnostics,
    MarketStructureScanPolicy,
    StructureAwareFilteredMarketAttentionRadar,
    StructureAwareMarketAttentionFilters,
    StructureCoverageStatus,
    StructureTimeframeFilter,
    _advanced_filters_accept,
    _select_final_candidates,
    _structure_attention_key,
)
from ai_spot_trader.market.candles import CandleKey, CandleTimeframe
from ai_spot_trader.market.microstructure import MicrostructurePolicy, missing_microstructure
from ai_spot_trader.market.structure import (
    MarketStructurePolicy,
    MarketStructureState,
    MultiTimeframeStructureState,
    StructureEvent,
    TimeframeMarketStructure,
    summarize_market_structures,
)

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


def _market(symbol: str, market_type: MarketType = MarketType.SPOT) -> ExecutableMarket:
    return ExecutableMarket(symbol=symbol, market_type=market_type)


def _structure(
    *,
    m5: tuple[MarketStructureState, StructureEvent | None] = (
        MarketStructureState.RANGE,
        None,
    ),
    m15: tuple[MarketStructureState, StructureEvent | None] = (
        MarketStructureState.RANGE,
        None,
    ),
    h1: tuple[MarketStructureState, StructureEvent | None] = (
        MarketStructureState.RANGE,
        None,
    ),
    h4: tuple[MarketStructureState, StructureEvent | None] = (
        MarketStructureState.RANGE,
        None,
    ),
):
    frames = tuple(
        TimeframeMarketStructure(timeframe=timeframe, state=state, event=event)
        for timeframe, (state, event) in (
            (CandleTimeframe.M5, m5),
            (CandleTimeframe.M15, m15),
            (CandleTimeframe.H1, h1),
            (CandleTimeframe.H4, h4),
        )
    )
    return summarize_market_structures(observed_at=NOW, timeframes=frames)


def _snapshot(
    symbol: str,
    *,
    trend: TrendDirection = TrendDirection.NEUTRAL,
    structure=None,
    activity_state: MarketActivityState = MarketActivityState.NORMAL,
    market_type: MarketType = MarketType.SPOT,
) -> MarketAttentionSnapshotV6:
    market = _market(symbol, market_type)
    activity = MarketActivitySnapshotV4(
        market=market,
        observed_at=NOW,
        status=RadarStatus.AVAILABLE,
        activity_state=activity_state,
        horizons=(),
        trend_direction=trend,
    )
    return MarketAttentionSnapshotV6(
        market_activity=activity,
        microstructure=missing_microstructure(market=market, observed_at=NOW),
        market_structure=structure or _structure(),
    )


def test_filter_model_defaults_preserve_historical_behavior() -> None:
    filters = StructureAwareMarketAttentionFilters()
    assert filters.market_scope is MarketScope.ALL
    assert filters.trend_directions == ()
    assert filters.structure_global_states == ()
    assert not filters.trend_filter_enabled
    assert not filters.structure_filter_enabled
    assert not filters.attention_filter_enabled
    assert not filters.structure_5m.enabled
    assert not filters.structure_15m.enabled
    assert not filters.structure_1h.enabled
    assert not filters.structure_4h.enabled


def test_filter_model_rejects_unknown_duplicates_and_keeps_or_semantics() -> None:
    with pytest.raises(ValidationError):
        StructureAwareMarketAttentionFilters(trend_directions=["UNKNOWN"])
    with pytest.raises(ValidationError):
        StructureAwareMarketAttentionFilters(trend_directions=["UP", "UP"])
    with pytest.raises(ValidationError):
        StructureAwareMarketAttentionFilters(structure_global_states=["UNKNOWN"])
    with pytest.raises(ValidationError):
        StructureTimeframeFilter(states=["UNKNOWN"])
    with pytest.raises(ValidationError):
        StructureTimeframeFilter(events=["BOS_UP", "BOS_UP"])

    filters = StructureAwareMarketAttentionFilters(trend_directions=["UP", "MIXED"])
    assert _advanced_filters_accept(_snapshot("A/USD", trend=TrendDirection.UP), filters)
    assert _advanced_filters_accept(_snapshot("B/USD", trend=TrendDirection.MIXED), filters)
    assert not _advanced_filters_accept(_snapshot("C/USD", trend=TrendDirection.DOWN), filters)


def test_structure_filters_are_and_between_timeframes_and_state_event_fields() -> None:
    filters = StructureAwareMarketAttentionFilters(
        trend_directions=["DOWN"],
        structure_1h={"states": ["BEARISH"]},
        structure_4h={"states": ["TRANSITION"], "events": ["CHOCH_DOWN"]},
    )
    matching = _snapshot(
        "PENDLE/USD",
        trend=TrendDirection.DOWN,
        structure=_structure(
            h1=(MarketStructureState.BEARISH, StructureEvent.BOS_DOWN),
            h4=(MarketStructureState.TRANSITION, StructureEvent.CHOCH_DOWN),
        ),
    )
    assert _advanced_filters_accept(matching, filters)

    wrong_h1 = matching.model_copy(
        update={
            "market_structure": _structure(
                h1=(MarketStructureState.BULLISH, StructureEvent.BOS_UP),
                h4=(MarketStructureState.TRANSITION, StructureEvent.CHOCH_DOWN),
            )
        }
    )
    assert not _advanced_filters_accept(wrong_h1, filters)

    missing_event = matching.model_copy(
        update={
            "market_structure": _structure(
                h1=(MarketStructureState.BEARISH, StructureEvent.BOS_DOWN),
                h4=(MarketStructureState.TRANSITION, None),
            )
        }
    )
    assert not _advanced_filters_accept(missing_event, filters)


def test_unknown_structure_is_fail_closed_when_structure_filter_is_active() -> None:
    filters = StructureAwareMarketAttentionFilters(
        structure_4h={"states": ["TRANSITION"]}
    )
    unknown = _snapshot(
        "UNKNOWN/USD",
        structure=_structure(
            m5=(MarketStructureState.UNKNOWN, None),
            m15=(MarketStructureState.UNKNOWN, None),
            h1=(MarketStructureState.UNKNOWN, None),
            h4=(MarketStructureState.UNKNOWN, None),
        ),
    )
    assert not _advanced_filters_accept(unknown, filters)




def test_non_available_market_is_fail_closed_even_with_a_matching_cached_structure() -> None:
    matching = _snapshot(
        "STALE/USD",
        structure=_structure(h4=(MarketStructureState.TRANSITION, StructureEvent.CHOCH_DOWN)),
    )
    matching = matching.model_copy(
        update={
            "market_activity": matching.market_activity.model_copy(
                update={"status": RadarStatus.ERROR}
            )
        }
    )
    filters = StructureAwareMarketAttentionFilters(
        structure_4h={"events": ["CHOCH_DOWN"]}
    )
    assert not _advanced_filters_accept(matching, filters)
    assert _select_final_candidates(
        items=(matching,),
        canonical_candidate_markets=frozenset(),
        filters=StructureAwareMarketAttentionFilters(),
        candidate_limit=10,
    ) == ()


def test_additive_v6_contract_serializes_advanced_filters_and_structure_coverage() -> None:
    filters = StructureAwareMarketAttentionFilters(
        market_scope="SPOT",
        trend_directions=["DOWN"],
        structure_4h={"states": ["TRANSITION"], "events": ["CHOCH_DOWN"]},
    )
    coverage = MarketStructureCoverageDiagnostics(
        eligible_market_count=2,
        fresh_market_count=1,
        expired_market_count=0,
        unseen_market_count=1,
        scanned_market_count=1,
        coverage_ratio=0.5,
        effective_market_limit=2,
        estimated_refreshes_per_full_rotation=1,
        estimated_full_rotation_seconds=300.0,
        cache_ttl_seconds=3600.0,
        rotation_within_cache_ttl=True,
        status="ROTATING",
    )
    overview = MarketAttentionOverviewV6Structure(
        observed_at=NOW,
        status=RadarStatus.AVAILABLE,
        market_scope=MarketScope.SPOT,
        filters=filters,
        structure_coverage=coverage,
    )
    payload = overview.model_dump(mode="json")
    assert payload["protocol_version"] == "market-attention-radar-v6"
    assert payload["filters"]["trend_directions"] == ["DOWN"]
    assert payload["filters"]["structure_4h"]["events"] == ["CHOCH_DOWN"]
    assert payload["structure_coverage"]["status"] == "ROTATING"


def test_structural_attention_is_directionally_symmetric_and_prefers_higher_timeframes() -> None:
    down_h4 = _structure(h4=(MarketStructureState.TRANSITION, StructureEvent.CHOCH_DOWN))
    up_h4 = _structure(h4=(MarketStructureState.TRANSITION, StructureEvent.CHOCH_UP))
    down_h1 = _structure(h1=(MarketStructureState.TRANSITION, StructureEvent.CHOCH_DOWN))
    bos_h4 = _structure(h4=(MarketStructureState.BEARISH, StructureEvent.BOS_DOWN))

    assert _structure_attention_key(down_h4) == _structure_attention_key(up_h4)
    assert _structure_attention_key(down_h4) > _structure_attention_key(down_h1)
    assert _structure_attention_key(down_h4) > _structure_attention_key(bos_h4)


def test_normal_activity_with_choch_can_enter_but_persistent_state_alone_does_not() -> None:
    bearish_choch = _snapshot(
        "PENDLE/USD",
        trend=TrendDirection.DOWN,
        structure=_structure(
            h1=(MarketStructureState.BEARISH, StructureEvent.BOS_DOWN),
            h4=(MarketStructureState.TRANSITION, StructureEvent.CHOCH_DOWN),
        ),
    )
    bullish_choch = _snapshot(
        "REVERSAL/USD",
        trend=TrendDirection.UP,
        structure=_structure(
            h1=(MarketStructureState.BULLISH, StructureEvent.BOS_UP),
            h4=(MarketStructureState.TRANSITION, StructureEvent.CHOCH_UP),
        ),
    )
    persistent = _snapshot(
        "PERSISTENT/USD",
        structure=_structure(
            m5=(MarketStructureState.BEARISH, None),
            m15=(MarketStructureState.BEARISH, None),
            h1=(MarketStructureState.BEARISH, None),
            h4=(MarketStructureState.BEARISH, None),
        ),
    )

    selected = _select_final_candidates(
        items=(bearish_choch, bullish_choch, persistent),
        canonical_candidate_markets=frozenset(),
        filters=StructureAwareMarketAttentionFilters(),
        candidate_limit=10,
    )
    assert {item.market.symbol for item in selected} == {"PENDLE/USD", "REVERSAL/USD"}
    assert all(item.market_activity.activity_state is MarketActivityState.NORMAL for item in selected)


def test_explicit_structure_filter_can_search_persistent_states_without_making_them_default_anomalies() -> None:
    persistent = _snapshot(
        "TREND/USD",
        structure=_structure(
            m5=(MarketStructureState.BULLISH, None),
            m15=(MarketStructureState.BULLISH, None),
            h1=(MarketStructureState.BULLISH, None),
            h4=(MarketStructureState.BULLISH, None),
        ),
    )
    filters = StructureAwareMarketAttentionFilters(structure_global_states=["BULLISH"])
    selected = _select_final_candidates(
        items=(persistent,),
        canonical_candidate_markets=frozenset(),
        filters=filters,
        candidate_limit=10,
    )
    assert [item.market.symbol for item in selected] == ["TREND/USD"]


def test_structure_priority_complements_but_does_not_override_canonical_interest_rank() -> None:
    canonical = _snapshot("CANONICAL/USD").model_copy(
        update={"interest_level": RadarInterestLevel.MEDIUM}
    )
    structural = _snapshot(
        "STRUCTURAL/USD",
        structure=_structure(h4=(MarketStructureState.TRANSITION, StructureEvent.CHOCH_DOWN)),
    )
    selected = _select_final_candidates(
        items=(structural, canonical),
        canonical_candidate_markets=frozenset({canonical.market}),
        filters=StructureAwareMarketAttentionFilters(),
        candidate_limit=1,
    )
    assert [item.market.symbol for item in selected] == ["CANONICAL/USD"]


def test_candidate_limit_is_always_respected() -> None:
    items = tuple(
        _snapshot(
            f"S{index}/USD",
            structure=_structure(h4=(MarketStructureState.TRANSITION, StructureEvent.CHOCH_DOWN)),
        )
        for index in range(8)
    )
    selected = _select_final_candidates(
        items=items,
        canonical_candidate_markets=frozenset(),
        filters=StructureAwareMarketAttentionFilters(),
        candidate_limit=3,
    )
    assert len(selected) == 3


class _Catalogue:
    async def list_markets(self):
        return ()

    async def aclose(self) -> None:
        return None


class _Metadata:
    async def metadata_by_symbol(self):
        return {}

    async def aclose(self) -> None:
        return None


class _Microstructure:
    async def fetch_order_book(self, symbol: str, *, limit: int):
        raise RuntimeError("unused")

    async def fetch_recent_trades(self, symbol: str, *, limit: int):
        raise RuntimeError("unused")

    async def aclose(self) -> None:
        return None


class _NativeCandles:
    def __init__(self) -> None:
        self.calls: list[tuple[CandleKey, datetime, int]] = []

    async def history_as_of(self, key: CandleKey, *, as_of: datetime, limit: int = 1000):
        self.calls.append((key, as_of, limit))
        return ()

    async def history(self, key: CandleKey, *, limit: int = 1000):
        return ()


def _radar(*, market_limit: int = 2, ttl: float = 600.0):
    candles = _NativeCandles()
    radar = StructureAwareFilteredMarketAttentionRadar(
        candle_service=candles,  # type: ignore[arg-type]
        catalogue=_Catalogue(),
        microstructure_provider=_Microstructure(),  # type: ignore[arg-type]
        metadata_provider=_Metadata(),
        policy=MarketAttentionPolicy(scan_limit=10, candidate_limit=10, candle_limit=160),
        microstructure_policy=MicrostructurePolicy(),
        structure_policy=MarketStructurePolicy(history_limit=100),
        structure_scan_policy=MarketStructureScanPolicy(
            market_limit_per_refresh=market_limit,
            cache_ttl_seconds=ttl,
        ),
    )
    return radar, candles


def test_structure_rotation_is_deterministic_and_separate_from_ohlcv_rotation() -> None:
    radar, _candles = _radar(market_limit=2)
    markets = (
        _market("C/USD"),
        _market("A/USD"),
        _market("B/USD"),
        _market("BTC/USD", MarketType.PERPETUAL),
        _market("ETH/USD", MarketType.PERPETUAL),
    )
    first = radar._next_structure_batch(markets)
    second = radar._next_structure_batch(markets)
    radar._structure_scan_cursor = 0
    repeated = radar._next_structure_batch(markets)

    assert first == repeated
    assert set(first).isdisjoint(second)
    assert radar._scan_cursors == {MarketType.SPOT: 0, MarketType.PERPETUAL: 0}


def test_structure_cache_reuses_fresh_snapshot_and_refreshes_after_ttl() -> None:
    async def scenario() -> None:
        radar, candles = _radar(market_limit=1, ttl=600.0)
        market = _market("PENDLE/USD")

        assert await radar._scan_structure((market,), observed_at=NOW) == 1
        assert len(candles.calls) == 4
        assert [call[0].timeframe for call in candles.calls] == list(
            (CandleTimeframe.M5, CandleTimeframe.M15, CandleTimeframe.H1, CandleTimeframe.H4)
        )
        assert all(call[1] == NOW for call in candles.calls)

        assert await radar._scan_structure(
            (market,), observed_at=NOW + timedelta(seconds=300)
        ) == 0
        assert len(candles.calls) == 4

        assert await radar._scan_structure(
            (market,), observed_at=NOW + timedelta(seconds=601)
        ) == 1
        assert len(candles.calls) == 8
        await radar.aclose()

    asyncio.run(scenario())



def test_structure_cache_never_reuses_a_snapshot_from_the_future() -> None:
    async def scenario() -> None:
        radar, candles = _radar(market_limit=1, ttl=600.0)
        market = _market("CAUSAL/USD")
        future = NOW + timedelta(seconds=300)

        assert await radar._scan_structure((market,), observed_at=future) == 1
        assert len(candles.calls) == 4
        assert market not in radar._fresh_structures(NOW)

        assert await radar._scan_structure((market,), observed_at=NOW) == 1
        assert len(candles.calls) == 8
        assert radar._structure_cache[market].observed_at == NOW
        await radar.aclose()

    asyncio.run(scenario())

def test_structure_coverage_distinguishes_unseen_expired_and_configuration_too_slow() -> None:
    radar, _candles = _radar(market_limit=2, ttl=600.0)
    markets = tuple(_market(f"S{index}/USD") for index in range(5))
    diagnostics = radar._structure_coverage(markets, NOW, scanned_count=0)
    assert diagnostics.unseen_market_count == 5
    assert diagnostics.fresh_market_count == 0
    assert diagnostics.status is StructureCoverageStatus.CONFIGURATION_TOO_SLOW

    empty = radar._structure_coverage((), NOW, scanned_count=0)
    assert empty.status is StructureCoverageStatus.NO_MARKETS
    assert empty.coverage_ratio is None


def test_structure_coverage_model_requires_a_complete_partition() -> None:
    with pytest.raises(ValidationError):
        MarketStructureCoverageDiagnostics(
            eligible_market_count=3,
            fresh_market_count=1,
            expired_market_count=0,
            unseen_market_count=1,
        )
