from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient

from ai_spot_trader.analytics.paper import PaperAnalyticsReport, build_paper_analytics_report
from ai_spot_trader.core.config import Settings
from ai_spot_trader.main import create_app
from ai_spot_trader.persistence.runs import (
    PaperRunPage,
    PaperRunSortOrder,
    PaperRunView,
)

RUN_A = UUID("aaaaaaaa-0000-0000-0000-000000000001")
RUN_B = UUID("bbbbbbbb-0000-0000-0000-000000000002")
NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


class FakePaperRunReader:
    def __init__(self) -> None:
        self.runs = (
            PaperRunView(RUN_A, NOW, NOW + timedelta(hours=1), "SPOT", "BTC/EUR"),
            PaperRunView(RUN_B, NOW + timedelta(hours=2), None, "PERPETUAL", "BTC/USD"),
        )

    async def list_runs(
        self,
        *,
        limit: int,
        offset: int,
        order: PaperRunSortOrder,
    ) -> PaperRunPage:
        items = list(self.runs)
        if order is PaperRunSortOrder.DESC:
            items.reverse()
        return PaperRunPage(tuple(items[offset : offset + limit]), len(items), limit, offset)

    async def get_run(self, paper_run_id: UUID) -> PaperRunView | None:
        return next((item for item in self.runs if item.paper_run_id == paper_run_id), None)


class FakeRunScopedAnalyticsReader:
    def __init__(self) -> None:
        self.requested: list[UUID] = []

    async def paper_analytics(self) -> PaperAnalyticsReport:
        return build_paper_analytics_report(())

    async def paper_analytics_for_run(self, paper_run_id: UUID) -> PaperAnalyticsReport:
        self.requested.append(paper_run_id)
        return build_paper_analytics_report(())


def test_run_listing_and_explicit_analytics_selection() -> None:
    analytics = FakeRunScopedAnalyticsReader()
    app = create_app(
        Settings(_env_file=None, environment="test"),
        analytics_reader=analytics,
        paper_run_reader=FakePaperRunReader(),
    )

    with TestClient(app) as client:
        runs = client.get("/api/v1/paper-runs?order=asc")
        missing_default = client.get("/api/v1/analytics")
        selected = client.get(f"/api/v1/analytics?paper_run_id={RUN_A}")
        current = client.get("/api/v1/paper-runs/current")

    assert runs.status_code == 200
    assert [item["paper_run_id"] for item in runs.json()["items"]] == [
        str(RUN_A),
        str(RUN_B),
    ]
    assert runs.json()["items"][0]["market_type"] == "SPOT"
    assert runs.json()["items"][1]["market_type"] == "PERPETUAL"

    assert missing_default.status_code == 400
    assert selected.status_code == 200
    assert selected.json()["paper_run_id"] == str(RUN_A)
    assert analytics.requested == [RUN_A]
    assert current.status_code == 404


class FakePaperRunLifecycle:
    def __init__(self, current_run_id: UUID) -> None:
        self.current_run_id: UUID | None = current_run_id

    async def initialize(self) -> PaperRunView:
        raise AssertionError("test injects lifecycle after app startup")

    async def close(self) -> None:
        self.current_run_id = None


def test_current_run_is_the_default_for_analytics_and_run_endpoint() -> None:
    analytics = FakeRunScopedAnalyticsReader()
    app = create_app(
        Settings(_env_file=None, environment="test"),
        analytics_reader=analytics,
        paper_run_reader=FakePaperRunReader(),
    )

    with TestClient(app) as client:
        app.state.runtime.paper_run_lifecycle = FakePaperRunLifecycle(RUN_B)
        current = client.get("/api/v1/paper-runs/current")
        default_analytics = client.get("/api/v1/analytics")
        app.state.runtime.paper_run_lifecycle = None

    assert current.status_code == 200
    assert current.json()["paper_run_id"] == str(RUN_B)
    assert current.json()["is_current"] is True
    assert default_analytics.status_code == 200
    assert default_analytics.json()["paper_run_id"] == str(RUN_B)
    assert analytics.requested == [RUN_B]
