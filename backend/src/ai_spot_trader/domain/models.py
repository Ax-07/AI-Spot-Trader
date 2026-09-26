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
    TradingStyle,
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
    """Canonical SPOT inventory, cost accounting and causal mark-to-market."""

    asset: NonEmptyText
    quantity: NonNegativeDecimal
    available: NonNegativeDecimal
    average_entry_price: PositiveDecimal | None = None
    remaining_cost_basis: NonNegativeDecimal | None = None
    realized_pnl: Decimal = Decimal(0)
    accounting_complete: bool = False
    mark_price: PositiveDecimal | None = None
    mark_observed_at: UtcDateTime | None = None
    mark_source: Literal["LAST_PRICE"] | None = None
    market_value: NonNegativeDecimal | None = None
    unrealized_pnl: Decimal | None = None
    valuation_complete: bool = False

    @model_validator(mode="after")
    def validate_spot_accounting(self) -> "AssetPosition":
        if self.available > self.quantity:
            raise ValueError("available quantity cannot exceed held quantity")
        if self.accounting_complete:
            if self.quantity <= 0:
                raise ValueError("complete SPOT accounting requires a positive held quantity")
            if self.average_entry_price is None or self.remaining_cost_basis is None:
                raise ValueError(
                    "complete SPOT accounting requires average_entry_price and remaining_cost_basis"
                )
            if self.remaining_cost_basis <= 0:
                raise ValueError(
                    "complete SPOT accounting requires a positive remaining_cost_basis"
                )
        elif self.average_entry_price is not None or self.remaining_cost_basis is not None:
            raise ValueError(
                "incomplete SPOT accounting cannot expose partial cost-basis fields"
            )

        mark_facts = (
            self.mark_price,
            self.mark_observed_at,
            self.mark_source,
            self.market_value,
        )
        has_mark = self.mark_price is not None
        if any(value is not None for value in mark_facts) and not all(
            value is not None for value in mark_facts
        ):
            raise ValueError("SPOT mark fields must be complete or entirely unavailable")
        if not has_mark:
            if self.unrealized_pnl is not None or self.valuation_complete:
                raise ValueError("SPOT valuation cannot be complete without a mark")
            return self

        assert self.mark_price is not None
        assert self.market_value is not None
        expected_market_value = self.mark_price * self.quantity
        if self.market_value != expected_market_value:
            raise ValueError("SPOT market_value must equal mark_price * quantity")
        if not self.accounting_complete:
            if self.unrealized_pnl is not None or self.valuation_complete:
                raise ValueError(
                    "incomplete SPOT accounting cannot expose a canonical unrealized P&L"
                )
            return self

        assert self.remaining_cost_basis is not None
        expected_unrealized = self.market_value - self.remaining_cost_basis
        if self.unrealized_pnl != expected_unrealized:
            raise ValueError(
                "SPOT unrealized_pnl must equal market_value - remaining_cost_basis"
            )
        if not self.valuation_complete:
            raise ValueError("complete SPOT accounting plus mark requires complete valuation")
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
    mark_observed_at: UtcDateTime | None = None
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
    """Canonical PAPER portfolio with SPOT accounting and deterministic valuation totals."""

    portfolio_state_id: UUID
    as_of: UtcDateTime
    mode: ExecutionMode = ExecutionMode.PAPER
    settlement_asset: NonEmptyText | None = None
    balances: tuple[AssetBalance, ...] = ()
    positions: tuple[AssetPosition, ...] = ()
    derivative_positions: tuple[DerivativePosition, ...] = ()
    cash_available: NonNegativeDecimal | None = None
    spot_remaining_cost_basis_total: NonNegativeDecimal | None = None
    spot_market_value_total: NonNegativeDecimal | None = None
    spot_realized_pnl_total: Decimal | None = None
    spot_unrealized_pnl_total: Decimal | None = None
    equity: Decimal | None = None
    exposure_value: NonNegativeDecimal | None = None
    exposure_fraction: NonNegativeDecimal | None = None
    valuation_complete: bool = False

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

        for position in self.positions:
            if position.mark_observed_at is not None and position.mark_observed_at > self.as_of:
                raise ValueError("SPOT position mark cannot be newer than PortfolioState.as_of")
        if self.settlement_asset is None:
            if self.cash_available is not None:
                raise ValueError("cash_available requires settlement_asset")
        else:
            settlement_balance = next(
                (balance for balance in self.balances if balance.asset == self.settlement_asset),
                None,
            )
            if self.cash_available is not None:
                if settlement_balance is None or settlement_balance.available != self.cash_available:
                    raise ValueError("cash_available must match the settlement balance")

        if self.spot_remaining_cost_basis_total is not None:
            if any(position.remaining_cost_basis is None for position in self.positions):
                raise ValueError("SPOT cost-basis total requires complete position accounting")
            expected = sum(
                (cast(Decimal, position.remaining_cost_basis) for position in self.positions),
                Decimal(0),
            )
            if self.spot_remaining_cost_basis_total != expected:
                raise ValueError("SPOT cost-basis total must equal open position cost bases")

        if self.spot_market_value_total is not None:
            if any(position.market_value is None for position in self.positions):
                raise ValueError("SPOT market-value total requires marks for every position")
            expected = sum(
                (cast(Decimal, position.market_value) for position in self.positions),
                Decimal(0),
            )
            if self.spot_market_value_total != expected:
                raise ValueError("SPOT market-value total must equal open position market values")

        if self.spot_unrealized_pnl_total is not None:
            if any(position.unrealized_pnl is None for position in self.positions):
                raise ValueError("SPOT unrealized total requires complete position valuations")
            expected = sum(
                (cast(Decimal, position.unrealized_pnl) for position in self.positions),
                Decimal(0),
            )
            if self.spot_unrealized_pnl_total != expected:
                raise ValueError("SPOT unrealized total must equal open position unrealized P&L")

        if self.valuation_complete:
            required = (
                self.cash_available,
                self.spot_market_value_total,
                self.equity,
                self.exposure_value,
            )
            if any(value is None for value in required):
                raise ValueError("complete portfolio valuation requires cash, value, equity and exposure")
            assert self.cash_available is not None
            assert self.spot_market_value_total is not None
            assert self.equity is not None
            assert self.exposure_value is not None
            expected_equity = self.cash_available + self.spot_market_value_total + sum(
                (
                    position.margin_used
                    + position.unrealized_pnl
                    + position.cumulative_funding
                    for position in self.derivative_positions
                ),
                Decimal(0),
            )
            if self.equity != expected_equity:
                raise ValueError("portfolio equity must match canonical marked components")
            expected_exposure = self.spot_market_value_total + sum(
                (position.notional for position in self.derivative_positions),
                Decimal(0),
            )
            if self.exposure_value != expected_exposure:
                raise ValueError("portfolio exposure_value must match marked position exposure")
            if self.equity > 0:
                expected_fraction = self.exposure_value / self.equity
                if self.exposure_fraction != expected_fraction:
                    raise ValueError("portfolio exposure_fraction must equal exposure_value / equity")
            elif self.exposure_fraction is not None:
                raise ValueError("portfolio exposure_fraction requires positive equity")
        elif any(
            value is not None
            for value in (self.equity, self.exposure_value, self.exposure_fraction)
        ):
            raise ValueError("incomplete portfolio valuation cannot expose equity or exposure")
        return self


class AggressivenessContext(DomainModel):
    """Versioned strategic interpretation of one configured aggressiveness level."""

    mapping_version: NonEmptyText
    level: Annotated[int, Field(ge=1, le=10)]
    posture: NonEmptyText
    strategic_instruction: NonEmptyText


class TradingStyleContext(DomainModel):
    """Versioned strategic horizon guidance for one configured trading style."""

    mapping_version: NonEmptyText
    style: TradingStyle
    horizon_guidance: NonEmptyText
    preferred_timeframes: Annotated[
        tuple[Literal["1m", "5m", "15m", "30m", "1h", "4h", "1d"], ...],
        Field(min_length=1),
    ]
    position_holding_guidance: NonEmptyText
    opportunity_frequency_guidance: NonEmptyText
    cost_sensitivity: NonEmptyText

    @model_validator(mode="after")
    def validate_preferred_timeframes(self) -> "TradingStyleContext":
        if len(set(self.preferred_timeframes)) != len(self.preferred_timeframes):
            raise ValueError("preferred_timeframes must be unique")
        return self


class ExecutionCostContext(DomainModel):
    """Canonical PAPER execution costs visible to the strategic Agent."""

    fee_rate: NonNegativeDecimal
    spread_bps: NonNegativeDecimal
    slippage_bps: NonNegativeDecimal


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
    agent_protocol: "ExperimentAgentProtocolSnapshot | None" = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )

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
        if self.agent_protocol is not None:
            protocol_symbols = tuple(
                sorted({market.symbol for market in self.agent_protocol.executable_markets})
            )
            if protocol_symbols != self.universe:
                raise ValueError(
                    "experiment universe must equal the typed executable-market symbol projection"
                )
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


class ExperimentAgentPhaseSnapshot(DomainModel):
    """Canonical record of whether one strategic phase exposes read-only tools."""

    tools_enabled: bool
    max_tool_calls: NonNegativeInt

    @model_validator(mode="after")
    def validate_tool_budget(self) -> "ExperimentAgentPhaseSnapshot":
        if self.tools_enabled and self.max_tool_calls == 0:
            raise ValueError("an enabled Agent tool phase requires a positive call budget")
        if not self.tools_enabled and self.max_tool_calls != 0:
            raise ValueError("a disabled Agent tool phase must use max_tool_calls=0")
        return self


class ExperimentAgentProtocolSnapshot(DomainModel):
    """Controlled strategic environment for causal multi-market model experiments."""

    executable_markets: tuple[ExecutableMarket, ...]
    market_selection_protocol_version: NonEmptyText
    selection_phase: ExperimentAgentPhaseSnapshot
    final_decision_phase: ExperimentAgentPhaseSnapshot
    tool_definitions_digest: Sha256Digest | None = None
    tool_timeout_seconds: PositiveDecimal | None = None
    tool_max_result_bytes: PositiveInt | None = None
    list_markets_max_limit: PositiveInt | None = None

    @model_validator(mode="after")
    def validate_agent_protocol(self) -> "ExperimentAgentProtocolSnapshot":
        if not self.executable_markets:
            raise ValueError("multi-market Agent protocol requires an executable universe")
        ordered = tuple(
            sorted(
                self.executable_markets,
                key=lambda market: (market.market_type.value, market.symbol),
            )
        )
        if ordered != self.executable_markets:
            raise ValueError(
                "Agent protocol executable_markets must use deterministic sorted order"
            )
        if len(set(self.executable_markets)) != len(self.executable_markets):
            raise ValueError("Agent protocol executable_markets must be unique")

        tools_exposed = (
            self.selection_phase.tools_enabled or self.final_decision_phase.tools_enabled
        )
        tool_identity = (
            self.tool_definitions_digest,
            self.tool_timeout_seconds,
            self.tool_max_result_bytes,
            self.list_markets_max_limit,
        )
        if tools_exposed and any(value is None for value in tool_identity):
            raise ValueError("enabled Agent tools require definitions and all effective bounds")
        if not tools_exposed and any(value is not None for value in tool_identity):
            raise ValueError(
                "disabled Agent tools cannot carry an inactive tool capability identity"
            )
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


StrategicTimeframe = Literal["1m", "5m", "15m", "30m", "1h", "4h", "1d"]


class StrategicCandleSnapshot(DomainModel):
    """Compact causal projection of the latest candle visible at one decision boundary."""

    open_time: UtcDateTime
    close_time: UtcDateTime
    open: PositiveDecimal
    high: PositiveDecimal
    low: PositiveDecimal
    close: PositiveDecimal
    volume: NonNegativeDecimal
    is_final: bool
    updated_at: UtcDateTime


class StrategicTimeframeContext(DomainModel):
    """Bounded descriptive facts for one requested strategic timeframe."""

    timeframe: StrategicTimeframe
    availability: Literal["AVAILABLE", "PARTIAL", "MISSING"]
    requested_depth: PositiveInt
    candle_count: NonNegativeInt
    covered_from: UtcDateTime | None = None
    covered_to: UtcDateTime | None = None
    has_gaps: bool
    gap_count: NonNegativeInt
    is_stale: bool | None = None
    latest_candle: StrategicCandleSnapshot | None = None
    window_open: PositiveDecimal | None = None
    window_high: PositiveDecimal | None = None
    window_low: PositiveDecimal | None = None
    window_close: PositiveDecimal | None = None
    window_volume: NonNegativeDecimal | None = None
    return_fraction: Decimal | None = None

    @model_validator(mode="after")
    def validate_quality_state(self) -> "StrategicTimeframeContext":
        if self.has_gaps is not (self.gap_count > 0):
            raise ValueError("has_gaps must match gap_count")
        summary = (
            self.covered_from,
            self.covered_to,
            self.is_stale,
            self.latest_candle,
            self.window_open,
            self.window_high,
            self.window_low,
            self.window_close,
            self.window_volume,
        )
        if self.candle_count == 0:
            if self.availability != "MISSING":
                raise ValueError("empty timeframe context must be MISSING")
            if any(value is not None for value in summary) or self.gap_count != 0:
                raise ValueError("MISSING timeframe context cannot carry candle facts")
            if self.return_fraction is not None:
                raise ValueError("MISSING timeframe context cannot carry return_fraction")
            return self
        if self.availability == "MISSING":
            raise ValueError("non-empty timeframe context cannot be MISSING")
        if any(value is None for value in summary):
            raise ValueError("non-empty timeframe context requires complete summary fields")
        assert self.covered_from is not None
        assert self.covered_to is not None
        assert self.latest_candle is not None
        assert self.window_open is not None
        assert self.window_close is not None
        if self.covered_from > self.covered_to:
            raise ValueError("timeframe coverage cannot be inverted")
        if not self.latest_candle.open_time <= self.covered_to <= self.latest_candle.close_time:
            raise ValueError("covered_to must remain inside the latest candle interval")
        if self.candle_count < self.requested_depth or self.has_gaps:
            if self.availability != "PARTIAL":
                raise ValueError("incomplete or gapped timeframe context must be PARTIAL")
        elif self.availability != "AVAILABLE":
            raise ValueError("complete contiguous timeframe context must be AVAILABLE")
        expected_return = self.window_close / self.window_open - Decimal(1)
        if self.return_fraction != expected_return:
            raise ValueError("return_fraction must match window endpoints")
        return self


class StrategicMarketTimeframes(DomainModel):
    """Stable multi-timeframe context for one executable market."""

    symbol: NonEmptyText
    market_type: MarketType
    timeframes: Annotated[tuple[StrategicTimeframeContext, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_market_timeframes(self) -> "StrategicMarketTimeframes":
        parse_canonical_symbol(self.symbol)
        names = tuple(item.timeframe for item in self.timeframes)
        if len(set(names)) != len(names):
            raise ValueError("strategic timeframes must be unique per market")
        return self


class StrategicMultiTimeframeContext(DomainModel):
    """Versioned compact causal candle context shared across one strategic cycle."""

    context_version: Literal["strategic-mtf-v1"]
    as_of: UtcDateTime
    style: TradingStyle
    style_mapping_version: NonEmptyText
    markets: Annotated[tuple[StrategicMarketTimeframes, ...], Field(min_length=1)]
    total_candle_count: NonNegativeInt

    @model_validator(mode="after")
    def validate_context(self) -> "StrategicMultiTimeframeContext":
        ordered = tuple(
            sorted(self.markets, key=lambda item: (item.market_type.value, item.symbol))
        )
        if ordered != self.markets:
            raise ValueError("multi-timeframe markets must use deterministic sorted order")
        keys = tuple((item.symbol, item.market_type) for item in self.markets)
        if len(set(keys)) != len(keys):
            raise ValueError("multi-timeframe markets must be unique")
        expected_total = sum(
            timeframe.candle_count
            for market in self.markets
            for timeframe in market.timeframes
        )
        if self.total_candle_count != expected_total:
            raise ValueError("total_candle_count must match timeframe counts")
        for market in self.markets:
            for timeframe in market.timeframes:
                latest = timeframe.latest_candle
                if latest is not None:
                    if latest.updated_at > self.as_of or latest.open_time > self.as_of:
                        raise ValueError("multi-timeframe context contains post-as_of candle data")
                    if latest.is_final and latest.close_time > self.as_of:
                        raise ValueError("final candle cannot close after multi-timeframe as_of")
        return self


class MarketSelectionInput(DomainModel):
    """Causal research boundary shown to the same strategic Agent before market acquisition."""

    cycle_id: UUID
    created_at: UtcDateTime
    portfolio_state: PortfolioState
    executable_markets: tuple[ExecutableMarket, ...]
    aggressiveness: Annotated[int, Field(ge=1, le=10)]
    aggressiveness_context: AggressivenessContext | None = None
    trading_style_context: TradingStyleContext | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    execution_cost_context: ExecutionCostContext | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    multi_timeframe_context: StrategicMultiTimeframeContext | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
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
        if (self.trading_style_context is None) != (self.execution_cost_context is None):
            raise ValueError(
                "trading_style_context and execution_cost_context must be supplied together"
            )
        self._validate_multi_timeframe_context()
        manifest = self.experiment_manifest
        if manifest is not None:
            if self.aggressiveness_context is None:
                raise ValueError("experiment_manifest requires aggressiveness_context")
            if manifest.aggressiveness != self.aggressiveness_context:
                raise ValueError("experiment_manifest aggressiveness context mismatch")
            if manifest.agent_protocol is not None:
                if manifest.agent_protocol.executable_markets != self.executable_markets:
                    raise ValueError(
                        "executable market universe does not match the experiment Agent protocol"
                    )
            elif any(market.symbol not in manifest.universe for market in self.executable_markets):
                raise ValueError("executable market is outside the experiment universe")
        return self

    def _validate_multi_timeframe_context(self) -> None:
        context = self.multi_timeframe_context
        style = self.trading_style_context
        if context is None:
            return
        if style is None:
            raise ValueError("multi_timeframe_context requires trading_style_context")
        if context.as_of != self.created_at:
            raise ValueError("multi_timeframe_context as_of must match selection created_at")
        if (
            context.style is not style.style
            or context.style_mapping_version != style.mapping_version
        ):
            raise ValueError("multi_timeframe_context trading style identity mismatch")
        expected_markets = tuple(
            (market.symbol, market.market_type) for market in self.executable_markets
        )
        actual_markets = tuple((market.symbol, market.market_type) for market in context.markets)
        if actual_markets != expected_markets:
            raise ValueError("multi_timeframe_context markets must match executable_markets")
        for market in context.markets:
            actual_timeframes = tuple(item.timeframe for item in market.timeframes)
            if actual_timeframes != style.preferred_timeframes:
                raise ValueError("multi_timeframe_context timeframes must match trading style")


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
    trading_style_context: TradingStyleContext | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    execution_cost_context: ExecutionCostContext | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    multi_timeframe_context: StrategicMultiTimeframeContext | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
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
        if (self.trading_style_context is None) != (self.execution_cost_context is None):
            raise ValueError(
                "trading_style_context and execution_cost_context must be supplied together"
            )
        self._validate_multi_timeframe_context()
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
        if manifest.agent_protocol is not None:
            if selection is None:
                raise ValueError("multi-market experiment manifests require MarketSelection")
            selected_market = ExecutableMarket(
                symbol=selection.symbol,
                market_type=selection.market_type,
            )
            if selected_market not in manifest.agent_protocol.executable_markets:
                raise ValueError(
                    "AgentInput selected market is outside the typed experiment universe"
                )
        elif self.market_state.symbol not in manifest.universe:
            raise ValueError("AgentInput symbol is outside the experiment universe")
        return self

    def _validate_multi_timeframe_context(self) -> None:
        context = self.multi_timeframe_context
        style = self.trading_style_context
        if context is None:
            return
        if style is None:
            raise ValueError("multi_timeframe_context requires trading_style_context")
        if context.as_of > self.created_at:
            raise ValueError("multi_timeframe_context cannot postdate AgentInput")
        if (
            context.style is not style.style
            or context.style_mapping_version != style.mapping_version
        ):
            raise ValueError("multi_timeframe_context trading style identity mismatch")
        if self.market_selection is None:
            expected = ((self.market_state.symbol, self.market_state.market_type),)
        else:
            # Selection snapshots intentionally contain the entire executable universe and are
            # reused unchanged for the final decision. The selected market must merely be present.
            expected = None
        actual = tuple((market.symbol, market.market_type) for market in context.markets)
        if expected is not None and actual != expected:
            raise ValueError("legacy multi_timeframe_context must contain the current market only")
        if (self.market_state.symbol, self.market_state.market_type) not in actual:
            raise ValueError("multi_timeframe_context must contain the selected market")
        for market in context.markets:
            actual_timeframes = tuple(item.timeframe for item in market.timeframes)
            if actual_timeframes != style.preferred_timeframes:
                raise ValueError("multi_timeframe_context timeframes must match trading style")


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
            if self.reduce_only or self.margin_delta != 0:
                raise ValueError("SPOT fills cannot carry derivative execution fields")
            if self.action is TradingAction.BUY and self.realized_pnl != 0:
                raise ValueError("SPOT BUY fills cannot realize P&L")
            if self.funding_payment != 0 or self.contract_size != 1:
                raise ValueError("SPOT fills require contract_size=1 and no funding")
        return self


ExperimentManifest.model_rebuild()
