import type { JsonObject, JsonValue } from "@/lib/api/types";

const dateTimeFormatter = new Intl.DateTimeFormat("fr-FR", {
  dateStyle: "short",
  timeStyle: "medium",
});

const numberFormatter = new Intl.NumberFormat("fr-FR", {
  maximumFractionDigits: 10,
});

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

export function formatFailure(
  failure: { stage: string; error_type: string; timed_out: boolean } | null | undefined,
): string {
  if (!failure) return "Aucune";
  return `${failure.stage} · ${failure.error_type}${failure.timed_out ? " · timeout" : ""}`;
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
  return Object.entries(context)
    .slice(0, limit)
    .map(([key, value]) => [key, formatContextValue(value)]);
}
