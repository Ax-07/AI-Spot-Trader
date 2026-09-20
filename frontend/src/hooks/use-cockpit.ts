"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError } from "@/lib/api/client";
import type {
  CycleDetailResponse,
  CyclePageResponse,
  DecisionPageResponse,
  EngineStatusResponse,
  ExecutionPageResponse,
  HealthResponse,
  LatestErrorResponse,
  MarketStateResponse,
  PortfolioResponse,
  RiskAssessmentPageResponse,
} from "@/lib/api/types";

export type ResourceState<T> =
  | { kind: "loading" }
  | { kind: "ready"; data: T }
  | { kind: "empty"; message: string }
  | { kind: "unavailable"; message: string }
  | { kind: "error"; message: string };

type CockpitResources = {
  health: ResourceState<HealthResponse>;
  engine: ResourceState<EngineStatusResponse>;
  portfolio: ResourceState<PortfolioResponse>;
  market: ResourceState<MarketStateResponse>;
  latestCycle: ResourceState<CycleDetailResponse>;
  latestError: ResourceState<LatestErrorResponse>;
  cycles: ResourceState<CyclePageResponse>;
  decisions: ResourceState<DecisionPageResponse>;
  riskAssessments: ResourceState<RiskAssessmentPageResponse>;
  executions: ResourceState<ExecutionPageResponse>;
};

const loading = { kind: "loading" } as const;
const POLL_INTERVAL_MS = 10_000;

async function loadResource<T>(
  request: () => Promise<T>,
  emptyMessage: string,
  unavailableMessage: string,
): Promise<ResourceState<T>> {
  try {
    return { kind: "ready", data: await request() };
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 404) {
        return { kind: "empty", message: emptyMessage };
      }
      if (error.status === 503) {
        return { kind: "unavailable", message: unavailableMessage };
      }
      return { kind: "error", message: error.message };
    }
    return { kind: "error", message: "Erreur inattendue côté cockpit" };
  }
}

export function useCockpit() {
  const [resources, setResources] = useState<CockpitResources>({
    health: loading,
    engine: loading,
    portfolio: loading,
    market: loading,
    latestCycle: loading,
    latestError: loading,
    cycles: loading,
    decisions: loading,
    riskAssessments: loading,
    executions: loading,
  });
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const [controlPending, setControlPending] = useState<"start" | "stop" | null>(null);
  const [controlError, setControlError] = useState<string | null>(null);
  const refreshInFlight = useRef(false);

  const refresh = useCallback(async () => {
    if (refreshInFlight.current) return;
    refreshInFlight.current = true;
    setRefreshing(true);

    try {
      const [
        health,
        engine,
        portfolio,
        market,
        latestCycle,
        latestError,
        cycles,
        decisions,
        riskAssessments,
        executions,
      ] = await Promise.all([
        loadResource(api.health, "Aucune donnée health", "Backend indisponible"),
        loadResource(api.engine, "Moteur sans état", "Moteur non configuré"),
        loadResource(api.portfolio, "Portefeuille vide", "Portefeuille PAPER non configuré"),
        loadResource(api.latestMarket, "Aucun marché durable", "Audit store non configuré"),
        loadResource(api.latestCycle, "Aucun cycle journalisé", "Audit store non configuré"),
        loadResource(api.latestError, "Aucune erreur technique journalisée", "Audit store non configuré"),
        loadResource(() => api.cycles(), "Aucun cycle journalisé", "Audit store non configuré"),
        loadResource(() => api.decisions(), "Aucune décision journalisée", "Audit store non configuré"),
        loadResource(
          () => api.riskAssessments(),
          "Aucun résultat Risk journalisé",
          "Audit store non configuré",
        ),
        loadResource(() => api.executions(), "Aucune exécution journalisée", "Audit store non configuré"),
      ]);

      setResources({
        health,
        engine,
        portfolio,
        market,
        latestCycle,
        latestError,
        cycles,
        decisions,
        riskAssessments,
        executions,
      });
      setLastUpdatedAt(new Date().toISOString());
    } finally {
      setRefreshing(false);
      refreshInFlight.current = false;
    }
  }, []);

  useEffect(() => {
    void refresh();

    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void refresh();
      }
    }, POLL_INTERVAL_MS);

    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        void refresh();
      }
    };
    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [refresh]);

  const runControl = useCallback(
    async (action: "start" | "stop") => {
      if (controlPending) return;
      setControlPending(action);
      setControlError(null);
      try {
        const engine = action === "start" ? await api.startEngine() : await api.stopEngine();
        setResources((current) => ({
          ...current,
          engine: { kind: "ready", data: engine },
        }));
        await refresh();
      } catch (error) {
        setControlError(error instanceof ApiError ? error.message : "Commande moteur impossible");
      } finally {
        setControlPending(null);
      }
    },
    [controlPending, refresh],
  );

  return {
    resources,
    refreshing,
    lastUpdatedAt,
    controlPending,
    controlError,
    refresh,
    startEngine: () => runControl("start"),
    stopEngine: () => runControl("stop"),
  };
}
