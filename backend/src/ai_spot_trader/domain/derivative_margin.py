from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from ai_spot_trader.domain.models import DerivativeInstrument, DomainModel

ZERO = Decimal(0)
ONE = Decimal(1)


class DerivativeMarginTier(DomainModel):
    """One provider-normalized derivative margin floor for a projected position size."""

    threshold: Decimal = Field(ge=0)
    threshold_basis: Literal["CONTRACTS", "POSITION_NOTIONAL"]
    initial_margin_rate: Decimal = Field(gt=0, le=1)
    maintenance_margin_rate: Decimal = Field(gt=0, le=1)

    @model_validator(mode="after")
    def validate_rates(self) -> "DerivativeMarginTier":
        if self.maintenance_margin_rate > self.initial_margin_rate:
            raise ValueError("maintenance margin rate cannot exceed initial margin rate")
        return self


class TieredDerivativeInstrument(DerivativeInstrument):
    """Derivative instrument retaining one explicit, selected public margin curve."""

    margin_tiers: tuple[DerivativeMarginTier, ...] = Field(min_length=1)
    margin_schedule_source: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_margin_curve(self) -> "TieredDerivativeInstrument":
        bases = {tier.threshold_basis for tier in self.margin_tiers}
        if len(bases) != 1:
            raise ValueError("derivative margin tiers must use one threshold basis")
        thresholds = tuple(tier.threshold for tier in self.margin_tiers)
        if thresholds[0] != ZERO:
            raise ValueError("derivative margin tiers must start at threshold zero")
        if thresholds != tuple(sorted(thresholds)) or len(set(thresholds)) != len(thresholds):
            raise ValueError("derivative margin tiers must have unique ascending thresholds")
        initials = tuple(tier.initial_margin_rate for tier in self.margin_tiers)
        maintenance = tuple(tier.maintenance_margin_rate for tier in self.margin_tiers)
        if initials != tuple(sorted(initials)):
            raise ValueError("initial margin rates cannot decrease across size tiers")
        if maintenance != tuple(sorted(maintenance)):
            raise ValueError("maintenance margin rates cannot decrease across size tiers")
        first = self.margin_tiers[0]
        if self.initial_margin_rate != first.initial_margin_rate:
            raise ValueError("instrument initial_margin_rate must match the first margin tier")
        if self.maintenance_margin_rate != first.maintenance_margin_rate:
            raise ValueError("instrument maintenance_margin_rate must match the first margin tier")
        if self.max_leverage > ONE / first.initial_margin_rate:
            raise ValueError("instrument max_leverage cannot exceed the first margin tier")
        return self


@dataclass(frozen=True, slots=True)
class ApplicableDerivativeMargin:
    """Canonical margin parameters selected for one projected derivative position."""

    initial_margin_rate: Decimal
    maintenance_margin_rate: Decimal
    max_leverage: Decimal
    tier: DerivativeMarginTier | None
    schedule_source: str | None


def resolve_derivative_margin(
    instrument: DerivativeInstrument,
    *,
    projected_quantity: Decimal,
    projected_notional: Decimal,
) -> ApplicableDerivativeMargin:
    """Resolve one canonical margin tier; scalar instruments remain fully compatible."""

    if projected_quantity < ZERO or projected_notional < ZERO:
        raise ValueError("projected derivative size cannot be negative")
    if not isinstance(instrument, TieredDerivativeInstrument):
        return ApplicableDerivativeMargin(
            initial_margin_rate=instrument.initial_margin_rate,
            maintenance_margin_rate=instrument.maintenance_margin_rate,
            max_leverage=min(instrument.max_leverage, ONE / instrument.initial_margin_rate),
            tier=None,
            schedule_source=None,
        )

    basis = instrument.margin_tiers[0].threshold_basis
    metric = projected_quantity if basis == "CONTRACTS" else projected_notional
    selected = instrument.margin_tiers[0]
    for tier in instrument.margin_tiers[1:]:
        if metric < tier.threshold:
            break
        selected = tier
    return ApplicableDerivativeMargin(
        initial_margin_rate=selected.initial_margin_rate,
        maintenance_margin_rate=selected.maintenance_margin_rate,
        max_leverage=min(instrument.max_leverage, ONE / selected.initial_margin_rate),
        tier=selected,
        schedule_source=instrument.margin_schedule_source,
    )
