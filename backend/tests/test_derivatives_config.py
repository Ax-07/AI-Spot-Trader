from decimal import Decimal
from typing import Any

import pytest
from pydantic import SecretStr

from ai_spot_trader.core.config import (
    PaperRunConfiguration,
    PaperRuntimeConfigurationError,
    Settings,
)
from ai_spot_trader.domain.enums import MarketType


def settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "_env_file": None,
        "environment": "test",
        "paper_symbol": "BTC/USD",
        "paper_market_type": MarketType.PERPETUAL,
        "paper_initial_capital": Decimal("1000"),
        "paper_settlement_asset": "USD",
        "paper_derivative_leverage": Decimal("1"),
        "trading_cadence_seconds": 30.0,
        "aggressiveness": 5,
        "cycle_market_timeout_seconds": 5.0,
        "cycle_agent_timeout_seconds": 30.0,
        "cycle_broker_timeout_seconds": 5.0,
        "risk_max_order_notional": Decimal("250"),
        "risk_allowed_pairs": frozenset({"BTC/USD"}),
        "risk_allow_quantity_reduction": True,
        "risk_max_derivative_leverage": Decimal("2"),
        "risk_max_derivative_position_notional": Decimal("500"),
        "risk_max_total_derivative_exposure": Decimal("1000"),
        "risk_derivative_liquidation_buffer_ratio": Decimal("1.10"),
        "paper_fee_rate": Decimal("0.001"),
        "paper_spread_bps": Decimal("2"),
        "paper_slippage_bps": Decimal("3"),
        "database_url": SecretStr("postgresql+asyncpg://test:test@localhost/test"),
        "openai_api_key": SecretStr("test-key"),
    }
    values.update(overrides)
    return Settings(**values)


def test_perpetual_runtime_defaults_to_one_x_but_keeps_explicit_internal_cap() -> None:
    run = PaperRunConfiguration.from_settings(settings())
    assert run.market_type is MarketType.PERPETUAL
    assert run.derivative_leverage == Decimal("1")
    assert run.max_derivative_leverage == Decimal("2")


def test_perpetual_runtime_requires_explicit_exposure_caps() -> None:
    with pytest.raises(PaperRuntimeConfigurationError, match="risk_max_total_derivative_exposure"):
        PaperRunConfiguration.from_settings(settings(risk_max_total_derivative_exposure=None))


def test_dated_future_execution_is_not_enabled_in_batch_16() -> None:
    with pytest.raises(PaperRuntimeConfigurationError, match="PERPETUAL only"):
        PaperRunConfiguration.from_settings(settings(paper_market_type=MarketType.FUTURE))
