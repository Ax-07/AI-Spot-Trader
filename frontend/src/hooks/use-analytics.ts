"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError } from "@/lib/api/client";
import type { PaperAnalyticsResponse } from "@/lib/api/types";
import type { ResourceState } from "@/hooks/use-cockpit";

const POLL_INTERVAL_MS = 10_000;

export function useAnalytics() {
  const [state, setState] = useState<ResourceState<PaperAnalyticsResponse>>({
    kind: "loading",
  });
  const [refreshing, setRefreshing] = useState(false);
  const refreshInFlight = useRef(false);

  const refresh = useCallback(async () => {
    if (refreshInFlight.current) return;
    refreshInFlight.current = true;
    setRefreshing(true);
    try {
      setState({ kind: "ready", data: await api.analytics() });
    } catch (error) {
      if (error instanceof ApiError && error.status === 503) {
        setState({ kind: "unavailable", message: "Analytics PAPER non configurés" });
      } else if (error instanceof ApiError) {
        setState({ kind: "error", message: error.message });
      } else {
        setState({ kind: "error", message: "Erreur inattendue côté analytics" });
      }
    } finally {
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

  return { state, refreshing, refresh };
}
