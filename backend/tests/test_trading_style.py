from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from ai_spot_trader.agent.prompt import PROTECTED_AGENT_CONTRACT, compose_agent_instructions
from ai_spot_trader.agent.strategy_client import StrategyInstructionsClient
from ai_spot_trader.campaign_composition import _campaign_agent_contexts
from ai_spot_trader.control_plane import CampaignConfiguration
from ai_spot_trader.domain.enums import LLMModel, MarketType, TradingStyle
from ai_spot_trader.domain.experiments import (
    TRADING_STYLE_MAPPING_VERSION,
    aggressiveness_context,
    trading_style_context,
)
from ai_spot_trader.domain.models import (
    AgentInput,
    AssetBalance,
    ExecutionCostContext,
    ExecutableMarket,
    MarketSelectionInput,
    MarketState,
    PortfolioState,
)
from ai_spot_trader.market.discovery import MarketCandidate, MarketDiscoveryInput
from ai_spot_trader.market.research import MarketResearchSnapshot

NOW = datetime(2026, 9, 26, 10, 0, tzinfo=UTC)
MARKET = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT)
LEGACY_CONFIGURATION_DIGEST = "e369decaa3ac79695221f5e0f8eb7cc9a654c3e3b5a67f25dcd15db30041eb6f"


def _configuration(style: TradingStyle | None = None) -> CampaignConfiguration:
    return CampaignConfiguration(
        llm_model=LLMModel.LUNA,
        aggressiveness=5,
        trading_cadence_seconds=30.0,
        trading_style=style,
        trading_style_mapping_version=(
            TRADING_STYLE_MAPPING_VERSION if style is not None else None
        ),
        paper_initial_capital=Decimal("1000"),
        paper_settlement_asset="USD",
        paper_executable_markets=(MARKET,),
        paper_fee_rate=Decimal("0.0026"),
        paper_spread_bps=Decimal("5"),
        paper_slippage_bps=Decimal("3"),
        risk_max_order_notional=Decimal("100"),
        risk_allowed_pairs=("BTC/USD",),
        risk_allow_quantity_reduction=True,
        cycle_market_timeout_seconds=20.0,
        cycle_agent_timeout_seconds=35.0,
        cycle_broker_timeout_seconds=5.0,
    )


def _portfolio() -> PortfolioState:
    return PortfolioState(
        portfolio_state_id=uuid4(),
        as_of=NOW,
        settlement_asset="USD",
        balances=(AssetBalance(asset="USD", available=Decimal("1000")),),
        cash_available=Decimal("1000"),
    )


def _market_state() -> MarketState:
    return MarketState(
        market_state_id=uuid4(),
        as_of=NOW,
        symbol="BTC/USD",
        last_price=Decimal("50000"),
        market_type=MarketType.SPOT,
    )


def _costs() -> ExecutionCostContext:
    return ExecutionCostContext(
        fee_rate=Decimal("0.0026"),
        spread_bps=Decimal("5"),
        slippage_bps=Decimal("3"),
    )


def test_trading_style_mapping_is_deterministic_versioned_and_independent_from_aggressiveness() -> None:
    scalp = trading_style_context(TradingStyle.SCALP)
    swing = trading_style_context(TradingStyle.SWING)

    assert scalp == trading_style_context(TradingStyle.SCALP)
    assert swing == trading_style_context(TradingStyle.SWING)
    assert scalp.mapping_version == TRADING_STYLE_MAPPING_VERSION
    assert swing.mapping_version == TRADING_STYLE_MAPPING_VERSION
    assert scalp.preferred_timeframes == ("1m", "5m", "15m", "30m")
    assert swing.preferred_timeframes == ("1h", "4h", "1d")
    assert scalp.cost_sensitivity == "VERY_HIGH"
    assert "timer" in scalp.position_holding_guidance
    assert "timer" in swing.position_holding_guidance

    # Style and aggressiveness are separate axes: neither helper accepts or derives the other.
    assert aggressiveness_context(2).level == 2
    assert aggressiveness_context(9).level == 9
    assert trading_style_context(TradingStyle.SCALP) == scalp
    assert trading_style_context(TradingStyle.SWING) == swing


def test_campaign_configuration_preserves_legacy_payload_and_digest() -> None:
    legacy = _configuration()
    payload = legacy.canonical_payload()

    assert "trading_style" not in payload
    assert "trading_style_mapping_version" not in payload
    assert legacy.digest == LEGACY_CONFIGURATION_DIGEST

    serialized = json.loads(legacy.model_dump_json())
    assert "trading_style" not in serialized
    assert "trading_style_mapping_version" not in serialized


def test_campaign_configuration_validates_style_mapping_and_changes_identity() -> None:
    scalp = _configuration(TradingStyle.SCALP)
    swing = _configuration(TradingStyle.SWING)

    assert scalp.digest != swing.digest
    assert scalp.canonical_payload()["trading_style"] == "SCALP"
    assert swing.canonical_payload()["trading_style"] == "SWING"

    base = _configuration().model_dump()
    with pytest.raises(ValidationError, match="must be supplied together"):
        CampaignConfiguration.model_validate({**base, "trading_style": TradingStyle.SCALP})
    with pytest.raises(ValidationError, match="must be supplied together"):
        CampaignConfiguration.model_validate(
            {**base, "trading_style_mapping_version": TRADING_STYLE_MAPPING_VERSION}
        )
    with pytest.raises(ValidationError, match="unsupported trading style mapping version"):
        CampaignConfiguration.model_validate(
            {
                **base,
                "trading_style": TradingStyle.SCALP,
                "trading_style_mapping_version": "trading-style-map-v999",
            }
        )


def test_campaign_agent_context_uses_exact_paper_costs_and_is_legacy_optional() -> None:
    assert _campaign_agent_contexts(_configuration()) == (None, None)

    style, costs = _campaign_agent_contexts(_configuration(TradingStyle.SCALP))
    assert style == trading_style_context(TradingStyle.SCALP)
    assert costs == _costs()


def test_structured_boundaries_carry_style_and_cost_context_without_legacy_noise() -> None:
    aggression = aggressiveness_context(5)
    style = trading_style_context(TradingStyle.SCALP)
    costs = _costs()
    portfolio = _portfolio()

    legacy_selection = MarketSelectionInput(
        cycle_id=uuid4(),
        created_at=NOW,
        portfolio_state=portfolio,
        executable_markets=(MARKET,),
        aggressiveness=5,
        aggressiveness_context=aggression,
    )
    legacy_payload = legacy_selection.model_dump(mode="json")
    assert "trading_style_context" not in legacy_payload
    assert "execution_cost_context" not in legacy_payload

    selection = MarketSelectionInput(
        cycle_id=uuid4(),
        created_at=NOW,
        portfolio_state=portfolio,
        executable_markets=(MARKET,),
        aggressiveness=5,
        aggressiveness_context=aggression,
        trading_style_context=style,
        execution_cost_context=costs,
    )
    assert selection.trading_style_context == style
    assert selection.execution_cost_context == costs

    agent_input = AgentInput(
        cycle_id=uuid4(),
        created_at=NOW,
        market_state=_market_state(),
        portfolio_state=portfolio,
        aggressiveness=5,
        aggressiveness_context=aggression,
        trading_style_context=style,
        execution_cost_context=costs,
    )
    assert agent_input.trading_style_context == style
    assert agent_input.execution_cost_context == costs

    candidate = MarketCandidate(
        market=MARKET,
        status="online",
        venue_symbol="XBTUSD",
        snapshot=MarketResearchSnapshot(
            symbol="BTC/USD",
            market_type=MarketType.SPOT,
            as_of=NOW,
            last_price=Decimal("50000"),
        ),
    )
    discovery = MarketDiscoveryInput(
        discovery_id=uuid4(),
        created_at=NOW,
        portfolio_state=portfolio,
        candidates=(candidate,),
        watchlist_limit=1,
        aggressiveness=5,
        aggressiveness_context=aggression,
        trading_style_context=style,
        execution_cost_context=costs,
        market_discovery_context={"protocol_version": "market-discovery-v1"},
    )
    assert discovery.trading_style_context == style
    assert discovery.execution_cost_context == costs


def test_prompt_composition_adds_canonical_style_and_cost_sections_only_when_configured() -> None:
    aggression = aggressiveness_context(5)
    legacy = compose_agent_instructions(
        strategy_prompt="Cherche une opportunite defendable.",
        aggressiveness_context=aggression,
    )
    expected_legacy = "\n\n".join(
        (
            PROTECTED_AGENT_CONTRACT.rstrip(),
            "STRATEGIE OPERATEUR EDITABLE (subordonnee au contrat protege) :\n"
            "Cherche une opportunite defendable.",
            "CONTEXTE D'AGRESSIVITE CANONIQUE :\n"
            "niveau=5/10\n"
            f"posture={aggression.posture}\n"
            f"instruction={aggression.strategic_instruction}",
        )
    )
    assert legacy.instructions == expected_legacy
    assert "CONTEXTE DE STYLE DE TRADING CANONIQUE" not in legacy.instructions
    assert "CONTEXTE DE COUTS D'EXECUTION PAPER CANONIQUE" not in legacy.instructions

    styled = compose_agent_instructions(
        strategy_prompt="Cherche une opportunite defendable.",
        aggressiveness_context=aggression,
        trading_style_context=trading_style_context(TradingStyle.SCALP),
        execution_cost_context=_costs(),
    )
    assert styled.instructions.startswith(expected_legacy + "\n\n")
    assert "style=SCALP" in styled.instructions
    assert "preferred_timeframes=1m,5m,15m,30m" in styled.instructions
    assert "fee_rate=0.0026" in styled.instructions
    assert "spread_bps=5" in styled.instructions
    assert "slippage_bps=3" in styled.instructions


def test_strategy_instructions_client_preserves_legacy_and_reads_structured_style_context() -> None:
    aggression = aggressiveness_context(5)
    style = trading_style_context(TradingStyle.SWING)
    costs = _costs()
    portfolio = _portfolio()
    client = StrategyInstructionsClient(object(), strategy_prompt="Reste selectif.")

    legacy_input = MarketSelectionInput(
        cycle_id=uuid4(),
        created_at=NOW,
        portfolio_state=portfolio,
        executable_markets=(MARKET,),
        aggressiveness=5,
        aggressiveness_context=aggression,
    )
    legacy_instructions = client.effective_instructions(legacy_input.model_dump_json())
    assert legacy_instructions == compose_agent_instructions(
        strategy_prompt="Reste selectif.",
        aggressiveness_context=aggression,
    ).instructions

    styled_input = legacy_input.model_copy(
        update={
            "trading_style_context": style,
            "execution_cost_context": costs,
        }
    )
    styled_instructions = client.effective_instructions(styled_input.model_dump_json())
    assert "style=SWING" in styled_instructions
    assert "preferred_timeframes=1h,4h,1d" in styled_instructions
    assert "fee_rate=0.0026" in styled_instructions
