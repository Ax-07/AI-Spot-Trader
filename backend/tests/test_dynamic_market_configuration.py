from decimal import Decimal

import pytest
from pydantic import ValidationError

from ai_spot_trader.control_plane import CampaignConfiguration
from ai_spot_trader.domain.enums import LLMModel, MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.discovery import MarketDiscoveryPolicy


def base(**overrides: object) -> CampaignConfiguration:
    values: dict[str, object] = {
        "llm_model": LLMModel.LUNA,
        "aggressiveness": 5,
        "trading_cadence_seconds": 30.0,
        "paper_initial_capital": Decimal("1000"),
        "paper_settlement_asset": "USD",
        "paper_executable_markets": (
            ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT),
        ),
        "market_discovery": MarketDiscoveryPolicy(
            market_types=(MarketType.SPOT,),
            min_window_observations=0,
        ),
        "paper_fee_rate": Decimal("0.001"),
        "paper_spread_bps": Decimal("2"),
        "paper_slippage_bps": Decimal("2"),
        "risk_max_order_notional": Decimal("100"),
        "risk_allowed_pairs": None,
        "risk_allow_quantity_reduction": True,
        "risk_max_derivative_leverage": Decimal("1"),
        "cycle_market_timeout_seconds": 20.0,
        "cycle_agent_timeout_seconds": 35.0,
        "cycle_broker_timeout_seconds": 5.0,
    }
    values.update(overrides)
    return CampaignConfiguration.model_validate(values)


def test_dynamic_spot_allows_null_pair_whitelist() -> None:
    config = base()
    assert config.risk_allowed_pairs is None
    assert config.market_discovery is not None
    assert config.market_discovery.market_types == (MarketType.SPOT,)


def test_static_campaign_still_requires_pair_whitelist() -> None:
    with pytest.raises(ValidationError, match="static campaigns require risk_allowed_pairs"):
        base(market_discovery=None, risk_allowed_pairs=None)


def test_optional_dynamic_pair_whitelist_must_cover_bootstrap() -> None:
    with pytest.raises(ValidationError, match="bootstrap executable symbol"):
        base(risk_allowed_pairs=("ETH/USD",))


def test_dynamic_perpetual_requires_existing_derivative_caps() -> None:
    with pytest.raises(ValidationError, match="risk_max_derivative_position_notional"):
        base(
            paper_executable_markets=(
                ExecutableMarket(symbol="BTC/USD", market_type=MarketType.PERPETUAL),
            ),
            market_discovery=MarketDiscoveryPolicy(
                market_types=(MarketType.PERPETUAL,),
                min_window_observations=0,
            ),
            paper_derivative_leverage=Decimal("2"),
            risk_max_derivative_leverage=Decimal("3"),
        )


def test_discovery_market_type_requires_matching_bootstrap_type() -> None:
    with pytest.raises(ValidationError, match="requires a bootstrap executable market"):
        base(
            market_discovery=MarketDiscoveryPolicy(
                market_types=(MarketType.PERPETUAL, MarketType.SPOT),
                min_window_observations=0,
            ),
            risk_max_derivative_position_notional=Decimal("500"),
            risk_max_total_derivative_exposure=Decimal("1000"),
        )


def test_static_payload_omits_discovery_field_for_historical_digest_compatibility() -> None:
    config = base(
        market_discovery=None,
        risk_allowed_pairs=("BTC/USD",),
    )

    payload = config.canonical_payload()

    assert "market_discovery" not in payload
    assert payload["risk_allowed_pairs"] == ["BTC/USD"]
