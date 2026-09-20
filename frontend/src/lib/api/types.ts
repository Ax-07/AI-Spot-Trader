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
