import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal, cast
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    model_validator,
)

from ai_spot_trader.domain.enums import (
    DerivativeContractKind,
    ExecutionMode,
    ExperimentVariable,
    LLMModel,
    MarginMode,
    MarketType,
    PositionSide,
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


def canonical_json_digest(value: JsonValue) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class DomainModel(BaseModel):
    """Base configuration shared by domain boundary contracts."""

    model_config = ConfigDict(extra="forbid", strict=True)


class AssetBalance(DomainModel):
    """Available amount for one portfolio settlement asset."""

    asset: NonEmptyText
    available: NonNegativeDecimal


class AssetPosition(DomainModel):
    """Held and currently available quantity for one SPOT portfolio position asset."""

    asset: NonEmptyText
    quantity: NonNegativeDecimal
    available: NonNegativeDecimal

    @model_validator(mode="after")
    def available_cannot_exceed_quantity(self) -> "AssetPosition":
        if self.available > self.quantity:
            raise ValueError("available quantity cannot exceed held quantity")
        return self


class DerivativeInstrument(DomainModel):
    """Provider-normalized derivative contract metadata used by PAPER/Risk."""

    symbol: NonEmptyText
    venue_symbol: NonEmptyText
    market_type: MarketType
    contract_kind: DerivativeContractKind
    underlying_asset: NonEmptyText
    quote_asset: NonEmptyText
    contract_size: PositiveDecimal
    tick_size: PositiveDecimal
    min_order_quantity: PositiveDecimal
    max_position_quantity: PositiveDecimal | None = None
    initial_margin_rate: PositiveDecimal
    maintenance_margin_rate: PositiveDecimal
    max_leverage: PositiveDecimal
    funding_interval_seconds: PositiveDecimal | None = None
    expires_at: UtcDateTime | None = None

    @model_validator(mode="after")
    def validate_derivative_contract(self) -> "DerivativeInstrument":
        parse_canonical_symbol(self.symbol)
        if self.market_type is MarketType.SPOT:
            raise ValueError("DerivativeInstrument cannot use SPOT market_type")
        if self.initial_margin_rate > Decimal(1):
            raise ValueError("initial_margin_rate cannot exceed 1")
        if self.maintenance_margin_rate > self.initial_margin_rate:
            raise ValueError("maintenance_margin_rate cannot exceed initial_margin_rate")
        if self.max_leverage < Decimal(1):
            raise ValueError("max_leverage must be at least 1")
        if self.market_type is MarketType.PERPETUAL:
            if self.expires_at is not None:
                raise ValueError("PERPETUAL instruments cannot have expires_at")
            if self.funding_interval_seconds is None:
                raise ValueError("PERPETUAL instruments require funding_interval_seconds")
        elif self.market_type is MarketType.FUTURE and self.expires_at is None:
            raise ValueError("dated FUTURE instruments require expires_at")
        return self


class DerivativeMarketContext(DomainModel):
    """Derivative-specific public market facts attached to the canonical MarketState."""

    observed_at: UtcDateTime
    instrument: DerivativeInstrument
    mark_price: PositiveDecimal
    index_price: PositiveDecimal | None = None
    funding_rate: Decimal | None = None

    @model_validator(mode="after")
    def funding_only_for_perpetuals(self) -> "DerivativeMarketContext":
        if (
            self.instrument.market_type is not MarketType.PERPETUAL
            and self.funding_rate is not None
        ):
            raise ValueError("funding_rate is only valid for PERPETUAL instruments")
        return self


class DerivativePosition(DomainModel):
    """Net one-way PAPER derivative position with explicit margin and P&L."""

    symbol: NonEmptyText
    side: PositionSide
    quantity: PositiveDecimal
    average_entry_price: PositiveDecimal
    mark_price: PositiveDecimal
    contract_size: PositiveDecimal = Decimal(1)
    notional: PositiveDecimal
    realized_pnl: Decimal = Decimal(0)
    unrealized_pnl: Decimal
    leverage: PositiveDecimal
    margin_used: PositiveDecimal
    initial_margin_rate: PositiveDecimal
    maintenance_margin_rate: PositiveDecimal
    maintenance_margin: NonNegativeDecimal
    cumulative_funding: Decimal = Decimal(0)
    liquidation_price: PositiveDecimal | None = None
    margin_mode: MarginMode = MarginMode.ISOLATED
    funding_updated_at: UtcDateTime | None = None

    @model_validator(mode="after")
    def validate_derivative_position(self) -> "DerivativePosition":
        parse_canonical_symbol(self.symbol)
        expected_notional = self.mark_price * self.quantity * self.contract_size
        if self.notional != expected_notional:
            raise ValueError("derivative notional must equal mark_price * quantity * contract_size")
        expected_maintenance = self.notional * self.maintenance_margin_rate
        if self.maintenance_margin != expected_maintenance:
            raise ValueError("maintenance_margin must match notional * maintenance_margin_rate")
        if self.maintenance_margin_rate > self.initial_margin_rate:
            raise ValueError("maintenance margin rate cannot exceed initial margin rate")
        if self.leverage < Decimal(1):
            raise ValueError("derivative leverage must be at least 1")
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
    """Canonical deterministic SPOT or derivative market snapshot."""

    market_state_id: UUID
    as_of: UtcDateTime
    symbol: NonEmptyText
    last_price: PositiveDecimal
    context: MarketContext | None = None
    market_type: MarketType = MarketType.SPOT
    derivative: DerivativeMarketContext | None = None

    @model_validator(mode="after")
    def validate_market_contexts(self) -> "MarketState":
        if self.context is not None and self.context.last_observed_at > self.as_of:
            raise ValueError("market context cannot contain observations newer than the snapshot")
        if self.market_type is MarketType.SPOT:
            if self.derivative is not None:
                raise ValueError("SPOT MarketState cannot carry derivative context")
            return self
        if self.derivative is None:
            raise ValueError("derivative MarketState requires derivative context")
        if self.derivative.observed_at > self.as_of:
            raise ValueError("derivative observation cannot be newer than the snapshot")
        if self.derivative.instrument.symbol != self.symbol:
            raise ValueError("derivative instrument symbol must match MarketState symbol")
        if self.derivative.instrument.market_type is not self.market_type:
            raise ValueError("derivative instrument market_type must match MarketState")
        if self.last_price != self.derivative.mark_price:
            raise ValueError("derivative MarketState last_price must equal mark_price")
        return self


class PortfolioState(DomainModel):
    """Canonical PAPER portfolio with separate SPOT holdings and derivative positions."""

    portfolio_state_id: UUID
    as_of: UtcDateTime
    mode: ExecutionMode = ExecutionMode.PAPER
    balances: tuple[AssetBalance, ...] = ()
    positions: tuple[AssetPosition, ...] = ()
    derivative_positions: tuple[DerivativePosition, ...] = ()

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
        derivative_symbols = tuple(position.symbol for position in self.derivative_positions)
        if len(set(derivative_symbols)) != len(derivative_symbols):
            raise ValueError("portfolio derivative positions must be one-way and unique by symbol")
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
    comparison_variable: ExperimentVariable | None = None
    experiment_group_digest: Sha256Digest | None = None
    replicate_index: PositiveInt | None = None
    replicate_count: PositiveInt | None = None

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

        repeat_fields = (
            self.comparison_variable,
            self.experiment_group_digest,
            self.replicate_index,
            self.replicate_count,
        )
        if any(value is not None for value in repeat_fields):
            if any(value is None for value in repeat_fields):
                raise ValueError("versioned repeated experiments require complete group metadata")
            assert self.replicate_index is not None
            assert self.replicate_count is not None
            if self.replicate_index > self.replicate_count:
                raise ValueError("replicate_index cannot exceed replicate_count")
        return self


class ExecutableMarket(DomainModel):
    """One explicitly authorized PAPER market addressable by symbol and market type."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    symbol: NonEmptyText
    market_type: MarketType

    @model_validator(mode="after")
    def validate_executable_market(self) -> "ExecutableMarket":
        parse_canonical_symbol(self.symbol)
        if self.market_type is MarketType.FUTURE:
            raise ValueError("dated FUTURE markets are not executable")
        return self


class AgentToolTrace(DomainModel):
    """Sanitized durable trace of one Agent-visible read-only tool execution."""

    call_id: NonEmptyText
    tool_name: NonEmptyText
    arguments: dict[str, JsonValue]
    started_at: UtcDateTime
    completed_at: UtcDateTime
    status: Literal["SUCCESS", "ERROR"]
    error_type: NonEmptyText | None = None
    result: dict[str, JsonValue]
    result_digest: Sha256Digest

    @model_validator(mode="after")
    def validate_trace(self) -> "AgentToolTrace":
        if self.completed_at < self.started_at:
            raise ValueError("tool trace completed_at cannot precede started_at")
        if self.status == "SUCCESS" and self.error_type is not None:
            raise ValueError("successful tool traces cannot carry error_type")
        if self.status == "ERROR" and self.error_type is None:
            raise ValueError("error tool traces require a sanitized error_type")
        if self.result_digest != canonical_json_digest(self.result):
            raise ValueError("tool trace result_digest must match the normalized result")
        return self


class MarketSelectionInput(DomainModel):
    """Causal research boundary shown to the same strategic Agent before market acquisition."""

    cycle_id: UUID
    created_at: UtcDateTime
    portfolio_state: PortfolioState
    executable_markets: tuple[ExecutableMarket, ...]
    aggressiveness: Annotated[int, Field(ge=1, le=10)]
    aggressiveness_context: AggressivenessContext | None = None
    experiment_manifest: ExperimentManifest | None = None

    @model_validator(mode="after")
    def validate_selection_context(self) -> "MarketSelectionInput":
        if self.portfolio_state.as_of > self.created_at:
            raise ValueError("PortfolioState cannot be newer than MarketSelectionInput")
        if not self.executable_markets:
            raise ValueError("market selection requires a non-empty executable universe")
        ordered = tuple(
            sorted(
                self.executable_markets,
                key=lambda market: (market.market_type.value, market.symbol),
            )
        )
        if ordered != self.executable_markets:
            raise ValueError("executable_markets must use deterministic sorted order")
        keys = tuple((market.symbol, market.market_type) for market in self.executable_markets)
        if len(set(keys)) != len(keys):
            raise ValueError("executable_markets must be unique by symbol + market_type")
        if (
            self.aggressiveness_context is not None
            and self.aggressiveness_context.level != self.aggressiveness
        ):
            raise ValueError("aggressiveness_context level must match aggressiveness")
        manifest = self.experiment_manifest
        if manifest is not None:
            if self.aggressiveness_context is None:
                raise ValueError("experiment_manifest requires aggressiveness_context")
            if manifest.aggressiveness != self.aggressiveness_context:
                raise ValueError("experiment_manifest aggressiveness context mismatch")
            if any(market.symbol not in manifest.universe for market in self.executable_markets):
                raise ValueError("executable market is outside the experiment universe")
        return self


def market_selection_digest(
    *,
    selection_id: UUID,
    cycle_id: UUID,
    selected_at: datetime,
    symbol: str,
    market_type: MarketType,
    tool_traces: tuple[AgentToolTrace, ...],
    rationale: str | None = None,
) -> str:
    payload = {
        "selection_id": str(selection_id),
        "cycle_id": str(cycle_id),
        "selected_at": selected_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "symbol": symbol,
        "market_type": market_type.value,
        "rationale": rationale,
        "tool_traces": [trace.model_dump(mode="json") for trace in tool_traces],
    }
    return canonical_json_digest(cast(JsonValue, payload))


class MarketSelection(DomainModel):
    """Explicit auditable market chosen by the strategic Agent before executable acquisition."""

    selection_id: UUID
    cycle_id: UUID
    selected_at: UtcDateTime
    symbol: NonEmptyText
    market_type: MarketType
    rationale: str | None = None
    tool_traces: tuple[AgentToolTrace, ...] = ()
    selection_digest: Sha256Digest

    @model_validator(mode="after")
    def validate_selection(self) -> "MarketSelection":
        parse_canonical_symbol(self.symbol)
        if self.market_type is MarketType.FUTURE:
            raise ValueError("dated FUTURE markets cannot be selected for execution")
        call_ids = tuple(trace.call_id for trace in self.tool_traces)
        if len(call_ids) != len(set(call_ids)):
            raise ValueError("MarketSelection tool_traces must have unique call_id values")
        if any(trace.completed_at > self.selected_at for trace in self.tool_traces):
            raise ValueError("selection cannot use tool data completed after selected_at")
        expected = market_selection_digest(
            selection_id=self.selection_id,
            cycle_id=self.cycle_id,
            selected_at=self.selected_at,
            symbol=self.symbol,
            market_type=self.market_type,
            tool_traces=self.tool_traces,
            rationale=self.rationale,
        )
        if self.selection_digest != expected:
            raise ValueError("MarketSelection selection_digest mismatch")
        return self


class AgentInput(DomainModel):
    """Structured final-decision boundary for the single strategic trading agent."""

    cycle_id: UUID
    created_at: UtcDateTime
    market_state: MarketState
    portfolio_state: PortfolioState
    aggressiveness: Annotated[int, Field(ge=1, le=10)]
    aggressiveness_context: AggressivenessContext | None = None
    experiment_manifest: ExperimentManifest | None = None
    market_selection: MarketSelection | None = None

    @model_validator(mode="after")
    def validate_experimental_context(self) -> "AgentInput":
        if self.market_state.as_of > self.created_at:
            raise ValueError("MarketState cannot be newer than AgentInput.created_at")
        if self.portfolio_state.as_of > self.created_at:
            raise ValueError("PortfolioState cannot be newer than AgentInput.created_at")
        if (
            self.aggressiveness_context is not None
            and self.aggressiveness_context.level != self.aggressiveness
        ):
            raise ValueError("aggressiveness_context level must match aggressiveness")
        selection = self.market_selection
        if selection is not None:
            if selection.cycle_id != self.cycle_id:
                raise ValueError("MarketSelection cycle_id must match AgentInput")
            if selection.selected_at > self.created_at:
                raise ValueError("MarketSelection cannot postdate AgentInput")
            if selection.symbol != self.market_state.symbol:
                raise ValueError("MarketSelection symbol must match MarketState")
            if selection.market_type is not self.market_state.market_type:
                raise ValueError("MarketSelection market_type must match MarketState")
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
    market_type: MarketType = MarketType.SPOT
    tool_traces: tuple[AgentToolTrace, ...] = ()

    @model_validator(mode="after")
    def validate_proposed_quantity(self) -> "DecisionCandidate":
        if self.action is TradingAction.HOLD:
            if self.proposed_quantity is not None:
                raise ValueError("HOLD cannot propose an execution quantity")
        elif self.proposed_quantity is None:
            raise ValueError("BUY and SELL decisions require proposed_quantity")
        call_ids = tuple(trace.call_id for trace in self.tool_traces)
        if len(call_ids) != len(set(call_ids)):
            raise ValueError("tool_traces must have unique call_id values")
        if any(trace.completed_at > self.created_at for trace in self.tool_traces):
            raise ValueError("tool trace data cannot be newer than the final decision")
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
    """Risk-approved PAPER execution request for SPOT or derivatives."""

    execution_id: UUID
    cycle_id: UUID
    decision_id: UUID
    risk_assessment_id: UUID
    created_at: UtcDateTime
    mode: ExecutionMode = ExecutionMode.PAPER
    action: TradingAction
    symbol: NonEmptyText
    quantity: PositiveDecimal
    market_type: MarketType = MarketType.SPOT
    reduce_only: bool = False
    leverage: PositiveDecimal | None = None

    @model_validator(mode="after")
    def validate_execution_contract(self) -> "ExecutionIntent":
        if self.action is TradingAction.HOLD:
            raise ValueError("HOLD does not create an execution intent")
        if self.market_type is MarketType.SPOT:
            if self.reduce_only:
                raise ValueError("SPOT intents cannot be reduce_only")
            if self.leverage is not None:
                raise ValueError("SPOT intents cannot use leverage")
        elif self.leverage is None:
            raise ValueError("derivative intents require explicit leverage")
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
    market_type: MarketType = MarketType.SPOT
    contract_size: PositiveDecimal = Decimal(1)
    reduce_only: bool = False
    realized_pnl: Decimal = Decimal(0)
    margin_delta: Decimal = Decimal(0)
    funding_payment: Decimal = Decimal(0)

    @model_validator(mode="after")
    def validate_paper_fill(self) -> "Fill":
        if self.action is TradingAction.HOLD:
            raise ValueError("HOLD cannot produce a fill")
        if self.pricing_as_of > self.filled_at:
            raise ValueError("pricing snapshot cannot be newer than the fill")
        if self.notional != self.price * self.quantity * self.contract_size:
            raise ValueError(
                "fill notional must equal execution price times quantity times contract_size"
            )

        if self.action is TradingAction.BUY:
            adverse_price_delta = self.price - self.reference_price
        else:
            adverse_price_delta = self.reference_price - self.price
        if adverse_price_delta < 0:
            raise ValueError("PAPER execution costs cannot improve the reference price")
        expected_execution_cost = adverse_price_delta * self.quantity * self.contract_size
        if self.spread_cost + self.slippage_cost != expected_execution_cost:
            raise ValueError(
                "spread_cost plus slippage_cost must explain the execution price delta"
            )
        if self.market_type is MarketType.SPOT:
            if self.reduce_only or self.realized_pnl != 0 or self.margin_delta != 0:
                raise ValueError("SPOT fills cannot carry derivative execution fields")
            if self.funding_payment != 0 or self.contract_size != 1:
                raise ValueError("SPOT fills require contract_size=1 and no funding")
        return self
