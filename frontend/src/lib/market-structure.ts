import type { AttentionTimeframe, MarketAttentionSnapshot } from "./market-attention";

export type SwingKind = "HIGH" | "LOW";
export type SwingClassification = "HH" | "HL" | "LH" | "LL";
export type MarketStructureState = "BULLISH" | "BEARISH" | "RANGE" | "TRANSITION" | "UNKNOWN";
export type MultiTimeframeStructureState = MarketStructureState | "MIXED";
export type StructureEvent = "BOS_UP" | "BOS_DOWN" | "CHOCH_UP" | "CHOCH_DOWN";

export type SwingPoint = {
  kind: SwingKind;
  price: string;
  open_time: string;
  confirmed_at: string;
  classification: SwingClassification | null;
};

export type TimeframeMarketStructure = {
  timeframe: AttentionTimeframe;
  state: MarketStructureState;
  event: StructureEvent | null;
  history_count: number;
  latest_final_close: string | null;
  confirmed_swing_highs: SwingPoint[];
  confirmed_swing_lows: SwingPoint[];
  swings: SwingPoint[];
  sequence: SwingClassification[];
  error_type: string | null;
};

export type MultiTimeframeMarketStructure = {
  observed_at: string;
  global_state: MultiTimeframeStructureState;
  timeframes: TimeframeMarketStructure[];
};

type StructuredMarketAttentionSnapshot = MarketAttentionSnapshot & {
  market_structure?: MultiTimeframeMarketStructure;
};

export function marketStructure(
  item: MarketAttentionSnapshot,
): MultiTimeframeMarketStructure | null {
  return (item as StructuredMarketAttentionSnapshot).market_structure ?? null;
}

export function structureTimeframe(
  structure: MultiTimeframeMarketStructure | null | undefined,
  timeframe: AttentionTimeframe,
): TimeframeMarketStructure | null {
  return structure?.timeframes.find((item) => item.timeframe === timeframe) ?? null;
}

export function structureStateLabel(
  value: MultiTimeframeStructureState | null | undefined,
): string {
  if (value === "BULLISH") return "Haussière";
  if (value === "BEARISH") return "Baissière";
  if (value === "RANGE") return "Range";
  if (value === "TRANSITION") return "Transition";
  if (value === "MIXED") return "Mixte";
  return "Indéterminée";
}

export function timeframeStructureLabel(
  value: TimeframeMarketStructure | null | undefined,
): string {
  if (value?.state === "TRANSITION" && value.event === "CHOCH_DOWN") {
    return "Transition baissière";
  }
  if (value?.state === "TRANSITION" && value.event === "CHOCH_UP") {
    return "Transition haussière";
  }
  return structureStateLabel(value?.state);
}

export function structureEventLabel(value: StructureEvent | null | undefined): string | null {
  if (value === "BOS_UP") return "BOS haussier";
  if (value === "BOS_DOWN") return "BOS baissier";
  if (value === "CHOCH_UP") return "Changement de caractère haussier";
  if (value === "CHOCH_DOWN") return "Rupture de structure haussière";
  return null;
}

export function swingSequenceLabel(
  value: TimeframeMarketStructure | null | undefined,
): string {
  if (!value?.sequence.length) return "—";
  return value.sequence.join(" → ");
}
