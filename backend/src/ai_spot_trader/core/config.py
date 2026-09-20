from functools import lru_cache
from typing import Literal

from pydantic import Field
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


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""

    return Settings()
