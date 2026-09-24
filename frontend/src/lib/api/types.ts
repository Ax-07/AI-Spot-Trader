export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[];
export type JsonObject = { [key: string]: JsonValue };

export type HealthResponse = {
  status: "ok";
  service: string;
  environment: string;
};

export type CycleFailure = {
  stage: string;
  error_type: string;
  timed_out: boolean;
};

export type EngineStatus = "RUNNING" | "STOPPED" | "UNAVAILABLE";

export type EngineStatusResponse = {
  configured: boolean;
  status: EngineStatus;
  last_cycle_id: string | null;
  last_cycle_status: string | null;
  last_cycle_failure: CycleFailure | null;
  last_unexpected_error_type: string | null;
};

export type AssetBalanceResponse = {
  asset: string;
  available: string;
};

export type AssetPositionResponse = {
  asset: string;
  quantity: string;
  available: string;
  average_entry_price: string | null;
  remaining_cost_basis: string | null;
  realized_pnl: string;
  accounting_complete: boolean;
};

export type DerivativePositionResponse = {
  symbol: string;
  side: "LONG" | "SHORT";
  quantity: string;
  average_entry_price: string;
  mark_price: string;
  contract_size: string;
  notional: string;
  realized_pnl: string;
  unrealized_pnl: string;
  leverage: string;
  margin_used: string;
  initial_margin_rate: string;
  maintenance_margin_rate: string;
  maintenance_margin: string;
  cumulative_funding: string;
  liquidation_price: string | null;
  margin_mode: "ISOLATED" | "CROSS";
  funding_updated_at: string | null;
};

export type PortfolioResponse = {
  portfolio_state_id: string;
  as_of: string;
  mode: "PAPER";
  balances: AssetBalanceResponse[];
  positions: AssetPositionResponse[];
  derivative_positions: DerivativePositionResponse[];
};

export type ExecutableMarketType = "SPOT" | "PERPETUAL";
export type HistoricalMarketType = ExecutableMarketType | "FUTURE";

export type ExecutableMarketResponse = {
  symbol: string;
  market_type: ExecutableMarketType;
};

export type MarketStateResponse = {
  market_state_id: string;
  as_of: string;
  symbol: string;
  last_price: string;
  market_type: HistoricalMarketType;
  context: JsonObject | null;
  derivative: JsonObject | null;
};

export type CycleSummaryResponse = {
  cycle_id: string;
  paper_run_id: string | null;
  status: string;
  recorded_at: string;
  decision_action: string | null;
  symbol: string | null;
  market_type: HistoricalMarketType | null;
  risk_status: string | null;
  execution_id: string | null;
  fill_count: number;
  failure: CycleFailure | null;
};

export type FillResponse = {
  fill_id: string;
  execution_id: string;
  market_state_id: string;
  filled_at: string;
  payload: JsonObject;
};

export type DecisionResponse = {
  decision_id: string;
  cycle_id: string;
  created_at: string;
  action: string;
  symbol: string;
  payload: JsonObject;
};

export type RiskAssessmentResponse = {
  risk_assessment_id: string;
  cycle_id: string;
  decision_id: string;
  assessed_at: string;
  status: string;
  payload: JsonObject;
};

export type ExecutionResponse = {
  execution_id: string;
  cycle_id: string;
  decision_id: string;
  risk_assessment_id: string;
  created_at: string;
  action: string;
  symbol: string;
  payload: JsonObject;
  fills: FillResponse[];
};

export type CycleDetailResponse = {
  cycle_id: string;
  paper_run_id: string | null;
  status: string;
  recorded_at: string;
  failure: CycleFailure | null;
  market_state_id: string | null;
  portfolio_state_before_id: string | null;
  portfolio_state_after_id: string | null;
  market_as_of: string | null;
  portfolio_before_as_of: string | null;
  portfolio_after_as_of: string | null;
  market_selection_input: JsonObject | null;
  market_selection: JsonObject | null;
  agent_input: JsonObject | null;
  agent_tool_traces: JsonObject[];
  decision: JsonObject | null;
  risk_assessment: JsonObject | null;
  execution_intent: JsonObject | null;
  fills: FillResponse[];
  portfolio_state_after: JsonObject | null;
};

export type PageResponse<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export type CyclePageResponse = PageResponse<CycleSummaryResponse>;
export type DecisionPageResponse = PageResponse<DecisionResponse>;
export type RiskAssessmentPageResponse = PageResponse<RiskAssessmentResponse>;
export type ExecutionPageResponse = PageResponse<ExecutionResponse>;

export type LatestErrorResponse = {
  cycle_id: string;
  paper_run_id: string | null;
  recorded_at: string;
  failure: CycleFailure;
};

export type PaperRunResponse = {
  paper_run_id: string;
  campaign_id: string | null;
  started_at: string;
  ended_at: string | null;
  market_type: HistoricalMarketType | null;
  symbol: string | null;
  execution_universe: ExecutableMarketResponse[];
  resumed_from_paper_run_id: string | null;
  recovery_version: string | null;
  is_current: boolean;
};

export type PaperRunPageResponse = PageResponse<PaperRunResponse>;

export type PaperAnalyticsSummaryResponse = {
  initial_equity: string | null;
  ending_equity: string | null;
  gross_pnl: string;
  net_pnl: string;
  fees: string;
  spread_cost: string;
  slippage_cost: string;
  funding_pnl: string;
  max_drawdown_value: string;
  max_drawdown_fraction: string | null;
  current_drawdown_value: string;
  current_drawdown_fraction: string | null;
  current_exposure_value: string;
  current_exposure_fraction: string | null;
  trade_count: number;
  buy_trade_count: number;
  sell_trade_count: number;
  hold_count: number;
  reject_count: number;
  modify_count: number;
  completed_cycle_count: number;
  failed_cycle_count: number;
  valued_cycle_count: number;
  first_at: string | null;
  last_at: string | null;
};

export type PaperAnalyticsPointResponse = {
  cycle_id: string;
  at: string;
  status: string;
  action: string | null;
  risk_status: string | null;
  symbol: string;
  reference_price: string;
  equity: string;
  gross_pnl: string;
  net_pnl: string;
  cumulative_fees: string;
  cumulative_spread_cost: string;
  cumulative_slippage_cost: string;
  cumulative_funding_pnl: string;
  exposure_value: string;
  exposure_fraction: string | null;
  cumulative_return_fraction: string | null;
  drawdown_value: string;
  drawdown_fraction: string | null;
  trade_count: number;
};

export type PaperDailyPerformanceResponse = {
  day: string;
  closing_at: string;
  closing_equity: string;
  gross_pnl: string;
  net_pnl: string;
  daily_net_pnl: string;
  daily_return_fraction: string | null;
  cumulative_return_fraction: string | null;
  fees: string;
  spread_cost: string;
  slippage_cost: string;
  funding_pnl: string;
  trade_count: number;
};

export type PaperAnalyticsResponse = {
  paper_run_id: string | null;
  calculation_version: string;
  timezone: "UTC";
  source_digest: string;
  summary: PaperAnalyticsSummaryResponse;
  points: PaperAnalyticsPointResponse[];
  daily: PaperDailyPerformanceResponse[];
};

export type ChatRole = "OPERATOR" | "AGENT";

export type ChatMessageResponse = {
  message_id: string;
  created_at: string;
  role: ChatRole;
  content: string;
};

export type ChatExchangeResponse = {
  session_id: string;
  model: LlmModel;
  historical_cycle_id: string | null;
  operator_message: ChatMessageResponse;
  agent_message: ChatMessageResponse;
  history_size: number;
};

export type ChatHistoryResponse = {
  session_id: string;
  model: LlmModel;
  messages: ChatMessageResponse[];
  max_messages: number;
};

export type LlmModel = "gpt-5.6-luna" | "gpt-5.6-sol";

export type StrategyResponse = {
  strategy_id: string;
  strategy_name: string;
  created_at: string;
  archived_at: string | null;
  latest_revision: number | null;
};

export type StrategyRevisionResponse = {
  strategy_id: string;
  strategy_revision: number;
  strategy_prompt: string;
  strategy_prompt_digest: string;
  base_agent_contract_version: string;
  created_at: string;
};

export type StrategyCreateResponse = {
  strategy: StrategyResponse;
  revision: StrategyRevisionResponse;
};

export type StrategyRevisionComparisonResponse = {
  strategy_id: string;
  left_revision: number;
  right_revision: number;
  left_digest: string;
  right_digest: string;
  identical: boolean;
  unified_diff: string;
};

export type CampaignConfiguration = {
  configuration_version: "paper-control-plane-config-v1";
  llm_model: LlmModel;
  aggressiveness: number;
  trading_cadence_seconds: number;
  paper_initial_capital: string;
  paper_settlement_asset: string;
  paper_executable_markets: ExecutableMarketResponse[];
  paper_fee_rate: string;
  paper_spread_bps: string;
  paper_slippage_bps: string;
  paper_derivative_leverage: string;
  paper_derivative_margin_mode: "ISOLATED";
  risk_max_order_notional: string;
  risk_allowed_pairs: string[];
  risk_allow_quantity_reduction: boolean;
  risk_max_derivative_leverage: string;
  risk_max_derivative_position_notional: string | null;
  risk_max_total_derivative_exposure: string | null;
  risk_derivative_liquidation_buffer_ratio: string;
  cycle_market_timeout_seconds: number;
  cycle_agent_timeout_seconds: number;
  cycle_broker_timeout_seconds: number;
};

export type CampaignResponse = {
  campaign_id: string;
  created_at: string;
  strategy_id: string;
  strategy_revision: number;
  strategy_prompt_digest: string;
  base_agent_contract_version: string;
  configuration: CampaignConfiguration;
  configuration_digest: string;
  experiment_protocol_version: "paper-experiment-v4";
  experiment_digest: string;
};

export type CampaignActivationResponse = {
  campaign: CampaignResponse;
  paper_run_id: string | null;
  engine: EngineStatusResponse;
};

export type PromptPreviewPhase = "MARKET_SELECTION" | "FINAL_DECISION";

export type PromptPreviewResponse = {
  strategy_id: string;
  strategy_revision: number;
  strategy_prompt_digest: string;
  base_agent_contract_version: string;
  aggressiveness: number;
  phase: PromptPreviewPhase;
  instructions: string;
  dynamic_input_model: "MarketSelectionInput" | "AgentInput";
  dynamic_input: null;
  note: string;
};
