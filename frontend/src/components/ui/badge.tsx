import * as React from "react";

import { cn } from "@/lib/utils";

type BadgeTone = "neutral" | "success" | "warning" | "danger" | "info";

const tones: Record<BadgeTone, string> = {
  neutral: "border-border bg-muted text-foreground",
  success: "border-success/30 bg-success-subtle text-success-foreground",
  warning: "border-warning/35 bg-warning-subtle text-warning-foreground",
  danger: "border-destructive/30 bg-destructive-subtle text-destructive-subtle-foreground",
  info: "border-info/30 bg-info-subtle text-info-foreground",
};

export function Badge({
  className,
  tone = "neutral",
  ...props
}: React.ComponentProps<"span"> & { tone?: BadgeTone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.09em]",
        tones[tone],
        className,
      )}
      {...props}
    />
  );
}
