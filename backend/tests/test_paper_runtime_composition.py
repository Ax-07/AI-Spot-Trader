import asyncio
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

import ai_spot_trader.composition as composition_module
from ai_spot_trader.composition import build_paper_runtime
from ai_spot_trader.core.config import (
    PaperRunConfiguration,
    PaperRuntimeConfigurationError,
    Settings,
)
from ai_spot_trader.core.runtime import AppRuntime, TradingEngineAlreadyRunningError
from ai_spot_trader.domain.enums import LLMModel
from ai_spot_trader.main import create_app
from ai_spot_trader.persistence.audit import (
    AuditedTradingCycleRunner,
    CycleAuditUnavailableError,
)
from ai_spot_trader.trading.engine import (
    TradingCycleFailure,
    TradingCycleResult,
    TradingCycleStage,
    TradingCycleStatus,
)


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "_env_file": None,
        "environment": "test",
        "paper_symbol": "BTC/EUR",
        "paper_initial_capital": Decimal("1000"),
        "paper_settlement_asset": "EUR",
        "trading_cadence_seconds": 30.0,
        "aggressiveness": 4,
        "cycle_market_timeout_seconds": 5.0,
        "cycle_agent_timeout_seconds": 30.0,
        "cycle_broker_timeout_seconds": 5.0,
        "risk_max_order_notional": Decimal("100"),
        "risk_allowed_pairs": frozenset({"BTC/EUR"}),
        "risk_allow_quantity_reduction": True,
        "paper_fee_rate": Decimal("0.0026"),
        "paper_spread_bps": Decimal("5"),
        "paper_slippage_bps": Decimal("3"),
        "database_url": SecretStr(
            "postgresql+asyncpg://test-user:test-password@localhost:5432/ai_spot_trader_test"
        ),
        "openai_api_key": SecretStr("test-only-openai-key"),
        "llm_model": LLMModel.SOL,
    }
    values.update(overrides)
    return Settings(**values)


def _minimal_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {"_env_file": None, "environment": "test"}
    values.update(overrides)
    return Settings(**values)


def test_settings_env_file_is_backend_local_and_cwd_independent() -> None:
    env_file = Path(str(Settings.model_config["env_file"]))

    assert env_file.name == ".env"
    assert env_file.parent.name == "backend"


def test_paper_run_configuration_fails_closed_when_required_values_are_missing() -> None:
    settings = _minimal_settings()

    with pytest.raises(PaperRuntimeConfigurationError) as error:
        PaperRunConfiguration.from_settings(settings)

    message = str(error.value)
    assert "paper_symbol" in message
    assert "paper_initial_capital" in message
    assert "database_url" in message
    assert "openai_api_key" in message


def test_composed_app_startup_fails_closed_without_real_run_configuration() -> None:
    app = create_app(_minimal_settings(), compose_paper=True)

    with pytest.raises(PaperRuntimeConfigurationError), TestClient(app):
        pass


def test_non_paper_execution_mode_remains_unrepresentable() -> None:
    with pytest.raises(ValidationError):
        _minimal_settings(execution_mode="LIVE")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"paper_settlement_asset": "USD"}, "quote asset"),
        ({"risk_allowed_pairs": frozenset({"ETH/EUR"})}, "risk_allowed_pairs"),
        (
            {"database_url": SecretStr("sqlite+aiosqlite:///:memory:")},
            "PostgreSQL",
        ),
    ],
)
def test_paper_run_configuration_rejects_inconsistent_runtime_values(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(PaperRuntimeConfigurationError, match=message):
        PaperRunConfiguration.from_settings(_settings(**overrides))


def test_complete_paper_composition_shares_canonical_runtime_objects() -> None:
    composition = build_paper_runtime(_settings())
    try:
        assert composition.runtime.trading_engine is composition.trading_engine
        assert composition.runtime.portfolio is composition.portfolio
        assert composition.runtime.audit_reader is not None
        assert composition.runtime.analytics_reader is not None

        assert composition.risk_engine._cost_model is composition.cost_model
        assert composition.broker._cost_model is composition.cost_model
        assert composition.audited_runner._delegate is composition.cycle_runner
        assert cast(object, composition.trading_engine._runner) is composition.audited_runner

        assert composition.agent._model is LLMModel.SOL
        assert composition.chat_service.model is LLMModel.SOL

        portfolio = composition.portfolio.snapshot()
        assert tuple((item.asset, item.available) for item in portfolio.balances) == (
            ("EUR", Decimal("1000")),
        )
        assert portfolio.positions == ()
    finally:
        asyncio.run(composition.runtime.close())


def test_runtime_composition_imports_only_public_kraken_market_data() -> None:
    source_file = composition_module.__file__
    assert source_file is not None
    source = Path(source_file).read_text(encoding="utf-8")

    assert "build_kraken_market_data_source" in source
    assert "KrakenPrivate" not in source
    assert "kraken_api_key" not in source.lower()
    assert "withdraw" not in source.lower()


@dataclass
class _FakeFailure:
    stage: str
    error_type: str
    timed_out: bool = False


@dataclass
class _FakeResult:
    cycle_id: UUID
    status: str
    failure: _FakeFailure | None = None


class _FakeSingleCycleEngine:
    def __init__(self) -> None:
        self.is_running = False
        self.last_result: _FakeResult | None = None
        self.last_unexpected_error_type: str | None = None
        self.start_calls = 0
        self.stop_calls = 0
        self.run_calls = 0
        self.error: Exception | None = None

    async def start(self) -> None:
        self.start_calls += 1
        self.is_running = True

    async def stop(self) -> None:
        self.stop_calls += 1
        self.is_running = False

    async def run_cycle(self) -> _FakeResult:
        self.run_calls += 1
        if self.error is not None:
            raise self.error
        result = _FakeResult(cycle_id=uuid4(), status="COMPLETED")
        self.last_result = result
        return result


def test_http_run_cycle_uses_the_injected_canonical_engine_exactly_once() -> None:
    engine = _FakeSingleCycleEngine()
    app = create_app(
        _minimal_settings(),
        trading_engine=engine,
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/engine/run-cycle")

    assert response.status_code == 200
    assert engine.run_calls == 1
    assert engine.start_calls == 0
    assert response.json()["last_cycle_status"] == "COMPLETED"


def test_http_run_cycle_refuses_while_autonomous_loop_is_active() -> None:
    engine = _FakeSingleCycleEngine()
    engine.is_running = True
    app = create_app(
        _minimal_settings(),
        trading_engine=engine,
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/engine/run-cycle")

    assert response.status_code == 409
    assert engine.run_calls == 0


def test_http_run_cycle_sanitizes_audit_or_runner_exceptions() -> None:
    engine = _FakeSingleCycleEngine()
    engine.error = RuntimeError("postgresql://secret-user:secret-password@host/db")
    app = create_app(
        _minimal_settings(),
        trading_engine=engine,
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/engine/run-cycle")

    assert response.status_code == 503
    assert "secret-password" not in response.text
    assert response.json()["detail"] == (
        "trading cycle failed before durable canonical completion"
    )


def test_runtime_serializes_single_cycle_and_start_commands() -> None:
    class BlockingEngine(_FakeSingleCycleEngine):
        def __init__(self) -> None:
            super().__init__()
            self.entered = asyncio.Event()
            self.release = asyncio.Event()

        async def run_cycle(self) -> _FakeResult:
            self.run_calls += 1
            self.entered.set()
            await self.release.wait()
            result = _FakeResult(cycle_id=uuid4(), status="COMPLETED")
            self.last_result = result
            return result

    async def scenario() -> None:
        engine = BlockingEngine()
        runtime = AppRuntime(trading_engine=engine)
        cycle_task = asyncio.create_task(runtime.run_engine_cycle_once())
        await engine.entered.wait()
        start_task = asyncio.create_task(runtime.start_engine())
        await asyncio.sleep(0)
        assert engine.start_calls == 0
        engine.release.set()
        await cycle_task
        await start_task
        assert engine.run_calls == 1
        assert engine.start_calls == 1
        await runtime.close()

    asyncio.run(scenario())


def test_runtime_rejects_manual_cycle_when_engine_is_running() -> None:
    async def scenario() -> None:
        engine = _FakeSingleCycleEngine()
        engine.is_running = True
        runtime = AppRuntime(trading_engine=engine)
        with pytest.raises(TradingEngineAlreadyRunningError):
            await runtime.run_engine_cycle_once()
        assert engine.run_calls == 0

    asyncio.run(scenario())


def test_audited_runner_latches_closed_after_first_persistence_failure() -> None:
    result = TradingCycleResult(
        cycle_id=uuid4(),
        status=TradingCycleStatus.FAILED,
        failure=TradingCycleFailure(
            stage=TradingCycleStage.MARKET,
            error_type="TestFailure",
        ),
    )

    class Delegate:
        def __init__(self) -> None:
            self.calls = 0

        async def run_cycle(self) -> TradingCycleResult:
            self.calls += 1
            return result

    class FailingWriter:
        def __init__(self) -> None:
            self.preflight_calls = 0
            self.calls = 0

        async def ensure_available(self) -> None:
            self.preflight_calls += 1

        async def record(self, value: TradingCycleResult) -> bool:
            self.calls += 1
            assert value is result
            raise RuntimeError("audit unavailable")

    async def scenario() -> None:
        delegate = Delegate()
        writer = FailingWriter()
        runner = AuditedTradingCycleRunner(delegate=delegate, audit_writer=writer)

        with pytest.raises(RuntimeError, match="audit unavailable"):
            await runner.run_cycle()
        with pytest.raises(CycleAuditUnavailableError):
            await runner.run_cycle()

        assert delegate.calls == 1
        assert writer.preflight_calls == 1
        assert writer.calls == 1

    asyncio.run(scenario())


def test_audit_preflight_failure_blocks_delegate_before_market_agent_risk_broker() -> None:
    class Delegate:
        def __init__(self) -> None:
            self.calls = 0

        async def run_cycle(self) -> TradingCycleResult:
            self.calls += 1
            raise AssertionError("delegate must not run when audit preflight fails")

    class UnavailableWriter:
        def __init__(self) -> None:
            self.preflight_calls = 0
            self.record_calls = 0

        async def ensure_available(self) -> None:
            self.preflight_calls += 1
            raise RuntimeError("database unavailable")

        async def record(self, value: TradingCycleResult) -> bool:
            self.record_calls += 1
            return True

    async def scenario() -> None:
        delegate = Delegate()
        writer = UnavailableWriter()
        runner = AuditedTradingCycleRunner(delegate=delegate, audit_writer=writer)

        with pytest.raises(RuntimeError, match="database unavailable"):
            await runner.run_cycle()
        with pytest.raises(CycleAuditUnavailableError):
            await runner.run_cycle()

        assert delegate.calls == 0
        assert writer.preflight_calls == 1
        assert writer.record_calls == 0

    asyncio.run(scenario())


def test_runtime_close_stops_engine_and_closes_network_resource_before_database() -> None:
    events: list[str] = []

    class Engine(_FakeSingleCycleEngine):
        async def stop(self) -> None:
            events.append("engine")
            await super().stop()

    class NetworkResource:
        async def aclose(self) -> None:
            events.append("network")

    class DatabaseResource:
        async def close(self) -> None:
            events.append("database")

    async def scenario() -> None:
        runtime = AppRuntime(
            trading_engine=Engine(),
            owned_resources=(NetworkResource(),),
            owned_database=DatabaseResource(),
        )
        await runtime.close()

    asyncio.run(scenario())
    assert events == ["engine", "network", "database"]
