"use client";

import { useEffect, useState } from "react";
import { Clock3 } from "lucide-react";

import { ApiError } from "../../lib/api";
import { Button, GlassCard, Modal } from "./ui";

type SessionExpiryDialogProps = {
  open: boolean;
  expiresAt: number | null;
  loading: boolean;
  onExtend: () => Promise<void>;
  onDismiss: () => void;
};

export default function SessionExpiryDialog({
  open,
  expiresAt,
  loading,
  onExtend,
  onDismiss,
}: Readonly<SessionExpiryDialogProps>) {
  const [error, setError] = useState<string | null>(null);
  const [minutesRemaining, setMinutesRemaining] = useState<number | null>(null);

  useEffect(() => {
    if (!open || !expiresAt) {
      setMinutesRemaining(null);
      setError(null);
      return;
    }

    const updateRemaining = () => {
      setMinutesRemaining(Math.max(1, Math.ceil((expiresAt - Date.now()) / 60_000)));
    };

    updateRemaining();
    const timer = window.setInterval(updateRemaining, 30_000);
    return () => window.clearInterval(timer);
  }, [open, expiresAt]);

  const handleExtend = async () => {
    setError(null);
    try {
      await onExtend();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "We could not extend your session. Please try again.");
    }
  };

  return (
    <Modal open={open} onClose={onDismiss} titleId="session-expiry-title" maxWidthClassName="max-w-[480px]">
      <GlassCard elevation="high" padding="lg" className="border border-[rgba(249,115,22,0.28)]">
        <div className="flex items-start gap-4">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[rgba(249,115,22,0.14)] text-[var(--color-primary-light)]">
            <Clock3 size={21} aria-hidden="true" />
          </div>
          <div>
            <p className="eyebrow">SESSION</p>
            <h2 id="session-expiry-title" className="mt-1 text-[21px] font-semibold text-ink-heading">
              Keep your session active?
            </h2>
            <p className="mt-2 text-[13px] leading-[1.65] text-ink-muted">
              {minutesRemaining
                ? `Your session expires in about ${minutesRemaining} minute${minutesRemaining === 1 ? "" : "s"}. Extend it to keep working without signing in again.`
                : "Your session is about to expire. Extend it to keep working without signing in again."}
            </p>
          </div>
        </div>

        {error && <p className="mt-4 text-[12px] leading-[1.5] text-[var(--color-error)]">{error}</p>}

        <div className="mt-7 flex justify-end gap-3">
          <Button type="button" variant="ghost" onClick={onDismiss} disabled={loading}>
            Not now
          </Button>
          <Button type="button" onClick={handleExtend} loading={loading}>
            Extend session
          </Button>
        </div>
      </GlassCard>
    </Modal>
  );
}