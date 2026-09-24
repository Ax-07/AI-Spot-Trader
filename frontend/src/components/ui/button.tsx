import * as React from "react";

import { cn } from "@/lib/utils";

type ButtonVariant = "default" | "secondary" | "outline" | "destructive" | "ghost";

type ButtonProps = React.ComponentProps<"button"> & {
  variant?: ButtonVariant;
  size?: "default" | "sm";
};

const variants: Record<ButtonVariant, string> = {
  default: "border border-primary bg-primary text-primary-foreground shadow-sm hover:bg-primary/90",
  secondary: "border border-border bg-secondary text-secondary-foreground shadow-sm hover:bg-secondary/80",
  outline: "border border-border bg-background text-foreground shadow-sm hover:bg-muted",
  destructive: "border border-destructive bg-destructive text-destructive-foreground shadow-sm hover:bg-destructive/90",
  ghost: "border border-transparent text-foreground hover:bg-muted",
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
        "inline-flex items-center justify-center gap-2 rounded-lg font-semibold transition-[background-color,border-color,color,box-shadow,transform] duration-150 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-55 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background active:translate-y-px",
        size === "sm" ? "h-8 px-3 text-xs" : "h-10 px-4 text-sm",
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}
