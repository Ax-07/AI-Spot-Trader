from typing import Any

import pytest
from pydantic import ValidationError

from ai_spot_trader.core.config import Settings
from ai_spot_trader.domain.enums import ExecutionMode, LLMModel


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {"_env_file": None}
    values.update(overrides)
    return Settings(**values)


def test_settings_defaults_are_safe_for_local_bootstrap() -> None:
    settings = _settings()

    assert settings.environment == "development"
    assert settings.api_host == "127.0.0.1"
    assert settings.api_port == 8000
    assert settings.log_level == "INFO"
    assert settings.execution_mode is ExecutionMode.PAPER
    assert settings.llm_model is LLMModel.LUNA
    assert settings.aggressiveness is None
    assert settings.kraken_rest_url == "https://api.kraken.com"
    assert settings.kraken_ws_url == "wss://ws.kraken.com/v2"
    assert settings.kraken_ws_max_reconnect_attempts == 2
    assert settings.kraken_stale_after_seconds is None
    assert not any("api_key" in name or "secret" in name for name in Settings.model_fields)


def test_settings_read_prefixed_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_SPOT_TRADER_ENVIRONMENT", "test")
    monkeypatch.setenv("AI_SPOT_TRADER_API_PORT", "8123")
    monkeypatch.setenv("AI_SPOT_TRADER_LLM_MODEL", "gpt-5.6-sol")
    monkeypatch.setenv("AI_SPOT_TRADER_AGGRESSIVENESS", "8")

    settings = _settings()

    assert settings.environment == "test"
    assert settings.api_port == 8123
    assert settings.llm_model is LLMModel.SOL
    assert settings.aggressiveness == 8


@pytest.mark.parametrize("aggressiveness", [0, 11])
def test_aggressiveness_must_stay_between_one_and_ten(aggressiveness: int) -> None:
    with pytest.raises(ValidationError):
        _settings(aggressiveness=aggressiveness)


def test_live_execution_mode_is_not_configurable() -> None:
    with pytest.raises(ValidationError):
        _settings(execution_mode="LIVE")
