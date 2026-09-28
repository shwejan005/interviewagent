"use client"

import * as React from "react"
import { motion } from "framer-motion"

import { cn } from "@/lib/utils"
import { EASE_OUT } from "@/lib/motion"

export interface TimelineStage {
  id: string
  label: string
  description?: string
}

export interface StageTimelineProps {
  stages: TimelineStage[]
  /** Index of the stage in progress. Everything before it reads as complete. */
  currentIndex: number
  orientation?: "horizontal" | "vertical"
  className?: string
}

/**
 * Progress rail for the five-stage evaluation pipeline.
 *
 * The filled connector is a `scaleX`/`scaleY` transform on a full-length bar
 * rather than an animated width, so advancing a stage costs one composited
 * frame instead of a layout pass on every step.
 */
function stageLabelClass(active: boolean, complete: boolean) {
  if (active) return "text-ink-heading"
  if (complete) return "text-ink-muted"
  return "text-ink-subtle"
}

export function StageTimeline({
  stages,
  currentIndex,
  orientation = "horizontal",
  className,
}: Readonly<StageTimelineProps>) {
  const isHorizontal = orientation === "horizontal"
  const total = Math.max(stages.length - 1, 1)
  const fill = Math.max(0, Math.min(currentIndex, total)) / total

  return (
    <div
      className={cn(
        "relative",
        isHorizontal ? "flex items-start justify-between gap-2" : "flex flex-col gap-6",
        className,
      )}
    >
      <div
        aria-hidden="true"
        className={cn(
          "absolute bg-[var(--color-border)]",
          isHorizontal ? "left-0 right-0 top-[11px] h-px" : "bottom-0 left-[11px] top-0 w-px",
        )}
      >
        <motion.div
          className="h-full w-full bg-[var(--color-primary)]"
          style={{ transformOrigin: isHorizontal ? "left center" : "center top" }}
          initial={false}
          animate={isHorizontal ? { scaleX: fill } : { scaleY: fill }}
          transition={{ duration: 0.5, ease: EASE_OUT }}
        />
      </div>

      {stages.map((stage, index) => {
        const complete = index < currentIndex
        const active = index === currentIndex

        return (
          <div
            key={stage.id}
            className={cn(
              "relative z-[1]",
              isHorizontal ? "flex flex-1 flex-col items-center text-center" : "flex items-start gap-3",
            )}
          >
            <motion.span
              initial={false}
              animate={{ scale: active ? 1.15 : 1 }}
              transition={{ duration: 0.25, ease: EASE_OUT }}
              className={cn(
                "flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full border text-[10px] font-semibold",
                complete && "border-[var(--color-primary)] bg-[var(--color-primary)] text-black",
                active &&
                  "border-[var(--color-primary)] bg-[var(--color-bg)] text-[var(--color-primary)] shadow-glow-primary",
                !complete && !active && "border-[var(--color-border)] bg-[var(--color-bg)] text-ink-subtle",
              )}
            >
              {complete ? "✓" : index + 1}
            </motion.span>

            <div className={cn(isHorizontal ? "mt-2" : "")}>
              <p className={cn("text-[12px] font-medium", stageLabelClass(active, complete))}>
                {stage.label}
              </p>
              {stage.description && (
                <p className="mt-0.5 text-[11px] text-ink-subtle">{stage.description}</p>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
