"use client"

import * as React from "react"
import { motion } from "framer-motion"

import { cn } from "@/lib/utils"
import { fadeUp, staggerContainer } from "@/lib/motion"

export interface PageHeaderProps {
  eyebrow?: string
  title: React.ReactNode
  description?: React.ReactNode
  actions?: React.ReactNode
  className?: string
}

export function PageHeader({ eyebrow, title, description, actions, className }: Readonly<PageHeaderProps>) {
  return (
    <motion.header
      initial="hidden"
      animate="visible"
      variants={staggerContainer(0.06)}
      className={cn("flex flex-wrap items-end justify-between gap-6", className)}
    >
      <div className="min-w-0 max-w-[62ch]">
        {eyebrow && (
          <motion.p variants={fadeUp} className="eyebrow">
            {eyebrow}
          </motion.p>
        )}
        <motion.h1
          variants={fadeUp}
          className={cn(
            "text-[clamp(26px,4vw,38px)] font-semibold leading-[1.15] tracking-normal text-ink-heading",
            eyebrow && "mt-2",
          )}
        >
          {title}
        </motion.h1>
        {description && (
          <motion.p variants={fadeUp} className="mt-3 text-[15px] leading-relaxed text-ink-muted">
            {description}
          </motion.p>
        )}
      </div>
      {actions && (
        <motion.div variants={fadeUp} className="flex flex-wrap items-center gap-3">
          {actions}
        </motion.div>
      )}
    </motion.header>
  )
}
