from dataclasses import dataclass
from typing import cast
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
from ai_spot_trader.integrations.kraken.market_data import (
    KrakenMarketDataSource,
    build_kraken_market_data_source,
)
from ai_spot_trader.persistence.analytics import SqlAlchemyPaperAnalyticsQueryService
from ai_spot_trader.persistence.audit import AuditedTradingCycleRunner
from ai_spot_trader.persistence.db import Database
from ai_spot_trader.persistence.query import SqlAlchemyCycleAuditQueryService
from ai_spot_trader.persistence.repository import SqlAlchemyCycleAuditRepository
from ai_spot_trader.portfolio.ledger import PaperPortfolioLedger
from ai_spot_trader.risk.engine import RiskEngine
from ai_spot_trader.risk.policy import RiskPolicy
from ai_spot_trader.trading.engine import (
    TradingCycleRunner,
    TradingCycleTimeouts,
    TradingEngine,
)


@dataclass(frozen=True, slots=True)
class PaperRuntimeComposition:
    """Canonical objects assembled for the executable PAPER application."""

    runtime: AppRuntime
    chat_service: OperatorChatService
    market_data: KrakenMarketDataSource
    portfolio: PaperPortfolioLedger
    agent: OpenAIDecisionProvider
    risk_engine: RiskEngine
    broker: PaperBroker
    cost_model: PaperExecutionCostModel
    cycle_runner: TradingCycleRunner
    audited_runner: AuditedTradingCycleRunner
    trading_engine: TradingEngine


def build_paper_runtime(settings: Settings) -> PaperRuntimeComposition:
    """Compose the real PAPER runtime from existing canonical components only."""

    run = PaperRunConfiguration.from_settings(settings)
    clock = SystemClock()

    database = Database(run.database_url.get_secret_value())
    audit_repository = SqlAlchemyCycleAuditRepository(database.sessions)
    audit_reader = SqlAlchemyCycleAuditQueryService(database.sessions)
    analytics_reader = SqlAlchemyPaperAnalyticsQueryService(database.sessions)

    market_data = build_kraken_market_data_source(settings, clock=clock)
    openai_client = OpenAIResponsesClient(
        api_key=run.openai_api_key,
        base_url=settings.openai_base_url,
        timeout_seconds=settings.openai_timeout_seconds,
    )
    agent = OpenAIDecisionProvider(
        client=openai_client,
        model=run.llm_model,
        clock=clock,
    )

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
        market_data=market_data,
        portfolio=portfolio,
        agent=agent,
        risk_engine=risk_engine,
        broker=broker,
        symbol=run.symbol,
        aggressiveness=run.aggressiveness,
        timeouts=TradingCycleTimeouts(
            market_seconds=run.market_timeout_seconds,
            agent_seconds=run.agent_timeout_seconds,
            broker_seconds=run.broker_timeout_seconds,
        ),
        clock=clock,
    )
    audited_runner = AuditedTradingCycleRunner(
        delegate=cycle_runner,
        audit_writer=audit_repository,
    )
    trading_engine = TradingEngine(
        runner=cast(TradingCycleRunner, audited_runner),
        cadence_seconds=run.cadence_seconds,
    )

    runtime = AppRuntime(
        trading_engine=trading_engine,
        portfolio=portfolio,
        audit_reader=audit_reader,
        analytics_reader=analytics_reader,
        owned_database=database,
        owned_resources=(market_data,),
    )
    chat_service = OperatorChatService(
        provider=OpenAIChatProvider(client=openai_client, model=run.llm_model),
        context_source=RuntimeChatContextSource(runtime),
    )

    return PaperRuntimeComposition(
        runtime=runtime,
        chat_service=chat_service,
        market_data=market_data,
        portfolio=portfolio,
        agent=agent,
        risk_engine=risk_engine,
        broker=broker,
        cost_model=cost_model,
        cycle_runner=cycle_runner,
        audited_runner=audited_runner,
        trading_engine=trading_engine,
    )
