import type {
  CycleDetailResponse,
  CyclePageResponse,
  DecisionPageResponse,
  EngineStatusResponse,
  ExecutionPageResponse,
  HealthResponse,
  LatestErrorResponse,
  MarketStateResponse,
  PaperAnalyticsResponse,
  PortfolioResponse,
  RiskAssessmentPageResponse,
} from "@/lib/api/types";

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

function extractDetail(payload: unknown): string | null {
  if (
    typeof payload === "object" &&
    payload !== null &&
    "detail" in payload &&
    typeof payload.detail === "string"
  ) {
    return payload.detail;
  }
  return null;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(apiPath(path), {
      ...init,
      cache: "no-store",
      headers: {
        Accept: "application/json",
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError("Backend inaccessible", null);
  }

  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    if (response.ok) {
      throw new ApiError("Réponse backend invalide", response.status);
    }
  }

  if (!response.ok) {
    const detail = extractDetail(payload);
    throw new ApiError(detail ?? `Erreur API ${response.status}`, response.status, detail);
  }

  return payload as T;
}

export const api = {
  health: () => requestJson<HealthResponse>("/health"),
  engine: () => requestJson<EngineStatusResponse>("/api/v1/engine"),
  startEngine: () =>
    requestJson<EngineStatusResponse>("/api/v1/engine/start", { method: "POST" }),
  stopEngine: () =>
    requestJson<EngineStatusResponse>("/api/v1/engine/stop", { method: "POST" }),
  portfolio: () => requestJson<PortfolioResponse>("/api/v1/portfolio"),
  latestMarket: () => requestJson<MarketStateResponse>("/api/v1/market/latest"),
  latestError: () => requestJson<LatestErrorResponse>("/api/v1/errors/latest"),
  latestCycle: () => requestJson<CycleDetailResponse>("/api/v1/cycles/latest"),
  cycle: (cycleId: string) =>
    requestJson<CycleDetailResponse>(`/api/v1/cycles/${encodeURIComponent(cycleId)}`),
  cycles: (limit = 12) =>
    requestJson<CyclePageResponse>(`/api/v1/cycles?limit=${limit}&offset=0&order=desc`),
  decisions: (limit = 8) =>
    requestJson<DecisionPageResponse>(`/api/v1/decisions?limit=${limit}&offset=0&order=desc`),
  riskAssessments: (limit = 8) =>
    requestJson<RiskAssessmentPageResponse>(
      `/api/v1/risk-assessments?limit=${limit}&offset=0&order=desc`,
    ),
  executions: (limit = 8) =>
    requestJson<ExecutionPageResponse>(
      `/api/v1/executions?limit=${limit}&offset=0&order=desc`,
    ),
  analytics: () => requestJson<PaperAnalyticsResponse>("/api/v1/analytics"),
};
