from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.experiments import aggressiveness_context
from ai_spot_trader.domain.models import AssetBalance, ExecutableMarket, PortfolioState
from ai_spot_trader.market.discovery import (
    MarketCandidate,
    MarketDiscoveryAudit,
    WatchlistEntry,
)
from ai_spot_trader.market.research import MarketResearchSnapshot
from ai_spot_trader.persistence.repository import _selection_input_payload
from ai_spot_trader.trading.discovery_runner import DiscoveredMarketSelectionInput
from ai_spot_trader.trading.engine import (
    TradingCycleFailure,
    TradingCycleResult,
    TradingCycleStage,
    TradingCycleStatus,
)

NOW = datetime(2026, 9, 25, 13, 0, tzinfo=UTC)
BTC = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT)
ETH = ExecutableMarket(symbol="ETH/USD", market_type=MarketType.SPOT)


def test_discovery_audit_is_serialized_with_canonical_selection_input() -> None:
    cycle_id = uuid4()
    portfolio = PortfolioState(
        portfolio_state_id=uuid4(),
        as_of=NOW,
        settlement_asset="USD",
        balances=(AssetBalance(asset="USD", available=Decimal("1000")),),
        cash_available=Decimal("1000"),
        valuation_complete=False,
    )
    selection_input = DiscoveredMarketSelectionInput(
        cycle_id=cycle_id,
        created_at=NOW,
        portfolio_state=portfolio,
        executable_markets=(BTC, ETH),
        aggressiveness=5,
        aggressiveness_context=aggressiveness_context(5),
        market_discovery=MarketDiscoveryAudit(
            discovery_id=uuid4(),
            status="REFRESHED",
            observed_at=NOW,
            candidate_market_count=2,
            input_created_at=NOW,
            candidates=(
                MarketCandidate(
                    market=BTC,
                    status="online",
                    venue_symbol="BTC/USD",
                    snapshot=MarketResearchSnapshot(
                        symbol="BTC/USD",
                        market_type=MarketType.SPOT,
                        as_of=NOW,
                        last_price=Decimal("100"),
                    ),
                ),
                MarketCandidate(
                    market=ETH,
                    status="online",
                    venue_symbol="ETH/USD",
                    snapshot=MarketResearchSnapshot(
                        symbol="ETH/USD",
                        market_type=MarketType.SPOT,
                        as_of=NOW,
                        last_price=Decimal("200"),
                    ),
                ),
            ),
            selection_selected_at=NOW,
            previous_watchlist=(BTC,),
            effective_watchlist=(BTC, ETH),
            added_markets=(ETH,),
            maintained_markets=(BTC,),
            selection_rationale="surveillance test",
            selection_entries=(
                WatchlistEntry(market=BTC, rationale="maintien"),
                WatchlistEntry(market=ETH, rationale="ajout"),
            ),
        ),
    )
    result = TradingCycleResult(
        cycle_id=cycle_id,
        status=TradingCycleStatus.FAILED,
        failure=TradingCycleFailure(
            stage=TradingCycleStage.MARKET_SELECTION,
            error_type="TestStop",
        ),
        market_selection_input=selection_input,
    )

    payload = _selection_input_payload(result)

    assert payload is not None
    discovery = payload["market_discovery"]
    assert discovery["status"] == "REFRESHED"
    assert discovery["added_markets"] == [
        {"symbol": "ETH/USD", "market_type": "SPOT"}
    ]
    assert discovery["maintained_markets"] == [
        {"symbol": "BTC/USD", "market_type": "SPOT"}
    ]
