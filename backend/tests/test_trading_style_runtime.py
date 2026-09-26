from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from ai_spot_trader.control_plane import CampaignConfiguration
from ai_spot_trader.domain.enums import LLMModel, MarketType, TradingStyle
from ai_spot_trader.domain.experiments import (
    TRADING_STYLE_MAPPING_VERSION,
    aggressiveness_context,
    trading_style_context,
)
from ai_spot_trader.domain.models import (
    AssetBalance,
    ExecutionCostContext,
    ExecutableMarket,
    MarketSelection,
    MarketState,
    PortfolioState,
    market_selection_digest,
)
from ai_spot_trader.market.discovery import MarketDiscoveryCoordinator, MarketDiscoveryPolicy
from ai_spot_trader.persistence.control_plane import SqlAlchemyControlPlaneStore
from ai_spot_trader.persistence.db import Database
from ai_spot_trader.trading import discovery_runner as discovery_runner_module
from ai_spot_trader.trading.discovery_runner import DynamicMarketTradingCycleRunner
from ai_spot_trader.trading.engine import TradingCycleRunner, TradingCycleTimeouts

NOW = datetime(2026, 9, 26, 11, 0, tzinfo=UTC)
MARKET = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT)


class FixedClock:
    def now(self) -> datetime:
        return NOW


class StaticPortfolio:
    def __init__(self) -> None:
        self.state = PortfolioState(
            portfolio_state_id=uuid4(),
            as_of=NOW,
            settlement_asset="USD",
            balances=(AssetBalance(asset="USD", available=Decimal("1000")),),
            cash_available=Decimal("1000"),
        )

    def snapshot(self, *, as_of: datetime | None = None) -> PortfolioState:
        return self.state


class StaticExecutableMarketData:
    async def snapshot(self, symbol: str, market_type: MarketType) -> MarketState:
        assert symbol == MARKET.symbol
        assert market_type is MARKET.market_type
        return MarketState(
            market_state_id=uuid4(),
            as_of=NOW,
            symbol=MARKET.symbol,
            last_price=Decimal("50000"),
            market_type=MARKET.market_type,
        )


class CapturingAgent:
    def __init__(self) -> None:
        self.selection_input = None
        self.agent_input = None

    async def select_market(self, selection_input):
        self.selection_input = selection_input
        selection_id = uuid4()
        selected_at = selection_input.created_at
        return MarketSelection(
            selection_id=selection_id,
            cycle_id=selection_input.cycle_id,
            selected_at=selected_at,
            symbol=MARKET.symbol,
            market_type=MARKET.market_type,
            rationale="Contexte suffisant pour le test.",
            tool_traces=(),
            selection_digest=market_selection_digest(
                selection_id=selection_id,
                cycle_id=selection_input.cycle_id,
                selected_at=selected_at,
                symbol=MARKET.symbol,
                market_type=MARKET.market_type,
                rationale="Contexte suffisant pour le test.",
                tool_traces=(),
            ),
        )

    async def generate_decision(self, agent_input):
        self.agent_input = agent_input
        raise RuntimeError("stop after context capture")


def _costs() -> ExecutionCostContext:
    return ExecutionCostContext(
        fee_rate=Decimal("0.0026"),
        spread_bps=Decimal("5"),
        slippage_bps=Decimal("3"),
    )


def _config(style: TradingStyle | None) -> CampaignConfiguration:
    return CampaignConfiguration(
        llm_model=LLMModel.LUNA,
        aggressiveness=5,
        trading_cadence_seconds=30.0,
        trading_style=style,
        trading_style_mapping_version=(
            TRADING_STYLE_MAPPING_VERSION if style is not None else None
        ),
        paper_initial_capital=Decimal("1000"),
        paper_settlement_asset="USD",
        paper_executable_markets=(MARKET,),
        paper_fee_rate=Decimal("0.0026"),
        paper_spread_bps=Decimal("5"),
        paper_slippage_bps=Decimal("3"),
        risk_max_order_notional=Decimal("100"),
        risk_allowed_pairs=("BTC/USD",),
        risk_allow_quantity_reduction=True,
        cycle_market_timeout_seconds=20.0,
        cycle_agent_timeout_seconds=35.0,
        cycle_broker_timeout_seconds=5.0,
    )


def test_trading_cycle_runner_propagates_style_and_costs_to_selection_and_final_input() -> None:
    async def scenario() -> None:
        agent = CapturingAgent()
        style = trading_style_context(TradingStyle.SCALP)
        costs = _costs()
        runner = TradingCycleRunner(
            portfolio=StaticPortfolio(),
            agent=agent,
            risk_engine=object(),  # not reached: the fake Agent stops the cycle first
            broker=object(),  # not reached
            aggressiveness=5,
            timeouts=TradingCycleTimeouts(
                market_seconds=1.0,
                agent_seconds=1.0,
                broker_seconds=1.0,
            ),
            executable_market_data=StaticExecutableMarketData(),
            executable_markets=(MARKET,),
            trading_style_context=style,
            execution_cost_context=costs,
            clock=FixedClock(),
        )

        result = await runner.run_cycle()
        assert result.market_selection_input is not None
        assert result.agent_input is not None
        assert agent.selection_input is result.market_selection_input
        assert agent.agent_input is result.agent_input
        assert result.market_selection_input.trading_style_context == style
        assert result.market_selection_input.execution_cost_context == costs
        assert result.agent_input.trading_style_context == style
        assert result.agent_input.execution_cost_context == costs

    asyncio.run(scenario())


def test_market_discovery_audit_retains_style_and_cost_context() -> None:
    style = trading_style_context(TradingStyle.SWING)
    costs = _costs()
    coordinator = MarketDiscoveryCoordinator(
        research=object(),  # unused by cache_result
        agent=object(),  # unused by cache_result
        policy=MarketDiscoveryPolicy(
            market_types=(MarketType.SPOT,),
            candidate_probe_limit=1,
            candidate_limit=1,
            watchlist_limit=1,
        ),
        settlement_asset="USD",
        bootstrap_markets=(MARKET,),
        aggressiveness=5,
        aggressiveness_context=aggressiveness_context(5),
        trading_style_context=style,
        execution_cost_context=costs,
        clock=FixedClock(),
    )

    result = coordinator.cache_result(status="CACHE_REUSED")
    assert result.audit.trading_style_context == style
    assert result.audit.execution_cost_context == costs


def test_dynamic_runner_forwards_style_and_cost_context_to_canonical_runner(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeCanonicalRunner:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

        async def run_cycle(self):
            return "sentinel"

    monkeypatch.setattr(discovery_runner_module, "TradingCycleRunner", FakeCanonicalRunner)
    style = trading_style_context(TradingStyle.SCALP)
    costs = _costs()
    runner = DynamicMarketTradingCycleRunner(
        portfolio=object(),
        agent=object(),
        risk_engine=object(),
        broker=object(),
        aggressiveness=5,
        timeouts=TradingCycleTimeouts(
            market_seconds=1.0,
            agent_seconds=1.0,
            broker_seconds=1.0,
        ),
        executable_market_data=object(),
        bootstrap_markets=(MARKET,),
        capacity_evaluator=object(),
        discovery=object(),
        settlement_asset="USD",
        trading_style_context=style,
        execution_cost_context=costs,
    )

    async def scenario() -> None:
        result = await runner._run_canonical(  # noqa: SLF001 - intentional regression boundary test
            effective=(MARKET,),
            portfolio_source=object(),
        )
        assert result == "sentinel"

    asyncio.run(scenario())
    assert captured["trading_style_context"] == style
    assert captured["execution_cost_context"] == costs


def test_style_change_creates_new_immutable_campaign_and_name_only_update_does_not() -> None:
    async def scenario() -> None:
        database = Database("sqlite+aiosqlite:///:memory:")
        await database.create_schema_for_tests()
        store = SqlAlchemyControlPlaneStore(database.sessions, clock=FixedClock())
        try:
            first = await store.create_session_bundle(
                name="Style session",
                strategy_prompt="Cherche une opportunite defendable.",
                configuration=_config(TradingStyle.SCALP),
            )
            second = await store.update_session_bundle(
                first.strategy.strategy_id,
                name="Style session",
                strategy_prompt="Cherche une opportunite defendable.",
                configuration=_config(TradingStyle.SWING),
            )
            assert second.campaign.campaign_id != first.campaign.campaign_id
            assert second.campaign.configuration_digest != first.campaign.configuration_digest
            assert second.campaign.experiment_digest != first.campaign.experiment_digest
            assert second.revision.strategy_revision == first.revision.strategy_revision

            renamed = await store.update_session_bundle(
                first.strategy.strategy_id,
                name="Style session renamed",
                strategy_prompt="Cherche une opportunite defendable.",
                configuration=_config(TradingStyle.SWING),
            )
            assert renamed.campaign.campaign_id == second.campaign.campaign_id
            assert renamed.campaign.configuration_digest == second.campaign.configuration_digest
        finally:
            await database.close()

    asyncio.run(scenario())


def test_legacy_campaign_roundtrip_keeps_historical_configuration_digest() -> None:
    async def scenario() -> None:
        database = Database("sqlite+aiosqlite:///:memory:")
        await database.create_schema_for_tests()
        store = SqlAlchemyControlPlaneStore(database.sessions, clock=FixedClock())
        try:
            bundle = await store.create_session_bundle(
                name="Legacy session",
                strategy_prompt="Reste selectif.",
                configuration=_config(None),
            )
            loaded = await store.get_campaign(bundle.campaign.campaign_id)
            assert loaded is not None
            assert loaded.configuration_digest == bundle.campaign.configuration_digest
            assert loaded.configuration.trading_style is None
            assert loaded.configuration.trading_style_mapping_version is None
            assert "trading_style" not in loaded.configuration.canonical_payload()
        finally:
            await database.close()

    asyncio.run(scenario())


def test_style_does_not_mutate_risk_configuration() -> None:
    scalp = _config(TradingStyle.SCALP)
    swing = _config(TradingStyle.SWING)
    risk_fields = (
        "risk_max_order_notional",
        "risk_allowed_pairs",
        "risk_allow_quantity_reduction",
        "risk_max_derivative_leverage",
        "risk_max_derivative_position_notional",
        "risk_max_total_derivative_exposure",
        "risk_derivative_liquidation_buffer_ratio",
    )
    assert tuple(getattr(scalp, name) for name in risk_fields) == tuple(
        getattr(swing, name) for name in risk_fields
    )
