from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ai_spot_trader import __version__
from ai_spot_trader.api.routes.audit import router as audit_router
from ai_spot_trader.api.routes.engine import router as engine_router
from ai_spot_trader.api.routes.health import router as health_router
from ai_spot_trader.api.routes.portfolio import router as portfolio_router
from ai_spot_trader.core.config import Settings, get_settings
from ai_spot_trader.core.runtime import (
    AppRuntime,
    PortfolioSnapshotSource,
    StoppableTradingEngine,
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
) -> FastAPI:
    """Create FastAPI without starting trading or performing external I/O."""

    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        owned_database: Database | None = None
        resolved_audit_reader = audit_reader
        database_secret = resolved_settings.database_url
        if resolved_audit_reader is None and database_secret is not None:
            database_url = database_secret.get_secret_value().strip()
            if database_url:
                owned_database = Database(database_url)
                resolved_audit_reader = SqlAlchemyCycleAuditQueryService(
                    owned_database.sessions
                )

        runtime = AppRuntime(
            trading_engine=trading_engine,
            portfolio=portfolio,
            audit_reader=resolved_audit_reader,
            owned_database=owned_database,
        )
        app.state.runtime = runtime
        yield
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
    return app


app = create_app()
