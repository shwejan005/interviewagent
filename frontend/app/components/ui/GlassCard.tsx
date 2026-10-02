"use client"

import * as React from "react"
import { motion, type HTMLMotionProps } from "framer-motion"

import { cn } from "@/lib/utils"
import { fadeUp } from "@/lib/motion"

type Elevation = "low" | "mid" | "high"

const ELEVATION_CLASS: Record<Elevation, string> = {
  low: "glass-low",
  mid: "glass",
  high: "glass-high",
}

export interface GlassCardProps extends Omit<HTMLMotionProps<"div">, "ref"> {
  elevation?: Elevation
  /** Adds the hover lift and sheen sweep. Use for cards that link somewhere. */
  interactive?: boolean
  /** Animate in on mount. Turn off inside a staggered parent, which drives its own children. */
  animate?: boolean
  padding?: "none" | "sm" | "md" | "lg"
}

const PADDING_CLASS = {
  none: "",
  sm: "p-4",
  md: "p-6",
  lg: "p-8",
} as const

export const GlassCard = React.forwardRef<HTMLDivElement, GlassCardProps>(
  function GlassCard(
    { className, elevation = "mid", interactive = false, animate = false, padding = "md", children, ...props },
    ref,
  ) {
    const animationProps = animate
      ? { initial: "hidden" as const, animate: "visible" as const, variants: fadeUp }
      : {}

    return (
      <motion.div
        ref={ref}
        className={cn(
          ELEVATION_CLASS[elevation],
          PADDING_CLASS[padding],
          interactive && "glass-interactive",
          className,
        )}
        {...animationProps}
        {...props}
      >
        {children}
      </motion.div>
    )
  },
)
