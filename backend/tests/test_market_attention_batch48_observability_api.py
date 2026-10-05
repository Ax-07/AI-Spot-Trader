from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_spot_trader.api.routes.market_attention import router as market_attention_router

NOW = datetime(2026, 10, 5, 10, 0, tzinfo=UTC)


class Reader:
    latest = SimpleNamespace()

    def history(self, *, limit: int = 24):
        ranking = SimpleNamespace(
            score=2,
            components=(
                SimpleNamespace(
                    name="OPEN_INTEREST",
                    contribution=1,
                    series=(SimpleNamespace(series="open-interest", status="AVAILABLE"),),
                ),
                SimpleNamespace(
                    name="FUNDING",
                    contribution=1,
                    series=(SimpleNamespace(series="funding", status="AVAILABLE"),),
                ),
                SimpleNamespace(
                    name="LIQUIDATION_VOLUME",
                    contribution=0,
                    series=(SimpleNamespace(series="liquidation-volume", status="STALE"),),
                ),
                SimpleNamespace(
                    name="ORDER_FLOW",
                    contribution=0,
                    series=(
                        SimpleNamespace(series="cvd", status="INSUFFICIENT_HISTORY"),
                        SimpleNamespace(series="aggressor-differential", status="TECHNICAL_ERROR"),
                    ),
                ),
            ),
            applied_to_ranking=True,
            rank_change=0,
            order_flow_deduplicated=False,
            order_flow_conflict=False,
        )
        candidate = SimpleNamespace(
            market=SimpleNamespace(symbol="BTC/USD", market_type="PERPETUAL"),
            analytics_ranking=ranking,
        )
        overview = SimpleNamespace(
            observed_at=NOW,
            market_scope="PERPETUAL",
            shortlist=(candidate,),
            perpetual_analytics_coverage=SimpleNamespace(status="ROTATING"),
        )
        return (overview,)[-limit:]


def _client(service) -> TestClient:
    app = FastAPI()
    app.state.market_attention = service
    app.include_router(market_attention_router)
    return TestClient(app)


def test_observability_endpoint_is_additive_read_only_and_bounded() -> None:
    with _client(Reader()) as client:
        response = client.get("/api/v1/market-attention/observability?limit=96")
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "analytics-ranking-observability-v1"
    assert payload["requested_history_limit"] == 96
    assert payload["snapshots_observed"] == 1
    assert payload["score_distribution"]["score_2"] == 1
    assert payload["reranking_applicable_snapshots"] == 1
    assert payload["effective_reranking_snapshots"] == 0
    assert payload["analytics_applicable_but_no_rank_change_snapshots"] == 1


def test_observability_endpoint_without_radar_returns_empty_diagnostic() -> None:
    with _client(None) as client:
        response = client.get("/api/v1/market-attention/observability")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source_snapshot_count"] == 0
    assert payload["snapshots_observed"] == 0
    assert payload["market_coverage"] == []


def test_observability_limit_is_validated_by_fastapi() -> None:
    with _client(Reader()) as client:
        assert client.get("/api/v1/market-attention/observability?limit=0").status_code == 422
        assert client.get("/api/v1/market-attention/observability?limit=97").status_code == 422
