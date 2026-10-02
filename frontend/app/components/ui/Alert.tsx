import * as React from "react"

import { cn } from "@/lib/utils"

export type AlertTone = "info" | "success" | "warning" | "error"

const TONE: Record<AlertTone, { wrap: string; icon: string }> = {
  info: { wrap: "border-[rgba(99,102,241,0.35)] bg-[rgba(99,102,241,0.1)] text-[#c7d2fe]", icon: "ℹ" },
  success: { wrap: "border-[rgba(34,197,94,0.35)] bg-[rgba(34,197,94,0.1)] text-[#bbf7d0]", icon: "✓" },
  warning: { wrap: "border-[rgba(245,158,11,0.35)] bg-[rgba(245,158,11,0.1)] text-[#fde68a]", icon: "!" },
  error: { wrap: "border-[rgba(239,68,68,0.35)] bg-[rgba(239,68,68,0.1)] text-[#fecaca]", icon: "×" },
}

export interface AlertProps extends React.HTMLAttributes<HTMLDivElement> {
  tone?: AlertTone
  title?: string
}

export function Alert({ tone = "info", title, className, children, ...props }: Readonly<AlertProps>) {
  const { wrap, icon } = TONE[tone]

  return (
    <div
      className={cn("flex gap-3 rounded-[10px] border px-4 py-3 text-[13px] leading-relaxed", wrap, className)}
      // Only errors interrupt; the rest are static prose that a live region
      // would announce redundantly.
      role={tone === "error" ? "alert" : undefined}
      {...props}
    >
      <span aria-hidden="true" className="mt-px shrink-0 font-semibold opacity-80">
        {icon}
      </span>
      <div className="min-w-0">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className={cn(title && "mt-1 opacity-90")}>{children}</div>}
      </div>
    </div>
  )
}
