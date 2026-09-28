"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import Navbar from "../components/Navbar";
import {
  Alert,
  Button,
  ButtonLink,
  EmptyState,
  GlassCard,
  PageHeader,
  PageShell,
  SkeletonList,
  StatusPill,
} from "../components/ui";
import type { PillTone } from "../components/ui";
import { useAuth } from "../../lib/auth-context";
import { api, ApiError } from "../../lib/api";
import type { Referral } from "../../lib/types";
import { staggerContainer, staggerItem } from "../../lib/motion";

const STATUS_TONE: Record<string, PillTone> = {
  PENDING: "warning",
  APPLIED: "success",
};

export default function ReferralsPage() {
  const router = useRouter();
  const { actor, loading: authLoading } = useAuth();
  const [referrals, setReferrals] = useState<Referral[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actingOn, setActingOn] = useState<number | null>(null);

  useEffect(() => {
    if (authLoading) return;
    if (!actor) {
      router.push("/login?next=/referrals");
      return;
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, actor]);

  const load = async () => {
    setLoading(true);
    try {
      const data = await api.get<{ referrals: Referral[] }>("/me/referrals");
      setReferrals(data.referrals);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load referrals.");
    } finally {
      setLoading(false);
    }
  };

  const handleAccept = async (id: number) => {
    setActingOn(id);
    setError(null);
    try {
      await api.post(`/me/referrals/${id}/apply`, {});
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to accept referral.");
    } finally {
      setActingOn(null);
    }
  };

  const handleDecline = async (id: number) => {
    setActingOn(id);
    setError(null);
    try {
      await api.post(`/me/referrals/${id}/decline`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to decline referral.");
    } finally {
      setActingOn(null);
    }
  };

  if (authLoading || loading) {
    return (
      <div className="min-h-screen">
        <Navbar />
        <PageShell className="!max-w-[760px] pt-[112px]">
          <SkeletonList count={3} />
        </PageShell>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Navbar />
      <PageShell className="!max-w-[760px] pt-[112px]">
        <PageHeader
          eyebrow="REFERRALS"
          title="Sent to you"
          description="A recruiter thought you'd be a good fit for these roles."
        />

        {error && (
          <Alert tone="error" className="mt-6">
            {error}
          </Alert>
        )}

        <div className="mt-8">
          {referrals.length === 0 ? (
            <EmptyState
              title="No referrals yet"
              description="Turn on “discoverable” in your profile so recruiters can find and refer you."
              action={<ButtonLink href="/profile">Go to profile</ButtonLink>}
            />
          ) : (
            <motion.div
              initial="hidden"
              animate="visible"
              variants={staggerContainer(0.05)}
              className="flex flex-col gap-3"
            >
              {referrals.map((ref) => (
                <motion.div key={ref.id} variants={staggerItem}>
                  <GlassCard>
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0">
                        <p className="text-[14px] font-semibold text-ink-heading">{ref.posting_title}</p>
                        <p className="mt-0.5 text-[12px] text-ink-subtle">{ref.org_name}</p>
                      </div>
                      <StatusPill tone={STATUS_TONE[ref.status] ?? "muted"}>{ref.status}</StatusPill>
                    </div>

                    {ref.note && (
                      <p className="mt-3 border-l-2 border-[var(--color-primary)] pl-3 text-[13px] italic leading-[1.65] text-ink-muted">
                        &ldquo;{ref.note}&rdquo;
                      </p>
                    )}

                    {ref.status === "PENDING" && (
                      <div className="mt-5 flex flex-wrap gap-2">
                        <Button
                          size="sm"
                          onClick={() => handleAccept(ref.id)}
                          loading={actingOn === ref.id}
                        >
                          Accept &amp; apply
                        </Button>
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => handleDecline(ref.id)}
                          disabled={actingOn === ref.id}
                        >
                          Decline
                        </Button>
                      </div>
                    )}
                  </GlassCard>
                </motion.div>
              ))}
            </motion.div>
          )}
        </div>
      </PageShell>
    </div>
  );
}
