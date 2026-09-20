"use client";

import { FormEvent, useState } from "react";
import { MessageSquareText, Send, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useChat } from "@/hooks/use-chat";

function formatTime(value: string) {
  return new Intl.DateTimeFormat("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

export function ChatPanel() {
  const [draft, setDraft] = useState("");
  const {
    messages,
    model,
    historicalCycleId,
    loading,
    sending,
    error,
    send,
    clearLocalSession,
  } = useChat();

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const sent = await send(draft);
    if (sent) setDraft("");
  }

  return (
    <section className="mx-auto w-full max-w-7xl px-4 pb-6 sm:px-6 lg:px-8">
      <Card>
        <CardHeader className="gap-2">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-1.5">
              <CardTitle className="flex items-center gap-2">
                <MessageSquareText className="h-4 w-4" />
                Chat opérateur avec l&apos;Agent
              </CardTitle>
              <CardDescription>
                Conversation informative uniquement. Ce canal ne crée aucun trade, ne modifie pas
                Risk et n&apos;injecte pas ses messages dans les cycles autonomes.
              </CardDescription>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={clearLocalSession}
              disabled={sending || messages.length === 0}
              title="Oublier la session locale de chat"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Nouvelle session
            </Button>
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <span>Modèle : {model ?? "modèle Agent configuré"}</span>
            {historicalCycleId ? (
              <span>Cycle historique ancré : {historicalCycleId}</span>
            ) : null}
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="max-h-[28rem] min-h-52 space-y-3 overflow-y-auto rounded-lg border bg-muted/20 p-3">
            {loading ? (
              <p className="text-sm text-muted-foreground">Chargement du chat…</p>
            ) : messages.length === 0 ? (
              <div className="space-y-2 text-sm text-muted-foreground">
                <p>Pose une question sur le marché, le portefeuille ou les derniers cycles.</p>
                <p>
                  Pour un ancien cycle précis, tu peux écrire « cycle &lt;UUID&gt; : pourquoi cette
                  décision ? » afin d&apos;ancrer l&apos;explication sur ses faits historiques.
                </p>
              </div>
            ) : (
              messages.map((message) => (
                <article
                  key={message.message_id}
                  className={
                    message.role === "OPERATOR"
                      ? "ml-auto max-w-[90%] rounded-lg border bg-background p-3"
                      : "mr-auto max-w-[95%] rounded-lg bg-muted p-3"
                  }
                >
                  <div className="mb-1 flex items-center justify-between gap-4 text-[11px] uppercase tracking-wide text-muted-foreground">
                    <span>{message.role === "OPERATOR" ? "Opérateur" : "Agent"}</span>
                    <span>{formatTime(message.created_at)}</span>
                  </div>
                  <p className="whitespace-pre-wrap text-sm leading-6">{message.content}</p>
                </article>
              ))
            )}
          </div>

          {error ? (
            <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </p>
          ) : null}

          <form onSubmit={onSubmit} className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <label className="flex-1 space-y-1.5 text-sm font-medium">
              Message
              <textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                maxLength={4000}
                rows={3}
                placeholder="Pourquoi as-tu HOLD au dernier cycle ?"
                className="w-full resize-y rounded-md border bg-background px-3 py-2 text-sm font-normal outline-none focus:ring-2 focus:ring-ring"
              />
            </label>
            <Button type="submit" disabled={sending || draft.trim().length === 0}>
              <Send className="h-4 w-4" />
              {sending ? "Réponse…" : "Envoyer"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </section>
  );
}
