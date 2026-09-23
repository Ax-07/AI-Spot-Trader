from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_spot_trader.agent.prompt import BASE_AGENT_CONTRACT_VERSION
from ai_spot_trader.domain.enums import LLMModel, MarginMode, MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.domain.symbols import parse_canonical_symbol

CONTROL_PLANE_CONFIGURATION_VERSION = "paper-control-plane-config-v1"
CAMPAIGN_EXPERIMENT_PROTOCOL_VERSION = "paper-experiment-v4"

PositiveDecimal = Annotated[Decimal, Field(gt=0)]
NonNegativeDecimal = Annotated[Decimal, Field(ge=0)]


def _canonical_digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ControlPlaneModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class CampaignConfiguration(ControlPlaneModel):
    """Whitelisted operator configuration persisted without process secrets."""

    configuration_version: str = CONTROL_PLANE_CONFIGURATION_VERSION
    llm_model: LLMModel
    aggressiveness: int = Field(ge=1, le=10)
    trading_cadence_seconds: float = Field(gt=0)

    paper_initial_capital: PositiveDecimal
    paper_settlement_asset: str = Field(min_length=1, max_length=16)
    paper_executable_markets: tuple[ExecutableMarket, ...]

    paper_fee_rate: NonNegativeDecimal = Field(lt=1)
    paper_spread_bps: NonNegativeDecimal
    paper_slippage_bps: NonNegativeDecimal

    paper_derivative_leverage: PositiveDecimal = Decimal(1)
    paper_derivative_margin_mode: MarginMode = MarginMode.ISOLATED

    risk_max_order_notional: PositiveDecimal
    risk_allowed_pairs: tuple[str, ...]
    risk_allow_quantity_reduction: bool

    risk_max_derivative_leverage: PositiveDecimal = Decimal(1)
    risk_max_derivative_position_notional: PositiveDecimal | None = None
    risk_max_total_derivative_exposure: PositiveDecimal | None = None
    risk_derivative_liquidation_buffer_ratio: PositiveDecimal = Decimal("1.10")

    cycle_market_timeout_seconds: float = Field(gt=0)
    cycle_agent_timeout_seconds: float = Field(gt=0)
    cycle_broker_timeout_seconds: float = Field(gt=0)

    @field_validator("paper_settlement_asset")
    @classmethod
    def normalize_settlement_asset(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("paper_settlement_asset cannot be empty")
        return normalized

    @field_validator("risk_allowed_pairs")
    @classmethod
    def normalize_allowed_pairs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("risk_allowed_pairs cannot be empty")
        stripped = tuple(item.strip() for item in value)
        if any(not item for item in stripped):
            raise ValueError("risk_allowed_pairs cannot contain empty values")
        if len(set(stripped)) != len(stripped):
            raise ValueError("risk_allowed_pairs must be unique")
        for symbol in stripped:
            parse_canonical_symbol(symbol)
        return tuple(sorted(stripped))

    @field_validator("paper_executable_markets")
    @classmethod
    def normalize_markets(
        cls, value: tuple[ExecutableMarket, ...]
    ) -> tuple[ExecutableMarket, ...]:
        if not value:
            raise ValueError("paper_executable_markets cannot be empty")
        ordered = tuple(sorted(value, key=lambda item: (item.market_type.value, item.symbol)))
        if len(set(ordered)) != len(ordered):
            raise ValueError("paper_executable_markets must be unique")
        return ordered

    @model_validator(mode="after")
    def validate_structural_configuration(self) -> CampaignConfiguration:
        if self.configuration_version != CONTROL_PLANE_CONFIGURATION_VERSION:
            raise ValueError("unsupported control-plane configuration version")
        if self.paper_spread_bps + self.paper_slippage_bps >= Decimal(10_000):
            raise ValueError("combined paper spread and slippage must be below 10000 bps")

        executable_symbols: set[str] = set()
        has_perpetual = False
        for market in self.paper_executable_markets:
            if market.market_type is MarketType.FUTURE:
                raise ValueError("dated FUTURE markets are not executable")
            _, quote_asset = parse_canonical_symbol(market.symbol)
            if quote_asset != self.paper_settlement_asset:
                raise ValueError(
                    "all executable markets must quote the configured settlement asset"
                )
            executable_symbols.add(market.symbol)
            has_perpetual = has_perpetual or market.market_type is MarketType.PERPETUAL

        if not executable_symbols.issubset(set(self.risk_allowed_pairs)):
            raise ValueError("every executable symbol must be present in risk_allowed_pairs")

        if self.paper_derivative_margin_mode is not MarginMode.ISOLATED:
            raise ValueError("PAPER PERPETUAL supports ISOLATED margin only")
        if self.paper_derivative_leverage < Decimal(1):
            raise ValueError("paper_derivative_leverage must be at least 1")
        if self.risk_max_derivative_leverage < Decimal(1):
            raise ValueError("risk_max_derivative_leverage must be at least 1")
        if self.paper_derivative_leverage > self.risk_max_derivative_leverage:
            raise ValueError(
                "paper_derivative_leverage cannot exceed risk_max_derivative_leverage"
            )
        if self.risk_derivative_liquidation_buffer_ratio < Decimal(1):
            raise ValueError("risk_derivative_liquidation_buffer_ratio must be at least 1")
        if has_perpetual and self.risk_max_derivative_position_notional is None:
            raise ValueError(
                "PERPETUAL campaigns require risk_max_derivative_position_notional"
            )
        if has_perpetual and self.risk_max_total_derivative_exposure is None:
            raise ValueError("PERPETUAL campaigns require risk_max_total_derivative_exposure")
        return self

    def canonical_payload(self) -> dict[str, object]:
        payload = self.model_dump(mode="json")
        assert isinstance(payload, dict)
        return payload

    @property
    def digest(self) -> str:
        return _canonical_digest(self.canonical_payload())


def campaign_identity_digest(
    *,
    strategy_id: UUID,
    strategy_revision: int,
    strategy_prompt_digest_value: str,
    base_agent_contract_version: str,
    configuration_digest: str,
) -> str:
    """Canonical paper-experiment-v4 identity without embedding any secret."""

    return _canonical_digest(
        {
            "experiment_protocol_version": CAMPAIGN_EXPERIMENT_PROTOCOL_VERSION,
            "strategy_id": str(strategy_id),
            "strategy_revision": strategy_revision,
            "strategy_prompt_digest": strategy_prompt_digest_value,
            "base_agent_contract_version": base_agent_contract_version,
            "configuration_digest": configuration_digest,
        }
    )


__all__ = [
    "BASE_AGENT_CONTRACT_VERSION",
    "CAMPAIGN_EXPERIMENT_PROTOCOL_VERSION",
    "CONTROL_PLANE_CONFIGURATION_VERSION",
    "CampaignConfiguration",
    "campaign_identity_digest",
]
