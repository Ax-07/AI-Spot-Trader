"use client";

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api/client";
import type { ChatMessageResponse } from "@/lib/api/types";

const SESSION_STORAGE_KEY = "ai-spot-trader-chat-session";

export function useChat() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessageResponse[]>([]);
  const [model, setModel] = useState<string | null>(null);
  const [historicalCycleId, setHistoricalCycleId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const storedSession = window.localStorage.getItem(SESSION_STORAGE_KEY);
    if (!storedSession) {
      queueMicrotask(() => {
        if (!cancelled) setLoading(false);
      });
      return () => {
        cancelled = true;
      };
    }

    void api
      .chatHistory(storedSession)
      .then((history) => {
        if (cancelled) return;
        setSessionId(history.session_id);
        setMessages(history.messages);
        setModel(history.model);
      })
      .catch((loadError: unknown) => {
        if (cancelled) return;
        if (loadError instanceof ApiError && loadError.status === 404) {
          window.localStorage.removeItem(SESSION_STORAGE_KEY);
          setSessionId(null);
          setMessages([]);
          return;
        }
        setError(
          loadError instanceof ApiError ? loadError.message : "Historique chat indisponible",
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const send = useCallback(
    async (text: string) => {
      const message = text.trim();
      if (!message || sending) return false;

      setSending(true);
      setError(null);
      try {
        let activeSession = sessionId;
        let exchange;
        try {
          exchange = await api.sendChatMessage({
            session_id: activeSession,
            message,
          });
        } catch (sendError) {
          if (!(sendError instanceof ApiError) || sendError.status !== 404 || !activeSession) {
            throw sendError;
          }
          window.localStorage.removeItem(SESSION_STORAGE_KEY);
          activeSession = null;
          exchange = await api.sendChatMessage({
            session_id: null,
            message,
          });
        }

        setSessionId(exchange.session_id);
        window.localStorage.setItem(SESSION_STORAGE_KEY, exchange.session_id);
        setModel(exchange.model);
        setHistoricalCycleId(exchange.historical_cycle_id);
        setMessages((current) => [
          ...current,
          exchange.operator_message,
          exchange.agent_message,
        ]);
        return true;
      } catch (sendError) {
        setError(
          sendError instanceof ApiError ? sendError.message : "Message chat impossible",
        );
        return false;
      } finally {
        setSending(false);
      }
    },
    [sending, sessionId],
  );

  const clearLocalSession = useCallback(() => {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
    setSessionId(null);
    setMessages([]);
    setHistoricalCycleId(null);
    setError(null);
  }, []);

  return {
    sessionId,
    messages,
    model,
    historicalCycleId,
    loading,
    sending,
    error,
    send,
    clearLocalSession,
  };
}
