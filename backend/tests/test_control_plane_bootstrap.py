from fastapi.testclient import TestClient
from pydantic import SecretStr

from ai_spot_trader.core.config import Settings
from ai_spot_trader.main import create_app


def test_backend_can_boot_with_database_infrastructure_and_no_active_campaign() -> None:
    app = create_app(
        Settings(
            _env_file=None,
            environment="test",
            database_url=SecretStr("sqlite+aiosqlite:///:memory:"),
        ),
        compose_paper=True,
    )

    with TestClient(app) as client:
        engine = client.get("/api/v1/engine")
        active = client.get("/api/v1/campaigns/active")

    assert engine.status_code == 200
    assert engine.json()["status"] == "UNAVAILABLE"
    assert active.status_code == 404
