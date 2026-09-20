from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from ai_spot_trader.domain.enums import ExecutionMode, RiskDecision, TradingAction

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PositiveDecimal = Annotated[Decimal, Field(gt=0)]
NonNegativeDecimal = Annotated[Decimal, Field(ge=0)]
PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]


def _normalize_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


UtcDateTime = Annotated[AwareDatetime, AfterValidator(_normalize_utc)]


class DomainModel(BaseModel):
    """Base configuration shared by domain boundary contracts."""

    model_config = ConfigDict(extra="forbid", strict=True)


class AssetBalance(DomainModel):
    """Available amount for one portfolio settlement asset."""

    asset: NonEmptyText
    available: NonNegativeDecimal


class AssetPosition(DomainModel):
    """Held and currently available quantity for one portfolio position asset."""

    asset: NonEmptyText
    quantity: NonNegativeDecimal
    available: NonNegativeDecimal

    @model_validator(mode="after")
    def available_cannot_exceed_quantity(self) -> "AssetPosition":
        if self.available > self.quantity:
            raise ValueError("available quantity cannot exceed held quantity")
        return self


class MarketObservation(DomainModel):
    """Provider-agnostic normalized last-price observation."""

    observed_at: UtcDateTime
    symbol: NonEmptyText
    last_price: PositiveDecimal


class MarketWindowStats(DomainModel):
    """Descriptive statistics calculated for one closed market horizon."""

    horizon_seconds: PositiveDecimal
    window_start: UtcDateTime
    observation_count: NonNegativeInt
    is_complete: bool
    first_observed_at: UtcDateTime | None = None
    last_observed_at: UtcDateTime | None = None
    first_price: PositiveDecimal | None = None
    last_price: PositiveDecimal | None = None
    min_price: PositiveDecimal | None = None
    max_price: PositiveDecimal | None = None
    price_range: NonNegativeDecimal | None = None
    return_fraction: Decimal | None = None
    realized_volatility: NonNegativeDecimal | None = None

    @model_validator(mode="after")
    def validate_statistics(self) -> "MarketWindowStats":
        core_values = (
            self.first_observed_at,
            self.last_observed_at,
            self.first_price,
            self.last_price,
            self.min_price,
            self.max_price,
            self.price_range,
        )
        if self.observation_count == 0:
            if self.is_complete or any(value is not None for value in core_values):
                raise ValueError(
                    "empty market windows cannot be complete or carry price statistics"
                )
            if self.return_fraction is not None or self.realized_volatility is not None:
                raise ValueError("empty market windows cannot carry derived statistics")
            return self

        if any(value is None for value in core_values):
            raise ValueError("non-empty market windows require core price statistics")

        first_observed_at = self.first_observed_at
        last_observed_at = self.last_observed_at
        first_price = self.first_price
        last_price = self.last_price
        min_price = self.min_price
        max_price = self.max_price
        price_range = self.price_range
        assert first_observed_at is not None
        assert last_observed_at is not None
        assert first_price is not None
        assert last_price is not None
        assert min_price is not None
        assert max_price is not None
        assert price_range is not None

        if first_observed_at < self.window_start or first_observed_at > last_observed_at:
            raise ValueError("market window timestamps are inconsistent")
        if min_price > max_price:
            raise ValueError("market window minimum cannot exceed maximum")
        if not min_price <= first_price <= max_price or not min_price <= last_price <= max_price:
            raise ValueError("market window endpoint prices must remain within min/max")
        if price_range != max_price - min_price:
            raise ValueError("market window price_range must equal max_price - min_price")

        if self.observation_count == 1:
            if first_observed_at != last_observed_at or first_price != last_price:
                raise ValueError("a one-observation window must have identical endpoints")
            if self.return_fraction is not None or self.realized_volatility is not None:
                raise ValueError("one observation is insufficient for derived return statistics")
            return self

        if self.return_fraction is None:
            raise ValueError("two or more observations require return_fraction")
        if self.observation_count < 3 and self.realized_volatility is not None:
            raise ValueError("at least three observations are required for realized volatility")
        if self.observation_count >= 3 and self.realized_volatility is None:
            raise ValueError("three or more observations require realized volatility")
        return self


class MarketContext(DomainModel):
    """Freshness and multi-horizon descriptive context attached to a MarketState."""

    last_observed_at: UtcDateTime
    data_age_seconds: NonNegativeDecimal
    stale_after_seconds: PositiveDecimal | None = None
    is_stale: bool | None = None
    windows: tuple[MarketWindowStats, ...] = ()

    @model_validator(mode="after")
    def validate_freshness_and_horizons(self) -> "MarketContext":
        if self.stale_after_seconds is None:
            if self.is_stale is not None:
                raise ValueError(
                    "is_stale must be unavailable when no stale threshold was evaluated"
                )
        else:
            expected = self.data_age_seconds > self.stale_after_seconds
            if self.is_stale is None or self.is_stale is not expected:
                raise ValueError("is_stale must match the evaluated stale threshold")

        horizons = tuple(window.horizon_seconds for window in self.windows)
        if horizons != tuple(sorted(horizons)) or len(set(horizons)) != len(horizons):
            raise ValueError("market windows must have unique ascending horizons")
        return self


class MarketState(DomainModel):
    """Canonical deterministic market snapshot exposed to downstream components."""

    market_state_id: UUID
    as_of: UtcDateTime
    symbol: NonEmptyText
    last_price: PositiveDecimal
    context: MarketContext | None = None

    @model_validator(mode="after")
    def context_cannot_be_from_the_future(self) -> "MarketState":
        if self.context is not None and self.context.last_observed_at > self.as_of:
            raise ValueError("market context cannot contain observations newer than the snapshot")
        return self


class PortfolioState(DomainModel):
    """Canonical PAPER portfolio snapshot with disjoint balance and position roles."""

    portfolio_state_id: UUID
    as_of: UtcDateTime
    mode: ExecutionMode = ExecutionMode.PAPER
    balances: tuple[AssetBalance, ...] = ()
    positions: tuple[AssetPosition, ...] = ()

    @model_validator(mode="after")
    def asset_roles_must_be_unambiguous(self) -> "PortfolioState":
        balance_assets = tuple(balance.asset for balance in self.balances)
        position_assets = tuple(position.asset for position in self.positions)
        if len(set(balance_assets)) != len(balance_assets):
            raise ValueError("portfolio balances must contain unique assets")
        if len(set(position_assets)) != len(position_assets):
            raise ValueError("portfolio positions must contain unique assets")
        overlap = set(balance_assets) & set(position_assets)
        if overlap:
            names = ", ".join(sorted(overlap))
            raise ValueError(f"portfolio asset roles must be disjoint: {names}")
        return self


class AgentInput(DomainModel):
    """Structured input boundary for the single strategic trading agent."""

    cycle_id: UUID
    created_at: UtcDateTime
    market_state: MarketState
    portfolio_state: PortfolioState
    aggressiveness: Annotated[int, Field(ge=1, le=10)]


class DecisionCandidate(DomainModel):
    """Validated strategic decision candidate before deterministic risk review."""

    decision_id: UUID
    cycle_id: UUID
    created_at: UtcDateTime
    action: TradingAction
    symbol: NonEmptyText
    rationale: str | None = None


class RiskAssessment(DomainModel):
    """Auditable outcome produced by the deterministic Risk Engine."""

    risk_assessment_id: UUID
    cycle_id: UUID
    decision_id: UUID
    assessed_at: UtcDateTime
    status: RiskDecision
    reasons: tuple[str, ...] = ()


class ExecutionIntent(DomainModel):
    """Risk-approved PAPER execution request for BUY or SELL only."""

    execution_id: UUID
    cycle_id: UUID
    decision_id: UUID
    risk_assessment_id: UUID
    created_at: UtcDateTime
    mode: ExecutionMode = ExecutionMode.PAPER
    action: TradingAction
    symbol: NonEmptyText
    quantity: PositiveDecimal

    @model_validator(mode="after")
    def hold_is_not_executable(self) -> "ExecutionIntent":
        if self.action is TradingAction.HOLD:
            raise ValueError("HOLD does not create an execution intent")
        return self


class Fill(DomainModel):
    """Auditable fact describing one complete simulated PAPER fill."""

    fill_id: UUID
    execution_id: UUID
    market_state_id: UUID
    filled_at: UtcDateTime
    pricing_as_of: UtcDateTime
    action: TradingAction
    symbol: NonEmptyText
    quantity: PositiveDecimal
    reference_price: PositiveDecimal
    price: PositiveDecimal
    notional: PositiveDecimal
    fee: NonNegativeDecimal
    spread_cost: NonNegativeDecimal
    slippage_cost: NonNegativeDecimal

    @model_validator(mode="after")
    def validate_paper_fill(self) -> "Fill":
        if self.action is TradingAction.HOLD:
            raise ValueError("HOLD cannot produce a fill")
        if self.pricing_as_of > self.filled_at:
            raise ValueError("pricing snapshot cannot be newer than the fill")
        if self.notional != self.price * self.quantity:
            raise ValueError("fill notional must equal execution price times quantity")

        if self.action is TradingAction.BUY:
            adverse_price_delta = self.price - self.reference_price
        else:
            adverse_price_delta = self.reference_price - self.price
        if adverse_price_delta < 0:
            raise ValueError("PAPER execution costs cannot improve the reference price")
        expected_execution_cost = adverse_price_delta * self.quantity
        if self.spread_cost + self.slippage_cost != expected_execution_cost:
            raise ValueError(
                "spread_cost plus slippage_cost must explain the execution price delta"
            )
        return self
