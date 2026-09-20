from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from ai_spot_trader.domain.enums import ExecutionMode, LLMModel

Environment = Literal["development", "test", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    """Typed process configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="AI_SPOT_TRADER_",
        extra="ignore",
    )

    app_name: str = "AI Spot Trader"
    environment: Environment = "development"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    log_level: LogLevel = "INFO"
    execution_mode: ExecutionMode = ExecutionMode.PAPER
    llm_model: LLMModel = LLMModel.LUNA
    aggressiveness: int | None = Field(default=None, ge=1, le=10)
    openai_api_key: SecretStr | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_timeout_seconds: float = Field(default=30.0, gt=0)
    kraken_rest_url: str = "https://api.kraken.com"
    kraken_ws_url: str = "wss://ws.kraken.com/v2"
    kraken_rest_timeout_seconds: float = Field(default=10.0, gt=0)
    kraken_ws_receive_timeout_seconds: float = Field(default=15.0, gt=0)
    kraken_ws_max_reconnect_attempts: int = Field(default=2, ge=0, le=10)
    kraken_ws_reconnect_delay_seconds: float = Field(default=1.0, ge=0)
    kraken_stale_after_seconds: float | None = Field(default=None, gt=0)
    database_url: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""

    return Settings()
