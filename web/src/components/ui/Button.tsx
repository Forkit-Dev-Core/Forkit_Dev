import * as React from "react"
import { cn } from "@/lib/utils"

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "destructive" | "outline" | "secondary" | "ghost" | "link";
  size?: "default" | "sm" | "lg" | "icon";
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "default", ...props }, ref) => {
    const variants = {
      default: "bg-accent text-[#f1ebdf] shadow-[0_14px_26px_rgba(0,129,144,0.18)] hover:bg-accent-dark",
      destructive: "bg-semantic-danger text-white hover:bg-semantic-danger/90",
      outline: "border border-border bg-white/78 text-text hover:border-primary/30 hover:bg-primary/5",
      secondary: "bg-surface-soft text-primary hover:bg-primary/8",
      ghost: "text-text hover:bg-primary/6 hover:text-primary",
      link: "text-primary underline-offset-4 hover:text-accent-dark hover:underline",
    }

    const sizes = {
      default: "h-10 px-4 py-2",
      sm: "h-9 rounded-md px-3",
      lg: "h-11 rounded-md px-8",
      icon: "h-10 w-10",
    }

    return (
      <button
        className={cn(
          "inline-flex items-center justify-center whitespace-nowrap rounded-xl text-sm font-semibold ring-offset-bg transition-all duration-180 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-soft focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
          variants[variant],
          sizes[size],
          className
        )}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button }
