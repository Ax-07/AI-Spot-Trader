import type {
  CampaignActivationResponse,
  CampaignConfiguration,
  CampaignResponse,
  ChatExchangeResponse,
  ChatHistoryResponse,
  CycleDetailResponse,
  CyclePageResponse,
  DecisionPageResponse,
  EngineStatusResponse,
  ExecutableMarketType,
  ExecutionPageResponse,
  HealthResponse,
  LatestErrorResponse,
  MarketStateResponse,
  PaperAnalyticsResponse,
  PaperRunPageResponse,
  PaperRunResponse,
  PortfolioResponse,
  PromptPreviewPhase,
  PromptPreviewResponse,
  RiskAssessmentPageResponse,
  StrategyCreateResponse,
  StrategyResponse,
  StrategyRevisionComparisonResponse,
  StrategyRevisionResponse,
} from "@/lib/api/types";
import type {
  CandleHistoryResponse,
  CandleStreamStatusResponse,
  CandleTimeframe,
} from "@/lib/market-candles";

const API_PREFIX = "/backend";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number | null,
    readonly detail: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function apiPath(path: string) {
  return `${API_PREFIX}${path}`;
}

export function backendWebSocketUrl(path: string) {
  if (typeof window === "undefined") return apiPath(path);
  const url = new URL(apiPath(path), window.location.href);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

function pydanticDetail(value: unknown): string | null {
  if (typeof value !== "object" || value === null) return null;
  const record = value as Record<string, unknown>;
  const message = typeof record.msg === "string" ? record.msg : null;
  const location = Array.isArray(record.loc)
    ? record.loc.filter((item) => typeof item === "string" || typeof item === "number").join(".")
    : "";
  if (!message) return null;
  return location ? `${location}: ${message}` : message;
}

function extractDetail(payload: unknown): string | null {
  if (typeof payload !== "object" || payload === null || !("detail" in payload)) return null;
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map(pydanticDetail).filter((item): item is string => Boolean(item));
    return messages.length ? messages.join(" · ") : null;
  }
  return pydanticDetail(detail);
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(apiPath(path), {
      ...init,
      cache: "no-store",
      headers: { Accept: "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError("Backend inaccessible", null);
  }

  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    if (response.ok) throw new ApiError("Réponse backend invalide", response.status);
  }

  if (!response.ok) {
    const detail = extractDetail(payload);
    throw new ApiError(detail ?? `Erreur API ${response.status}`, response.status, detail);
  }
  return payload as T;
}

function jsonBody(value: unknown): Pick<RequestInit, "headers" | "body"> {
  return { headers: { "Content-Type": "application/json" }, body: JSON.stringify(value) };
}

function candleQuery({
  symbol,
  marketType,
  timeframe,
  limit,
}: {
  symbol: string;
  marketType: ExecutableMarketType;
  timeframe: CandleTimeframe;
  limit?: number;
}) {
  const params = new URLSearchParams({ symbol, market_type: marketType, timeframe });
  if (limit !== undefined) params.set("limit", String(limit));
  return params.toString();
}

export const api = {
  health: () => requestJson<HealthResponse>("/health"),
  engine: () => requestJson<EngineStatusResponse>("/api/v1/engine"),
  startEngine: () => requestJson<EngineStatusResponse>("/api/v1/engine/start", { method: "POST" }),
  stopEngine: () => requestJson<EngineStatusResponse>("/api/v1/engine/stop", { method: "POST" }),
  runCycle: () => requestJson<EngineStatusResponse>("/api/v1/engine/run-cycle", { method: "POST" }),
  portfolio: () => requestJson<PortfolioResponse>("/api/v1/portfolio"),
  latestMarket: () => requestJson<MarketStateResponse>("/api/v1/market/latest"),
  latestError: () => requestJson<LatestErrorResponse>("/api/v1/errors/latest"),
  latestCycle: () => requestJson<CycleDetailResponse>("/api/v1/cycles/latest"),
  cycle: (cycleId: string) => requestJson<CycleDetailResponse>(`/api/v1/cycles/${encodeURIComponent(cycleId)}`),
  cycles: (limit = 12) => requestJson<CyclePageResponse>(`/api/v1/cycles?limit=${limit}&offset=0&order=desc`),
  decisions: (limit = 8) => requestJson<DecisionPageResponse>(`/api/v1/decisions?limit=${limit}&offset=0&order=desc`),
  riskAssessments: (limit = 8) => requestJson<RiskAssessmentPageResponse>(`/api/v1/risk-assessments?limit=${limit}&offset=0&order=desc`),
  executions: (limit = 8, filters?: { symbol?: string; action?: "BUY" | "SELL" }) => {
    const params = new URLSearchParams({ limit: String(limit), offset: "0", order: "desc" });
    if (filters?.symbol) params.set("symbol", filters.symbol);
    if (filters?.action) params.set("action", filters.action);
    return requestJson<ExecutionPageResponse>(`/api/v1/executions?${params.toString()}`);
  },
  candles: (input: { symbol: string; marketType: ExecutableMarketType; timeframe: CandleTimeframe; limit?: number }) =>
    requestJson<CandleHistoryResponse>(`/api/v1/markets/candles?${candleQuery(input)}`),
  candleStatus: (input: { symbol: string; marketType: ExecutableMarketType; timeframe: CandleTimeframe }) =>
    requestJson<CandleStreamStatusResponse>(`/api/v1/markets/candles/status?${candleQuery(input)}`),
  analytics: () => requestJson<PaperAnalyticsResponse>("/api/v1/analytics"),
  paperRuns: (limit = 100, offset = 0) => requestJson<PaperRunPageResponse>(`/api/v1/paper-runs?limit=${limit}&offset=${offset}&order=desc`),
  currentPaperRun: () => requestJson<PaperRunResponse>("/api/v1/paper-runs/current"),
  paperRun: (paperRunId: string) => requestJson<PaperRunResponse>(`/api/v1/paper-runs/${encodeURIComponent(paperRunId)}`),

  strategies: () => requestJson<StrategyResponse[]>("/api/v1/strategies"),
  strategy: (strategyId: string) => requestJson<StrategyResponse>(`/api/v1/strategies/${encodeURIComponent(strategyId)}`),
  createStrategy: (payload: { strategy_name: string; strategy_prompt: string }) =>
    requestJson<StrategyCreateResponse>("/api/v1/strategies", { method: "POST", ...jsonBody(payload) }),
  renameStrategy: (strategyId: string, strategyName: string) =>
    requestJson<StrategyResponse>(`/api/v1/strategies/${encodeURIComponent(strategyId)}`, { method: "PATCH", ...jsonBody({ strategy_name: strategyName }) }),
  archiveStrategy: (strategyId: string) =>
    requestJson<StrategyResponse>(`/api/v1/strategies/${encodeURIComponent(strategyId)}/archive`, { method: "POST" }),
  createStrategyRevision: (strategyId: string, strategyPrompt: string) =>
    requestJson<StrategyRevisionResponse>(`/api/v1/strategies/${encodeURIComponent(strategyId)}/revisions`, { method: "POST", ...jsonBody({ strategy_prompt: strategyPrompt }) }),
  strategyRevision: (strategyId: string, revision: number) =>
    requestJson<StrategyRevisionResponse>(`/api/v1/strategies/${encodeURIComponent(strategyId)}/revisions/${revision}`),
  compareStrategyRevisions: (strategyId: string, left: number, right: number) =>
    requestJson<StrategyRevisionComparisonResponse>(`/api/v1/strategies/${encodeURIComponent(strategyId)}/compare?left=${left}&right=${right}`),

  campaigns: () => requestJson<CampaignResponse[]>("/api/v1/campaigns"),
  activeCampaign: () => requestJson<CampaignActivationResponse>("/api/v1/campaigns/active"),
  campaign: (campaignId: string) => requestJson<CampaignResponse>(`/api/v1/campaigns/${encodeURIComponent(campaignId)}`),
  createCampaign: (payload: { strategy_id: string; strategy_revision: number; configuration: CampaignConfiguration }) =>
    requestJson<CampaignResponse>("/api/v1/campaigns", { method: "POST", ...jsonBody(payload) }),
  activateCampaign: (campaignId: string) =>
    requestJson<CampaignActivationResponse>(`/api/v1/campaigns/${encodeURIComponent(campaignId)}/activate`, { method: "POST" }),
  resumeCampaign: (campaignId: string) =>
    requestJson<CampaignActivationResponse>(`/api/v1/campaigns/${encodeURIComponent(campaignId)}/resume`, { method: "POST" }),

  promptPreview: (payload: { strategy_id: string; strategy_revision: number; aggressiveness: number; phase: PromptPreviewPhase }) =>
    requestJson<PromptPreviewResponse>("/api/v1/prompt-preview", { method: "POST", ...jsonBody(payload) }),

  sendChatMessage: (payload: { session_id: string | null; message: string; context_cycle_id?: string | null }) =>
    requestJson<ChatExchangeResponse>("/api/v1/chat/messages", { method: "POST", ...jsonBody(payload) }),
  chatHistory: (sessionId: string) =>
    requestJson<ChatHistoryResponse>(`/api/v1/chat/sessions/${encodeURIComponent(sessionId)}`),
};
