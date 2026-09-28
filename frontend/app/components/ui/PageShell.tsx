"use client"

import * as React from "react"
import { motion } from "framer-motion"

import { cn } from "@/lib/utils"
import { DUR, EASE_OUT } from "@/lib/motion"

export interface PageShellProps {
  children: React.ReactNode
  className?: string
  /** Constrains content to --max-width with standard page padding. */
  contained?: boolean
}

/**
 * Standard page wrapper: sits above the ambient background and fades the
 * content in on mount so navigation never snaps.
 */
export function PageShell({ children, className, contained = true }: Readonly<PageShellProps>) {
  return (
    <motion.main
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: DUR.base, ease: EASE_OUT }}
      className={cn(
        "content-layer",
        contained && "mx-auto w-full max-w-[var(--max-width)] px-6 py-12",
        className,
      )}
    >
      {children}
    </motion.main>
  )
}
