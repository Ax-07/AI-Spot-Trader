import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from ai_spot_trader.agent.provider import OpenAIDecisionProvider
from ai_spot_trader.agent.watchlist import OpenAIWatchlistSelector
from ai_spot_trader.domain.enums import (
    DerivativeContractKind,
    LLMModel,
    MarketType,
)
from ai_spot_trader.domain.experiments import aggressiveness_context
from ai_spot_trader.domain.models import (
    AssetBalance,
    DerivativeInstrument,
    DerivativeMarketContext,
    ExecutableMarket,
    PortfolioState,
)
from ai_spot_trader.market.discovery import (
    MarketCandidate,
    MarketDiscoveryCoordinator,
    MarketDiscoveryInput,
    MarketDiscoveryPolicy,
    WatchlistEntry,
    WatchlistSelection,
)
from ai_spot_trader.market.research import (
    MarketResearchMarket,
    MarketResearchPage,
    MarketResearchSnapshot,
)

NOW = datetime(2026, 9, 25, 10, 0, tzinfo=UTC)
BTC = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT)
ETH = ExecutableMarket(symbol="ETH/USD", market_type=MarketType.SPOT)
SOL = ExecutableMarket(symbol="SOL/USD", market_type=MarketType.SPOT)
BTC_PERP = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.PERPETUAL)


class MutableClock:
    def __init__(self) -> None:
        self.value = NOW

    def now(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


class FakeResearch:
    max_list_limit = 100

    def __init__(
        self,
        markets: tuple[MarketResearchMarket, ...],
        snapshots: dict[tuple[str, MarketType], MarketResearchSnapshot],
    ) -> None:
        self.markets = markets
        self.snapshots = snapshots
        self.list_calls = 0
        self.snapshot_calls: list[tuple[str, MarketType]] = []
        self.list_error: Exception | None = None

    async def list_markets(self, *, market_type, cursor: int, limit: int):
        self.list_calls += 1
        if self.list_error is not None:
            raise self.list_error
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
        self.snapshot_calls.append((symbol, market_type))
        value = self.snapshots[(symbol, market_type)]
        if isinstance(value, Exception):
            raise value
        return value


class SequenceAgent:
    def __init__(self, selections: list[tuple[ExecutableMarket, ...] | Exception]) -> None:
        self.selections = selections
        self.calls: list[MarketDiscoveryInput] = []

    async def select_watchlist(self, value: MarketDiscoveryInput) -> WatchlistSelection:
        self.calls.append(value)
        selected = self.selections.pop(0)
        if isinstance(selected, Exception):
            raise selected
        return WatchlistSelection(
            discovery_id=value.discovery_id,
            selected_at=value.created_at,
            entries=tuple(WatchlistEntry(market=market, rationale="test") for market in selected),
            rationale="watchlist test",
        )


class FixedStructuredClient:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.calls = 0

    async def generate_structured_decision(self, **kwargs) -> str:
        self.calls += 1
        return json.dumps(self.payload)


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


def spot_market(symbol: str, *, status: str = "online", quote: str = "USD") -> MarketResearchMarket:
    return MarketResearchMarket(
        symbol=symbol,
        market_type=MarketType.SPOT,
        venue_symbol=symbol,
        status=status,
        underlying_asset=symbol.split("/")[0],
        quote_asset=quote,
    )


def spot_snapshot(symbol: str, *, as_of: datetime = NOW) -> MarketResearchSnapshot:
    return MarketResearchSnapshot(
        symbol=symbol,
        market_type=MarketType.SPOT,
        as_of=as_of,
        last_price=Decimal("100"),
    )


def perp_market(symbol: str) -> MarketResearchMarket:
    base, quote = symbol.split("/")
    return MarketResearchMarket(
        symbol=symbol,
        market_type=MarketType.PERPETUAL,
        venue_symbol=f"PF_{base}{quote}",
        status="tradeable",
        contract_kind=DerivativeContractKind.LINEAR,
        underlying_asset=base,
        quote_asset=quote,
    )


def perp_snapshot(symbol: str) -> MarketResearchSnapshot:
    base, quote = symbol.split("/")
    instrument = DerivativeInstrument(
        symbol=symbol,
        venue_symbol=f"PF_{base}{quote}",
        market_type=MarketType.PERPETUAL,
        contract_kind=DerivativeContractKind.LINEAR,
        underlying_asset=base,
        quote_asset=quote,
        contract_size=Decimal("1"),
        tick_size=Decimal("0.1"),
        min_order_quantity=Decimal("0.001"),
        initial_margin_rate=Decimal("0.1"),
        maintenance_margin_rate=Decimal("0.05"),
        max_leverage=Decimal("10"),
        funding_interval_seconds=Decimal("3600"),
    )
    return MarketResearchSnapshot(
        symbol=symbol,
        market_type=MarketType.PERPETUAL,
        as_of=NOW,
        last_price=Decimal("100"),
        derivative=DerivativeMarketContext(
            observed_at=NOW,
            instrument=instrument,
            mark_price=Decimal("100"),
        ),
    )


def policy(*types: MarketType, refresh: int = 60) -> MarketDiscoveryPolicy:
    return MarketDiscoveryPolicy(
        market_types=tuple(sorted(types, key=lambda item: item.value)),
        catalog_refresh_seconds=refresh,
        watchlist_refresh_seconds=refresh,
        candidate_probe_limit=10,
        candidate_limit=10,
        watchlist_limit=4,
        max_snapshot_age_seconds=120,
        min_window_observations=0,
    )


def coordinator(
    *,
    research: FakeResearch,
    agent: SequenceAgent,
    clock: MutableClock,
    discovery_policy: MarketDiscoveryPolicy | None = None,
    risk_allowed_pairs: frozenset[str] | None = None,
) -> MarketDiscoveryCoordinator:
    return MarketDiscoveryCoordinator(
        research=research,  # type: ignore[arg-type]
        agent=agent,
        policy=discovery_policy or policy(MarketType.SPOT),
        settlement_asset="USD",
        bootstrap_markets=(BTC,),
        aggressiveness=5,
        aggressiveness_context=aggressiveness_context(5),
        risk_allowed_pairs=risk_allowed_pairs,
        clock=clock,
    )


def test_catalogue_filters_incompatible_status_and_quote_without_ranking_trade_quality() -> None:
    markets = (
        spot_market("BTC/USD"),
        spot_market("ETH/USD", status="cancel_only"),
        spot_market("SOL/EUR", quote="EUR"),
    )
    research = FakeResearch(markets, {("BTC/USD", MarketType.SPOT): spot_snapshot("BTC/USD")})
    agent = SequenceAgent([(BTC,)])
    clock = MutableClock()

    result = asyncio.run(
        coordinator(research=research, agent=agent, clock=clock).refresh_if_due(
            portfolio_state=portfolio()
        )
    )

    assert result.watchlist == (BTC,)
    assert result.audit.status == "REFRESHED"
    assert result.audit.catalogue_market_count == 3
    assert result.audit.compatible_market_count == 1
    assert agent.calls[0].candidates[0].market == BTC


def test_no_lookahead_future_snapshot_is_never_exposed_to_agent() -> None:
    research = FakeResearch(
        (spot_market("ETH/USD"),),
        {("ETH/USD", MarketType.SPOT): spot_snapshot("ETH/USD", as_of=NOW + timedelta(seconds=1))},
    )
    agent = SequenceAgent([(ETH,)])
    result = asyncio.run(
        coordinator(research=research, agent=agent, clock=MutableClock()).refresh_if_due(
            portfolio_state=portfolio()
        )
    )

    assert result.audit.status == "FALLBACK"
    assert result.watchlist == (BTC,)
    assert agent.calls == []


def test_agent_can_select_multiple_markets_and_audit_additions() -> None:
    markets = (spot_market("BTC/USD"), spot_market("ETH/USD"), spot_market("SOL/USD"))
    snapshots = {
        (item.symbol, MarketType.SPOT): spot_snapshot(item.symbol) for item in markets
    }
    agent = SequenceAgent([(BTC, ETH, SOL)])
    result = asyncio.run(
        coordinator(
            research=FakeResearch(markets, snapshots),
            agent=agent,
            clock=MutableClock(),
        ).refresh_if_due(portfolio_state=portfolio())
    )

    assert result.watchlist == (BTC, ETH, SOL)
    assert result.audit.added_markets == (BTC, ETH, SOL)
    assert tuple(candidate.market for candidate in result.audit.candidates) == (BTC, ETH, SOL)
    assert result.audit.input_created_at == NOW
    assert result.audit.selection_selected_at == NOW
    assert len(result.audit.selection_entries) == 3


def test_watchlist_audits_add_maintain_and_remove() -> None:
    markets = (spot_market("BTC/USD"), spot_market("ETH/USD"), spot_market("SOL/USD"))
    snapshots = {
        (item.symbol, MarketType.SPOT): spot_snapshot(item.symbol) for item in markets
    }
    agent = SequenceAgent([(BTC, ETH), (ETH, SOL)])
    clock = MutableClock()
    service = coordinator(research=FakeResearch(markets, snapshots), agent=agent, clock=clock)

    first = asyncio.run(service.refresh_if_due(portfolio_state=portfolio()))
    clock.advance(61)
    second = asyncio.run(service.refresh_if_due(portfolio_state=portfolio()))

    assert first.watchlist == (BTC, ETH)
    assert second.watchlist == (ETH, SOL)
    assert second.audit.added_markets == (SOL,)
    assert second.audit.maintained_markets == (ETH,)
    assert second.audit.removed_markets == (BTC,)


def test_agent_market_outside_candidate_universe_falls_back_to_previous_watchlist() -> None:
    research = FakeResearch(
        (spot_market("BTC/USD"),),
        {("BTC/USD", MarketType.SPOT): spot_snapshot("BTC/USD")},
    )
    agent = SequenceAgent([(BTC,), (ETH,)])
    clock = MutableClock()
    service = coordinator(research=research, agent=agent, clock=clock)
    asyncio.run(service.refresh_if_due(portfolio_state=portfolio()))
    clock.advance(61)

    result = asyncio.run(service.refresh_if_due(portfolio_state=portfolio()))

    assert result.audit.status == "FALLBACK"
    assert result.watchlist == (BTC,)
    assert result.audit.error_type == "ValueError"


def test_llm_unavailability_retains_previous_watchlist() -> None:
    research = FakeResearch(
        (spot_market("BTC/USD"),),
        {("BTC/USD", MarketType.SPOT): spot_snapshot("BTC/USD")},
    )
    agent = SequenceAgent([(BTC,), RuntimeError("llm unavailable")])
    clock = MutableClock()
    service = coordinator(research=research, agent=agent, clock=clock)
    asyncio.run(service.refresh_if_due(portfolio_state=portfolio()))
    clock.advance(61)

    result = asyncio.run(service.refresh_if_due(portfolio_state=portfolio()))

    assert result.watchlist == (BTC,)
    assert result.audit.status == "FALLBACK"
    assert result.audit.error_type == "RuntimeError"


def test_kraken_unavailability_uses_bootstrap_and_is_throttled() -> None:
    research = FakeResearch((), {})
    research.list_error = RuntimeError("kraken unavailable")
    agent = SequenceAgent([])
    clock = MutableClock()
    service = coordinator(research=research, agent=agent, clock=clock)

    first = asyncio.run(service.refresh_if_due(portfolio_state=portfolio()))
    second = asyncio.run(service.refresh_if_due(portfolio_state=portfolio()))

    assert first.watchlist == (BTC,)
    assert first.audit.status == "FALLBACK"
    assert second.audit.status == "CACHE_REUSED"
    assert research.list_calls == 1


def test_optional_risk_whitelist_restricts_dynamic_candidates() -> None:
    markets = (spot_market("BTC/USD"), spot_market("ETH/USD"))
    snapshots = {
        ("BTC/USD", MarketType.SPOT): spot_snapshot("BTC/USD"),
        ("ETH/USD", MarketType.SPOT): spot_snapshot("ETH/USD"),
    }
    agent = SequenceAgent([(ETH,)])
    result = asyncio.run(
        coordinator(
            research=FakeResearch(markets, snapshots),
            agent=agent,
            clock=MutableClock(),
            risk_allowed_pairs=frozenset({"ETH/USD"}),
        ).refresh_if_due(portfolio_state=portfolio())
    )
    assert result.watchlist == (ETH,)
    assert tuple(candidate.market for candidate in agent.calls[0].candidates) == (ETH,)


def test_linear_perpetual_can_enter_candidate_universe() -> None:
    research = FakeResearch(
        (perp_market("BTC/USD"),),
        {("BTC/USD", MarketType.PERPETUAL): perp_snapshot("BTC/USD")},
    )
    agent = SequenceAgent([(BTC_PERP,)])
    service = MarketDiscoveryCoordinator(
        research=research,  # type: ignore[arg-type]
        agent=agent,
        policy=policy(MarketType.PERPETUAL),
        settlement_asset="USD",
        bootstrap_markets=(BTC_PERP,),
        aggressiveness=5,
        aggressiveness_context=aggressiveness_context(5),
        clock=MutableClock(),
    )
    result = asyncio.run(service.refresh_if_due(portfolio_state=portfolio()))
    assert result.watchlist == (BTC_PERP,)


def test_openai_watchlist_selector_rejects_market_outside_candidates() -> None:
    client = FixedStructuredClient(
        {
            "markets": [
                {"symbol": "ETH/USD", "market_type": "SPOT", "rationale": "hors univers"}
            ],
            "rationale": "test",
        }
    )
    provider = OpenAIDecisionProvider(
        client=client,
        model=LLMModel.LUNA,
        clock=MutableClock(),
    )
    selector = OpenAIWatchlistSelector(provider)
    value = MarketDiscoveryInput(
        discovery_id=uuid4(),
        created_at=NOW,
        portfolio_state=portfolio(),
        candidates=(
            MarketCandidate(
                market=BTC,
                status="online",
                venue_symbol="BTC/USD",
                snapshot=spot_snapshot("BTC/USD"),
            ),
        ),
        watchlist_limit=4,
        aggressiveness=5,
        aggressiveness_context=aggressiveness_context(5),
        market_discovery_context={"protocol_version": "market-discovery-v1"},
    )
    with pytest.raises(Exception, match="outside the candidate universe"):
        asyncio.run(selector.select_watchlist(value))


def test_openai_watchlist_selector_supports_multi_market_output() -> None:
    client = FixedStructuredClient(
        {
            "markets": [
                {"symbol": "ETH/USD", "market_type": "SPOT", "rationale": "eth"},
                {"symbol": "BTC/USD", "market_type": "SPOT", "rationale": "btc"},
            ],
            "rationale": "deux marches",
        }
    )
    provider = OpenAIDecisionProvider(client=client, model=LLMModel.LUNA, clock=MutableClock())
    selector = OpenAIWatchlistSelector(provider)
    value = MarketDiscoveryInput(
        discovery_id=uuid4(),
        created_at=NOW,
        portfolio_state=portfolio(),
        candidates=(
            MarketCandidate(
                market=BTC,
                status="online",
                venue_symbol="BTC/USD",
                snapshot=spot_snapshot("BTC/USD"),
            ),
            MarketCandidate(
                market=ETH,
                status="online",
                venue_symbol="ETH/USD",
                snapshot=spot_snapshot("ETH/USD"),
            ),
        ),
        watchlist_limit=4,
        aggressiveness=5,
        aggressiveness_context=aggressiveness_context(5),
        market_discovery_context={"protocol_version": "market-discovery-v1"},
    )
    result = asyncio.run(selector.select_watchlist(value))
    assert result.markets == (BTC, ETH)


def test_catalogue_duplicate_execution_addresses_are_collapsed_deterministically() -> None:
    markets = (
        MarketResearchMarket(
            symbol="BTC/USD",
            market_type=MarketType.SPOT,
            venue_symbol="A-BTCUSD",
            status="online",
            underlying_asset="BTC",
            quote_asset="USD",
        ),
        MarketResearchMarket(
            symbol="BTC/USD",
            market_type=MarketType.SPOT,
            venue_symbol="B-BTCUSD",
            status="online",
            underlying_asset="BTC",
            quote_asset="USD",
        ),
    )
    research = FakeResearch(
        markets,
        {("BTC/USD", MarketType.SPOT): spot_snapshot("BTC/USD")},
    )
    agent = SequenceAgent([(BTC,)])

    result = asyncio.run(
        coordinator(
            research=research,
            agent=agent,
            clock=MutableClock(),
        ).refresh_if_due(portfolio_state=portfolio())
    )

    assert result.audit.compatible_market_count == 1
    assert tuple(candidate.market for candidate in agent.calls[0].candidates) == (BTC,)
