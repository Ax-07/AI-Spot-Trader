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
from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import AssetBalance, PortfolioState
from ai_spot_trader.domain.ports import MarketDataSource
from ai_spot_trader.integrations.kraken.derivatives import (
    KrakenDerivativesMarketDataSource,
    KrakenDerivativesPublicClient,
)
from ai_spot_trader.integrations.kraken.market_data import build_kraken_market_data_source
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


class RuntimeMarketDataSource(MarketDataSource, Protocol):
    """Canonical market source plus the runtime-owned async close surface."""

    async def aclose(self) -> None: ...


@dataclass(frozen=True, slots=True)
class PaperRuntimeComposition:
    """Canonical objects assembled for the executable PAPER application."""

    runtime: AppRuntime
    chat_service: OperatorChatService
    market_data: RuntimeMarketDataSource
    portfolio: PaperPortfolioLedger
    agent: OpenAIDecisionProvider
    risk_engine: RiskEngine
    broker: PaperBroker
    cost_model: PaperExecutionCostModel
    cycle_runner: TradingCycleRunner
    audited_runner: AuditedTradingCycleRunner
    trading_engine: TradingEngine


def build_paper_runtime(settings: Settings) -> PaperRuntimeComposition:
    """Compose one canonical SPOT or PERPETUAL PAPER runtime."""

    run = PaperRunConfiguration.from_settings(settings)
    clock = SystemClock()

    database = Database(run.database_url.get_secret_value())
    audit_repository = SqlAlchemyCycleAuditRepository(database.sessions)
    audit_reader = SqlAlchemyCycleAuditQueryService(database.sessions)
    analytics_reader = SqlAlchemyPaperAnalyticsQueryService(database.sessions)

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

    if run.market_type is MarketType.SPOT:
        market_data: RuntimeMarketDataSource = build_kraken_market_data_source(
            settings, clock=clock
        )
    else:
        market_data = KrakenDerivativesMarketDataSource(
            KrakenDerivativesPublicClient(
                settings.kraken_derivatives_rest_url,
                timeout_seconds=settings.kraken_rest_timeout_seconds,
            ),
            clock=clock,
            market_sink=portfolio,
            stale_after=(
                timedelta(seconds=settings.kraken_stale_after_seconds)
                if settings.kraken_stale_after_seconds is not None
                else None
            ),
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
