import * as React from "react";

import { cn } from "@/lib/utils";

type ButtonVariant = "default" | "outline" | "destructive" | "ghost";

type ButtonProps = React.ComponentProps<"button"> & {
  variant?: ButtonVariant;
  size?: "default" | "sm";
};

const variants: Record<ButtonVariant, string> = {
  default: "bg-foreground text-background hover:opacity-90",
  outline: "border bg-background hover:bg-muted",
  destructive: "bg-red-600 text-white hover:bg-red-700",
  ghost: "hover:bg-muted",
};

export function Button({
  className,
  variant = "default",
  size = "default",
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors disabled:pointer-events-none disabled:opacity-45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        size === "sm" ? "h-8 px-3 text-xs" : "h-10 px-4 text-sm",
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}
