import * as React from "react"

import { cn } from "@/lib/utils"

export interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  width?: string | number
  height?: string | number
  circle?: boolean
}

export function Skeleton({ className, width, height, circle = false, style, ...props }: Readonly<SkeletonProps>) {
  return (
    <div
      className={cn("skeleton", circle && "!rounded-full", className)}
      style={{ width, height, ...style }}
      aria-hidden="true"
      {...props}
    />
  )
}

/** Placeholder matching the shape of a GlassCard row. */
export function SkeletonCard({ className }: Readonly<{ className?: string }>) {
  return (
    <div className={cn("glass-low p-6", className)}>
      <Skeleton height={12} width="35%" />
      <Skeleton className="mt-3" height={20} width="65%" />
      <Skeleton className="mt-4" height={10} width="100%" />
      <Skeleton className="mt-2" height={10} width="80%" />
    </div>
  )
}

export function SkeletonList({ count = 3, className }: Readonly<{ count?: number; className?: string }>) {
  return (
    <div className={cn("flex flex-col gap-4", className)} aria-busy="true" aria-label="Loading">
      {Array.from({ length: count }, (_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  )
}
