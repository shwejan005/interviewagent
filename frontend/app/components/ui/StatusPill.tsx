import * as React from "react"

import { cn } from "@/lib/utils"

export type PillTone = "success" | "warning" | "error" | "primary" | "muted"

const TONE_CLASS: Record<PillTone, string> = {
  success: "status-tag-success",
  warning: "status-tag-warning",
  error: "status-tag-error",
  primary: "status-tag-primary",
  muted: "status-tag-muted",
}

export interface StatusPillProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: PillTone
  /** Adds a slow pulse. Reserve for genuinely in-flight work. */
  pulse?: boolean
}

export function StatusPill({ tone = "muted", pulse = false, className, children, ...props }: Readonly<StatusPillProps>) {
  return (
    <span
      className={cn(
        "status-tag",
        TONE_CLASS[tone],
        pulse && "before:animate-pulse",
        className,
      )}
      {...props}
    >
      {children}
    </span>
  )
}
