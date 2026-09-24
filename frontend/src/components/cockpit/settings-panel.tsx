"use client";

import { BookOpenText, MessageSquareText, Settings2, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { ChatPanel } from "@/components/cockpit/chat-panel";
import { ControlPlanePanel } from "@/components/cockpit/control-plane-panel";
import { OperatorGuide } from "@/components/cockpit/operator-guide";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type SettingsView = "help" | "assistant" | "advanced";

const OPTIONS = [
  { id: "help" as const, label: "Aide", detail: "Guide opérateur", icon: BookOpenText },
  { id: "assistant" as const, label: "Assistant", detail: "Chat informatif", icon: MessageSquareText },
  { id: "advanced" as const, label: "Avancé", detail: "Strategies, versions et Campaigns", icon: Settings2 },
];

export function SettingsPanel() {
  const [view, setView] = useState<SettingsView>("help");

  return (
    <div>
      <div className="mx-auto w-full max-w-[1500px] px-4 pt-6 sm:px-6 xl:px-8">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Aide et administration</p>
          <h2 className="mt-1 text-2xl font-semibold tracking-tight">Réglages</h2>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">Le parcours courant reste simple. Les objets techniques, comparaisons de versions et paramètres détaillés restent disponibles ici à la demande.</p>
        </div>

        <div className="mt-5 grid gap-3 sm:grid-cols-3">
          {OPTIONS.map((option) => {
            const Icon = option.icon;
            const active = view === option.id;
            return (
              <button key={option.id} type="button" onClick={() => setView(option.id)} className={cn("rounded-xl border p-4 text-left transition", active ? "border-foreground bg-foreground text-background" : "bg-background hover:bg-muted/40")}>
                <div className="flex items-center gap-2 font-semibold"><Icon className="size-4" />{option.label}</div>
                <p className={cn("mt-1 text-xs", active ? "text-background/65" : "text-muted-foreground")}>{option.detail}</p>
              </button>
            );
          })}
        </div>

        {view === "advanced" ? (
          <Card className="mt-5 border-amber-200 bg-amber-50 shadow-none">
            <CardContent className="flex gap-3 py-4 text-sm text-amber-900"><ShieldCheck className="mt-0.5 size-4 shrink-0" /><div><p className="font-semibold">Mode avancé</p><p className="mt-1 text-xs leading-relaxed">Cette vue expose les objets techniques canoniques Strategy, StrategyRevision, Campaign, activation, recovery et les paramètres complets. Elle n’introduit aucune logique de trading parallèle.</p></div></CardContent>
          </Card>
        ) : null}
      </div>

      {view === "help" ? <OperatorGuide /> : null}
      {view === "assistant" ? <ChatPanel /> : null}
      {view === "advanced" ? <ControlPlanePanel /> : null}
    </div>
  );
}
