import json
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from ai_spot_trader.control_plane import (
    CAMPAIGN_EXPERIMENT_PROTOCOL_VERSION,
    CampaignConfiguration,
    StrategicSchedule,
    campaign_identity_digest,
)
from ai_spot_trader.domain.enums import (
    LLMModel,
    MarginMode,
    MarketType,
    TradingCadenceMode,
    TradingStyle,
)
from ai_spot_trader.domain.experiments import TRADING_STYLE_MAPPING_VERSION
from ai_spot_trader.domain.models import ExecutableMarket


def _spot_config(**overrides: object) -> CampaignConfiguration:
    values: dict[str, object] = {
        "llm_model": LLMModel.LUNA,
        "aggressiveness": 5,
        "trading_cadence_seconds": 30.0,
        "paper_initial_capital": Decimal("1000"),
        "paper_settlement_asset": "USD",
        "paper_executable_markets": (
            ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),
        ),
        "paper_fee_rate": Decimal("0.0026"),
        "paper_spread_bps": Decimal("5"),
        "paper_slippage_bps": Decimal("3"),
        "paper_derivative_leverage": Decimal("1"),
        "paper_derivative_margin_mode": MarginMode.ISOLATED,
        "risk_max_order_notional": Decimal("100"),
        "risk_allowed_pairs": ("BTC/USD",),
        "risk_allow_quantity_reduction": True,
        "risk_max_derivative_leverage": Decimal("1"),
        "cycle_market_timeout_seconds": 20.0,
        "cycle_agent_timeout_seconds": 35.0,
        "cycle_broker_timeout_seconds": 5.0,
    }
    values.update(overrides)
    return CampaignConfiguration.model_validate(values)


def _perpetual_config() -> CampaignConfiguration:
    return _spot_config(
        paper_executable_markets=(
            ExecutableMarket(symbol="ETH/USD", market_type=MarketType.PERPETUAL),
        ),
        risk_allowed_pairs=("ETH/USD",),
        paper_derivative_leverage=Decimal("2"),
        risk_max_derivative_leverage=Decimal("3"),
        risk_max_derivative_position_notional=Decimal("500"),
        risk_max_total_derivative_exposure=Decimal("750"),
        risk_derivative_liquidation_buffer_ratio=Decimal("1.20"),
    )


def _style_fields(style: TradingStyle) -> dict[str, object]:
    return {
        "trading_style": style,
        "trading_style_mapping_version": TRADING_STYLE_MAPPING_VERSION,
    }


def test_spot_configuration_digest_is_canonical_and_secret_free() -> None:
    left = _spot_config(risk_allowed_pairs=("BTC/USD", "ETH/USD"))
    right = _spot_config(risk_allowed_pairs=("ETH/USD", "BTC/USD"))

    assert left.digest == right.digest
    payload = left.canonical_payload()
    encoded = str(payload).lower()
    assert "api_key" not in encoded
    assert "database_url" not in encoded
    assert "password" not in encoded


def test_legacy_configuration_omits_schedule_and_keeps_interval_semantics() -> None:
    config = _spot_config()

    assert config.effective_trading_cadence_mode is TradingCadenceMode.INTERVAL
    assert config.decision_timeframe is None
    assert "strategic_schedule" not in config.canonical_payload()

    decoded = CampaignConfiguration.model_validate_json(
        json.dumps(config.canonical_payload())
    )
    assert decoded == config
    assert decoded.digest == config.digest
    assert "strategic_schedule" not in decoded.canonical_payload()


def test_campaign_configuration_accepts_json_market_type_values() -> None:
    for expected in (_spot_config(), _perpetual_config()):
        decoded = CampaignConfiguration.model_validate_json(
            json.dumps(expected.canonical_payload())
        )

        assert decoded == expected
        assert decoded.digest == expected.digest


def test_campaign_configuration_json_market_type_adapter_stays_fail_closed() -> None:
    payload = _spot_config().canonical_payload()
    markets = payload["paper_executable_markets"]
    assert isinstance(markets, list)
    markets[0]["market_type"] = "UNKNOWN"

    with pytest.raises(ValidationError):
        CampaignConfiguration.model_validate_json(json.dumps(payload))


def test_explicit_interval_schedule_roundtrips_without_decision_timeframe() -> None:
    config = _spot_config(
        strategic_schedule=StrategicSchedule(mode=TradingCadenceMode.INTERVAL)
    )

    assert config.effective_trading_cadence_mode is TradingCadenceMode.INTERVAL
    assert config.decision_timeframe is None
    assert config.canonical_payload()["strategic_schedule"] == {"mode": "INTERVAL"}

    decoded = CampaignConfiguration.model_validate_json(
        json.dumps(config.canonical_payload())
    )
    assert decoded == config
    assert decoded.digest == config.digest


@pytest.mark.parametrize(
    ("style", "timeframe"),
    [
        (TradingStyle.SCALP, "1m"),
        (TradingStyle.SCALP, "5m"),
        (TradingStyle.SCALP, "15m"),
        (TradingStyle.SCALP, "30m"),
        (TradingStyle.SWING, "1h"),
        (TradingStyle.SWING, "4h"),
        (TradingStyle.SWING, "1d"),
    ],
)
def test_candle_close_schedule_accepts_only_canonical_style_timeframes(
    style: TradingStyle,
    timeframe: str,
) -> None:
    config = _spot_config(
        **_style_fields(style),
        strategic_schedule={"mode": "CANDLE_CLOSE", "decision_timeframe": timeframe},
    )

    assert config.effective_trading_cadence_mode is TradingCadenceMode.CANDLE_CLOSE
    assert config.decision_timeframe == timeframe
    decoded = CampaignConfiguration.model_validate_json(
        json.dumps(config.canonical_payload())
    )
    assert decoded == config
    assert decoded.digest == config.digest


def test_candle_close_requires_explicit_trading_style() -> None:
    with pytest.raises(ValidationError, match="requires an explicit trading_style"):
        _spot_config(
            strategic_schedule={"mode": "CANDLE_CLOSE", "decision_timeframe": "5m"}
        )


@pytest.mark.parametrize(
    ("style", "timeframe"),
    [(TradingStyle.SCALP, "4h"), (TradingStyle.SWING, "5m")],
)
def test_candle_close_rejects_timeframe_outside_selected_style(
    style: TradingStyle,
    timeframe: str,
) -> None:
    with pytest.raises(ValidationError, match="decision_timeframe"):
        _spot_config(
            **_style_fields(style),
            strategic_schedule={"mode": "CANDLE_CLOSE", "decision_timeframe": timeframe},
        )


def test_schedule_model_rejects_missing_or_extraneous_timeframe() -> None:
    with pytest.raises(ValidationError, match="requires decision_timeframe"):
        StrategicSchedule(mode=TradingCadenceMode.CANDLE_CLOSE)
    with pytest.raises(ValidationError, match="cannot define decision_timeframe"):
        StrategicSchedule(
            mode=TradingCadenceMode.INTERVAL,
            decision_timeframe="5m",
        )


def test_perpetual_configuration_captures_all_effective_risk_limits() -> None:
    config = _perpetual_config()

    payload = config.canonical_payload()
    assert payload["paper_derivative_leverage"] == "2"
    assert payload["risk_max_derivative_leverage"] == "3"
    assert payload["risk_max_derivative_position_notional"] == "500"
    assert payload["risk_max_total_derivative_exposure"] == "750"
    assert payload["risk_derivative_liquidation_buffer_ratio"] == "1.20"


def test_perpetual_configuration_fails_closed_without_derivative_caps() -> None:
    with pytest.raises(ValidationError):
        _spot_config(
            paper_executable_markets=(
                ExecutableMarket(symbol="ETH/USD", market_type=MarketType.PERPETUAL),
            ),
            risk_allowed_pairs=("ETH/USD",),
            paper_derivative_leverage=Decimal("2"),
            risk_max_derivative_leverage=Decimal("3"),
        )


def test_campaign_configuration_rejects_non_whitelisted_secret_fields() -> None:
    with pytest.raises(ValidationError):
        _spot_config(openai_api_key=None)


def test_campaign_configuration_rejects_unknown_schedule_fields() -> None:
    with pytest.raises(ValidationError):
        _spot_config(strategic_schedule={"mode": "INTERVAL", "unknown": True})


def test_campaign_v4_digest_is_sensitive_to_strategy_and_configuration() -> None:
    strategy_id = UUID("189a0000-0000-0000-0000-000000000001")
    config = _spot_config()
    base = campaign_identity_digest(
        strategy_id=strategy_id,
        strategy_revision=1,
        strategy_prompt_digest_value="a" * 64,
        base_agent_contract_version="agent-contract-v1",
        configuration_digest=config.digest,
    )
    changed_prompt = campaign_identity_digest(
        strategy_id=strategy_id,
        strategy_revision=1,
        strategy_prompt_digest_value="b" * 64,
        base_agent_contract_version="agent-contract-v1",
        configuration_digest=config.digest,
    )
    changed_config = campaign_identity_digest(
        strategy_id=strategy_id,
        strategy_revision=1,
        strategy_prompt_digest_value="a" * 64,
        base_agent_contract_version="agent-contract-v1",
        configuration_digest=_spot_config(aggressiveness=6).digest,
    )

    assert CAMPAIGN_EXPERIMENT_PROTOCOL_VERSION == "paper-experiment-v4"
    assert len(base) == 64
    assert base != changed_prompt
    assert base != changed_config
