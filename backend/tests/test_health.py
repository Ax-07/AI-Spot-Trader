from typing import Any

from fastapi.testclient import TestClient

from ai_spot_trader.core.config import Settings
from ai_spot_trader.main import create_app


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {"_env_file": None}
    values.update(overrides)
    return Settings(**values)


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
