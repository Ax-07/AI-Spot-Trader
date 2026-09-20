from typing import Any

from fastapi.testclient import TestClient

from ai_spot_trader.analytics.paper import PaperAnalyticsReport, build_paper_analytics_report
from ai_spot_trader.core.config import Settings
from ai_spot_trader.main import create_app
from ai_spot_trader.persistence.query import AuditDataIntegrityError, AuditStoreUnavailableError


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {"_env_file": None, "environment": "test"}
    values.update(overrides)
    return Settings(**values)


class EmptyAnalyticsReader:
    async def paper_analytics(self) -> PaperAnalyticsReport:
        return build_paper_analytics_report(())


class UnavailableAnalyticsReader:
    async def paper_analytics(self) -> PaperAnalyticsReport:
        raise AuditStoreUnavailableError("audit store unavailable")


class InvalidAnalyticsReader:
    async def paper_analytics(self) -> PaperAnalyticsReport:
        raise AuditDataIntegrityError("invalid durable analytics facts")


def test_empty_analytics_response_is_deterministic() -> None:
    with TestClient(
        create_app(_settings(), analytics_reader=EmptyAnalyticsReader())
    ) as client:
        response = client.get("/api/v1/analytics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["calculation_version"] == "paper-analytics-v1"
    assert payload["timezone"] == "UTC"
    assert payload["summary"]["initial_equity"] is None
    assert payload["summary"]["net_pnl"] == "0"
    assert payload["summary"]["trade_count"] == 0
    assert payload["points"] == []
    assert payload["daily"] == []


def test_analytics_endpoint_requires_configured_reader() -> None:
    with TestClient(create_app(_settings())) as client:
        response = client.get("/api/v1/analytics")

    assert response.status_code == 503
    assert response.json() == {"detail": "analytics store is not configured"}


def test_analytics_endpoint_sanitizes_store_and_integrity_failures() -> None:
    with TestClient(
        create_app(_settings(), analytics_reader=UnavailableAnalyticsReader())
    ) as client:
        unavailable = client.get("/api/v1/analytics")
    with TestClient(
        create_app(_settings(), analytics_reader=InvalidAnalyticsReader())
    ) as client:
        invalid = client.get("/api/v1/analytics")

    assert unavailable.status_code == 503
    assert unavailable.json() == {"detail": "analytics store is unavailable"}
    assert invalid.status_code == 500
    assert invalid.json() == {"detail": "analytics data is unavailable"}
