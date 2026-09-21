from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ai_spot_trader import __version__
from ai_spot_trader.agent.openai_client import OpenAIResponsesClient
from ai_spot_trader.api.routes.analytics import router as analytics_router
from ai_spot_trader.api.routes.audit import router as audit_router
from ai_spot_trader.api.routes.chat import router as chat_router
from ai_spot_trader.api.routes.engine import router as engine_router
from ai_spot_trader.api.routes.health import router as health_router
from ai_spot_trader.api.routes.portfolio import router as portfolio_router
from ai_spot_trader.chat.provider import OpenAIChatProvider
from ai_spot_trader.chat.service import OperatorChatService, RuntimeChatContextSource
from ai_spot_trader.composition import build_paper_runtime
from ai_spot_trader.core.config import Settings, get_settings
from ai_spot_trader.core.runtime import (
    AppRuntime,
    PortfolioSnapshotSource,
    StoppableTradingEngine,
)
from ai_spot_trader.persistence.analytics import (
    PaperAnalyticsReader,
    SqlAlchemyPaperAnalyticsQueryService,
)
from ai_spot_trader.persistence.db import Database
from ai_spot_trader.persistence.query import (
    CycleAuditReader,
    SqlAlchemyCycleAuditQueryService,
)


def create_app(
    settings: Settings | None = None,
    *,
    trading_engine: StoppableTradingEngine | None = None,
    portfolio: PortfolioSnapshotSource | None = None,
    audit_reader: CycleAuditReader | None = None,
    analytics_reader: PaperAnalyticsReader | None = None,
    chat_service: OperatorChatService | None = None,
    compose_paper: bool = False,
) -> FastAPI:
    """Create FastAPI; the module-level app composes PAPER only during lifespan startup."""

    resolved_settings = settings or get_settings()
    injected_dependencies = (
        trading_engine,
        portfolio,
        audit_reader,
        analytics_reader,
        chat_service,
    )
    if compose_paper and any(value is not None for value in injected_dependencies):
        raise ValueError("compose_paper cannot be combined with injected runtime dependencies")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved_chat_service: OperatorChatService | None
        if compose_paper:
            composition = build_paper_runtime(resolved_settings)
            runtime = composition.runtime
            resolved_chat_service = composition.chat_service
        else:
            owned_database: Database | None = None
            resolved_audit_reader = audit_reader
            resolved_analytics_reader = analytics_reader
            database_secret = resolved_settings.database_url
            if (
                (resolved_audit_reader is None or resolved_analytics_reader is None)
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

            runtime = AppRuntime(
                trading_engine=trading_engine,
                portfolio=portfolio,
                audit_reader=resolved_audit_reader,
                analytics_reader=resolved_analytics_reader,
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

        app.state.runtime = runtime
        app.state.chat_service = resolved_chat_service
        try:
            yield
        finally:
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
    app.include_router(chat_router)
    return app


app = create_app(compose_paper=True)
