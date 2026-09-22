from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Protocol, cast
from uuid import uuid4

from ai_spot_trader.agent.openai_client import OpenAIResponsesClient
from ai_spot_trader.agent.provider import OpenAIDecisionProvider
from ai_spot_trader.broker.paper import PaperBroker
from ai_spot_trader.broker.pricing import PaperExecutionCostModel
from ai_spot_trader.chat.provider import OpenAIChatProvider
from ai_spot_trader.chat.service import OperatorChatService, RuntimeChatContextSource
from ai_spot_trader.core.clock import SystemClock
from ai_spot_trader.core.config import PaperRunConfiguration, Settings
from ai_spot_trader.core.runtime import AppRuntime
from ai_spot_trader.domain.models import AssetBalance, PortfolioState
from ai_spot_trader.domain.ports import MarketDataSource
from ai_spot_trader.integrations.kraken.derivatives import (
    KrakenDerivativesMarketDataSource,
    KrakenDerivativesPublicClient,
)
from ai_spot_trader.integrations.kraken.market_data import (
    KrakenMarketDataSource,
    build_kraken_market_data_source,
)
from ai_spot_trader.integrations.kraken.research import KrakenMarketResearchBackend
from ai_spot_trader.market.execution import RoutedExecutableMarketDataSource
from ai_spot_trader.market.research import MarketResearchService
from ai_spot_trader.persistence.analytics import SqlAlchemyPaperAnalyticsQueryService
from ai_spot_trader.persistence.audit import AuditedTradingCycleRunner, RunBoundCycleAuditWriter
from ai_spot_trader.persistence.db import Database
from ai_spot_trader.persistence.query import SqlAlchemyCycleAuditQueryService
from ai_spot_trader.persistence.repository import SqlAlchemyCycleAuditRepository
from ai_spot_trader.persistence.runs import (
    SqlAlchemyPaperRunLifecycle,
    SqlAlchemyPaperRunQueryService,
)
from ai_spot_trader.portfolio.ledger import PaperPortfolioLedger
from ai_spot_trader.risk.engine import RiskEngine
from ai_spot_trader.risk.policy import RiskPolicy
from ai_spot_trader.tools.market_research import build_market_research_tool_registry
from ai_spot_trader.tools.read_only import ReadOnlyToolRegistry
from ai_spot_trader.trading.engine import (
    TradingCycleRunner,
    TradingCycleTimeouts,
    TradingEngine,
)


class RuntimeMarketDataSource(MarketDataSource, Protocol):
    """Canonical network market source plus the runtime-owned async close surface."""

    async def aclose(self) -> None: ...


@dataclass(frozen=True, slots=True)
class PaperRuntimeComposition:
    """Canonical objects assembled for the executable multi-market PAPER application."""

    runtime: AppRuntime
    chat_service: OperatorChatService
    market_data: RoutedExecutableMarketDataSource
    market_research: MarketResearchService
    agent_tools: ReadOnlyToolRegistry
    portfolio: PaperPortfolioLedger
    agent: OpenAIDecisionProvider
    risk_engine: RiskEngine
    broker: PaperBroker
    cost_model: PaperExecutionCostModel
    cycle_runner: TradingCycleRunner
    audited_runner: AuditedTradingCycleRunner
    trading_engine: TradingEngine
    paper_run_lifecycle: SqlAlchemyPaperRunLifecycle
    paper_run_reader: SqlAlchemyPaperRunQueryService


def _derivatives_source(
    settings: Settings,
    *,
    clock: SystemClock,
    market_sink: PaperPortfolioLedger | None,
) -> KrakenDerivativesMarketDataSource:
    return KrakenDerivativesMarketDataSource(
        KrakenDerivativesPublicClient(
            settings.kraken_derivatives_rest_url,
            timeout_seconds=settings.kraken_rest_timeout_seconds,
        ),
        clock=clock,
        market_sink=market_sink,
        stale_after=(
            timedelta(seconds=settings.kraken_stale_after_seconds)
            if settings.kraken_stale_after_seconds is not None
            else None
        ),
    )


def build_paper_runtime(settings: Settings) -> PaperRuntimeComposition:
    """Compose one canonical PAPER runtime with Agent-selected SPOT/PERPETUAL execution."""

    run = PaperRunConfiguration.from_settings(settings)
    clock = SystemClock()

    database = Database(run.database_url.get_secret_value())
    audit_repository = SqlAlchemyCycleAuditRepository(database.sessions)
    audit_reader = SqlAlchemyCycleAuditQueryService(database.sessions)
    analytics_reader = SqlAlchemyPaperAnalyticsQueryService(database.sessions)
    paper_run_lifecycle = SqlAlchemyPaperRunLifecycle(
        database.sessions,
        execution_universe=run.executable_markets,
        clock=clock,
    )
    paper_run_reader = SqlAlchemyPaperRunQueryService(database.sessions)

    initial_portfolio = PortfolioState(
        portfolio_state_id=uuid4(),
        as_of=clock.now(),
        balances=(
            AssetBalance(
                asset=run.settlement_asset,
                available=run.initial_capital,
            ),
        ),
    )
    portfolio = PaperPortfolioLedger(initial_state=initial_portfolio, clock=clock)

    # Research sources are distinct from execution sources. In particular, the research
    # Derivatives source has no market_sink and can never mark positions or accrue funding.
    research_spot: KrakenMarketDataSource = build_kraken_market_data_source(
        settings, clock=clock
    )
    research_derivatives_client = KrakenDerivativesPublicClient(
        settings.kraken_derivatives_rest_url,
        timeout_seconds=settings.kraken_rest_timeout_seconds,
    )
    research_derivatives = KrakenDerivativesMarketDataSource(
        research_derivatives_client,
        clock=clock,
        stale_after=(
            timedelta(seconds=settings.kraken_stale_after_seconds)
            if settings.kraken_stale_after_seconds is not None
            else None
        ),
    )
    market_research = MarketResearchService(
        KrakenMarketResearchBackend(
            spot=research_spot,
            derivatives=research_derivatives,
            derivatives_catalog=research_derivatives_client,
        ),
        max_list_limit=run.agent_tool_list_markets_max_limit,
        clock=clock,
    )
    agent_tools = build_market_research_tool_registry(
        market_research,
        timeout_seconds=run.agent_tool_timeout_seconds,
        max_result_bytes=run.agent_tool_max_result_bytes,
        clock=clock,
    )

    openai_client = OpenAIResponsesClient(
        api_key=run.openai_api_key,
        base_url=settings.openai_base_url,
        timeout_seconds=settings.openai_timeout_seconds,
    )
    agent = OpenAIDecisionProvider(
        client=openai_client,
        model=run.llm_model,
        clock=clock,
        tool_registry=agent_tools,
        max_tool_calls=run.agent_tool_max_calls,
    )

    execution_spot: RuntimeMarketDataSource = build_kraken_market_data_source(
        settings, clock=clock
    )
    execution_derivatives = _derivatives_source(
        settings,
        clock=clock,
        market_sink=portfolio,
    )
    market_data = RoutedExecutableMarketDataSource(
        spot=execution_spot,
        derivatives=execution_derivatives,
        allowed_markets=run.executable_markets,
    )

    cost_model = PaperExecutionCostModel(
        fee_rate=run.fee_rate,
        spread_bps=run.spread_bps,
        slippage_bps=run.slippage_bps,
    )
    risk_engine = RiskEngine(
        policy=RiskPolicy(
            max_order_notional=run.max_order_notional,
            allowed_pairs=run.allowed_pairs,
            allow_quantity_reduction=run.allow_quantity_reduction,
            derivative_leverage=run.derivative_leverage or Decimal(1),
            max_derivative_leverage=run.max_derivative_leverage or Decimal(1),
            max_derivative_position_notional=run.max_derivative_position_notional,
            max_total_derivative_exposure=run.max_total_derivative_exposure,
            derivative_liquidation_buffer_ratio=(
                run.derivative_liquidation_buffer_ratio or Decimal("1.10")
            ),
            derivative_margin_mode=run.derivative_margin_mode,
        ),
        cost_model=cost_model,
        clock=clock,
    )
    broker = PaperBroker(
        ledger=portfolio,
        cost_model=cost_model,
        clock=clock,
    )
    cycle_runner = TradingCycleRunner(
        executable_market_data=market_data,
        executable_markets=run.executable_markets,
        portfolio=portfolio,
        agent=agent,
        risk_engine=risk_engine,
        broker=broker,
        aggressiveness=run.aggressiveness,
        timeouts=TradingCycleTimeouts(
            market_seconds=run.market_timeout_seconds,
            agent_seconds=run.agent_timeout_seconds,
            broker_seconds=run.broker_timeout_seconds,
        ),
        clock=clock,
    )
    run_bound_writer = RunBoundCycleAuditWriter(
        delegate=audit_repository,
        run_provider=paper_run_lifecycle,
    )
    audited_runner = AuditedTradingCycleRunner(
        delegate=cycle_runner,
        audit_writer=run_bound_writer,
    )
    trading_engine = TradingEngine(
        runner=cast(TradingCycleRunner, audited_runner),
        cadence_seconds=run.cadence_seconds,
    )

    resources: list[RuntimeMarketDataSource] = [
        execution_spot,
        execution_derivatives,
        research_spot,
        research_derivatives,
    ]
    unique_resources: list[RuntimeMarketDataSource] = []
    for resource in resources:
        if all(resource is not owned for owned in unique_resources):
            unique_resources.append(resource)

    runtime = AppRuntime(
        trading_engine=trading_engine,
        portfolio=portfolio,
        audit_reader=audit_reader,
        analytics_reader=analytics_reader,
        paper_run_lifecycle=paper_run_lifecycle,
        paper_run_reader=paper_run_reader,
        owned_database=database,
        owned_resources=tuple(unique_resources),
    )
    chat_service = OperatorChatService(
        provider=OpenAIChatProvider(client=openai_client, model=run.llm_model),
        context_source=RuntimeChatContextSource(runtime),
    )

    return PaperRuntimeComposition(
        runtime=runtime,
        chat_service=chat_service,
        market_data=market_data,
        market_research=market_research,
        agent_tools=agent_tools,
        portfolio=portfolio,
        agent=agent,
        risk_engine=risk_engine,
        broker=broker,
        cost_model=cost_model,
        cycle_runner=cycle_runner,
        audited_runner=audited_runner,
        trading_engine=trading_engine,
        paper_run_lifecycle=paper_run_lifecycle,
        paper_run_reader=paper_run_reader,
    )
