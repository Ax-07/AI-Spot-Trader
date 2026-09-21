from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from ai_spot_trader.analytics.paper import PaperAnalyticsCycleFact, build_paper_analytics_report
from ai_spot_trader.domain.enums import DerivativeContractKind, MarketType, PositionSide
from ai_spot_trader.domain.models import (
    AgentInput,
    AssetBalance,
    DerivativeInstrument,
    DerivativeMarketContext,
    DerivativePosition,
    MarketState,
    PortfolioState,
)

START = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


def instrument() -> DerivativeInstrument:
    return DerivativeInstrument(
        symbol="BTC/USD",
        venue_symbol="PF_XBTUSD",
        market_type=MarketType.PERPETUAL,
        contract_kind=DerivativeContractKind.LINEAR,
        underlying_asset="BTC",
        quote_asset="USD",
        contract_size=Decimal("1"),
        tick_size=Decimal("1"),
        min_order_quantity=Decimal("0.01"),
        initial_margin_rate=Decimal("0.10"),
        maintenance_margin_rate=Decimal("0.05"),
        max_leverage=Decimal("10"),
        funding_interval_seconds=Decimal("3600"),
    )


def state(
    at: datetime,
    mark: str,
    unrealized: str,
    funding: str,
) -> tuple[MarketState, PortfolioState]:
    price = Decimal(mark)
    position = DerivativePosition(
        symbol="BTC/USD",
        side=PositionSide.LONG,
        quantity=Decimal("1"),
        average_entry_price=Decimal("100"),
        mark_price=price,
        notional=price,
        unrealized_pnl=Decimal(unrealized),
        leverage=Decimal("1"),
        margin_used=Decimal("100"),
        initial_margin_rate=Decimal("0.10"),
        maintenance_margin_rate=Decimal("0.05"),
        maintenance_margin=price * Decimal("0.05"),
        cumulative_funding=Decimal(funding),
        funding_updated_at=at,
    )
    market = MarketState(
        market_state_id=uuid4(),
        as_of=at,
        symbol="BTC/USD",
        last_price=price,
        market_type=MarketType.PERPETUAL,
        derivative=DerivativeMarketContext(
            observed_at=at,
            instrument=instrument(),
            mark_price=price,
            index_price=price,
            funding_rate=Decimal("0.01"),
        ),
    )
    portfolio = PortfolioState(
        portfolio_state_id=uuid4(),
        as_of=at,
        balances=(AssetBalance(asset="USD", available=Decimal("900")),),
        derivative_positions=(position,),
    )
    return market, portfolio


def fact(
    at: datetime,
    mark: str,
    unrealized: str,
    funding: str,
    digest_char: str,
) -> PaperAnalyticsCycleFact:
    market, portfolio = state(at, mark, unrealized, funding)
    cycle_id = uuid4()
    agent_input = AgentInput(
        cycle_id=cycle_id,
        created_at=at,
        market_state=market,
        portfolio_state=portfolio,
        aggressiveness=5,
    )
    return PaperAnalyticsCycleFact(
        cycle_id=cycle_id,
        status="COMPLETED",
        recorded_at=at,
        result_digest=digest_char * 64,
        agent_input_payload=agent_input.model_dump(mode="json"),
        decision_payload=None,
        risk_assessment_payload=None,
        fill_payloads=(),
        portfolio_after_payload=None,
    )


def test_derivatives_analytics_include_margin_unrealized_funding_and_exposure() -> None:
    report = build_paper_analytics_report(
        (
            fact(START, "100", "0", "0", "a"),
            fact(START + timedelta(hours=1), "110", "10", "-1.10", "b"),
        )
    )
    assert report.calculation_version == "paper-analytics-v2"
    assert report.summary.initial_equity == Decimal("1000")
    assert report.summary.ending_equity == Decimal("1008.90")
    assert report.summary.net_pnl == Decimal("8.90")
    assert report.summary.gross_pnl == Decimal("10.00")
    assert report.summary.funding_pnl == Decimal("-1.10")
    assert report.summary.current_exposure_value == Decimal("110")
