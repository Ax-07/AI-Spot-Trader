import pytest

from ai_spot_trader.core.config import Settings


def test_settings_defaults_are_safe_for_local_bootstrap() -> None:
    settings = Settings(_env_file=None)

    assert settings.environment == "development"
    assert settings.api_host == "127.0.0.1"
    assert settings.api_port == 8000
    assert settings.log_level == "INFO"


def test_settings_read_prefixed_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_SPOT_TRADER_ENVIRONMENT", "test")
    monkeypatch.setenv("AI_SPOT_TRADER_API_PORT", "8123")

    settings = Settings(_env_file=None)

    assert settings.environment == "test"
    assert settings.api_port == 8123
