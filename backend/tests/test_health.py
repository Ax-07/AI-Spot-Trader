import asyncio
from typing import Any

from fastapi.testclient import TestClient

from ai_spot_trader.core.config import Settings
from ai_spot_trader.main import create_app


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {"_env_file": None}
    values.update(overrides)
    return Settings(**values)


class FakeTradingEngine:
    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0
        self.is_running = False
        self.last_result = None
        self.last_unexpected_error_type = None
        self.stopped = asyncio.Event()

    async def start(self) -> None:
        self.start_calls += 1
        self.is_running = True

    async def stop(self) -> None:
        self.stop_calls += 1
        self.is_running = False
        self.stopped.set()


def test_health_endpoint() -> None:
    settings = _settings(environment="test")

    with TestClient(create_app(settings)) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "AI Spot Trader",
        "environment": "test",
    }


def test_lifespan_signals_async_runtime_shutdown() -> None:
    settings = _settings(environment="test")
    app = create_app(settings)

    with TestClient(app):
        runtime = app.state.runtime
        assert not runtime.shutdown_requested.is_set()

    assert runtime.shutdown_requested.is_set()


def test_lifespan_stops_injected_trading_engine_without_starting_it() -> None:
    settings = _settings(environment="test")
    engine = FakeTradingEngine()
    app = create_app(settings, trading_engine=engine)

    with TestClient(app):
        assert engine.start_calls == 0
        assert engine.stop_calls == 0

    assert engine.start_calls == 0
    assert engine.stop_calls == 1
    assert engine.stopped.is_set()
