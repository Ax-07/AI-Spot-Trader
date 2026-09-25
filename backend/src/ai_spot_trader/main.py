from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI

from ai_spot_trader import __version__
from ai_spot_trader.agent.openai_client import OpenAIResponsesClient
from ai_spot_trader.api.routes.analytics import router as analytics_router
from ai_spot_trader.api.routes.audit import router as audit_router
from ai_spot_trader.api.routes.candles import router as candles_router
from ai_spot_trader.api.routes.chat import router as chat_router
from ai_spot_trader.api.routes.control_plane import router as control_plane_router
from ai_spot_trader.api.routes.engine import router as engine_router
from ai_spot_trader.api.routes.health import router as health_router
from ai_spot_trader.api.routes.paper_runs import router as paper_runs_router
from ai_spot_trader.api.routes.portfolio import router as portfolio_router
from ai_spot_trader.api.routes.sessions import router as sessions_router
from ai_spot_trader.chat.provider import OpenAIChatProvider
from ai_spot_trader.chat.service import OperatorChatService, RuntimeChatContextSource
from ai_spot_trader.core.config import (
    PaperRuntimeConfigurationError,
    Settings,
    get_settings,
)
from ai_spot_trader.core.control_plane_runtime import CampaignRuntimeManager
from ai_spot_trader.core.runtime import (
    AppRuntime,
    PortfolioSnapshotSource,
    StoppableTradingEngine,
)
from ai_spot_trader.integrations.kraken.candles import KrakenCandleProvider
from ai_spot_trader.market.candles import CandleCache, CandleStreamService
from ai_spot_trader.persistence.analytics import (
    PaperAnalyticsReader,
    SqlAlchemyPaperAnalyticsQueryService,
)
from ai_spot_trader.persistence.campaign_runs import CampaignPaperRunQueryService
from ai_spot_trader.persistence.control_plane import SqlAlchemyControlPlaneStore
from ai_spot_trader.persistence.db import Database
from ai_spot_trader.persistence.query import (
    CycleAuditReader,
    SqlAlchemyCycleAuditQueryService,
)
from ai_spot_trader.persistence.runs import (
    PaperRunReader,
    SqlAlchemyPaperRunQueryService,
)


def create_app(
    settings: Settings | None = None,
    *,
    trading_engine: StoppableTradingEngine | None = None,
    portfolio: PortfolioSnapshotSource | None = None,
    audit_reader: CycleAuditReader | None = None,
    analytics_reader: PaperAnalyticsReader | None = None,
    paper_run_reader: PaperRunReader | None = None,
    chat_service: OperatorChatService | None = None,
    candle_service: CandleStreamService | None = None,
    compose_paper: bool = False,
) -> FastAPI:
    """Create FastAPI; market-data streams remain backend-owned and campaign-independent."""

    resolved_settings = settings or get_settings()
    injected_dependencies = (
        trading_engine,
        portfolio,
        audit_reader,
        analytics_reader,
        paper_run_reader,
        chat_service,
        candle_service,
    )
    if compose_paper and any(value is not None for value in injected_dependencies):
        raise ValueError("compose_paper cannot be combined with injected runtime dependencies")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved_chat_service: OperatorChatService | None
        control_plane_store: SqlAlchemyControlPlaneStore | None = None

        if compose_paper:
            database_secret = resolved_settings.database_url
            if database_secret is not None and database_secret.get_secret_value().strip():
                database = Database(database_secret.get_secret_value().strip())
                base_audit_reader = SqlAlchemyCycleAuditQueryService(database.sessions)
                base_analytics_reader = SqlAlchemyPaperAnalyticsQueryService(database.sessions)
                campaign_run_reader = CampaignPaperRunQueryService(database.sessions)
                control_plane_store = SqlAlchemyControlPlaneStore(database.sessions)
                runtime: AppRuntime | CampaignRuntimeManager = CampaignRuntimeManager(
                    settings=resolved_settings,
                    control_plane_store=control_plane_store,
                    database=database,
                    paper_run_reader=campaign_run_reader,
                    audit_reader=base_audit_reader,
                    analytics_reader=base_analytics_reader,
                )
            else:
                raise PaperRuntimeConfigurationError(
                    "Control Plane startup requires DATABASE_URL; "
                    "no campaign activation is required"
                )

            resolved_chat_service = None
            api_key = resolved_settings.openai_api_key
            if api_key is not None:
                client = OpenAIResponsesClient(
                    api_key=api_key,
                    base_url=resolved_settings.openai_base_url,
                    timeout_seconds=resolved_settings.openai_timeout_seconds,
                )
                resolved_chat_service = OperatorChatService(
                    provider=OpenAIChatProvider(
                        client=client,
                        model=resolved_settings.llm_model,
                    ),
                    context_source=RuntimeChatContextSource(runtime),  # type: ignore[arg-type]
                )
        else:
            owned_database: Database | None = None
            resolved_audit_reader = audit_reader
            resolved_analytics_reader = analytics_reader
            resolved_paper_run_reader = paper_run_reader
            database_secret = resolved_settings.database_url
            if (
                (
                    resolved_audit_reader is None
                    or resolved_analytics_reader is None
                    or resolved_paper_run_reader is None
                )
                and database_secret is not None
            ):
                database_url = database_secret.get_secret_value().strip()
                if database_url:
                    owned_database = Database(database_url)
                    if resolved_audit_reader is None:
                        resolved_audit_reader = SqlAlchemyCycleAuditQueryService(
                            owned_database.sessions
                        )
                    if resolved_analytics_reader is None:
                        resolved_analytics_reader = SqlAlchemyPaperAnalyticsQueryService(
                            owned_database.sessions
                        )
                    if resolved_paper_run_reader is None:
                        resolved_paper_run_reader = SqlAlchemyPaperRunQueryService(
                            owned_database.sessions
                        )

            runtime = AppRuntime(
                trading_engine=trading_engine,
                portfolio=portfolio,
                audit_reader=resolved_audit_reader,
                analytics_reader=resolved_analytics_reader,
                paper_run_reader=resolved_paper_run_reader,
                owned_database=owned_database,
            )
            resolved_chat_service = chat_service
            api_key = resolved_settings.openai_api_key
            if resolved_chat_service is None and api_key is not None:
                client = OpenAIResponsesClient(
                    api_key=api_key,
                    base_url=resolved_settings.openai_base_url,
                    timeout_seconds=resolved_settings.openai_timeout_seconds,
                )
                provider = OpenAIChatProvider(
                    client=client,
                    model=resolved_settings.llm_model,
                )
                resolved_chat_service = OperatorChatService(
                    provider=provider,
                    context_source=RuntimeChatContextSource(runtime),
                )

        resolved_candle_service = candle_service
        if resolved_candle_service is None:
            stale_seconds = resolved_settings.kraken_stale_after_seconds or 90.0
            resolved_candle_service = CandleStreamService(
                KrakenCandleProvider(
                    spot_rest_url=resolved_settings.kraken_rest_url,
                    spot_ws_url=resolved_settings.kraken_ws_url,
                    derivatives_rest_url=resolved_settings.kraken_derivatives_rest_url,
                    timeout_seconds=resolved_settings.kraken_rest_timeout_seconds,
                    ws_receive_timeout_seconds=max(
                        resolved_settings.kraken_ws_receive_timeout_seconds,
                        30.0,
                    ),
                ),
                cache=CandleCache(max_depth=1000),
                max_streams=32,
                stale_after=timedelta(seconds=stale_seconds),
                reconnect_delay_seconds=resolved_settings.kraken_ws_reconnect_delay_seconds,
            )

        app.state.runtime = runtime
        app.state.chat_service = resolved_chat_service
        app.state.control_plane_store = control_plane_store
        app.state.candle_service = resolved_candle_service
        try:
            await runtime.initialize()
            yield
        finally:
            await resolved_candle_service.aclose()
            await runtime.close()

    app = FastAPI(
        title=resolved_settings.app_name,
        version=__version__,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.include_router(health_router)
    app.include_router(engine_router)
    app.include_router(portfolio_router)
    app.include_router(audit_router)
    app.include_router(analytics_router)
    app.include_router(paper_runs_router)
    app.include_router(control_plane_router)
    app.include_router(sessions_router)
    app.include_router(chat_router)
    app.include_router(candles_router)
    return app


app = create_app(compose_paper=True)
