from ai_spot_trader.control_plane import CAMPAIGN_EXPERIMENT_PROTOCOL_VERSION
from ai_spot_trader.domain.experiments import (
    EXPERIMENT_PROTOCOL_VERSION,
    MODEL_EXPERIMENT_PROTOCOL_VERSION,
    MULTI_MARKET_MODEL_EXPERIMENT_PROTOCOL_VERSION,
)


def test_v4_is_additive_and_historical_protocol_names_are_unchanged() -> None:
    assert EXPERIMENT_PROTOCOL_VERSION == "paper-experiment-v1"
    assert MODEL_EXPERIMENT_PROTOCOL_VERSION == "paper-experiment-v2"
    assert MULTI_MARKET_MODEL_EXPERIMENT_PROTOCOL_VERSION == "paper-experiment-v3"
    assert CAMPAIGN_EXPERIMENT_PROTOCOL_VERSION == "paper-experiment-v4"
