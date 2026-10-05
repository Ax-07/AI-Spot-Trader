import type { CycleSummaryResponse } from "@/lib/api/types";

export type EconomicOperationResponse = {
  paper_run_id: string | null;
  cycle_id: string;
  decision_index: number;
  execution_id: string;
  filled_at: string;
  symbol: string;
  market_type: "SPOT" | "PERPETUAL" | "FUTURE";
  action: "BUY" | "SELL";
  economic_effect: string;
  quantity: string;
  reference_price: string;
  price: string;
  notional: string;
  fee: string;
  spread_cost: string;
  slippage_cost: string;
  funding_pnl: string;
  execution_costs: string;
  total_costs: string;
  realized_pnl: string;
  position_before: string;
  position_after: string;
  fill_count: number;
  fill_ids: string[];
};

export type EconomicHistorySummaryResponse = {
  initial_equity: string | null;
  ending_equity: string | null;
  gross_pnl: string;
  net_pnl: string;
  realized_pnl: string;
  unrealized_pnl: string | null;
  fees: string;
  spread_cost: string;
  slippage_cost: string;
  funding_pnl: string;
  execution_costs: string;
  total_costs: string;
  max_drawdown_value: string;
  max_drawdown_fraction: string | null;
  current_drawdown_value: string;
  current_drawdown_fraction: string | null;
  current_exposure_value: string;
  current_exposure_fraction: string | null;
  completed_cycle_count: number;
  failed_cycle_count: number;
  decision_count: number;
  buy_decision_count: number;
  sell_decision_count: number;
  hold_count: number;
  reject_count: number;
  modify_count: number;
  trade_count: number;
  buy_trade_count: number;
  sell_trade_count: number;
  fill_count: number;
  total_notional: string;
  turnover_fraction: string | null;
  costs_to_notional_fraction: string | null;
  costs_to_initial_equity_fraction: string | null;
  duration_hours: string | null;
  fills_per_hour: string | null;
  market_switch_count: number;
  market_switches_per_hour: string | null;
  open_count: number;
  increase_count: number;
  reduce_count: number;
  close_count: number;
  flip_count: number;
  long_effect_count: number;
  short_effect_count: number;
  first_at: string | null;
  last_at: string | null;
};

export type PaperObservabilityBreakdownResponse = {
  scope: "TOTAL" | "SPOT" | "PERPETUAL";
  gross_pnl: string | null;
  net_pnl: string | null;
  realized_pnl: string;
  unrealized_pnl: string | null;
  fees: string;
  spread_cost: string;
  slippage_cost: string;
  funding_pnl: string;
  execution_costs: string;
  total_costs: string;
  total_notional: string;
  trade_count: number;
  fill_count: number;
  current_exposure_value: string | null;
  current_exposure_fraction: string | null;
};

export type PaperDecisionFunnelResponse = {
  decision_count: number;
  buy_count: number;
  sell_count: number;
  hold_count: number;
  risk_allow_count: number;
  risk_modify_count: number;
  risk_reject_count: number;
  execution_intent_count: number;
  decisions_with_fill: number;
  decisions_without_fill: number;
  fill_count: number;
  economic_trade_count: number;
};

export type PaperMarketObservabilityResponse = {
  symbol: string;
  market_type: "SPOT" | "PERPETUAL" | "FUTURE";
  decision_count: number;
  buy_count: number;
  sell_count: number;
  hold_count: number;
  risk_allow_count: number;
  risk_modify_count: number;
  risk_reject_count: number;
  decisions_with_fill: number;
  decisions_without_fill: number;
  trade_count: number;
  fill_count: number;
  total_notional: string;
  fees: string;
  spread_cost: string;
  slippage_cost: string;
  funding_pnl: string | null;
  execution_costs: string;
  total_costs: string | null;
  realized_pnl: string;
  current_exposure_value: string | null;
  current_exposure_fraction: string | null;
  unrealized_pnl: string | null;
};

export type PaperObservabilityResponse = {
  calculation_version: string;
  timezone: "UTC";
  source_digest: string;
  breakdowns: PaperObservabilityBreakdownResponse[];
  funnel: PaperDecisionFunnelResponse;
  markets: PaperMarketObservabilityResponse[];
  unavailable_metrics: string[];
};

export type EconomicHistoryResponse = {
  paper_run_id: string;
  lineage_paper_run_ids: string[];
  calculation_version: string;
  timezone: "UTC";
  source_digest: string;
  summary: EconomicHistorySummaryResponse;
  operations: EconomicOperationResponse[];
  cycles: CycleSummaryResponse[];
  observability: PaperObservabilityResponse | null;
};

export function paperObservabilityBreakdown(
  report: EconomicHistoryResponse,
  scope: "TOTAL" | "SPOT" | "PERPETUAL",
): PaperObservabilityBreakdownResponse | null {
  return report.observability?.breakdowns.find((item) => item.scope === scope) ?? null;
}

export function paperObservabilityMarketKey(
  item: Pick<PaperMarketObservabilityResponse, "symbol" | "market_type">,
): string {
  return `${item.symbol}::${item.market_type}`;
}

const API_PREFIX = "/backend";

function detailMessage(payload: unknown): string | null {
  if (typeof payload !== "object" || payload === null || !("detail" in payload)) return null;
  const detail = (payload as { detail?: unknown }).detail;
  return typeof detail === "string" ? detail : null;
}

export async function fetchEconomicHistory(paperRunId: string): Promise<EconomicHistoryResponse> {
  const params = new URLSearchParams({ paper_run_id: paperRunId });
  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}/api/v1/economic-history?${params.toString()}`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new Error("Backend inaccessible");
  }

  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    if (response.ok) throw new Error("Réponse backend invalide");
  }
  if (!response.ok) {
    throw new Error(detailMessage(payload) ?? `Erreur API ${response.status}`);
  }
  return payload as EconomicHistoryResponse;
}

export function economicHistoryExportPath(paperRunId: string): string {
  const params = new URLSearchParams({ paper_run_id: paperRunId });
  return `${API_PREFIX}/api/v1/economic-history/export?${params.toString()}`;
}
