"use client";

import { BookOpenText, MessageSquareText, Palette, Settings2, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { ChatPanel } from "@/components/cockpit/chat-panel";
import { ControlPlanePanel } from "@/components/cockpit/control-plane-panel";
import { OperatorGuide } from "@/components/cockpit/operator-guide";
import { ThemeToggle } from "@/components/theme/theme-toggle";
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
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-muted-foreground">Aide et administration</p>
          <h2 className="mt-1 text-3xl font-semibold tracking-tight">Réglages</h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-muted-foreground">Le parcours courant reste simple. Les objets techniques, comparaisons de versions et paramètres détaillés restent disponibles ici à la demande.</p>
        </div>

        <Card className="mt-5 gap-4 py-4">
          <CardContent className="flex flex-col gap-4 px-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3">
              <div className="rounded-xl border bg-muted/50 p-2.5 text-muted-foreground"><Palette className="size-4" /></div>
              <div>
                <p className="text-sm font-semibold">Apparence</p>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">Clair, sombre ou synchronisé avec le système. Le choix est conservé sur cet appareil.</p>
              </div>
            </div>
            <ThemeToggle />
          </CardContent>
        </Card>

        <div className="mt-5 grid gap-3 sm:grid-cols-3">
          {OPTIONS.map((option) => {
            const Icon = option.icon;
            const active = view === option.id;
            return (
              <button
                key={option.id}
                type="button"
                onClick={() => setView(option.id)}
                aria-pressed={active}
                className={cn(
                  "rounded-2xl border p-4 text-left transition-colors",
                  active
                    ? "border-primary/40 bg-primary text-primary-foreground shadow-sm"
                    : "border-border/80 bg-card hover:border-primary/25 hover:bg-muted/40",
                )}
              >
                <div className="flex items-center gap-2 font-semibold"><Icon className="size-4" />{option.label}</div>
                <p className={cn("mt-1 text-xs", active ? "text-primary-foreground/80" : "text-muted-foreground")}>{option.detail}</p>
              </button>
            );
          })}
        </div>

        {view === "advanced" ? (
          <Card className="mt-5 border-warning/35 bg-warning-subtle shadow-none">
            <CardContent className="flex gap-3 py-4 text-sm text-warning-foreground">
              <ShieldCheck className="mt-0.5 size-4 shrink-0" />
              <div><p className="font-semibold">Mode avancé · surface technique</p><p className="mt-1 text-xs leading-relaxed">Cette vue expose les objets techniques canoniques Strategy, StrategyRevision, Campaign, activation, recovery et les paramètres complets. Elle n’introduit aucune logique de trading parallèle.</p></div>
            </CardContent>
          </Card>
        ) : null}
      </div>

      {view === "help" ? <OperatorGuide /> : null}
      {view === "assistant" ? <ChatPanel /> : null}
      {view === "advanced" ? <ControlPlanePanel /> : null}
    </div>
  );
}
