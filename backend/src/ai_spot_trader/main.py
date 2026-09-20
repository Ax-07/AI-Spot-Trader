from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ai_spot_trader import __version__
from ai_spot_trader.api.routes.health import router as health_router
from ai_spot_trader.core.config import Settings, get_settings
from ai_spot_trader.core.runtime import AppRuntime, StoppableTradingEngine


def create_app(
    settings: Settings | None = None,
    *,
    trading_engine: StoppableTradingEngine | None = None,
) -> FastAPI:
    """Create FastAPI without starting trading or performing external I/O."""

    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runtime = AppRuntime(trading_engine=trading_engine)
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
    return app


app = create_app()
