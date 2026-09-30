import type {
  CycleDetailResponse,
  CycleFailure,
  JsonObject,
  JsonValue,
  LatestErrorResponse,
} from "@/lib/api/types";

const dateTimeFormatter = new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "medium" });
const numberFormatter = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 10 });

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return dateTimeFormatter.format(date);
}

export function formatDecimal(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(parsed)) return String(value);
  return numberFormatter.format(parsed);
}

export function shortUuid(value: string | null | undefined): string {
  if (!value) return "—";
  return value.length > 12 ? `${value.slice(0, 8)}…${value.slice(-4)}` : value;
}

const FAILURE_LABELS: Record<string, string> = {
  TimeoutError: "Délai maximal du stage dépassé",
  LLMTimeoutError: "Timeout du fournisseur IA",
  LLMRateLimitError: "Limite temporaire du fournisseur IA",
  LLMQuotaError: "Quota / limite de dépenses du fournisseur IA",
  LLMProviderLimitError: "Autre limite du fournisseur IA",
  LLMServerError: "Autre erreur fournisseur IA",
  LLMNetworkError: "Autre erreur fournisseur IA",
  LLMHTTPError: "Autre erreur fournisseur IA",
  LLMTransportError: "Autre erreur fournisseur IA",
  LLMProviderError: "Autre erreur fournisseur IA",
};

export function formatFailure(failure: { stage: string; error_type: string; timed_out: boolean } | null | undefined): string {
  if (!failure) return "Aucune";
  const label = FAILURE_LABELS[failure.error_type] ?? failure.error_type;
  return `${failure.stage} · ${label}`;
}

export type CockpitFailurePresentation = {
  activeCycleFailure: CycleFailure | null;
  historicalError: LatestErrorResponse | null;
};

export function resolveCockpitFailurePresentation(
  latestCycle: Pick<CycleDetailResponse, "cycle_id" | "status" | "recorded_at" | "failure"> | null,
  latestError: LatestErrorResponse | null,
): CockpitFailurePresentation {
  if (!latestCycle) {
    return { activeCycleFailure: null, historicalError: null };
  }

  const activeCycleFailure = latestCycle.status === "FAILED" ? latestCycle.failure : null;
  if (!latestError) {
    return { activeCycleFailure, historicalError: null };
  }

  const errorMatchesActiveCycle = activeCycleFailure !== null && latestError.cycle_id === latestCycle.cycle_id;
  if (errorMatchesActiveCycle) {
    return { activeCycleFailure, historicalError: null };
  }

  const latestCycleTime = Date.parse(latestCycle.recorded_at);
  const latestErrorTime = Date.parse(latestError.recorded_at);
  const errorIsOlder = Number.isFinite(latestCycleTime) && Number.isFinite(latestErrorTime) && latestErrorTime < latestCycleTime;

  return {
    activeCycleFailure,
    historicalError: errorIsOlder ? latestError : null,
  };
}

function formatContextValue(value: JsonValue): string {
  if (value === null) return "—";
  if (typeof value === "boolean") return value ? "oui" : "non";
  if (typeof value === "number") return formatDecimal(value);
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return `${value.length} élément${value.length > 1 ? "s" : ""}`;
  return `${Object.keys(value).length} champ${Object.keys(value).length > 1 ? "s" : ""}`;
}

export function contextEntries(context: JsonObject | null, limit = 6): Array<[string, string]> {
  if (!context) return [];
  return Object.entries(context).slice(0, limit).map(([key, value]) => [key, formatContextValue(value)]);
}
