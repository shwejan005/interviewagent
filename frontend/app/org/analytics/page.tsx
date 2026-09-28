"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { animate, motion } from "framer-motion";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Sector,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { PieSectorShapeProps } from "recharts";

import Navbar from "../../components/Navbar";
import {
  GlassCard,
  PageHeader,
  PageShell,
  Select,
  SkeletonList,
  StatusPill,
} from "../../components/ui";
import type { PillTone } from "../../components/ui";
import { useAuth } from "../../../lib/auth-context";
import { api, ApiError } from "../../../lib/api";
import { notify } from "../../../lib/toast";
import type { AnalyticsOverview, FunnelResult, SelectionRatesResult } from "../../../lib/types";
import { DUR, EASE_OUT, staggerContainer, staggerItem } from "../../../lib/motion";

const CHART_COLORS = ["#f97316", "#6366f1", "#22c55e", "#f59e0b", "#ef4444", "#38bdf8", "#a78bfa", "#f472b6", "#94a3b8"];

const STAGE_TONE: Record<string, PillTone> = {
  HIRED: "success",
  OFFER: "success",
  REJECTED: "error",
  WITHDRAWN: "muted",
};

/** Flattens the 403-vs-detail branch so the caller stays ternary-free. */
function analyticsErrorMessage(err: unknown): string {
  if (!(err instanceof ApiError)) return "Failed to load analytics.";
  if (err.status === 403) {
    return "Analytics requires a hiring manager, org admin, or org owner role.";
  }
  return err.detail;
}

/** Ticks a displayed number up from 0 on mount/update — touches text only, not layout. */
function AnimatedStat({ value, suffix = "" }: Readonly<{ value: number; suffix?: string }>) {
  const [display, setDisplay] = useState(0);
  useEffect(() => {
    const controls = animate(0, value, { duration: 1, ease: EASE_OUT, onUpdate: setDisplay });
    return () => controls.stop();
  }, [value]);
  return <>{Math.round(display).toLocaleString()}{suffix}</>;
}

function StatCard({
  label,
  value,
  suffix,
  tone = "primary",
}: Readonly<{ label: string; value: number; suffix?: string; tone?: "primary" | "success" | "muted" }>) {
  const TONE_CLASSES: Record<"primary" | "success" | "muted", string> = {
    success: "text-[var(--color-success)]",
    muted: "text-ink-heading",
    primary: "text-brand",
  };
  const toneClass = TONE_CLASSES[tone];
  return (
    <motion.div variants={staggerItem}>
      <GlassCard padding="md" interactive>
        <p className="eyebrow">{label}</p>
        <p className={`mono mt-2 text-[26px] font-bold ${toneClass}`}>
          <AnimatedStat value={value} suffix={suffix} />
        </p>
      </GlassCard>
    </motion.div>
  );
}

function ChartTooltip({
  active,
  payload,
  label,
}: Readonly<{ active?: boolean; payload?: Array<{ name: string; value: number; color: string }>; label?: string }>) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-[10px] border border-subtle bg-[rgba(10,11,18,0.94)] px-3 py-2 text-[12px] shadow-[0_12px_32px_rgba(0,0,0,0.45)]">
      {label && <p className="mono mb-1 text-[10px] text-ink-subtle">{label}</p>}
      {payload.map((entry) => (
        <p key={entry.name} style={{ color: entry.color }} className="font-medium">
          {entry.name}: {entry.value}
        </p>
      ))}
    </div>
  );
}

function TrendChart({ trend }: Readonly<{ trend: AnalyticsOverview["trend"] }>) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={trend} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
        <defs>
          <linearGradient id="fillApplications" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#f97316" stopOpacity={0.45} />
            <stop offset="95%" stopColor="#f97316" stopOpacity={0.02} />
          </linearGradient>
          <linearGradient id="fillHires" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#22c55e" stopOpacity={0.5} />
            <stop offset="95%" stopColor="#22c55e" stopOpacity={0.03} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" vertical={false} />
        <XAxis
          dataKey="date"
          tickFormatter={(d: string) => new Date(d).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
          tick={{ fill: "#8b93a1", fontSize: 10 }}
          axisLine={{ stroke: "rgba(255,255,255,0.08)" }}
          tickLine={false}
          minTickGap={28}
        />
        <YAxis allowDecimals={false} tick={{ fill: "#8b93a1", fontSize: 10 }} axisLine={false} tickLine={false} width={28} />
        <Tooltip content={<ChartTooltip />} />
        <Area type="monotone" dataKey="applications" name="Applications" stroke="#f97316" fill="url(#fillApplications)" strokeWidth={2} animationDuration={900} />
        <Area type="monotone" dataKey="hires" name="Hires" stroke="#22c55e" fill="url(#fillHires)" strokeWidth={2} animationDuration={900} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

/** Cell is deprecated in recharts 3.x — colors are now applied via the shape prop instead. */
function StageSector(props: Readonly<PieSectorShapeProps>) {
  const { index = 0 } = props;
  return <Sector {...props} fill={CHART_COLORS[index % CHART_COLORS.length]} stroke="rgba(7,8,16,0.9)" strokeWidth={2} />;
}

function StageDonut({ stages }: Readonly<{ stages: AnalyticsOverview["stage_distribution"] }>) {
  const total = stages.reduce((sum, s) => sum + s.count, 0);
  return (
    <div className="grid grid-cols-1 items-center gap-4 sm:grid-cols-[220px_1fr]">
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie
            data={stages}
            dataKey="count"
            nameKey="stage"
            innerRadius={58}
            outerRadius={88}
            paddingAngle={2}
            animationDuration={900}
            shape={StageSector}
          />
          <Tooltip content={<ChartTooltip />} />
        </PieChart>
      </ResponsiveContainer>
      <div className="flex flex-col gap-2.5">
        {stages.map((s, i) => (
          <div key={s.stage} className="flex items-center justify-between gap-3 text-[12px]">
            <span className="flex items-center gap-2 text-ink-muted">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: CHART_COLORS[i % CHART_COLORS.length] }} />
              {s.stage}
            </span>
            <span className="mono text-ink-heading">{s.count} · {total ? Math.round((s.count / total) * 100) : 0}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function SourceBarChart({ sources }: Readonly<{ sources: AnalyticsOverview["source_breakdown"] }>) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={sources} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" vertical={false} />
        <XAxis dataKey="source" tick={{ fill: "#8b93a1", fontSize: 10 }} axisLine={{ stroke: "rgba(255,255,255,0.08)" }} tickLine={false} />
        <YAxis allowDecimals={false} tick={{ fill: "#8b93a1", fontSize: 10 }} axisLine={false} tickLine={false} width={28} />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
        <Legend wrapperStyle={{ fontSize: 11, color: "#8b93a1" }} />
        <Bar dataKey="applications" name="Applications" fill="#6366f1" radius={[4, 4, 0, 0]} animationDuration={800} />
        <Bar dataKey="hired" name="Hired" fill="#22c55e" radius={[4, 4, 0, 0]} animationDuration={800} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Ranked list with a growing fill bar — cheaper than another full chart and reads faster for a leaderboard. */
function Leaderboard({
  rows,
  primaryLabel,
  secondaryLabel = "hired",
}: Readonly<{
  rows: Array<{ key: string | number; label: string; primary: number; secondary?: number; meta?: string }>;
  primaryLabel: string;
  secondaryLabel?: string;
}>) {
  const max = Math.max(...rows.map((r) => r.primary), 1);
  return (
    <div className="flex flex-col gap-4">
      {rows.map((row, i) => (
        <div key={row.key}>
          <div className="flex items-center justify-between gap-3 text-[12px]">
            <span className="min-w-0 truncate font-medium text-ink-heading">{row.label}</span>
            <span className="mono shrink-0 text-ink-muted">
              {row.primary} {primaryLabel}
              {row.secondary !== undefined ? ` · ${row.secondary} ${secondaryLabel}` : ""}
              {row.meta ? ` · ${row.meta}` : ""}
            </span>
          </div>
          <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-glass-low">
            <motion.div
              initial={{ scaleX: 0 }}
              animate={{ scaleX: row.primary / max }}
              transition={{ duration: DUR.slow, ease: EASE_OUT, delay: 0.05 * i }}
              style={{ originX: 0 }}
              className="h-full rounded-full bg-[var(--color-primary)]"
            />
          </div>
        </div>
      ))}
    </div>
  );
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
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [funnel, setFunnel] = useState<FunnelResult | null>(null);
  const [selectionRates, setSelectionRates] = useState<SelectionRatesResult | null>(null);
  const [segmentBy, setSegmentBy] = useState<"source" | "experience_band">("source");
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (authLoading) return;
    if (!actor) {
      router.push("/login?next=/org/analytics");
      return;
    }
    if (!activeOrgId) return;
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, actor, activeOrgId, segmentBy, days]);

  const load = async () => {
    setLoading(true);
    try {
      const [overviewData, funnelData, ratesData] = await Promise.all([
        api.get<AnalyticsOverview>(`/orgs/${activeOrgId}/analytics/overview?days=${days}`),
        api.get<FunnelResult>(`/orgs/${activeOrgId}/analytics/funnel`),
        api.get<SelectionRatesResult>(`/orgs/${activeOrgId}/analytics/selection-rates?segment_by=${segmentBy}`),
      ]);
      setOverview(overviewData);
      setFunnel(funnelData);
      setSelectionRates(ratesData);
    } catch (err) {
      notify.error(analyticsErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  if (authLoading || loading) {
    return (
      <div className="min-h-screen">
        <Navbar />
        <PageShell className="!max-w-[1180px] pt-[112px]">
          <SkeletonList count={3} />
        </PageShell>
      </div>
    );
  }

  const totals = overview?.totals;

  return (
    <div className="min-h-screen">
      <Navbar />
      <PageShell className="!max-w-[1180px] pt-[112px]">
        <PageHeader
          eyebrow="RECRUITER ANALYTICS"
          title="Hiring performance"
          description="Volume, velocity, and fairness across every campaign in this workspace."
          actions={
            <Select
              aria-label="Date range"
              wrapperClassName="w-[160px]"
              value={String(days)}
              onChange={(e) => setDays(Number(e.target.value))}
            >
              <option value="30">Last 30 days</option>
              <option value="60">Last 60 days</option>
              <option value="90">Last 90 days</option>
            </Select>
          }
        />

        {totals && (
          <motion.div
            initial="hidden"
            animate="visible"
            variants={staggerContainer(0.06)}
            className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6"
          >
            <StatCard label="APPLICATIONS" value={totals.applications} />
            <StatCard label="ACTIVE PIPELINE" value={totals.active} tone="muted" />
            <StatCard label="HIRED" value={totals.hired} tone="success" />
            <StatCard label="OPEN ROLES" value={totals.open_postings} tone="muted" />
            <StatCard label="CONVERSION" value={totals.conversion_rate ? Math.round(totals.conversion_rate * 100) : 0} suffix="%" />
            <StatCard
              label="AVG TIME TO HIRE"
              value={totals.avg_time_to_hire_days ?? 0}
              suffix="d"
              tone={totals.avg_time_to_hire_days ? "primary" : "muted"}
            />
          </motion.div>
        )}

        <motion.div
          initial="hidden"
          animate="visible"
          variants={staggerContainer(0.08, 0.1)}
          className="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-3"
        >
          {overview && (
            <motion.div variants={staggerItem} className="lg:col-span-2">
              <GlassCard padding="lg">
                <p className="eyebrow">APPLICATIONS &amp; HIRES OVER TIME</p>
                <div className="mt-4">
                  <TrendChart trend={overview.trend} />
                </div>
              </GlassCard>
            </motion.div>
          )}

          {overview && overview.stage_distribution.length > 0 && (
            <motion.div variants={staggerItem}>
              <GlassCard padding="lg">
                <p className="eyebrow">PIPELINE STAGE MIX</p>
                <div className="mt-4">
                  <StageDonut stages={overview.stage_distribution} />
                </div>
              </GlassCard>
            </motion.div>
          )}

          {overview && overview.source_breakdown.length > 0 && (
            <motion.div variants={staggerItem}>
              <GlassCard padding="lg">
                <p className="eyebrow">SOURCE PERFORMANCE</p>
                <div className="mt-4">
                  <SourceBarChart sources={overview.source_breakdown} />
                </div>
              </GlassCard>
            </motion.div>
          )}

          {overview && overview.campaign_performance.length > 0 && (
            <motion.div variants={staggerItem}>
              <GlassCard padding="lg">
                <p className="eyebrow">CAMPAIGN PERFORMANCE</p>
                <div className="mt-5">
                  <Leaderboard
                    primaryLabel="applications"
                    rows={overview.campaign_performance.slice(0, 8).map((c) => ({
                      key: c.campaign_id,
                      label: c.name,
                      primary: c.applications,
                      secondary: c.hired,
                      meta: `${c.postings} roles`,
                    }))}
                  />
                </div>
              </GlassCard>
            </motion.div>
          )}

          {overview && overview.top_postings.length > 0 && (
            <motion.div variants={staggerItem} className={overview.campaign_performance.length > 0 ? "" : "lg:col-span-2"}>
              <GlassCard padding="lg">
                <p className="eyebrow">TOP ROLES BY APPLICANT VOLUME</p>
                <div className="mt-5">
                  <Leaderboard
                    primaryLabel="applications"
                    rows={overview.top_postings.map((p) => ({ key: p.posting_id, label: p.title, primary: p.applications, secondary: p.hired }))}
                  />
                </div>
              </GlassCard>
            </motion.div>
          )}

          {funnel && (
            <motion.div variants={staggerItem} className="lg:col-span-2">
              <GlassCard padding="lg">
                <p className="eyebrow">HIRING FUNNEL</p>
                <div className="mt-5">
                  {funnel.funnel.map((stage, i) => (
                    <div key={stage.stage} className="border-b border-subtle py-3 first:pt-0">
                      <div className="flex items-center justify-between gap-4">
                        <span className="flex items-center gap-2 text-[13px] text-ink-heading">
                          {stage.stage}
                          {STAGE_TONE[stage.stage] && <StatusPill tone={STAGE_TONE[stage.stage]}>{stage.stage}</StatusPill>}
                        </span>
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
                    wrapperClassName="w-[170px]"
                    value={segmentBy}
                    onChange={(e) => setSegmentBy(e.target.value as "source" | "experience_band")}
                  >
                    <option value="source">By source</option>
                    <option value="experience_band">By experience band</option>
                  </Select>
                </div>

                {selectionRates.flag_adverse_impact && (
                  <div className="mt-5 flex items-start gap-3 rounded-[10px] border border-[color-mix(in_srgb,var(--color-warning)_40%,transparent)] bg-[color-mix(in_srgb,var(--color-warning)_10%,transparent)] px-4 py-3">
                    <StatusPill tone="warning">FLAGGED</StatusPill>
                    <p className="text-[12px] leading-[1.6] text-ink-muted">
                      One segment is selected at less than 80% the rate of the highest-selecting segment
                      (ratio: {selectionRates.adverse_impact_ratio}). Review before drawing conclusions from a small sample.
                    </p>
                  </div>
                )}

                <div className="mt-5">
                  {Object.entries(selectionRates.segments).map(([key, seg], i) => (
                    <div key={key} className="border-b border-subtle py-3 first:pt-0">
                      <div className="flex items-center justify-between gap-4">
                        <span className="text-[13px] text-ink-heading">{key}</span>
                        <span className="mono text-[13px] text-ink-muted">
                          {seg.selected}/{seg.total} · {(seg.selection_rate * 100).toFixed(0)}%
                        </span>
                      </div>
                      <FunnelBar ratio={seg.selection_rate} delay={0.05 * i} />
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
