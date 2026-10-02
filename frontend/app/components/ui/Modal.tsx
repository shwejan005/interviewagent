"use client"

import * as React from "react"
import { createPortal } from "react-dom"
import { AnimatePresence, motion } from "framer-motion"

import { cn } from "@/lib/utils"

export interface ModalProps {
  open: boolean
  onClose: () => void
  titleId?: string
  maxWidthClassName?: string
  children: React.ReactNode
}

/**
 * Centered dialog, portaled to `document.body`.
 *
 * Portaling is not optional here: any ancestor page wraps content in a
 * `motion.main` with an animated transform (see PageShell), which creates a
 * stacking context that traps a nested fixed element below the navbar no
 * matter how high its z-index is set. Escaping to `body` sidesteps that.
 */
export function Modal({ open, onClose, titleId, maxWidthClassName = "max-w-[560px]", children }: Readonly<ModalProps>) {
  if (typeof document === "undefined") return null

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.dialog
          open
          aria-modal="true"
          aria-labelledby={titleId}
          className="fixed inset-0 z-[80] flex h-full w-full max-w-none items-center justify-center bg-black/70 p-5"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <motion.button
            aria-label="Close dialog"
            className="absolute inset-0 h-full w-full cursor-default border-0 bg-transparent"
            onClick={onClose}
          />
          <motion.div
            className={cn("relative w-full", maxWidthClassName)}
            initial={{ opacity: 0, scale: 0.94, y: 14 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }}
            transition={{ type: "spring", stiffness: 360, damping: 28 }}
          >
            {children}
          </motion.div>
        </motion.dialog>
      )}
    </AnimatePresence>,
    document.body,
  )
}
