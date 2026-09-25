"use client";

import { useEffect, useState } from "react";

import { api, ApiError, backendWebSocketUrl } from "@/lib/api/client";
import type { ExecutableMarketResponse } from "@/lib/api/types";
import {
  marketKey,
  mergeCandleSeries,
  type CandleResponse,
  type CandleStreamMessage,
  type CandleStreamStatusResponse,
  type CandleTimeframe,
} from "@/lib/market-candles";

type CandleConnectionState = "loading" | "ready" | "error";

type CacheEntry = {
  candles: CandleResponse[];
  status: CandleStreamStatusResponse;
};

type CandleViewState = {
  key: string | null;
  candles: CandleResponse[];
  status: CandleStreamStatusResponse | null;
  state: CandleConnectionState;
  error: string | null;
  reconnecting: boolean;
};

const SERIES_CACHE = new Map<string, CacheEntry>();
const SERIES_CACHE_LIMIT = 8;

function cacheKey(market: ExecutableMarketResponse, timeframe: CandleTimeframe) {
  return `${marketKey(market)}:${timeframe}`;
}

function remember(key: string, entry: CacheEntry) {
  SERIES_CACHE.delete(key);
  SERIES_CACHE.set(key, entry);
  while (SERIES_CACHE.size > SERIES_CACHE_LIMIT) {
    const oldest = SERIES_CACHE.keys().next().value as string | undefined;
    if (!oldest) break;
    SERIES_CACHE.delete(oldest);
  }
}

function streamPath(market: ExecutableMarketResponse, timeframe: CandleTimeframe, limit: number) {
  const params = new URLSearchParams({
    symbol: market.symbol,
    market_type: market.market_type,
    timeframe,
    limit: String(limit),
  });
  return `/api/v1/markets/candles/stream?${params.toString()}`;
}

function emptyView(key: string | null, state: CandleConnectionState): CandleViewState {
  return {
    key,
    candles: [],
    status: null,
    state,
    error: null,
    reconnecting: false,
  };
}

function cachedView(key: string, cached: CacheEntry): CandleViewState {
  return {
    key,
    candles: cached.candles,
    status: cached.status,
    state: "ready",
    error: cached.status.last_error,
    reconnecting: false,
  };
}

export function useMarketCandles(
  market: ExecutableMarketResponse | null,
  timeframe: CandleTimeframe,
  limit = 500,
) {
  const marketSymbol = market?.symbol ?? null;
  const marketType = market?.market_type ?? null;
  const activeMarket = marketSymbol && marketType
    ? { symbol: marketSymbol, market_type: marketType } satisfies ExecutableMarketResponse
    : null;
  const key = activeMarket ? cacheKey(activeMarket, timeframe) : null;
  const cached = key ? SERIES_CACHE.get(key) ?? null : null;
  const [liveView, setLiveView] = useState<CandleViewState>(() => emptyView(null, "ready"));
  const view = !key
    ? emptyView(null, "ready")
    : liveView.key === key
      ? liveView
      : cached
        ? cachedView(key, cached)
        : emptyView(key, "loading");

  useEffect(() => {
    if (!marketSymbol || !marketType || !key) return;

    let disposed = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let reconnectAttempt = 0;
    const effectKey = key;
    const effectMarket: ExecutableMarketResponse = { symbol: marketSymbol, market_type: marketType };
    const cachedAtStart = SERIES_CACHE.get(effectKey) ?? null;

    function updateView(update: (current: CandleViewState) => CandleViewState) {
      setLiveView((current) => {
        const base = current.key === effectKey
          ? current
          : cachedAtStart
            ? cachedView(effectKey, cachedAtStart)
            : emptyView(effectKey, "loading");
        return update(base);
      });
    }

    function updateCache(nextCandles: CandleResponse[], nextStatus: CandleStreamStatusResponse) {
      remember(effectKey, { candles: nextCandles, status: nextStatus });
    }

    function connect() {
      if (disposed) return;
      socket = new WebSocket(backendWebSocketUrl(streamPath(effectMarket, timeframe, limit)));

      socket.onopen = () => {
        if (disposed) return;
        reconnectAttempt = 0;
        updateView((current) => ({ ...current, reconnecting: false }));
      };

      socket.onmessage = (event) => {
        if (disposed || typeof event.data !== "string") return;
        let message: CandleStreamMessage;
        try {
          message = JSON.parse(event.data) as CandleStreamMessage;
        } catch {
          updateView((current) => ({ ...current, error: "Message WebSocket candles invalide" }));
          return;
        }

        if (message.type === "error") {
          updateView((current) => ({
            ...current,
            state: "error",
            error: message.detail || "Erreur WebSocket candles",
          }));
          return;
        }

        if (message.type === "snapshot") {
          const next = mergeCandleSeries([], message.candles, limit);
          updateCache(next, message.status);
          updateView(() => ({
            key: effectKey,
            candles: next,
            status: message.status,
            state: "ready",
            error: message.status.last_error,
            reconnecting: false,
          }));
          return;
        }

        if (message.type === "candle") {
          updateView((current) => {
            const next = mergeCandleSeries(current.candles, [message.candle], limit);
            updateCache(next, message.status);
            return {
              ...current,
              candles: next,
              status: message.status,
              state: "ready",
              error: message.status.last_error,
            };
          });
        }
      };

      socket.onerror = () => {
        if (!disposed) {
          updateView((current) => ({ ...current, error: "Connexion WebSocket candles interrompue" }));
        }
      };

      socket.onclose = () => {
        if (disposed) return;
        updateView((current) => ({
          ...current,
          status: current.status ? { ...current.status, connected: false } : null,
          reconnecting: true,
        }));
        reconnectAttempt += 1;
        const delay = Math.min(15_000, 1_000 * 2 ** Math.min(reconnectAttempt - 1, 4));
        reconnectTimer = window.setTimeout(connect, delay);
      };
    }

    void api
      .candles({
        symbol: marketSymbol,
        marketType,
        timeframe,
        limit,
      })
      .then((history) => {
        if (disposed) return;
        const next = mergeCandleSeries([], history.candles, limit);
        updateCache(next, history.status);
        updateView(() => ({
          key: effectKey,
          candles: next,
          status: history.status,
          state: "ready",
          error: history.status.last_error,
          reconnecting: false,
        }));
      })
      .catch((cause: unknown) => {
        if (disposed) return;
        updateView((current) => ({
          ...current,
          state: cachedAtStart ? "ready" : "error",
          error: cause instanceof ApiError ? cause.message : "Historique candles indisponible",
        }));
      })
      .finally(() => {
        if (!disposed) connect();
      });

    return () => {
      disposed = true;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      if (socket) {
        socket.onopen = null;
        socket.onmessage = null;
        socket.onerror = null;
        socket.onclose = null;
        if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
          socket.close(1000, "market changed");
        }
      }
    };
  }, [key, limit, marketSymbol, marketType, timeframe]);

  return {
    candles: view.candles,
    status: view.status,
    state: view.state,
    error: view.error,
    reconnecting: view.reconnecting,
  };
}
