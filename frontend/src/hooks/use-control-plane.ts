"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, ApiError } from "@/lib/api/client";
import type {
  CampaignActivationResponse,
  CampaignConfiguration,
  CampaignResponse,
  EngineStatusResponse,
  PaperRunPageResponse,
  PromptPreviewPhase,
  PromptPreviewResponse,
  StrategyResponse,
  StrategyRevisionComparisonResponse,
  StrategyRevisionResponse,
} from "@/lib/api/types";

const POLL_INTERVAL_MS = 10_000;

export type ControlFeedback = {
  tone: "success" | "error";
  message: string;
  status: number | null;
};

type ControlPlaneSnapshot = {
  strategies: StrategyResponse[];
  campaigns: CampaignResponse[];
  activeCampaign: CampaignActivationResponse | null;
  paperRuns: PaperRunPageResponse;
  engine: EngineStatusResponse | null;
};

const EMPTY_PAPER_RUNS: PaperRunPageResponse = {
  items: [],
  total: 0,
  limit: 100,
  offset: 0,
};

function actionFailure(error: unknown, fallback: string): ControlFeedback {
  if (error instanceof ApiError) {
    const prefix = error.status === null ? "Réseau" : `HTTP ${error.status}`;
    return {
      tone: "error",
      status: error.status,
      message: `${prefix} · ${error.message}`,
    };
  }
  return { tone: "error", status: null, message: fallback };
}

export function useControlPlane() {
  const [snapshot, setSnapshot] = useState<ControlPlaneSnapshot>({
    strategies: [],
    campaigns: [],
    activeCampaign: null,
    paperRuns: EMPTY_PAPER_RUNS,
    engine: null,
  });
  const [selectedStrategyId, setSelectedStrategyId] = useState<string | null>(null);
  const [revisions, setRevisions] = useState<StrategyRevisionResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [revisionsLoading, setRevisionsLoading] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<ControlFeedback | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const refreshInFlight = useRef(false);

  const refresh = useCallback(async () => {
    if (refreshInFlight.current) return;
    refreshInFlight.current = true;
    setRefreshing(true);
    try {
      const activePromise = api.activeCampaign().catch((error: unknown) => {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      });
      const [strategies, campaigns, activeCampaign, paperRuns, engine] = await Promise.all([
        api.strategies(),
        api.campaigns(),
        activePromise,
        api.paperRuns(100, 0),
        api.engine(),
      ]);
      setSnapshot({ strategies, campaigns, activeCampaign, paperRuns, engine });
      setSelectedStrategyId((current) => {
        if (current && strategies.some((item) => item.strategy_id === current)) return current;
        return (
          strategies.find((item) => item.archived_at === null)?.strategy_id ??
          strategies[0]?.strategy_id ??
          null
        );
      });
      setLastUpdatedAt(new Date().toISOString());
    } catch (error) {
      setFeedback(actionFailure(error, "Chargement du Control Plane impossible"));
    } finally {
      setLoading(false);
      setRefreshing(false);
      refreshInFlight.current = false;
    }
  }, []);

  useEffect(() => {
    const initialRefresh = window.setTimeout(() => {
      void refresh();
    }, 0);
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") void refresh();
    }, POLL_INTERVAL_MS);
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      window.clearTimeout(initialRefresh);
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [refresh]);

  const selectedStrategy = useMemo(
    () => snapshot.strategies.find((item) => item.strategy_id === selectedStrategyId) ?? null,
    [selectedStrategyId, snapshot.strategies],
  );

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!selectedStrategy || !selectedStrategy.latest_revision) {
        setRevisions([]);
        return;
      }
      setRevisionsLoading(true);
      try {
        const values = await Promise.all(
          Array.from({ length: selectedStrategy.latest_revision }, (_, index) =>
            api.strategyRevision(selectedStrategy.strategy_id, index + 1),
          ),
        );
        if (!cancelled) setRevisions(values.sort((a, b) => b.strategy_revision - a.strategy_revision));
      } catch (error) {
        if (!cancelled) {
          setRevisions([]);
          setFeedback(actionFailure(error, "Lecture des révisions impossible"));
        }
      } finally {
        if (!cancelled) setRevisionsLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [selectedStrategy]);

  const mutate = useCallback(
    async <T,>(
      action: string,
      operation: () => Promise<T>,
      successMessage: string,
      after?: (value: T) => void,
    ): Promise<T | null> => {
      if (busyAction) return null;
      setBusyAction(action);
      setFeedback(null);
      try {
        const value = await operation();
        after?.(value);
        setFeedback({ tone: "success", status: null, message: successMessage });
        await refresh();
        return value;
      } catch (error) {
        setFeedback(actionFailure(error, "Opération Control Plane impossible"));
        return null;
      } finally {
        setBusyAction(null);
      }
    },
    [busyAction, refresh],
  );

  const createStrategy = useCallback(
    (strategyName: string, strategyPrompt: string) =>
      mutate(
        "create-strategy",
        () => api.createStrategy({ strategy_name: strategyName, strategy_prompt: strategyPrompt }),
        "Strategy créée avec sa révision 1 immuable.",
        (value) => setSelectedStrategyId(value.strategy.strategy_id),
      ),
    [mutate],
  );

  const renameStrategy = useCallback(
    (strategyId: string, strategyName: string) =>
      mutate(
        "rename-strategy",
        () => api.renameStrategy(strategyId, strategyName),
        "Strategy renommée sans modifier ses révisions.",
      ),
    [mutate],
  );

  const archiveStrategy = useCallback(
    (strategyId: string) =>
      mutate(
        "archive-strategy",
        () => api.archiveStrategy(strategyId),
        "Strategy archivée. Le backend refusera toute nouvelle révision ou Campaign.",
      ),
    [mutate],
  );

  const createRevision = useCallback(
    (strategyId: string, strategyPrompt: string) =>
      mutate(
        "create-revision",
        () => api.createStrategyRevision(strategyId, strategyPrompt),
        "Nouvelle StrategyRevision immuable créée.",
      ),
    [mutate],
  );

  const createCampaign = useCallback(
    (strategyId: string, strategyRevision: number, configuration: CampaignConfiguration) =>
      mutate(
        "create-campaign",
        () =>
          api.createCampaign({
            strategy_id: strategyId,
            strategy_revision: strategyRevision,
            configuration,
          }),
        "Nouvelle Campaign persistée. Sa configuration et ses digests sont désormais immuables.",
      ),
    [mutate],
  );

  const activateCampaign = useCallback(
    (campaignId: string) =>
      mutate(
        "activate-campaign",
        () => api.activateCampaign(campaignId),
        "Activation fraîche effectuée. Un nouveau PAPER run est associé à la Campaign.",
      ),
    [mutate],
  );

  const resumeCampaign = useCallback(
    (campaignId: string) =>
      mutate(
        "resume-campaign",
        () => api.resumeCampaign(campaignId),
        "Reprise explicite effectuée via le recovery canonique du backend.",
      ),
    [mutate],
  );

  const engineCommand = useCallback(
    (command: "run-cycle" | "start" | "stop") => {
      const operation =
        command === "run-cycle" ? api.runCycle : command === "start" ? api.startEngine : api.stopEngine;
      const message =
        command === "run-cycle"
          ? "Un cycle canonique a été demandé au TradingEngine."
          : command === "start"
            ? "Boucle autonome démarrée côté backend. Fermer le frontend ne l'arrête pas."
            : "Arrêt explicite demandé au TradingEngine backend.";
      return mutate(`engine-${command}`, operation, message);
    },
    [mutate],
  );

  const compareRevisions = useCallback(
    async (strategyId: string, left: number, right: number): Promise<StrategyRevisionComparisonResponse | null> => {
      setBusyAction("compare-revisions");
      setFeedback(null);
      try {
        return await api.compareStrategyRevisions(strategyId, left, right);
      } catch (error) {
        setFeedback(actionFailure(error, "Comparaison des révisions impossible"));
        return null;
      } finally {
        setBusyAction(null);
      }
    },
    [],
  );

  const previewPrompt = useCallback(
    async (
      strategyId: string,
      strategyRevision: number,
      aggressiveness: number,
      phase: PromptPreviewPhase,
    ): Promise<PromptPreviewResponse | null> => {
      setBusyAction("prompt-preview");
      setFeedback(null);
      try {
        return await api.promptPreview({
          strategy_id: strategyId,
          strategy_revision: strategyRevision,
          aggressiveness,
          phase,
        });
      } catch (error) {
        setFeedback(actionFailure(error, "Preview du prompt impossible"));
        return null;
      } finally {
        setBusyAction(null);
      }
    },
    [],
  );

  return {
    ...snapshot,
    selectedStrategyId,
    selectedStrategy,
    setSelectedStrategyId,
    revisions,
    revisionsLoading,
    loading,
    refreshing,
    busyAction,
    feedback,
    setFeedback,
    lastUpdatedAt,
    refresh,
    createStrategy,
    renameStrategy,
    archiveStrategy,
    createRevision,
    compareRevisions,
    previewPrompt,
    createCampaign,
    activateCampaign,
    resumeCampaign,
    runCycle: () => engineCommand("run-cycle"),
    startEngine: () => engineCommand("start"),
    stopEngine: () => engineCommand("stop"),
  };
}
