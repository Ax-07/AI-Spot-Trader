export type StrategicThesisStatus =
  | "NEW"
  | "CONFIRMED"
  | "WEAKENING"
  | "INVALIDATED"
  | "COMPLETED";

export type StrategicThesisReviewResponse = {
  reviewed_at: string;
  status: StrategicThesisStatus;
  summary: string;
};

export type StrategicThesisPositionResponse = {
  thesis_id: string | null;
  symbol: string;
  market_type: "SPOT" | "PERPETUAL";
  side: "LONG" | "SHORT";
  quantity: string;
  memory_state: "ACTIVE" | "UNAVAILABLE_LEGACY";
  origin: "AGENT_OPENING" | "LEGACY_ADOPTION" | null;
  status: StrategicThesisStatus | null;
  created_at: string | null;
  activated_at: string | null;
  updated_at: string | null;
  horizon: string | null;
  thesis_summary: string | null;
  supporting_facts: string[];
  invalidation_conditions: string[];
  last_review: StrategicThesisReviewResponse | null;
};

export type StrategicThesisRevisionState =
  | "ACTIVE_COMMITTED"
  | "RETIRED_COMMITTED"
  | "PROPOSED_NOT_ACTIVATED"
  | "FAILED_CYCLE"
  | "UNAVAILABLE_LEGACY";

export type StrategicThesisRevisionResponse = {
  cycle_id: string;
  paper_run_id: string | null;
  decision_index: number;
  decision_id: string | null;
  thesis_id: string | null;
  reviewed_at: string;
  symbol: string;
  market_type: "SPOT" | "PERPETUAL";
  side: "LONG" | "SHORT" | null;
  status: StrategicThesisStatus;
  horizon: string;
  thesis_summary: string;
  review_summary: string;
  supporting_facts: string[];
  invalidation_conditions: string[];
  agent_action: "BUY" | "SELL" | "HOLD";
  risk_status: "ALLOW" | "MODIFY" | "REJECT" | null;
  fill_count: number;
  cycle_status: string;
  active_after_cycle: boolean | null;
  revision_state: StrategicThesisRevisionState;
};

export type StrategicThesisObservabilityResponse = {
  paper_run_id: string;
  lineage_paper_run_ids: string[];
  calculation_version: string;
  timezone: "UTC";
  as_of: string | null;
  positions: StrategicThesisPositionResponse[];
  revisions: StrategicThesisRevisionResponse[];
  total_revision_count: number;
  history_limit: number;
};

const API_PREFIX = "/backend";

function detailMessage(payload: unknown): string | null {
  if (typeof payload !== "object" || payload === null || !("detail" in payload)) return null;
  const detail = (payload as { detail?: unknown }).detail;
  return typeof detail === "string" ? detail : null;
}

export async function fetchStrategicTheses(
  paperRunId: string,
  historyLimit = 100,
): Promise<StrategicThesisObservabilityResponse> {
  const params = new URLSearchParams({
    paper_run_id: paperRunId,
    history_limit: String(historyLimit),
  });
  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}/api/v1/strategic-theses?${params.toString()}`, {
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
  return payload as StrategicThesisObservabilityResponse;
}

export function strategicThesisPositionKey(
  item: Pick<StrategicThesisPositionResponse, "symbol" | "market_type" | "side">,
): string {
  return `${item.symbol}::${item.market_type}::${item.side}`;
}

export function revisionsForStrategicPosition(
  report: StrategicThesisObservabilityResponse,
  position: Pick<StrategicThesisPositionResponse, "thesis_id">,
): StrategicThesisRevisionResponse[] {
  if (!position.thesis_id) return [];
  return report.revisions.filter((item) => item.thesis_id === position.thesis_id);
}
