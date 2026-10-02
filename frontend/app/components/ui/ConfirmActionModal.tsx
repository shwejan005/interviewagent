"use client"

import { Button } from "./Button"
import { GlassCard } from "./GlassCard"
import { Modal } from "./Modal"

type ConfirmActionModalProps = Readonly<{
  open: boolean
  onClose: () => void
  onConfirm: () => void
  title: string
  description: string
  confirmLabel: string
  busy?: boolean
}>

export function ConfirmActionModal({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmLabel,
  busy = false,
}: ConfirmActionModalProps) {
  return (
    <Modal open={open} onClose={onClose} titleId="confirm-action-title" maxWidthClassName="max-w-[480px]">
      <GlassCard elevation="high" padding="lg">
        <p className="eyebrow text-[var(--color-warning)]">CONFIRM CHANGE</p>
        <h2 id="confirm-action-title" className="mt-2 text-[18px] font-semibold text-ink-heading">
          {title}
        </h2>
        <p className="mt-3 text-[13px] leading-relaxed text-ink-muted">{description}</p>
        <div className="mt-6 flex flex-wrap justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button type="button" variant="danger" onClick={onConfirm} loading={busy}>
            {confirmLabel}
          </Button>
        </div>
      </GlassCard>
    </Modal>
  )
}
