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

from ai_spot_trader.domain.enums import (
    ExecutionMode,
    LLMModel,
    RiskDecision,
    RiskLimit,
    RiskReason,
    TradingAction,
)
from ai_spot_trader.domain.symbols import parse_canonical_symbol

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PositiveDecimal = Annotated[Decimal, Field(gt=0)]
NonNegativeDecimal = Annotated[Decimal, Field(ge=0)]
PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
Sha256Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


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


class AggressivenessContext(DomainModel):
    """Versioned strategic interpretation of one configured aggressiveness level."""

    mapping_version: NonEmptyText
    level: Annotated[int, Field(ge=1, le=10)]
    posture: NonEmptyText
    strategic_instruction: NonEmptyText


class ExperimentRiskPolicySnapshot(DomainModel):
    """Canonical experiment identity for deterministic RiskPolicy parameters."""

    max_order_notional: PositiveDecimal | None = None
    allowed_pairs: tuple[NonEmptyText, ...] | None = None
    stale_after_seconds: PositiveDecimal | None = None
    allow_quantity_reduction: bool

    @model_validator(mode="after")
    def pairs_are_canonical(self) -> "ExperimentRiskPolicySnapshot":
        if self.allowed_pairs is None:
            return self
        if not self.allowed_pairs:
            raise ValueError("allowed_pairs cannot be empty")
        if self.allowed_pairs != tuple(sorted(self.allowed_pairs)):
            raise ValueError("allowed_pairs must be sorted for reproducibility")
        if len(set(self.allowed_pairs)) != len(self.allowed_pairs):
            raise ValueError("allowed_pairs must be unique")
        for symbol in self.allowed_pairs:
            parse_canonical_symbol(symbol)
        return self


class ExperimentPaperCostSnapshot(DomainModel):
    """Canonical PAPER cost configuration recorded in an experiment manifest."""

    fee_rate: NonNegativeDecimal
    spread_bps: NonNegativeDecimal
    slippage_bps: NonNegativeDecimal


class ExperimentManifest(DomainModel):
    """Immutable protocol identity persisted with each experimental AgentInput."""

    protocol_version: NonEmptyText
    experiment_digest: Sha256Digest
    aggressiveness: AggressivenessContext
    llm_model: LLMModel
    prompt_version: NonEmptyText
    universe: tuple[NonEmptyText, ...]
    risk_policy: ExperimentRiskPolicySnapshot
    paper_costs: ExperimentPaperCostSnapshot
    analytics_version: NonEmptyText
    source_id: NonEmptyText
    source_digest: Sha256Digest | None = None
    window_start: UtcDateTime | None = None
    window_end: UtcDateTime | None = None

    @model_validator(mode="after")
    def validate_manifest_shape(self) -> "ExperimentManifest":
        if not self.universe:
            raise ValueError("experiment universe cannot be empty")
        if self.universe != tuple(sorted(self.universe)):
            raise ValueError("experiment universe must be sorted for reproducibility")
        if len(set(self.universe)) != len(self.universe):
            raise ValueError("experiment universe must contain unique symbols")
        for symbol in self.universe:
            parse_canonical_symbol(symbol)
        if (self.window_start is None) is not (self.window_end is None):
            raise ValueError("experiment window_start and window_end must be set together")
        if (
            self.window_start is not None
            and self.window_end is not None
            and self.window_end < self.window_start
        ):
            raise ValueError("experiment window_end cannot precede window_start")
        return self


class AgentInput(DomainModel):
    """Structured input boundary for the single strategic trading agent."""

    cycle_id: UUID
    created_at: UtcDateTime
    market_state: MarketState
    portfolio_state: PortfolioState
    aggressiveness: Annotated[int, Field(ge=1, le=10)]
    aggressiveness_context: AggressivenessContext | None = None
    experiment_manifest: ExperimentManifest | None = None

    @model_validator(mode="after")
    def validate_experimental_context(self) -> "AgentInput":
        if (
            self.aggressiveness_context is not None
            and self.aggressiveness_context.level != self.aggressiveness
        ):
            raise ValueError("aggressiveness_context level must match aggressiveness")
        manifest = self.experiment_manifest
        if manifest is None:
            return self
        if self.aggressiveness_context is None:
            raise ValueError("experiment_manifest requires aggressiveness_context")
        if manifest.aggressiveness != self.aggressiveness_context:
            raise ValueError("experiment_manifest aggressiveness context mismatch")
        if self.market_state.symbol not in manifest.universe:
            raise ValueError("AgentInput symbol is outside the experiment universe")
        return self


class DecisionCandidate(DomainModel):
    """Strategic action and proposed size before deterministic risk review."""

    decision_id: UUID
    cycle_id: UUID
    created_at: UtcDateTime
    action: TradingAction
    symbol: NonEmptyText
    proposed_quantity: PositiveDecimal | None = None
    rationale: str | None = None

    @model_validator(mode="after")
    def validate_proposed_quantity(self) -> "DecisionCandidate":
        if self.action is TradingAction.HOLD:
            if self.proposed_quantity is not None:
                raise ValueError("HOLD cannot propose an execution quantity")
        elif self.proposed_quantity is None:
            raise ValueError("BUY and SELL decisions require proposed_quantity")
        return self


class RiskAssessment(DomainModel):
    """Auditable outcome produced by the deterministic Risk Engine."""

    risk_assessment_id: UUID
    cycle_id: UUID
    decision_id: UUID
    assessed_at: UtcDateTime
    status: RiskDecision
    requested_quantity: PositiveDecimal | None = None
    authorized_quantity: PositiveDecimal | None = None
    evaluated_limits: tuple[RiskLimit, ...] = ()
    reasons: tuple[RiskReason, ...] = ()

    @model_validator(mode="after")
    def validate_risk_outcome(self) -> "RiskAssessment":
        if len(set(self.evaluated_limits)) != len(self.evaluated_limits):
            raise ValueError("evaluated_limits must contain unique checks")
        if self.status is RiskDecision.REJECT:
            if self.authorized_quantity is not None:
                raise ValueError("REJECT cannot authorize a quantity")
            if not self.reasons:
                raise ValueError("REJECT requires at least one reason")
            return self

        if self.status is RiskDecision.MODIFY:
            if self.requested_quantity is None or self.authorized_quantity is None:
                raise ValueError("MODIFY requires requested and authorized quantities")
            if self.authorized_quantity >= self.requested_quantity:
                raise ValueError("MODIFY must strictly reduce the requested quantity")
            if not self.reasons:
                raise ValueError("MODIFY requires at least one reason")
            return self

        if self.requested_quantity is None:
            if self.authorized_quantity is not None:
                raise ValueError("ALLOW without a requested quantity cannot authorize one")
        elif self.authorized_quantity != self.requested_quantity:
            raise ValueError("ALLOW must preserve the requested quantity")
        return self


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
