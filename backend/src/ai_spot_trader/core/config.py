from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from ai_spot_trader.domain.enums import ExecutionMode, LLMModel, MarginMode, MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.domain.symbols import parse_canonical_symbol

Environment = Literal["development", "test", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
_BACKEND_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class PaperRuntimeConfigurationError(ValueError):
    """Raised when the executable PAPER composition is incomplete or inconsistent."""


@dataclass(frozen=True, slots=True)
class PaperRunConfiguration:
    """Validated values required to compose one executable multi-market PAPER runtime."""

    symbol: str
    market_type: MarketType
    executable_markets: tuple[ExecutableMarket, ...]
    initial_capital: Decimal
    settlement_asset: str
    cadence_seconds: float
    aggressiveness: int
    market_timeout_seconds: float
    agent_timeout_seconds: float
    broker_timeout_seconds: float
    max_order_notional: Decimal
    allowed_pairs: frozenset[str]
    allow_quantity_reduction: bool
    fee_rate: Decimal
    spread_bps: Decimal
    slippage_bps: Decimal
    database_url: SecretStr
    openai_api_key: SecretStr
    llm_model: LLMModel
    derivative_leverage: Decimal | None = None
    max_derivative_leverage: Decimal | None = None
    max_derivative_position_notional: Decimal | None = None
    max_total_derivative_exposure: Decimal | None = None
    derivative_liquidation_buffer_ratio: Decimal | None = None
    derivative_margin_mode: MarginMode = MarginMode.ISOLATED
    agent_tool_max_calls: int = 6
    agent_tool_timeout_seconds: float = 5.0
    agent_tool_max_result_bytes: int = 32768
    agent_tool_list_markets_max_limit: int = 50

    @classmethod
    def from_settings(cls, settings: "Settings") -> "PaperRunConfiguration":
        """Fail closed unless every required PAPER value was explicitly supplied."""

        if settings.execution_mode is not ExecutionMode.PAPER:
            raise PaperRuntimeConfigurationError("the executable runtime only supports PAPER")
        required = {
            "paper_symbol": settings.paper_symbol,
            "paper_initial_capital": settings.paper_initial_capital,
            "paper_settlement_asset": settings.paper_settlement_asset,
            "trading_cadence_seconds": settings.trading_cadence_seconds,
            "aggressiveness": settings.aggressiveness,
            "cycle_market_timeout_seconds": settings.cycle_market_timeout_seconds,
            "cycle_agent_timeout_seconds": settings.cycle_agent_timeout_seconds,
            "cycle_broker_timeout_seconds": settings.cycle_broker_timeout_seconds,
            "risk_max_order_notional": settings.risk_max_order_notional,
            "risk_allowed_pairs": settings.risk_allowed_pairs,
            "risk_allow_quantity_reduction": settings.risk_allow_quantity_reduction,
            "paper_fee_rate": settings.paper_fee_rate,
            "paper_spread_bps": settings.paper_spread_bps,
            "paper_slippage_bps": settings.paper_slippage_bps,
            "database_url": settings.database_url,
            "openai_api_key": settings.openai_api_key,
        }
        missing = sorted(name for name, value in required.items() if value is None)
        if missing:
            raise PaperRuntimeConfigurationError(
                "missing required PAPER runtime settings: " + ", ".join(missing)
            )

        symbol = settings.paper_symbol
        initial_capital = settings.paper_initial_capital
        settlement_asset = settings.paper_settlement_asset
        cadence_seconds = settings.trading_cadence_seconds
        aggressiveness = settings.aggressiveness
        market_timeout_seconds = settings.cycle_market_timeout_seconds
        agent_timeout_seconds = settings.cycle_agent_timeout_seconds
        broker_timeout_seconds = settings.cycle_broker_timeout_seconds
        max_order_notional = settings.risk_max_order_notional
        allowed_pairs = settings.risk_allowed_pairs
        allow_quantity_reduction = settings.risk_allow_quantity_reduction
        fee_rate = settings.paper_fee_rate
        spread_bps = settings.paper_spread_bps
        slippage_bps = settings.paper_slippage_bps
        database_url = settings.database_url
        openai_api_key = settings.openai_api_key
        assert symbol is not None
        assert initial_capital is not None
        assert settlement_asset is not None
        assert cadence_seconds is not None
        assert aggressiveness is not None
        assert market_timeout_seconds is not None
        assert agent_timeout_seconds is not None
        assert broker_timeout_seconds is not None
        assert max_order_notional is not None
        assert allowed_pairs is not None
        assert allow_quantity_reduction is not None
        assert fee_rate is not None
        assert spread_bps is not None
        assert slippage_bps is not None
        assert database_url is not None
        assert openai_api_key is not None

        if settings.paper_market_type is MarketType.FUTURE:
            raise PaperRuntimeConfigurationError(
                "dated FUTURE is discoverable but PAPER execution supports SPOT/PERPETUAL only"
            )
        try:
            _, bootstrap_quote = parse_canonical_symbol(symbol)
        except ValueError as exc:
            raise PaperRuntimeConfigurationError(
                "paper_symbol must use canonical BASE/QUOTE"
            ) from exc

        executable_markets = _executable_markets(settings, bootstrap_symbol=symbol)
        bootstrap = ExecutableMarket(symbol=symbol, market_type=settings.paper_market_type)
        if bootstrap not in executable_markets:
            raise PaperRuntimeConfigurationError(
                "paper_symbol + paper_market_type must belong to paper_executable_markets"
            )

        if not settlement_asset.strip():
            raise PaperRuntimeConfigurationError("paper_settlement_asset cannot be empty")
        if settlement_asset != bootstrap_quote:
            raise PaperRuntimeConfigurationError(
                "paper_settlement_asset must equal the quote asset of paper_symbol"
            )
        for market in executable_markets:
            _, quote_asset = parse_canonical_symbol(market.symbol)
            if quote_asset != settlement_asset:
                raise PaperRuntimeConfigurationError(
                    "all paper_executable_markets must use paper_settlement_asset as quote"
                )

        if not allowed_pairs:
            raise PaperRuntimeConfigurationError("risk_allowed_pairs cannot be empty")
        for pair in allowed_pairs:
            try:
                parse_canonical_symbol(pair)
            except ValueError as exc:
                raise PaperRuntimeConfigurationError(
                    "risk_allowed_pairs must contain canonical BASE/QUOTE symbols"
                ) from exc
        executable_symbols = {market.symbol for market in executable_markets}
        if not executable_symbols.issubset(allowed_pairs):
            raise PaperRuntimeConfigurationError(
                "every paper_executable_markets symbol must be present in risk_allowed_pairs"
            )

        has_perpetual = any(
            market.market_type is MarketType.PERPETUAL for market in executable_markets
        )
        if has_perpetual:
            derivative_required = {
                "paper_derivative_leverage": settings.paper_derivative_leverage,
                "risk_max_derivative_leverage": settings.risk_max_derivative_leverage,
                "risk_max_derivative_position_notional": (
                    settings.risk_max_derivative_position_notional
                ),
                "risk_max_total_derivative_exposure": (
                    settings.risk_max_total_derivative_exposure
                ),
                "risk_derivative_liquidation_buffer_ratio": (
                    settings.risk_derivative_liquidation_buffer_ratio
                ),
            }
            derivative_missing = sorted(
                name for name, value in derivative_required.items() if value is None
            )
            if derivative_missing:
                raise PaperRuntimeConfigurationError(
                    "missing required PAPER runtime settings: "
                    + ", ".join(derivative_missing)
                )
            if settings.paper_derivative_margin_mode is not MarginMode.ISOLATED:
                raise PaperRuntimeConfigurationError(
                    "PAPER PERPETUAL execution supports ISOLATED margin only"
                )
            assert settings.paper_derivative_leverage is not None
            assert settings.risk_max_derivative_leverage is not None
            if settings.paper_derivative_leverage > settings.risk_max_derivative_leverage:
                raise PaperRuntimeConfigurationError(
                    "paper_derivative_leverage cannot exceed risk_max_derivative_leverage"
                )

        database_value = database_url.get_secret_value().strip()
        if not database_value:
            raise PaperRuntimeConfigurationError("database_url cannot be empty")
        if not database_value.startswith("postgresql+asyncpg://"):
            raise PaperRuntimeConfigurationError(
                "the executable PAPER runtime requires PostgreSQL via postgresql+asyncpg"
            )
        if not openai_api_key.get_secret_value().strip():
            raise PaperRuntimeConfigurationError("openai_api_key cannot be empty")
        if spread_bps + slippage_bps >= Decimal(10_000):
            raise PaperRuntimeConfigurationError(
                "combined paper_spread_bps and paper_slippage_bps must be below 10000"
            )

        return cls(
            symbol=symbol,
            market_type=settings.paper_market_type,
            executable_markets=executable_markets,
            initial_capital=initial_capital,
            settlement_asset=settlement_asset,
            cadence_seconds=cadence_seconds,
            aggressiveness=aggressiveness,
            market_timeout_seconds=market_timeout_seconds,
            agent_timeout_seconds=agent_timeout_seconds,
            broker_timeout_seconds=broker_timeout_seconds,
            max_order_notional=max_order_notional,
            allowed_pairs=allowed_pairs,
            allow_quantity_reduction=allow_quantity_reduction,
            fee_rate=fee_rate,
            spread_bps=spread_bps,
            slippage_bps=slippage_bps,
            database_url=database_url,
            openai_api_key=openai_api_key,
            llm_model=settings.llm_model,
            derivative_leverage=settings.paper_derivative_leverage,
            max_derivative_leverage=settings.risk_max_derivative_leverage,
            max_derivative_position_notional=settings.risk_max_derivative_position_notional,
            max_total_derivative_exposure=settings.risk_max_total_derivative_exposure,
            derivative_liquidation_buffer_ratio=(
                settings.risk_derivative_liquidation_buffer_ratio
            ),
            derivative_margin_mode=settings.paper_derivative_margin_mode,
            agent_tool_max_calls=settings.agent_tool_max_calls,
            agent_tool_timeout_seconds=settings.agent_tool_timeout_seconds,
            agent_tool_max_result_bytes=settings.agent_tool_max_result_bytes,
            agent_tool_list_markets_max_limit=settings.agent_tool_list_markets_max_limit,
        )


def _executable_markets(
    settings: "Settings",
    *,
    bootstrap_symbol: str,
) -> tuple[ExecutableMarket, ...]:
    configured = settings.paper_executable_markets
    if configured is None:
        return (
            ExecutableMarket(
                symbol=bootstrap_symbol,
                market_type=settings.paper_market_type,
            ),
        )
    if not configured:
        raise PaperRuntimeConfigurationError("paper_executable_markets cannot be empty")

    parsed: list[ExecutableMarket] = []
    for raw in configured:
        if not isinstance(raw, str) or not raw.strip() or ":" not in raw:
            raise PaperRuntimeConfigurationError(
                "paper_executable_markets entries must use MARKET_TYPE:BASE/QUOTE"
            )
        raw_type, raw_symbol = raw.split(":", 1)
        try:
            market_type = MarketType(raw_type.strip().upper())
        except ValueError as exc:
            raise PaperRuntimeConfigurationError(
                "paper_executable_markets contains an unsupported market type"
            ) from exc
        if market_type is MarketType.FUTURE:
            raise PaperRuntimeConfigurationError(
                "dated FUTURE is discoverable but PAPER execution supports SPOT/PERPETUAL only"
            )
        symbol = raw_symbol.strip()
        try:
            parse_canonical_symbol(symbol)
            parsed.append(ExecutableMarket(symbol=symbol, market_type=market_type))
        except ValueError as exc:
            raise PaperRuntimeConfigurationError(
                "paper_executable_markets must contain canonical typed markets"
            ) from exc

    ordered = tuple(sorted(parsed, key=lambda item: (item.market_type.value, item.symbol)))
    if len(set(ordered)) != len(ordered):
        raise PaperRuntimeConfigurationError("paper_executable_markets contains duplicates")
    return ordered


class Settings(BaseSettings):
    """Typed process configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=_BACKEND_ENV_FILE,
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
    paper_symbol: str | None = None
    paper_market_type: MarketType = MarketType.SPOT
    paper_executable_markets: tuple[str, ...] | None = None
    paper_initial_capital: Decimal | None = Field(default=None, gt=0)
    paper_settlement_asset: str | None = None
    paper_derivative_leverage: Decimal | None = Field(default=Decimal(1), ge=1)
    paper_derivative_margin_mode: MarginMode = MarginMode.ISOLATED
    trading_cadence_seconds: float | None = Field(default=None, gt=0)
    cycle_market_timeout_seconds: float | None = Field(default=None, gt=0)
    cycle_agent_timeout_seconds: float | None = Field(default=None, gt=0)
    cycle_broker_timeout_seconds: float | None = Field(default=None, gt=0)
    risk_max_order_notional: Decimal | None = Field(default=None, gt=0)
    risk_allowed_pairs: frozenset[str] | None = None
    risk_allow_quantity_reduction: bool | None = None
    risk_max_derivative_leverage: Decimal | None = Field(default=Decimal(1), ge=1)
    risk_max_derivative_position_notional: Decimal | None = Field(default=None, gt=0)
    risk_max_total_derivative_exposure: Decimal | None = Field(default=None, gt=0)
    risk_derivative_liquidation_buffer_ratio: Decimal | None = Field(
        default=Decimal("1.10"), ge=1
    )
    paper_fee_rate: Decimal | None = Field(default=None, ge=0, lt=1)
    paper_spread_bps: Decimal | None = Field(default=None, ge=0)
    paper_slippage_bps: Decimal | None = Field(default=None, ge=0)
    openai_api_key: SecretStr | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_timeout_seconds: float = Field(default=30.0, gt=0)
    agent_tool_max_calls: int = Field(default=6, ge=0, le=32)
    agent_tool_timeout_seconds: float = Field(default=5.0, gt=0)
    agent_tool_max_result_bytes: int = Field(default=32768, ge=1024, le=262144)
    agent_tool_list_markets_max_limit: int = Field(default=50, ge=1, le=200)
    kraken_rest_url: str = "https://api.kraken.com"
    kraken_ws_url: str = "wss://ws.kraken.com/v2"
    kraken_derivatives_rest_url: str = "https://futures.kraken.com/derivatives/api/v3"
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
