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
};

export type PortfolioResponse = {
  portfolio_state_id: string;
  as_of: string;
  mode: "PAPER";
  balances: AssetBalanceResponse[];
  positions: AssetPositionResponse[];
};

export type MarketStateResponse = {
  market_state_id: string;
  as_of: string;
  symbol: string;
  last_price: string;
  context: JsonObject | null;
};

export type CycleSummaryResponse = {
  cycle_id: string;
  status: string;
  recorded_at: string;
  decision_action: string | null;
  symbol: string | null;
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
  status: string;
  recorded_at: string;
  failure: CycleFailure | null;
  market_state_id: string | null;
  portfolio_state_before_id: string | null;
  portfolio_state_after_id: string | null;
  market_as_of: string | null;
  portfolio_before_as_of: string | null;
  portfolio_after_as_of: string | null;
  agent_input: JsonObject | null;
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
  recorded_at: string;
  failure: CycleFailure;
};

export type PaperAnalyticsSummaryResponse = {
  initial_equity: string | null;
  ending_equity: string | null;
  gross_pnl: string;
  net_pnl: string;
  fees: string;
  spread_cost: string;
  slippage_cost: string;
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
  trade_count: number;
};

export type PaperAnalyticsResponse = {
  calculation_version: string;
  timezone: "UTC";
  source_digest: string;
  summary: PaperAnalyticsSummaryResponse;
  points: PaperAnalyticsPointResponse[];
  daily: PaperDailyPerformanceResponse[];
};
