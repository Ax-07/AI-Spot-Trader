import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

import ai_spot_trader.trading.discovery_runner as discovery_runner_module
from ai_spot_trader.domain.enums import DerivativeContractKind, MarketType
from ai_spot_trader.domain.experiments import aggressiveness_context
from ai_spot_trader.domain.models import AssetBalance, ExecutableMarket, PortfolioState
from ai_spot_trader.market.attention import RadarStatus
from ai_spot_trader.market.discovery import (
    MarketDiscoveryCoordinator,
    MarketDiscoveryPolicy,
    RadarEmptyShortlistError,
    RadarNoExecutableCandidateError,
    RadarStaleError,
    RadarUnavailableError,
)
from ai_spot_trader.market.research import MarketResearchMarket, MarketResearchPage
from ai_spot_trader.risk.capacity import CapacityAssessment
from ai_spot_trader.trading.discovery_runner import DynamicMarketTradingCycleRunner
from ai_spot_trader.trading.engine import (
    TradingCycleFailure,
    TradingCycleResult,
    TradingCycleStage,
    TradingCycleStatus,
    TradingCycleTimeouts,
)

NOW = datetime(2026, 10, 5, 10, 0, tzinfo=UTC)
BTC_SPOT = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT)
BTC_PERP = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.PERPETUAL)
ETH_SPOT = ExecutableMarket(symbol="ETH/USD", market_type=MarketType.SPOT)
SOL_SPOT = ExecutableMarket(symbol="SOL/USD", market_type=MarketType.SPOT)


class FixedClock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


class FakeResearch:
    def __init__(self, markets: tuple[MarketResearchMarket, ...]) -> None:
        self.markets = markets
        self.max_list_limit = 100
        self.snapshot_calls = 0

    async def list_markets(self, *, market_type, cursor: int, limit: int):
        values = tuple(item for item in self.markets if item.market_type is market_type)
        page = values[cursor : cursor + limit]
        next_cursor = cursor + len(page) if cursor + len(page) < len(values) else None
        return MarketResearchPage(
            as_of=NOW,
            cursor=cursor,
            limit=limit,
            total_available=len(values),
            next_cursor=next_cursor,
            markets=page,
        )

    async def get_market_snapshot(self, *, symbol: str, market_type: MarketType):
        self.snapshot_calls += 1
        raise AssertionError("Radar mode must not build legacy MarketDiscovery candidates")


class FakeRadar:
    def __init__(
        self,
        markets: tuple[ExecutableMarket, ...],
        *,
        status: RadarStatus = RadarStatus.AVAILABLE,
        observed_at: datetime = NOW,
    ) -> None:
        # Deliberately attach future Batch 49.3-like data to prove that Batch 49.2
        # consumes only item.market identities.
        self.latest = SimpleNamespace(
            observed_at=observed_at,
            status=status,
            shortlist=tuple(
                SimpleNamespace(
                    market=market,
                    analytics_ranking={"score": 4},
                    perpetual_analytics={"open_interest": "secret-from-49.3"},
                    cvd="must-not-cross-boundary",
                    aggressor_differential="must-not-cross-boundary",
                )
                for market in markets
            ),
        )


def spot_market(symbol: str, *, quote: str = "USD", status: str = "online"):
    base, _ = symbol.split("/")
    return MarketResearchMarket(
        symbol=symbol,
        market_type=MarketType.SPOT,
        venue_symbol=symbol.replace("/", ""),
        status=status,
        underlying_asset=base,
        quote_asset=quote,
    )


def perp_market(symbol: str, *, status: str = "tradeable"):
    base, quote = symbol.split("/")
    return MarketResearchMarket(
        symbol=symbol,
        market_type=MarketType.PERPETUAL,
        venue_symbol=f"PF_{base}{quote}",
        status=status,
        contract_kind=DerivativeContractKind.LINEAR,
        underlying_asset=base,
        quote_asset=quote,
    )


def policy(*market_types: MarketType) -> MarketDiscoveryPolicy:
    return MarketDiscoveryPolicy(
        market_types=tuple(sorted(market_types, key=lambda item: item.value)),
        catalog_refresh_seconds=60,
        watchlist_refresh_seconds=60,
        candidate_probe_limit=10,
        candidate_limit=10,
        watchlist_limit=6,
        min_window_observations=0,
    )


def portfolio() -> PortfolioState:
    return PortfolioState(
        portfolio_state_id=uuid4(),
        as_of=NOW,
        settlement_asset="USD",
        balances=(AssetBalance(asset="USD", available=Decimal("1000")),),
        cash_available=Decimal("1000"),
        spot_remaining_cost_basis_total=Decimal(0),
        spot_market_value_total=Decimal(0),
        spot_realized_pnl_total=Decimal(0),
        spot_unrealized_pnl_total=Decimal(0),
        equity=Decimal("1000"),
        exposure_value=Decimal(0),
        exposure_fraction=Decimal(0),
        valuation_complete=True,
    )


def coordinator(
    *,
    radar: FakeRadar,
    research: FakeResearch,
    market_types: tuple[MarketType, ...],
    bootstrap: ExecutableMarket,
    risk_allowed_pairs: frozenset[str] | None = None,
) -> MarketDiscoveryCoordinator:
    return MarketDiscoveryCoordinator(
        research=research,  # type: ignore[arg-type]
        radar=radar,
        policy=policy(*market_types),
        settlement_asset="USD",
        bootstrap_markets=(bootstrap,),
        aggressiveness=5,
        aggressiveness_context=aggressiveness_context(5),
        risk_allowed_pairs=risk_allowed_pairs,
        clock=FixedClock(),
    )


def refresh(service: MarketDiscoveryCoordinator):
    return asyncio.run(service.refresh_if_due(portfolio_state=portfolio()))


def test_radar_spot_shortlist_becomes_agent_universe_and_excludes_catalogue_outsider() -> None:
    research = FakeResearch((spot_market("ETH/USD"), spot_market("SOL/USD")))
    result = refresh(
        coordinator(
            radar=FakeRadar((ETH_SPOT,)),
            research=research,
            market_types=(MarketType.SPOT,),
            bootstrap=BTC_SPOT,
        )
    )

    assert result.watchlist == (ETH_SPOT,)
    assert SOL_SPOT not in result.watchlist
    assert result.audit.source == "RADAR_SHORTLIST"
    assert research.snapshot_calls == 0


def test_radar_perpetual_shortlist_preserves_market_type() -> None:
    research = FakeResearch((spot_market("BTC/USD"), perp_market("BTC/USD")))
    result = refresh(
        coordinator(
            radar=FakeRadar((BTC_PERP,)),
            research=research,
            market_types=(MarketType.PERPETUAL,),
            bootstrap=BTC_PERP,
        )
    )

    assert result.watchlist == (BTC_PERP,)
    assert result.watchlist[0].market_type is MarketType.PERPETUAL


def test_radar_all_scope_keeps_same_symbol_spot_and_perpetual_distinct() -> None:
    research = FakeResearch((spot_market("BTC/USD"), perp_market("BTC/USD")))
    result = refresh(
        coordinator(
            radar=FakeRadar((BTC_SPOT, BTC_PERP)),
            research=research,
            market_types=(MarketType.SPOT, MarketType.PERPETUAL),
            bootstrap=BTC_SPOT,
        )
    )

    assert set(result.watchlist) == {BTC_SPOT, BTC_PERP}
    assert len(result.watchlist) == 2


def test_radar_identity_boundary_does_not_persist_batch49_3_analytics() -> None:
    research = FakeResearch((perp_market("BTC/USD"),))
    result = refresh(
        coordinator(
            radar=FakeRadar((BTC_PERP,)),
            research=research,
            market_types=(MarketType.PERPETUAL,),
            bootstrap=BTC_PERP,
        )
    )

    payload = result.audit.model_dump(mode="json")
    serialized = repr(payload).lower()
    assert "analytics_ranking" not in serialized
    assert "perpetual_analytics" not in serialized
    assert "open_interest" not in serialized
    assert "liquidation" not in serialized
    assert "cvd" not in serialized
    assert "aggressor" not in serialized
    assert payload["radar_shortlist"] == [
        {"symbol": "BTC/USD", "market_type": "PERPETUAL"}
    ]


def test_non_executable_quote_catalogue_and_risk_candidates_are_rejected() -> None:
    research = FakeResearch(
        (
            spot_market("ETH/USD"),
            spot_market("SOL/EUR", quote="EUR"),
        )
    )
    sol_eur = ExecutableMarket(symbol="SOL/EUR", market_type=MarketType.SPOT)
    unknown = ExecutableMarket(symbol="DOGE/USD", market_type=MarketType.SPOT)
    result = refresh(
        coordinator(
            radar=FakeRadar((sol_eur, unknown, ETH_SPOT)),
            research=research,
            market_types=(MarketType.SPOT,),
            bootstrap=BTC_SPOT,
            risk_allowed_pairs=frozenset({"ETH/USD"}),
        )
    )

    assert result.watchlist == (ETH_SPOT,)
    assert sol_eur in result.audit.radar_rejected_markets
    assert unknown in result.audit.radar_rejected_markets


@pytest.mark.parametrize(
    ("radar", "expected_error"),
    [
        (FakeRadar(()), RadarEmptyShortlistError.__name__),
        (FakeRadar((ETH_SPOT,), status=RadarStatus.ERROR), RadarUnavailableError.__name__),
        (FakeRadar((ETH_SPOT,), status=RadarStatus.STALE), RadarStaleError.__name__),
        (
            FakeRadar((ETH_SPOT,), observed_at=NOW - timedelta(seconds=901)),
            RadarStaleError.__name__,
        ),
    ],
)
def test_empty_unavailable_or_stale_radar_fails_closed(radar, expected_error: str) -> None:
    result = refresh(
        coordinator(
            radar=radar,
            research=FakeResearch((spot_market("ETH/USD"),)),
            market_types=(MarketType.SPOT,),
            bootstrap=BTC_SPOT,
        )
    )

    assert result.watchlist == ()
    assert result.audit.status == "FALLBACK"
    assert result.audit.error_type == expected_error


def test_perpetual_not_enabled_by_campaign_is_not_promoted_from_radar() -> None:
    result = refresh(
        coordinator(
            radar=FakeRadar((BTC_PERP,)),
            research=FakeResearch((perp_market("BTC/USD"), spot_market("ETH/USD"))),
            market_types=(MarketType.SPOT,),
            bootstrap=BTC_SPOT,
        )
    )

    assert result.watchlist == ()
    assert result.audit.error_type == RadarNoExecutableCandidateError.__name__


def test_dated_future_remains_non_executable() -> None:
    with pytest.raises(ValueError, match="FUTURE"):
        ExecutableMarket(symbol="BTC/USD", market_type=MarketType.FUTURE)


class _Ledger:
    def snapshot(self, *, as_of=None):
        return portfolio()


class _NormalCapacity:
    def evaluate(self, *, portfolio_state, executable_markets):
        return CapacityAssessment(
            mode="NORMAL",
            reason="test",
            spot_opening_capacity="POSSIBLE",
            perpetual_opening_capacity="POSSIBLE",
        )


class _RadarDiscoveryFailure:
    source = "RADAR_SHORTLIST"
    watchlist = ()

    async def refresh_if_due(self, *, portfolio_state):
        from ai_spot_trader.market.discovery import MarketDiscoveryAudit, MarketDiscoveryResult

        return MarketDiscoveryResult(
            watchlist=(),
            audit=MarketDiscoveryAudit(
                source="RADAR_SHORTLIST",
                status="FALLBACK",
                observed_at=NOW,
                radar_status=RadarStatus.ERROR,
                error_type=RadarUnavailableError.__name__,
            ),
        )

    def cache_result(self, *, status):
        raise AssertionError("normal capacity should refresh the Radar universe")


class _NeverCalledRisk:
    calls = 0

    def evaluate(self, **kwargs):
        self.calls += 1
        raise AssertionError("Risk must not be called when Radar universe failed closed")


class _NeverCalledBroker:
    calls = 0

    async def execute(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("Broker must not be called when Radar universe failed closed")


def test_radar_failure_without_positions_stops_before_agent_risk_and_broker(monkeypatch) -> None:
    class NeverCanonicalRunner:
        def __init__(self, **kwargs):
            raise AssertionError("canonical Agent runner must not start without a Radar universe")

    monkeypatch.setattr(discovery_runner_module, "TradingCycleRunner", NeverCanonicalRunner)
    risk = _NeverCalledRisk()
    broker = _NeverCalledBroker()
    runner = DynamicMarketTradingCycleRunner(
        portfolio=_Ledger(),
        agent=object(),  # canonical runner must not be reached
        risk_engine=risk,  # type: ignore[arg-type]
        broker=broker,  # type: ignore[arg-type]
        aggressiveness=5,
        timeouts=TradingCycleTimeouts(1, 1, 1),
        executable_market_data=object(),  # type: ignore[arg-type]
        bootstrap_markets=(BTC_SPOT,),
        capacity_evaluator=_NormalCapacity(),  # type: ignore[arg-type]
        discovery=_RadarDiscoveryFailure(),  # type: ignore[arg-type]
        settlement_asset="USD",
    )

    result = asyncio.run(runner.run_cycle())

    assert result.status is TradingCycleStatus.FAILED
    assert result.failure is not None
    assert result.failure.stage is TradingCycleStage.SELECTION_INPUT
    assert result.failure.error_type == RadarUnavailableError.__name__
    assert risk.calls == 0
    assert broker.calls == 0


class _CapturingCanonicalRunner:
    last_kwargs = None

    def __init__(self, **kwargs):
        type(self).last_kwargs = kwargs

    async def run_cycle(self):
        return TradingCycleResult(
            cycle_id=uuid4(),
            status=TradingCycleStatus.FAILED,
            failure=TradingCycleFailure(
                stage=TradingCycleStage.MARKET,
                error_type="TestStop",
            ),
        )


def test_dynamic_runner_passes_only_radar_shortlist_identities_to_canonical_agent(monkeypatch) -> None:
    monkeypatch.setattr(
        discovery_runner_module,
        "TradingCycleRunner",
        _CapturingCanonicalRunner,
    )
    discovery = coordinator(
        radar=FakeRadar((BTC_PERP, ETH_SPOT)),
        research=FakeResearch((perp_market("BTC/USD"), spot_market("ETH/USD"), spot_market("SOL/USD"))),
        market_types=(MarketType.SPOT, MarketType.PERPETUAL),
        bootstrap=BTC_SPOT,
    )
    runner = DynamicMarketTradingCycleRunner(
        portfolio=_Ledger(),
        agent=object(),  # replaced canonical runner captures the Agent universe seam
        risk_engine=object(),  # type: ignore[arg-type]
        broker=object(),  # type: ignore[arg-type]
        aggressiveness=5,
        timeouts=TradingCycleTimeouts(1, 1, 1),
        executable_market_data=object(),  # type: ignore[arg-type]
        bootstrap_markets=(BTC_SPOT,),
        capacity_evaluator=_NormalCapacity(),  # type: ignore[arg-type]
        discovery=discovery,
        settlement_asset="USD",
    )

    asyncio.run(runner.run_cycle())

    effective = _CapturingCanonicalRunner.last_kwargs["executable_markets"]
    assert set(effective) == {BTC_PERP, ETH_SPOT}
    assert SOL_SPOT not in effective
    assert all(set(market.model_dump()) == {"symbol", "market_type"} for market in effective)
