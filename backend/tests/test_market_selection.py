import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import SecretStr

from ai_spot_trader.agent.errors import AgentContractViolationError
from ai_spot_trader.agent.provider import OpenAIDecisionProvider
from ai_spot_trader.core.config import (
    PaperRunConfiguration,
    PaperRuntimeConfigurationError,
    Settings,
)
from ai_spot_trader.domain.enums import DerivativeContractKind, MarketType
from ai_spot_trader.domain.models import (
    AgentInput,
    AssetBalance,
    DerivativeInstrument,
    DerivativeMarketContext,
    ExecutableMarket,
    MarketSelectionInput,
    MarketState,
    PortfolioState,
)
from ai_spot_trader.market.execution import (
    ExecutableMarketSnapshotMismatchError,
    MarketOutsideExecutableUniverseError,
    RoutedExecutableMarketDataSource,
)

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
CYCLE = UUID("10000000-0000-0000-0000-000000000001")


class FixedClock:
    def now(self) -> datetime:
        return NOW


class StaticClient:
    def __init__(self, outputs: list[dict[str, object]]) -> None:
        self.outputs = list(outputs)
        self.calls: list[dict[str, object]] = []

    async def generate_structured_decision(self, **kwargs: object) -> str:
        self.calls.append(kwargs)
        return json.dumps(self.outputs.pop(0))


class Source:
    def __init__(self, state: MarketState) -> None:
        self.state = state
        self.calls: list[str] = []

    async def snapshot(self, symbol: str) -> MarketState:
        self.calls.append(symbol)
        return self.state


def portfolio() -> PortfolioState:
    return PortfolioState(
        portfolio_state_id=UUID("20000000-0000-0000-0000-000000000002"),
        as_of=NOW - timedelta(seconds=2),
        balances=(AssetBalance(asset="USD", available=Decimal("1000")),),
    )


def perpetual_state(symbol: str = "ETH/USD") -> MarketState:
    instrument = DerivativeInstrument(
        symbol=symbol,
        venue_symbol="PF_ETHUSD",
        market_type=MarketType.PERPETUAL,
        contract_kind=DerivativeContractKind.LINEAR,
        underlying_asset="ETH",
        quote_asset="USD",
        contract_size=Decimal("1"),
        tick_size=Decimal("0.1"),
        min_order_quantity=Decimal("0.001"),
        initial_margin_rate=Decimal("0.1"),
        maintenance_margin_rate=Decimal("0.05"),
        max_leverage=Decimal("10"),
        funding_interval_seconds=Decimal("3600"),
    )
    return MarketState(
        market_state_id=UUID("30000000-0000-0000-0000-000000000003"),
        as_of=NOW - timedelta(seconds=1),
        symbol=symbol,
        last_price=Decimal("2000"),
        market_type=MarketType.PERPETUAL,
        derivative=DerivativeMarketContext(
            observed_at=NOW - timedelta(seconds=1),
            instrument=instrument,
            mark_price=Decimal("2000"),
        ),
    )


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "environment": "test",
        "paper_symbol": "BTC/USD",
        "paper_market_type": MarketType.SPOT,
        "paper_executable_markets": ("SPOT:BTC/USD", "SPOT:ETH/USD"),
        "paper_initial_capital": Decimal("1000"),
        "paper_settlement_asset": "USD",
        "trading_cadence_seconds": 30.0,
        "aggressiveness": 5,
        "cycle_market_timeout_seconds": 5.0,
        "cycle_agent_timeout_seconds": 30.0,
        "cycle_broker_timeout_seconds": 5.0,
        "risk_max_order_notional": Decimal("250"),
        "risk_allowed_pairs": frozenset({"BTC/USD", "ETH/USD"}),
        "risk_allow_quantity_reduction": True,
        "paper_fee_rate": Decimal("0.001"),
        "paper_spread_bps": Decimal("2"),
        "paper_slippage_bps": Decimal("3"),
        "database_url": SecretStr("postgresql+asyncpg://test:test@localhost/test"),
        "openai_api_key": SecretStr("test-key"),
    }
    values.update(overrides)
    return Settings(**values)


def test_same_agent_selects_typed_market_then_decides_on_acquired_state() -> None:
    client = StaticClient([
        {"symbol": "ETH/USD", "market_type": "SPOT", "rationale": "meilleur contexte"},
        {"action": "HOLD", "symbol": "ETH/USD", "proposed_quantity": None, "rationale": "attendre"},
    ])
    provider = OpenAIDecisionProvider(client=client, clock=FixedClock())
    selection_input = MarketSelectionInput(
        cycle_id=CYCLE,
        created_at=NOW,
        portfolio_state=portfolio(),
        executable_markets=(
            ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),
            ExecutableMarket(symbol="ETH/USD", market_type=MarketType.SPOT),
        ),
        aggressiveness=5,
    )
    selection = asyncio.run(provider.select_market(selection_input))
    assert selection.symbol == "ETH/USD"
    assert selection.market_type is MarketType.SPOT

    selected_state = MarketState(
        market_state_id=UUID(int=88),
        as_of=NOW,
        symbol="ETH/USD",
        last_price=Decimal("2000"),
    )
    decision = asyncio.run(
        provider.generate_decision(
            AgentInput(
                cycle_id=CYCLE,
                created_at=NOW,
                market_state=selected_state,
                portfolio_state=portfolio(),
                aggressiveness=5,
                market_selection=selection,
            )
        )
    )
    assert decision.action.value == "HOLD"
    assert decision.symbol == "ETH/USD"
    assert decision.market_type is MarketType.SPOT
    assert decision.tool_traces == selection.tool_traces
    assert len(client.calls) == 2


def test_selection_outside_typed_universe_fails_closed() -> None:
    client = StaticClient([{"symbol": "SOL/USD", "market_type": "SPOT", "rationale": None}])
    provider = OpenAIDecisionProvider(client=client, clock=FixedClock())
    selection_input = MarketSelectionInput(
        cycle_id=CYCLE,
        created_at=NOW,
        portfolio_state=portfolio(),
        executable_markets=(ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),),
        aggressiveness=5,
    )
    with pytest.raises(AgentContractViolationError, match="outside"):
        asyncio.run(provider.select_market(selection_input))


def test_router_uses_exact_spot_or_perpetual_source() -> None:
    spot_state = MarketState(
        market_state_id=UUID("40000000-0000-0000-0000-000000000004"),
        as_of=NOW,
        symbol="BTC/USD",
        last_price=Decimal("60000"),
    )
    perp_state = perpetual_state()
    spot, deriv = Source(spot_state), Source(perp_state)
    router = RoutedExecutableMarketDataSource(
        spot=spot,
        derivatives=deriv,
        allowed_markets=(
            ExecutableMarket(symbol="ETH/USD", market_type=MarketType.PERPETUAL),
            ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),
        ),
    )
    # Constructor requires deterministic order: PERPETUAL sorts before SPOT.
    assert asyncio.run(router.snapshot("BTC/USD", MarketType.SPOT)) is spot_state
    assert asyncio.run(router.snapshot("ETH/USD", MarketType.PERPETUAL)) is perp_state
    assert spot.calls == ["BTC/USD"] and deriv.calls == ["ETH/USD"]


def test_router_rejects_outside_universe_and_mismatched_source() -> None:
    spot_state = MarketState(
        market_state_id=UUID("40000000-0000-0000-0000-000000000004"),
        as_of=NOW,
        symbol="BTC/USD",
        last_price=Decimal("60000"),
    )
    router = RoutedExecutableMarketDataSource(
        spot=Source(spot_state),
        derivatives=Source(perpetual_state()),
        allowed_markets=(ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),),
    )
    with pytest.raises(MarketOutsideExecutableUniverseError):
        asyncio.run(router.snapshot("ETH/USD", MarketType.SPOT))

    wrong = RoutedExecutableMarketDataSource(
        spot=Source(spot_state),
        derivatives=Source(perpetual_state()),
        allowed_markets=(ExecutableMarket(symbol="ETH/USD", market_type=MarketType.SPOT),),
    )
    with pytest.raises(ExecutableMarketSnapshotMismatchError):
        asyncio.run(wrong.snapshot("ETH/USD", MarketType.SPOT))


def test_configuration_builds_auditable_multi_market_universe() -> None:
    run = PaperRunConfiguration.from_settings(settings())
    assert run.executable_markets == (
        ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),
        ExecutableMarket(symbol="ETH/USD", market_type=MarketType.SPOT),
    )


def test_configuration_preserves_singleton_legacy_when_universe_omitted() -> None:
    run = PaperRunConfiguration.from_settings(settings(paper_executable_markets=None))
    assert run.executable_markets == (
        ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),
    )


def test_configuration_refuses_future_and_unwhitelisted_or_cross_quote_market() -> None:
    with pytest.raises(PaperRuntimeConfigurationError, match="SPOT/PERPETUAL only"):
        PaperRunConfiguration.from_settings(
            settings(paper_executable_markets=("SPOT:BTC/USD", "FUTURE:ETH/USD"))
        )
    with pytest.raises(PaperRuntimeConfigurationError, match="risk_allowed_pairs"):
        PaperRunConfiguration.from_settings(
            settings(
                paper_executable_markets=("SPOT:BTC/USD", "SPOT:SOL/USD"),
                risk_allowed_pairs=frozenset({"BTC/USD", "ETH/USD"}),
            )
        )
    with pytest.raises(PaperRuntimeConfigurationError, match="settlement"):
        PaperRunConfiguration.from_settings(
            settings(
                paper_executable_markets=("SPOT:BTC/USD", "SPOT:ETH/EUR"),
                risk_allowed_pairs=frozenset({"BTC/USD", "ETH/EUR"}),
            )
        )


def test_market_selection_rationale_is_preserved_and_digest_protected() -> None:
    client = StaticClient([
        {"symbol": "ETH/USD", "market_type": "SPOT", "rationale": "activité plus nette"},
    ])
    provider = OpenAIDecisionProvider(client=client, clock=FixedClock())
    selection_input = MarketSelectionInput(
        cycle_id=CYCLE,
        created_at=NOW,
        portfolio_state=portfolio(),
        executable_markets=(
            ExecutableMarket(symbol="ETH/USD", market_type=MarketType.SPOT),
        ),
        aggressiveness=5,
    )
    selection = asyncio.run(provider.select_market(selection_input))
    assert selection.rationale == "activité plus nette"
    with pytest.raises(ValueError, match="digest"):
        selection.model_copy(update={"rationale": "altéré"}, deep=True).__class__.model_validate(
            selection.model_copy(update={"rationale": "altéré"}).model_dump()
        )


def test_agent_cannot_select_dated_future_even_if_llm_emits_it() -> None:
    from ai_spot_trader.agent.errors import LLMOutputValidationError

    client = StaticClient([
        {"symbol": "ETH/USD", "market_type": "FUTURE", "rationale": None},
    ])
    provider = OpenAIDecisionProvider(client=client, clock=FixedClock())
    selection_input = MarketSelectionInput(
        cycle_id=CYCLE,
        created_at=NOW,
        portfolio_state=portfolio(),
        executable_markets=(
            ExecutableMarket(symbol="ETH/USD", market_type=MarketType.SPOT),
        ),
        aggressiveness=5,
    )
    with pytest.raises(LLMOutputValidationError, match="market-selection"):
        asyncio.run(provider.select_market(selection_input))


def test_router_rejects_non_linear_perpetual_instrument() -> None:
    from ai_spot_trader.market.execution import UnsupportedExecutableMarketError

    state = perpetual_state()
    assert state.derivative is not None
    inverse_instrument = state.derivative.instrument.model_copy(
        update={"contract_kind": DerivativeContractKind.INVERSE}
    )
    inverse_state = state.model_copy(
        update={
            "derivative": state.derivative.model_copy(
                update={"instrument": inverse_instrument}
            )
        }
    )
    router = RoutedExecutableMarketDataSource(
        spot=Source(
            MarketState(
                market_state_id=UUID(int=400),
                as_of=NOW,
                symbol="BTC/USD",
                last_price=Decimal("60000"),
            )
        ),
        derivatives=Source(inverse_state),
        allowed_markets=(
            ExecutableMarket(symbol="ETH/USD", market_type=MarketType.PERPETUAL),
        ),
    )
    with pytest.raises(UnsupportedExecutableMarketError, match="linear"):
        asyncio.run(router.snapshot("ETH/USD", MarketType.PERPETUAL))


def test_configuration_can_authorize_same_symbol_as_spot_and_perpetual() -> None:
    run = PaperRunConfiguration.from_settings(
        settings(
            paper_executable_markets=("SPOT:BTC/USD", "PERPETUAL:BTC/USD"),
            risk_allowed_pairs=frozenset({"BTC/USD"}),
            risk_max_derivative_position_notional=Decimal("500"),
            risk_max_total_derivative_exposure=Decimal("1000"),
        )
    )
    assert run.executable_markets == (
        ExecutableMarket(symbol="BTC/USD", market_type=MarketType.PERPETUAL),
        ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),
    )


def test_configuration_rejects_duplicate_typed_markets() -> None:
    with pytest.raises(PaperRuntimeConfigurationError, match="duplicates"):
        PaperRunConfiguration.from_settings(
            settings(
                paper_executable_markets=("SPOT:BTC/USD", "SPOT:BTC/USD"),
            )
        )
