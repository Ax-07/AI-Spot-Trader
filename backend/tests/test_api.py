import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient

from ai_spot_trader.core.config import Settings
from ai_spot_trader.core.runtime import AppRuntime
from ai_spot_trader.main import create_app
from ai_spot_trader.persistence.query import (
    AuditPage,
    AuditSortOrder,
    AuditStoreUnavailableError,
    CycleAuditDetail,
    CycleAuditSummary,
    CycleFailureView,
    DecisionAuditItem,
    ExecutionAuditItem,
    FillAuditItem,
    LatestErrorView,
    RiskAssessmentAuditItem,
)

NOW = datetime(2026, 9, 20, 17, 0, tzinfo=UTC)
CYCLE_HOLD = UUID("10000000-0000-0000-0000-000000000001")
CYCLE_REJECT = UUID("10000000-0000-0000-0000-000000000002")
CYCLE_ALLOW = UUID("10000000-0000-0000-0000-000000000003")
CYCLE_MODIFY = UUID("10000000-0000-0000-0000-000000000004")
CYCLE_FAILED = UUID("10000000-0000-0000-0000-000000000005")


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {"_env_file": None, "environment": "test"}
    values.update(overrides)
    return Settings(**values)


def _market_payload(cycle_id: UUID, offset: int) -> dict[str, object]:
    as_of = NOW + timedelta(minutes=offset)
    return {
        "cycle_id": str(cycle_id),
        "created_at": as_of.isoformat().replace("+00:00", "Z"),
        "market_state": {
            "market_state_id": str(UUID(int=300 + offset)),
            "as_of": as_of.isoformat().replace("+00:00", "Z"),
            "symbol": "BTC/EUR",
            "last_price": str(100 + offset),
            "context": None,
        },
        "portfolio_state": {
            "portfolio_state_id": str(UUID(int=400 + offset)),
            "as_of": as_of.isoformat().replace("+00:00", "Z"),
            "mode": "PAPER",
            "balances": [{"asset": "EUR", "available": "1000"}],
            "positions": [],
        },
        "aggressiveness": 5,
    }


def _decision_payload(cycle_id: UUID, action: str, offset: int) -> dict[str, object]:
    return {
        "decision_id": str(UUID(int=500 + offset)),
        "cycle_id": str(cycle_id),
        "created_at": (NOW + timedelta(minutes=offset)).isoformat().replace("+00:00", "Z"),
        "action": action,
        "symbol": "BTC/EUR",
        "proposed_quantity": None if action == "HOLD" else "1",
        "rationale": "test",
    }


def _risk_payload(
    cycle_id: UUID,
    action: str,
    risk_status: str,
    offset: int,
) -> dict[str, object]:
    requested = None if action == "HOLD" else "1"
    authorized: str | None
    if risk_status == "REJECT":
        authorized = None
    elif risk_status == "MODIFY":
        authorized = "0.5"
    else:
        authorized = requested
    return {
        "risk_assessment_id": str(UUID(int=600 + offset)),
        "cycle_id": str(cycle_id),
        "decision_id": str(UUID(int=500 + offset)),
        "assessed_at": (NOW + timedelta(minutes=offset)).isoformat().replace("+00:00", "Z"),
        "status": risk_status,
        "requested_quantity": requested,
        "authorized_quantity": authorized,
        "evaluated_limits": [],
        "reasons": ["HOLD_NO_EXECUTION"] if action == "HOLD" else [],
    }


def _summary(
    cycle_id: UUID,
    *,
    offset: int,
    action: str | None,
    risk_status: str | None,
    execution_id: UUID | None = None,
    fill_count: int = 0,
    failed: bool = False,
) -> CycleAuditSummary:
    return CycleAuditSummary(
        cycle_id=cycle_id,
        status="FAILED" if failed else "COMPLETED",
        recorded_at=NOW + timedelta(minutes=offset),
        decision_action=action,
        symbol="BTC/EUR" if action is not None else None,
        risk_status=risk_status,
        execution_id=execution_id,
        fill_count=fill_count,
        failure=(
            CycleFailureView(stage="AGENT", error_type="TimeoutError", timed_out=True)
            if failed
            else None
        ),
    )


def _detail(
    cycle_id: UUID,
    *,
    offset: int,
    action: str,
    risk_status: str,
    execution: bool = False,
) -> CycleAuditDetail:
    decision_id = UUID(int=500 + offset)
    risk_id = UUID(int=600 + offset)
    execution_id = UUID(int=700 + offset) if execution else None
    fill: FillAuditItem | None = None
    execution_payload: dict[str, object] | None = None
    portfolio_after: dict[str, object] | None = None
    if execution_id is not None:
        execution_payload = {
            "execution_id": str(execution_id),
            "cycle_id": str(cycle_id),
            "decision_id": str(decision_id),
            "risk_assessment_id": str(risk_id),
            "created_at": (NOW + timedelta(minutes=offset)).isoformat().replace("+00:00", "Z"),
            "mode": "PAPER",
            "action": action,
            "symbol": "BTC/EUR",
            "quantity": "0.5" if risk_status == "MODIFY" else "1",
        }
        fill = FillAuditItem(
            fill_id=UUID(int=800 + offset),
            execution_id=execution_id,
            market_state_id=UUID(int=300 + offset),
            filled_at=NOW + timedelta(minutes=offset),
            payload={
                "fill_id": str(UUID(int=800 + offset)),
                "execution_id": str(execution_id),
                "market_state_id": str(UUID(int=300 + offset)),
                "filled_at": (NOW + timedelta(minutes=offset)).isoformat().replace("+00:00", "Z"),
                "pricing_as_of": (NOW + timedelta(minutes=offset))
                .isoformat()
                .replace("+00:00", "Z"),
                "action": action,
                "symbol": "BTC/EUR",
                "quantity": "0.5" if risk_status == "MODIFY" else "1",
                "reference_price": "100",
                "price": "100",
                "notional": "50" if risk_status == "MODIFY" else "100",
                "fee": "0",
                "spread_cost": "0",
                "slippage_cost": "0",
            },
        )
        portfolio_after = {
            "portfolio_state_id": str(UUID(int=900 + offset)),
            "as_of": (NOW + timedelta(minutes=offset)).isoformat().replace("+00:00", "Z"),
            "mode": "PAPER",
            "balances": [{"asset": "EUR", "available": "900"}],
            "positions": [],
        }
    return CycleAuditDetail(
        cycle_id=cycle_id,
        status="COMPLETED",
        recorded_at=NOW + timedelta(minutes=offset),
        failure=None,
        market_state_id=UUID(int=300 + offset),
        portfolio_state_before_id=UUID(int=400 + offset),
        portfolio_state_after_id=(UUID(int=900 + offset) if execution else None),
        market_as_of=NOW + timedelta(minutes=offset),
        portfolio_before_as_of=NOW + timedelta(minutes=offset),
        portfolio_after_as_of=(NOW + timedelta(minutes=offset) if execution else None),
        agent_input=_market_payload(cycle_id, offset),
        decision=_decision_payload(cycle_id, action, offset),
        risk_assessment=_risk_payload(cycle_id, action, risk_status, offset),
        execution_intent=execution_payload,
        fills=() if fill is None else (fill,),
        portfolio_state_after=portfolio_after,
    )


class FakeAuditReader:
    def __init__(self) -> None:
        self.summaries = (
            _summary(CYCLE_HOLD, offset=1, action="HOLD", risk_status="ALLOW"),
            _summary(CYCLE_REJECT, offset=2, action="BUY", risk_status="REJECT"),
            _summary(
                CYCLE_ALLOW,
                offset=3,
                action="BUY",
                risk_status="ALLOW",
                execution_id=UUID(int=703),
                fill_count=1,
            ),
            _summary(
                CYCLE_MODIFY,
                offset=4,
                action="BUY",
                risk_status="MODIFY",
                execution_id=UUID(int=704),
                fill_count=1,
            ),
            _summary(
                CYCLE_FAILED,
                offset=5,
                action=None,
                risk_status=None,
                failed=True,
            ),
        )
        self.details = {
            CYCLE_HOLD: _detail(CYCLE_HOLD, offset=1, action="HOLD", risk_status="ALLOW"),
            CYCLE_REJECT: _detail(CYCLE_REJECT, offset=2, action="BUY", risk_status="REJECT"),
            CYCLE_ALLOW: _detail(
                CYCLE_ALLOW, offset=3, action="BUY", risk_status="ALLOW", execution=True
            ),
            CYCLE_MODIFY: _detail(
                CYCLE_MODIFY, offset=4, action="BUY", risk_status="MODIFY", execution=True
            ),
        }

    async def list_cycles(
        self,
        *,
        limit: int,
        offset: int,
        order: AuditSortOrder,
        status: str | None = None,
        action: str | None = None,
        risk_status: str | None = None,
    ) -> AuditPage[CycleAuditSummary]:
        values = [
            item
            for item in self.summaries
            if (status is None or item.status == status)
            and (action is None or item.decision_action == action)
            and (risk_status is None or item.risk_status == risk_status)
        ]
        values.sort(key=lambda item: (item.recorded_at, str(item.cycle_id)))
        if order is AuditSortOrder.DESC:
            values.reverse()
        total = len(values)
        return AuditPage(tuple(values[offset : offset + limit]), total, limit, offset)

    async def get_cycle(self, cycle_id: UUID) -> CycleAuditDetail | None:
        return self.details.get(cycle_id)

    async def latest_cycle(self) -> CycleAuditDetail | None:
        return self.details[CYCLE_MODIFY]

    async def list_decisions(
        self,
        *,
        limit: int,
        offset: int,
        order: AuditSortOrder,
        action: str | None = None,
        symbol: str | None = None,
    ) -> AuditPage[DecisionAuditItem]:
        values = []
        for cycle_id, detail in self.details.items():
            assert detail.decision is not None
            payload = detail.decision
            item = DecisionAuditItem(
                decision_id=UUID(str(payload["decision_id"])),
                cycle_id=cycle_id,
                created_at=datetime.fromisoformat(
                    str(payload["created_at"]).replace("Z", "+00:00")
                ),
                action=str(payload["action"]),
                symbol=str(payload["symbol"]),
                payload=payload,
            )
            if action is not None and item.action != action:
                continue
            if symbol is not None and item.symbol != symbol:
                continue
            values.append(item)
        values.sort(key=lambda item: (item.created_at, str(item.decision_id)))
        if order is AuditSortOrder.DESC:
            values.reverse()
        total = len(values)
        return AuditPage(tuple(values[offset : offset + limit]), total, limit, offset)

    async def list_risk_assessments(
        self,
        *,
        limit: int,
        offset: int,
        order: AuditSortOrder,
        status: str | None = None,
    ) -> AuditPage[RiskAssessmentAuditItem]:
        values = []
        for cycle_id, detail in self.details.items():
            assert detail.risk_assessment is not None
            payload = detail.risk_assessment
            item = RiskAssessmentAuditItem(
                risk_assessment_id=UUID(str(payload["risk_assessment_id"])),
                cycle_id=cycle_id,
                decision_id=UUID(str(payload["decision_id"])),
                assessed_at=datetime.fromisoformat(
                    str(payload["assessed_at"]).replace("Z", "+00:00")
                ),
                status=str(payload["status"]),
                payload=payload,
            )
            if status is None or item.status == status:
                values.append(item)
        values.sort(key=lambda item: (item.assessed_at, str(item.risk_assessment_id)))
        if order is AuditSortOrder.DESC:
            values.reverse()
        total = len(values)
        return AuditPage(tuple(values[offset : offset + limit]), total, limit, offset)

    async def list_executions(
        self,
        *,
        limit: int,
        offset: int,
        order: AuditSortOrder,
        action: str | None = None,
        symbol: str | None = None,
    ) -> AuditPage[ExecutionAuditItem]:
        values = []
        for cycle_id in (CYCLE_ALLOW, CYCLE_MODIFY):
            detail = self.details[cycle_id]
            assert detail.execution_intent is not None
            payload = detail.execution_intent
            item = ExecutionAuditItem(
                execution_id=UUID(str(payload["execution_id"])),
                cycle_id=cycle_id,
                decision_id=UUID(str(payload["decision_id"])),
                risk_assessment_id=UUID(str(payload["risk_assessment_id"])),
                created_at=datetime.fromisoformat(
                    str(payload["created_at"]).replace("Z", "+00:00")
                ),
                action=str(payload["action"]),
                symbol=str(payload["symbol"]),
                payload=payload,
                fills=detail.fills,
            )
            if action is not None and item.action != action:
                continue
            if symbol is not None and item.symbol != symbol:
                continue
            values.append(item)
        values.sort(key=lambda item: (item.created_at, str(item.execution_id)))
        if order is AuditSortOrder.DESC:
            values.reverse()
        total = len(values)
        return AuditPage(tuple(values[offset : offset + limit]), total, limit, offset)

    async def latest_error(self) -> LatestErrorView | None:
        return LatestErrorView(
            cycle_id=CYCLE_FAILED,
            recorded_at=NOW + timedelta(minutes=5),
            failure=CycleFailureView(
                stage="AGENT",
                error_type="SensitiveProviderError",
                timed_out=False,
            ),
        )

    async def latest_market_state(self) -> dict[str, object] | None:
        latest = self.details[CYCLE_MODIFY].agent_input
        assert latest is not None
        market = latest["market_state"]
        assert isinstance(market, dict)
        return dict(market)


class EmptyAuditReader(FakeAuditReader):
    async def list_cycles(
        self,
        *,
        limit: int,
        offset: int,
        order: AuditSortOrder,
        status: str | None = None,
        action: str | None = None,
        risk_status: str | None = None,
    ) -> AuditPage[CycleAuditSummary]:
        return AuditPage((), 0, limit, offset)

    async def latest_cycle(self) -> CycleAuditDetail | None:
        return None

    async def get_cycle(self, cycle_id: UUID) -> CycleAuditDetail | None:
        return None

    async def latest_error(self) -> LatestErrorView | None:
        return None

    async def latest_market_state(self) -> dict[str, object] | None:
        return None


class UnavailableAuditReader(FakeAuditReader):
    async def list_cycles(
        self,
        *,
        limit: int,
        offset: int,
        order: AuditSortOrder,
        status: str | None = None,
        action: str | None = None,
        risk_status: str | None = None,
    ) -> AuditPage[CycleAuditSummary]:
        raise AuditStoreUnavailableError("postgresql://secret-user:secret-password@host/db")


class FakePortfolio:
    def snapshot(self) -> dict[str, object]:
        return {
            "portfolio_state_id": "40000000-0000-0000-0000-000000000004",
            "as_of": "2026-09-20T17:00:00Z",
            "mode": "PAPER",
            "balances": [{"asset": "EUR", "available": "1000.50"}],
            "positions": [{"asset": "BTC", "quantity": "0.25", "available": "0.25"}],
        }


@dataclass
class FakeCycleFailure:
    stage: str
    error_type: str
    timed_out: bool


@dataclass
class FakeCycleResult:
    cycle_id: UUID
    status: str
    failure: FakeCycleFailure | None = None


class FakeEngine:
    def __init__(self) -> None:
        self.is_running = False
        self.start_calls = 0
        self.stop_calls = 0
        self.last_result: FakeCycleResult | None = FakeCycleResult(
            cycle_id=CYCLE_ALLOW,
            status="COMPLETED",
        )
        self.last_unexpected_error_type: str | None = None

    async def start(self) -> None:
        self.start_calls += 1
        self.is_running = True

    async def stop(self) -> None:
        self.stop_calls += 1
        self.is_running = False


class FakeCloseable:
    def __init__(self) -> None:
        self.close_calls = 0

    async def close(self) -> None:
        self.close_calls += 1


def test_engine_state_start_stop_and_no_automatic_startup() -> None:
    engine = FakeEngine()
    app = create_app(_settings(), trading_engine=engine)
    with TestClient(app) as client:
        assert engine.start_calls == 0
        initial = client.get("/api/v1/engine")
        assert initial.status_code == 200
        assert initial.json()["status"] == "STOPPED"
        assert initial.json()["last_cycle_id"] == str(CYCLE_ALLOW)

        started = client.post("/api/v1/engine/start")
        assert started.status_code == 200
        assert started.json()["status"] == "RUNNING"
        assert engine.start_calls == 1

        duplicate = client.post("/api/v1/engine/start")
        assert duplicate.status_code == 409

        stopped = client.post("/api/v1/engine/stop")
        assert stopped.status_code == 200
        assert stopped.json()["status"] == "STOPPED"
    assert engine.start_calls == 1


def test_unconfigured_engine_and_portfolio_are_explicit() -> None:
    with TestClient(create_app(_settings())) as client:
        engine = client.get("/api/v1/engine")
        assert engine.status_code == 200
        assert engine.json() == {
            "configured": False,
            "status": "UNAVAILABLE",
            "last_cycle_id": None,
            "last_cycle_status": None,
            "last_cycle_failure": None,
            "last_unexpected_error_type": None,
        }
        assert client.post("/api/v1/engine/start").status_code == 503
        assert client.get("/api/v1/portfolio").status_code == 503


def test_current_paper_portfolio_is_exposed_without_execution() -> None:
    with TestClient(create_app(_settings(), portfolio=FakePortfolio())) as client:
        response = client.get("/api/v1/portfolio")
    assert response.status_code == 200
    body = response.json()
    assert body["portfolio_state_id"] == "40000000-0000-0000-0000-000000000004"
    assert body["mode"] == "PAPER"
    assert body["balances"][0] == {"asset": "EUR", "available": "1000.50"}
    assert body["positions"][0]["asset"] == "BTC"


def test_empty_history_and_missing_resources() -> None:
    with TestClient(create_app(_settings(), audit_reader=EmptyAuditReader())) as client:
        history = client.get("/api/v1/cycles")
        assert history.status_code == 200
        assert history.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}
        assert client.get("/api/v1/cycles/latest").status_code == 404
        assert client.get(f"/api/v1/cycles/{CYCLE_HOLD}").status_code == 404
        assert client.get("/api/v1/errors/latest").status_code == 404
        assert client.get("/api/v1/market/latest").status_code == 404


def test_history_covers_hold_reject_allow_modify_and_failed_cycle() -> None:
    with TestClient(create_app(_settings(), audit_reader=FakeAuditReader())) as client:
        history = client.get("/api/v1/cycles?order=asc")
    assert history.status_code == 200
    items = history.json()["items"]
    assert [item["cycle_id"] for item in items] == [
        str(CYCLE_HOLD),
        str(CYCLE_REJECT),
        str(CYCLE_ALLOW),
        str(CYCLE_MODIFY),
        str(CYCLE_FAILED),
    ]
    assert items[0]["decision_action"] == "HOLD"
    assert items[0]["risk_status"] == "ALLOW"
    assert items[0]["execution_id"] is None
    assert items[1]["risk_status"] == "REJECT"
    assert items[1]["execution_id"] is None
    assert items[2]["risk_status"] == "ALLOW" and items[2]["fill_count"] == 1
    assert items[3]["risk_status"] == "MODIFY" and items[3]["fill_count"] == 1
    assert items[4]["status"] == "FAILED"
    assert items[4]["failure"] == {
        "stage": "AGENT",
        "error_type": "TimeoutError",
        "timed_out": True,
    }


def test_cycle_detail_preserves_ids_timestamps_intent_and_fills() -> None:
    with TestClient(create_app(_settings(), audit_reader=FakeAuditReader())) as client:
        response = client.get(f"/api/v1/cycles/{CYCLE_MODIFY}")
    assert response.status_code == 200
    body = response.json()
    assert body["cycle_id"] == str(CYCLE_MODIFY)
    assert body["recorded_at"] == "2026-09-20T17:04:00Z"
    assert body["market_state_id"] == str(UUID(int=304))
    assert body["decision"]["cycle_id"] == str(CYCLE_MODIFY)
    assert body["risk_assessment"]["status"] == "MODIFY"
    assert body["execution_intent"]["execution_id"] == str(UUID(int=704))
    assert body["fills"][0]["fill_id"] == str(UUID(int=804))
    assert body["portfolio_state_after_id"] == str(UUID(int=904))


def test_recent_decisions_risk_executions_and_market() -> None:
    with TestClient(create_app(_settings(), audit_reader=FakeAuditReader())) as client:
        decisions = client.get("/api/v1/decisions?action=HOLD")
        risk = client.get("/api/v1/risk-assessments?status=MODIFY")
        executions = client.get("/api/v1/executions?action=BUY")
        market = client.get("/api/v1/market/latest")
    assert decisions.status_code == 200 and decisions.json()["total"] == 1
    assert decisions.json()["items"][0]["action"] == "HOLD"
    assert risk.status_code == 200 and risk.json()["total"] == 1
    assert risk.json()["items"][0]["status"] == "MODIFY"
    assert executions.status_code == 200 and executions.json()["total"] == 2
    assert executions.json()["items"][0]["fills"]
    assert market.status_code == 200
    assert market.json()["symbol"] == "BTC/EUR"
    assert market.json()["market_state_id"] == str(UUID(int=304))


def test_pagination_filters_and_validation_are_deterministic() -> None:
    with TestClient(create_app(_settings(), audit_reader=FakeAuditReader())) as client:
        page = client.get("/api/v1/cycles?order=desc&limit=2&offset=1&status=COMPLETED")
        invalid_limit = client.get("/api/v1/cycles?limit=0")
        invalid_status = client.get("/api/v1/cycles?status=UNKNOWN")
        invalid_execution_action = client.get("/api/v1/executions?action=HOLD")
    assert page.status_code == 200
    assert page.json()["total"] == 4
    assert [item["cycle_id"] for item in page.json()["items"]] == [
        str(CYCLE_ALLOW),
        str(CYCLE_REJECT),
    ]
    assert invalid_limit.status_code == 422
    assert invalid_status.status_code == 422
    assert invalid_execution_action.status_code == 422


def test_latest_error_is_sanitized_and_never_exposes_raw_sensitive_message() -> None:
    with TestClient(create_app(_settings(), audit_reader=FakeAuditReader())) as client:
        response = client.get("/api/v1/errors/latest")
    assert response.status_code == 200
    body = response.json()
    assert body["failure"] == {
        "stage": "AGENT",
        "error_type": "SensitiveProviderError",
        "timed_out": False,
    }
    serialized = response.text.lower()
    assert "password" not in serialized
    assert "api key" not in serialized
    assert "raw message" not in serialized


def test_unavailable_database_maps_to_generic_503_without_secret_leak() -> None:
    with TestClient(create_app(_settings(), audit_reader=UnavailableAuditReader())) as client:
        response = client.get("/api/v1/cycles")
    assert response.status_code == 503
    assert response.json() == {"detail": "audit store is unavailable"}
    assert "secret-password" not in response.text


def test_unconfigured_audit_store_is_explicit() -> None:
    with TestClient(create_app(_settings())) as client:
        response = client.get("/api/v1/cycles")
    assert response.status_code == 503
    assert response.json() == {"detail": "audit store is not configured"}


def test_runtime_closes_owned_database_and_stops_engine() -> None:
    engine = FakeEngine()
    engine.is_running = True
    database = FakeCloseable()
    runtime = AppRuntime(trading_engine=engine, owned_database=database)

    asyncio.run(runtime.close())

    assert runtime.shutdown_requested.is_set()
    assert engine.stop_calls == 1
    assert database.close_calls == 1
