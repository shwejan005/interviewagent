"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import Navbar from "../../components/Navbar";
import {
  Alert,
  GlassCard,
  PageHeader,
  PageShell,
  Select,
  SkeletonList,
} from "../../components/ui";
import { useAuth } from "../../../lib/auth-context";
import { api, ApiError } from "../../../lib/api";
import type { FunnelResult, SelectionRatesResult } from "../../../lib/types";
import { DUR, EASE_OUT, staggerContainer, staggerItem } from "../../../lib/motion";

/** Flattens the 403-vs-detail branch so the caller stays ternary-free. */
function analyticsErrorMessage(err: unknown): string {
  if (!(err instanceof ApiError)) return "Failed to load analytics.";
  if (err.status === 403) {
    return "Analytics requires a hiring manager, org admin, or org owner role.";
  }
  return err.detail;
}

/** Horizontal bar that grows via transform only, so it stays GPU-composited. */
function FunnelBar({ ratio, delay }: Readonly<{ ratio: number; delay: number }>) {
  return (
    <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-glass-low">
      <motion.div
        initial={{ scaleX: 0 }}
        animate={{ scaleX: Math.max(ratio, 0.01) }}
        transition={{ duration: DUR.slow, ease: EASE_OUT, delay }}
        style={{ originX: 0 }}
        className="h-full rounded-full bg-[var(--color-primary)]"
      />
    </div>
  );
}

export default function AnalyticsPage() {
  const router = useRouter();
  const { actor, loading: authLoading, activeOrgId } = useAuth();
  const [funnel, setFunnel] = useState<FunnelResult | null>(null);
  const [selectionRates, setSelectionRates] = useState<SelectionRatesResult | null>(null);
  const [segmentBy, setSegmentBy] = useState<"source" | "experience_band">("source");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authLoading) return;
    if (!actor) {
      router.push("/login?next=/org/analytics");
      return;
    }
    if (!activeOrgId) return;
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, actor, activeOrgId, segmentBy]);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [funnelData, ratesData] = await Promise.all([
        api.get<FunnelResult>(`/orgs/${activeOrgId}/analytics/funnel`),
        api.get<SelectionRatesResult>(`/orgs/${activeOrgId}/analytics/selection-rates?segment_by=${segmentBy}`),
      ]);
      setFunnel(funnelData);
      setSelectionRates(ratesData);
    } catch (err) {
      setError(analyticsErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  if (authLoading || loading) {
    return (
      <div className="min-h-screen">
        <Navbar />
        <PageShell className="!max-w-[820px] pt-[112px]">
          <SkeletonList count={3} />
        </PageShell>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Navbar />
      <PageShell className="!max-w-[820px] pt-[112px]">
        <PageHeader eyebrow="RECRUITER ANALYTICS" title="Funnel & fairness" />

        {error && (
          <Alert tone="error" className="mt-6">
            {error}
          </Alert>
        )}

        <motion.div
          initial="hidden"
          animate="visible"
          variants={staggerContainer(0.08)}
          className="mt-8 flex flex-col gap-5"
        >
          {funnel && (
            <motion.div variants={staggerItem}>
              <GlassCard padding="lg">
                <p className="eyebrow">HIRING FUNNEL</p>
                <div className="mt-5">
                  {funnel.funnel.map((stage, i) => (
                    <div key={stage.stage} className="border-b border-subtle py-3 first:pt-0">
                      <div className="flex items-center justify-between gap-4">
                        <span className="text-[13px] text-ink-heading">{stage.stage}</span>
                        <div className="flex items-center gap-4">
                          <span className="mono text-[13px] text-ink-muted">{stage.reached}</span>
                          {stage.conversion_from_applied !== null && (
                            <span className="text-[12px] text-ink-subtle">
                              {(stage.conversion_from_applied * 100).toFixed(0)}% of applied
                            </span>
                          )}
                        </div>
                      </div>
                      <FunnelBar ratio={stage.conversion_from_applied ?? 1} delay={0.1 + i * 0.06} />
                    </div>
                  ))}
                </div>
                <div className="mt-4 flex gap-5 text-[12px] text-ink-subtle">
                  <span>Rejected: {funnel.rejected}</span>
                  <span>Withdrawn: {funnel.withdrawn}</span>
                </div>
              </GlassCard>
            </motion.div>
          )}

          {selectionRates && (
            <motion.div variants={staggerItem}>
              <GlassCard padding="lg">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="eyebrow">SELECTION RATE DIVERGENCE</p>
                  <Select
                    aria-label="Segment by"
                    wrapperClassName="w-[190px]"
                    value={segmentBy}
                    onChange={(e) => setSegmentBy(e.target.value as "source" | "experience_band")}
                  >
                    <option value="source">By source</option>
                    <option value="experience_band">By experience band</option>
                  </Select>
                </div>

                {selectionRates.flag_adverse_impact && (
                  <Alert tone="warning" title="Possible adverse impact" className="mt-5">
                    One segment is selected at less than 80% the rate of the highest-selecting
                    segment (ratio: {selectionRates.adverse_impact_ratio}). Review before drawing
                    conclusions from a small sample.
                  </Alert>
                )}

                <div className="mt-5">
                  {Object.entries(selectionRates.segments).map(([key, seg]) => (
                    <div
                      key={key}
                      className="flex items-center justify-between gap-4 border-b border-subtle py-3 first:pt-0"
                    >
                      <span className="text-[13px] text-ink-heading">{key}</span>
                      <span className="mono text-[13px] text-ink-muted">
                        {seg.selected}/{seg.total} · {(seg.selection_rate * 100).toFixed(0)}%
                      </span>
                    </div>
                  ))}
                </div>

                <p className="mt-5 text-[11px] leading-[1.65] text-ink-subtle">{selectionRates.note}</p>
              </GlassCard>
            </motion.div>
          )}
        </motion.div>
      </PageShell>
    </div>
  );
}
