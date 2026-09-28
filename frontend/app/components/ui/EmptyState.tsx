import * as React from "react"

import { cn } from "@/lib/utils"

export interface EmptyStateProps {
  icon?: React.ReactNode
  title: string
  description?: string
  action?: React.ReactNode
  className?: string
}

export function EmptyState({ icon, title, description, action, className }: Readonly<EmptyStateProps>) {
  return (
    <div className={cn("glass-low flex flex-col items-center px-6 py-14 text-center", className)}>
      {icon && (
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full border border-subtle bg-glass-low text-xl text-ink-subtle">
          {icon}
        </div>
      )}
      <p className="text-[16px] font-semibold text-ink-heading">{title}</p>
      {description && <p className="mt-2 max-w-[42ch] text-[13px] text-ink-muted">{description}</p>}
      {action && <div className="mt-6 flex flex-wrap justify-center gap-3">{action}</div>}
    </div>
  )
}
