"use client"

import * as React from "react"
import { createPortal } from "react-dom"
import { AnimatePresence, motion } from "framer-motion"

import { cn } from "@/lib/utils"

export interface SidePanelProps {
  open: boolean
  onClose: () => void
  titleId?: string
  widthClassName?: string
  children: React.ReactNode
}

/** Right-side sliding drawer, portaled to `document.body` for the same
 * stacking-context reason documented in Modal.tsx. */
export function SidePanel({ open, onClose, titleId, widthClassName = "max-w-[560px]", children }: Readonly<SidePanelProps>) {
  if (typeof document === "undefined") return null

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.dialog
          open
          aria-modal="true"
          aria-labelledby={titleId}
          className="fixed inset-0 z-[80] flex h-full w-full max-w-none bg-transparent p-0"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <motion.button
            aria-label="Close panel"
            className="h-full flex-1 cursor-default border-0 bg-black/65 backdrop-blur-[3px]"
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          />
          <motion.aside
            className={cn(
              "h-full w-full overflow-y-auto border-l border-subtle bg-[var(--color-bg)] shadow-[-20px_0_60px_rgba(0,0,0,0.42)]",
              widthClassName,
            )}
            initial={{ opacity: 0, x: 56 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 56 }}
            transition={{ type: "spring", damping: 30, stiffness: 340 }}
          >
            {children}
          </motion.aside>
        </motion.dialog>
      )}
    </AnimatePresence>,
    document.body,
  )
}
