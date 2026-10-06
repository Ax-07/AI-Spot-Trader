import asyncio
import hashlib
import json
from decimal import Decimal

import pytest
from pydantic import SecretStr, ValidationError

import ai_spot_trader.agent.client_factory as client_factory_module
from ai_spot_trader.agent.client_factory import (
    build_structured_decision_client,
    resolve_llm_configuration,
)
from ai_spot_trader.agent.ollama_client import OllamaStructuredDecisionClient
from ai_spot_trader.agent.openai_client import OpenAIResponsesClient
from ai_spot_trader.api.session_schemas import SessionCreateRequest, SessionUpdateRequest
from ai_spot_trader.control_plane import CampaignConfiguration
from ai_spot_trader.core.config import PaperRuntimeConfigurationError, Settings
from ai_spot_trader.domain.enums import LLMModel, LLMProviderKind, MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.persistence.control_plane import SqlAlchemyControlPlaneStore
from ai_spot_trader.persistence.db import Database


def _settings(
    *,
    provider: LLMProviderKind,
    openai_key: str | None = "test-openai-key",
    ollama_model: str = "runtime-local:9b",
    ollama_timeout_seconds: float = 60.0,
) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        llm_provider=provider,
        openai_api_key=SecretStr(openai_key) if openai_key is not None else None,
        ollama_model=ollama_model,
        ollama_timeout_seconds=ollama_timeout_seconds,
    )


def _config(
    *,
    provider: LLMProviderKind | None = None,
    llm_model: LLMModel = LLMModel.LUNA,
    ollama_model: str | None = None,
    ollama_timeout_seconds: float | None = None,
    agent_timeout_seconds: float = 90.0,
) -> CampaignConfiguration:
    return CampaignConfiguration(
        llm_model=llm_model,
        llm_provider=provider,
        ollama_model=ollama_model,
        ollama_timeout_seconds=ollama_timeout_seconds,
        aggressiveness=5,
        trading_cadence_seconds=30.0,
        paper_initial_capital=Decimal("1000"),
        paper_settlement_asset="USD",
        paper_executable_markets=(
            ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),
        ),
        paper_fee_rate=Decimal("0.001"),
        paper_spread_bps=Decimal("2"),
        paper_slippage_bps=Decimal("2"),
        risk_max_order_notional=Decimal("100"),
        risk_allowed_pairs=("BTC/USD",),
        risk_allow_quantity_reduction=True,
        cycle_market_timeout_seconds=20.0,
        cycle_agent_timeout_seconds=agent_timeout_seconds,
        cycle_broker_timeout_seconds=5.0,
    )


def _ollama_config(**overrides: object) -> CampaignConfiguration:
    values: dict[str, object] = {
        "provider": LLMProviderKind.OLLAMA,
        "ollama_model": "qwen3.5:9b",
        "ollama_timeout_seconds": 60.0,
        "agent_timeout_seconds": 90.0,
    }
    values.update(overrides)
    return _config(**values)  # type: ignore[arg-type]


def test_new_openai_campaign_persists_provider() -> None:
    config = _config(provider=LLMProviderKind.OPENAI, llm_model=LLMModel.SOL)
    payload = config.canonical_payload()
    assert payload["llm_provider"] == "OPENAI"
    assert payload["llm_model"] == "gpt-5.6-sol"
    assert "ollama_model" not in payload
    assert "ollama_timeout_seconds" not in payload


def test_new_ollama_campaign_persists_provider_model_and_timeout() -> None:
    config = _ollama_config(ollama_model="  qwen3.5:9b  ", ollama_timeout_seconds=55.0)
    payload = config.canonical_payload()
    assert payload["llm_provider"] == "OLLAMA"
    assert payload["ollama_model"] == "qwen3.5:9b"
    assert payload["ollama_timeout_seconds"] == 55.0


def test_campaign_configuration_contains_no_secret_or_base_url_fields() -> None:
    fields = set(CampaignConfiguration.model_fields)
    assert "openai_api_key" not in fields
    assert "kraken_api_key" not in fields
    assert "ollama_base_url" not in fields
    assert "openai_base_url" not in fields


def test_legacy_campaign_keeps_51_2_fields_absent_and_digest_stable() -> None:
    legacy = _config()
    payload = legacy.canonical_payload()
    assert "llm_provider" not in payload
    assert "ollama_model" not in payload
    assert "ollama_timeout_seconds" not in payload

    expected = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    loaded = CampaignConfiguration.model_validate(payload)
    assert loaded.canonical_payload() == payload
    assert loaded.digest == expected == legacy.digest


def test_new_session_requires_explicit_provider_but_legacy_update_can_preserve_absence() -> None:
    legacy = _config()
    with pytest.raises(ValidationError, match="explicit llm_provider"):
        SessionCreateRequest(
            name="Legacy-shaped new session",
            instructions="test",
            configuration=legacy,
        )

    update = SessionUpdateRequest(
        name="Existing legacy session",
        instructions="test",
        configuration=legacy,
    )
    assert update.configuration.llm_provider is None


def test_campaign_fields_round_trip_through_control_plane_store() -> None:
    async def scenario() -> None:
        database = Database("sqlite+aiosqlite:///:memory:")
        await database.create_schema_for_tests()
        store = SqlAlchemyControlPlaneStore(database.sessions)
        try:
            config = _ollama_config(ollama_model="roundtrip:9b", ollama_timeout_seconds=47.0)
            bundle = await store.create_session_bundle(
                name="Ollama round-trip",
                strategy_prompt="Use the canonical strategic Agent.",
                configuration=config,
            )
            loaded = await store.get_campaign(bundle.campaign.campaign_id)
            assert loaded is not None
            assert loaded.configuration.llm_provider is LLMProviderKind.OLLAMA
            assert loaded.configuration.ollama_model == "roundtrip:9b"
            assert loaded.configuration.ollama_timeout_seconds == 47.0
            assert loaded.configuration_digest == config.digest
        finally:
            await database.close()

    asyncio.run(scenario())


def test_legacy_campaign_uses_process_provider_and_process_ollama_model() -> None:
    resolved = resolve_llm_configuration(
        _settings(provider=LLMProviderKind.OLLAMA, ollama_model="legacy-runtime:9b"),
        campaign_configuration=_config(agent_timeout_seconds=90.0),
    )
    assert resolved.provider is LLMProviderKind.OLLAMA
    assert resolved.model == "legacy-runtime:9b"
    assert resolved.ollama_timeout_seconds == 60.0


def test_explicit_ollama_campaign_overrides_process_openai_and_never_constructs_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ForbiddenOpenAI:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("OpenAI transport must not be constructed")

    monkeypatch.setattr(client_factory_module, "OpenAIResponsesClient", ForbiddenOpenAI)
    settings = _settings(provider=LLMProviderKind.OPENAI, openai_key="valid-but-unused")
    client, model = build_structured_decision_client(
        settings,
        campaign_configuration=_ollama_config(ollama_model="campaign-local:9b"),
    )
    assert isinstance(client, OllamaStructuredDecisionClient)
    assert model == "campaign-local:9b"


def test_explicit_openai_campaign_overrides_process_ollama_and_never_constructs_ollama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ForbiddenOllama:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("Ollama transport must not be constructed")

    monkeypatch.setattr(client_factory_module, "OllamaStructuredDecisionClient", ForbiddenOllama)
    client, model = build_structured_decision_client(
        _settings(provider=LLMProviderKind.OLLAMA, openai_key="campaign-openai-key"),
        campaign_configuration=_config(provider=LLMProviderKind.OPENAI, llm_model=LLMModel.SOL),
    )
    assert isinstance(client, OpenAIResponsesClient)
    assert model is LLMModel.SOL


def test_ollama_campaign_does_not_require_openai_key() -> None:
    client, model = build_structured_decision_client(
        _settings(provider=LLMProviderKind.OPENAI, openai_key=None),
        campaign_configuration=_ollama_config(),
    )
    assert isinstance(client, OllamaStructuredDecisionClient)
    assert model == "qwen3.5:9b"


def test_openai_campaign_without_key_fails_closed_without_ollama_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ForbiddenOllama:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("Ollama fallback is forbidden")

    monkeypatch.setattr(client_factory_module, "OllamaStructuredDecisionClient", ForbiddenOllama)
    with pytest.raises(PaperRuntimeConfigurationError, match="OPENAI_API_KEY"):
        build_structured_decision_client(
            _settings(provider=LLMProviderKind.OLLAMA, openai_key=None),
            campaign_configuration=_config(provider=LLMProviderKind.OPENAI),
        )


def test_empty_ollama_model_is_rejected() -> None:
    with pytest.raises(ValidationError, match="ollama_model"):
        _ollama_config(ollama_model="   ")


def test_non_positive_ollama_timeout_is_rejected() -> None:
    with pytest.raises(ValidationError, match="ollama_timeout_seconds"):
        _ollama_config(ollama_timeout_seconds=0.0)


def test_incoherent_agent_and_ollama_timeouts_are_rejected() -> None:
    with pytest.raises(ValidationError, match="cycle_agent_timeout_seconds"):
        _ollama_config(ollama_timeout_seconds=60.0, agent_timeout_seconds=60.0)


def test_explicit_ollama_without_timeout_uses_process_transport_timeout() -> None:
    config = _ollama_config(ollama_timeout_seconds=None, agent_timeout_seconds=80.0)
    resolved = resolve_llm_configuration(
        _settings(provider=LLMProviderKind.OPENAI, ollama_timeout_seconds=45.0),
        campaign_configuration=config,
    )
    assert resolved.provider is LLMProviderKind.OLLAMA
    assert resolved.model == "qwen3.5:9b"
    assert resolved.ollama_timeout_seconds == 45.0


def test_effective_process_ollama_timeout_is_checked_for_explicit_campaign() -> None:
    config = _ollama_config(ollama_timeout_seconds=None, agent_timeout_seconds=40.0)
    with pytest.raises(PaperRuntimeConfigurationError, match="greater than the effective Ollama"):
        resolve_llm_configuration(
            _settings(provider=LLMProviderKind.OPENAI, ollama_timeout_seconds=60.0),
            campaign_configuration=config,
        )


def test_two_campaigns_resolve_different_transports_in_one_process() -> None:
    settings = _settings(provider=LLMProviderKind.OPENAI, openai_key="one-process-key")
    openai = resolve_llm_configuration(
        settings,
        campaign_configuration=_config(provider=LLMProviderKind.OPENAI, llm_model=LLMModel.SOL),
    )
    ollama = resolve_llm_configuration(
        settings,
        campaign_configuration=_ollama_config(ollama_model="second-session:9b"),
    )
    assert openai.provider is LLMProviderKind.OPENAI
    assert openai.model is LLMModel.SOL
    assert ollama.provider is LLMProviderKind.OLLAMA
    assert ollama.model == "second-session:9b"


def test_strategic_audit_context_binds_session_and_cycle_to_provider_call() -> None:
    from datetime import UTC, datetime
    from uuid import uuid4

    from ai_spot_trader.agent.llm_audit import (
        GLOBAL_LLM_AUDIT_STORE,
        current_llm_audit_context,
    )
    from ai_spot_trader.agent.strategic_thesis import StrategicThesisContextDecisionProvider
    from ai_spot_trader.domain.enums import TradingAction
    from ai_spot_trader.domain.models import (
        AssetBalance,
        DecisionCandidate,
        MarketState,
        PortfolioState,
    )
    from ai_spot_trader.domain.planning import CycleDecisionPlan, CycleDecisionPlanInput
    from ai_spot_trader.domain.strategic_thesis import StrategicPositionContext

    now = datetime(2026, 10, 6, 16, 50, tzinfo=UTC)
    session_id = uuid4()
    cycle_id = uuid4()

    class Source:
        async def build_context(self, plan_input: CycleDecisionPlanInput) -> StrategicPositionContext:
            return StrategicPositionContext(as_of=plan_input.created_at, positions=())

    class Delegate:
        last_tool_traces = ()

        async def generate_decision_plan(
            self,
            plan_input: CycleDecisionPlanInput,
        ) -> CycleDecisionPlan:
            context = current_llm_audit_context()
            assert context.session_id == session_id
            assert context.cycle_id == cycle_id
            GLOBAL_LLM_AUDIT_STORE.append(
                request={
                    "model": "qwen3.5:9b",
                    "input": json.dumps(
                        {
                            "cycle_id": str(plan_input.cycle_id),
                            "strategic_plan_contract": {},
                        }
                    ),
                },
                response={"message": {"content": "{}"}},
                provider="OLLAMA",
                status="SUCCESS",
            )
            decision = DecisionCandidate(
                decision_id=uuid4(),
                cycle_id=plan_input.cycle_id,
                created_at=plan_input.created_at,
                action=TradingAction.HOLD,
                symbol="BTC/USD",
                market_type=MarketType.SPOT,
                proposed_quantity=None,
                rationale="audit context test",
            )
            return CycleDecisionPlan(
                cycle_id=plan_input.cycle_id,
                created_at=plan_input.created_at,
                decisions=(decision,),
            )

    portfolio = PortfolioState(
        portfolio_state_id=uuid4(),
        as_of=now,
        settlement_asset="USD",
        balances=(AssetBalance(asset="USD", available=Decimal("1000")),),
        cash_available=Decimal("1000"),
    )
    market = MarketState(
        market_state_id=uuid4(),
        as_of=now,
        symbol="BTC/USD",
        last_price=Decimal("100"),
        market_type=MarketType.SPOT,
    )
    plan_input = CycleDecisionPlanInput(
        cycle_id=cycle_id,
        created_at=now,
        portfolio_state=portfolio,
        market_states=(market,),
        aggressiveness=5,
    )
    provider = StrategicThesisContextDecisionProvider(
        Delegate(),
        Source(),
        session_id=session_id,
    )

    GLOBAL_LLM_AUDIT_STORE.clear_for_tests()
    try:
        asyncio.run(provider.generate_decision_plan(plan_input))
        records = GLOBAL_LLM_AUDIT_STORE.list_records(
            session_id=session_id,
            category="STRATEGIC_MULTI_MARKET_PLAN",
        )
        assert len(records) == 1
        assert records[0].provider == "OLLAMA"
        assert records[0].model == "qwen3.5:9b"
        assert records[0].session_id == session_id
        assert records[0].cycle_id == cycle_id
    finally:
        GLOBAL_LLM_AUDIT_STORE.clear_for_tests()
