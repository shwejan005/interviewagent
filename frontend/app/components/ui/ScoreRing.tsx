"use client"

import * as React from "react"
import { motion, useMotionValue, useSpring, useTransform, useReducedMotion } from "framer-motion"

import { cn } from "@/lib/utils"

export interface ScoreRingProps {
  /** 0–100. */
  value: number
  size?: number
  strokeWidth?: number
  label?: string
  className?: string
}

function toneFor(value: number) {
  if (value >= 70) return "var(--color-success)"
  if (value >= 45) return "var(--color-warning)"
  return "var(--color-error)"
}

/**
 * Circular score gauge. The arc sweeps and the number counts up from zero.
 *
 * `strokeDashoffset` is animated rather than the arc's geometry, so the
 * browser only re-paints the stroke instead of re-running layout.
 */
export function ScoreRing({ value, size = 96, strokeWidth = 6, label, className }: Readonly<ScoreRingProps>) {
  const reduceMotion = useReducedMotion()
  const clamped = Math.max(0, Math.min(100, value))

  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const color = toneFor(clamped)

  const progress = useMotionValue(reduceMotion ? clamped : 0)
  const smooth = useSpring(progress, { stiffness: 90, damping: 22 })
  const offset = useTransform(smooth, (v) => circumference - (v / 100) * circumference)
  const [display, setDisplay] = React.useState(reduceMotion ? clamped : 0)

  React.useEffect(() => {
    progress.set(clamped)
  }, [clamped, progress])

  React.useEffect(() => {
    return smooth.on("change", (v) => setDisplay(Math.round(v)))
  }, [smooth])

  return (
    <div
      className={cn("relative inline-flex items-center justify-center", className)}
      style={{ width: size, height: size }}
      role="img"
      aria-label={label ? `${label}: ${clamped} out of 100` : `Score ${clamped} out of 100`}
    >
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(255,255,255,0.08)"
          strokeWidth={strokeWidth}
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          style={{ strokeDashoffset: offset, filter: `drop-shadow(0 0 6px ${color}55)` }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="mono font-semibold leading-none" style={{ fontSize: size * 0.26, color }}>
          {display}
        </span>
        {label && (
          <span className="mono mt-1 text-[9px] uppercase tracking-[0.1em] text-ink-subtle">{label}</span>
        )}
      </div>
    </div>
  )
}
