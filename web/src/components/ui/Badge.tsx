import * as React from "react"
import { cn } from "@/lib/utils"

export interface BadgeProps extends React.ComponentProps<"div"> {
  variant?: "default" | "success" | "warning" | "danger" | "info" | "outline";
}

function Badge({ className, variant = "default", ...props }: BadgeProps) {
  const variants = {
    default: "border border-border bg-surface-soft text-primary",
    success: "border border-accent/18 bg-accent/10 text-accent",
    warning: "border border-brand/20 bg-highlight/26 text-brand",
    danger: "border border-semantic-danger/20 bg-semantic-danger/10 text-semantic-danger",
    info: "border border-accent-soft/28 bg-accent-soft/14 text-primary",
    outline: "border border-border bg-white/60 text-text",
  }

  return (
    <div
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2",
        variants[variant],
        className
      )}
      {...props}
    />
  )
}

export { Badge }
