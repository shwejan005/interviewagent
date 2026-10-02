"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import Navbar from "../components/Navbar";
import {
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
import { staggerContainer, staggerItem } from "../../lib/motion";
import { cn } from "../../lib/utils";

const API_BASE = "/api";

const DECISION_TONE: Record<string, PillTone> = {
  HIRE: "success",
  HOLD: "warning",
  REJECT: "error",
};

const STATUS_TONE: Record<string, PillTone> = {
  IN_PROGRESS: "primary",
  COMPLETE: "success",
  REJECTED: "error",
};

const FILTERS = [
  { key: "all", label: "ALL" },
  { key: "COMPLETE", label: "COMPLETED" },
  { key: "IN_PROGRESS", label: "IN PROGRESS" },
  { key: "REJECTED", label: "REJECTED" },
];

type Evaluation = {
  id: number;
  candidate_name: string;
  role: string;
  status: string;
  current_round: number;
  overall_score: number | null;
  final_decision: string | null;
  created_at: string;
  updated_at: string;
  verdicts_summary?: Array<{ agent_type: string; decision: string; score: number }>;
};

type DashStats = {
  total: number;
  completed: number;
  in_progress: number;
  rejected: number;
  hired: number;
  hire_rate: number;
  avg_score: number;
};

function formatDate(d: string) {
  try {
    return new Date(d).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return d;
  }
}

function EvaluationRow({ ev }: Readonly<{ ev: Evaluation }>) {
  return (
    <motion.div variants={staggerItem}>
      <Link
        href={`/dashboard/${ev.id}`}
        className="glass glass-interactive block p-5 no-underline"
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="mb-1 flex flex-wrap items-center gap-2.5">
              <span className="text-[15px] font-semibold text-ink-heading">
                {ev.candidate_name || `Evaluation #${ev.id}`}
              </span>
              <StatusPill tone={STATUS_TONE[ev.status] ?? "muted"}>{ev.status}</StatusPill>
            </div>
            <p className="mono text-[12px] text-ink-subtle">
              {ev.role} • Stage {ev.current_round}/5 • {formatDate(ev.created_at)}
            </p>
          </div>

          <div className="flex items-center gap-4">
            {ev.overall_score !== null && (
              <span className="mono text-[16px] font-bold text-ink-heading">
                {ev.overall_score.toFixed(1)}/10
              </span>
            )}
            {ev.final_decision && (
              <StatusPill tone={DECISION_TONE[ev.final_decision] ?? "muted"}>
                {ev.final_decision}
              </StatusPill>
            )}
          </div>
        </div>
      </Link>
    </motion.div>
  );
}

type EvaluationListProps = {
  loading: boolean;
  evaluations: Evaluation[];
};

function EvaluationList({ loading, evaluations }: Readonly<EvaluationListProps>) {
  if (loading) return <SkeletonList count={4} />;

  if (evaluations.length === 0) {
    return (
      <EmptyState
        title="No evaluations in this view"
        description="No candidate evaluations match the selected filter."
        action={<ButtonLink href="/interview">Start evaluation</ButtonLink>}
      />
    );
  }

  return (
    <motion.div
      variants={staggerContainer(0.05)}
      initial="hidden"
      animate="visible"
      className="flex flex-col gap-2"
    >
      {evaluations.map((ev) => (
        <EvaluationRow key={ev.id} ev={ev} />
      ))}
    </motion.div>
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const [evaluations, setEvaluations] = useState<Evaluation[]>([]);
  const [stats, setStats] = useState<DashStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>("all");

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [evalRes, statsRes] = await Promise.all([
        fetch(`${API_BASE}/evaluations`),
        fetch(`${API_BASE}/dashboard/stats`),
      ]);

      if (evalRes.ok) {
        const evalData = await evalRes.json();
        setEvaluations(evalData.evaluations || []);
      }
      if (statsRes.ok) {
        const statsData = await statsRes.json();
        setStats(statsData);
      }
    } catch (err) {
      console.error("Failed to load dashboard:", err);
    } finally {
      setLoading(false);
    }
  };

  const filteredEvals = filter === "all"
    ? evaluations
    : evaluations.filter((e) => e.status === filter || e.final_decision === filter);

  const statCards = stats
    ? [
        { label: "Total", value: String(stats.total), tint: "text-ink-heading" },
        { label: "Completed", value: String(stats.completed), tint: "text-[var(--color-success)]" },
        { label: "In Progress", value: String(stats.in_progress), tint: "text-brand" },
        { label: "Rejected", value: String(stats.rejected), tint: "text-[var(--color-error)]" },
        { label: "Hired", value: String(stats.hired), tint: "text-[var(--color-success)]" },
        { label: "Hire Rate", value: `${stats.hire_rate}%`, tint: "text-brand" },
        {
          label: "Avg Score",
          value: stats.avg_score > 0 ? stats.avg_score.toFixed(1) : "—",
          tint: "text-brand",
        },
      ]
    : [];

  return (
    <div className="min-h-screen">
      <Navbar />

      <PageShell className="pt-[112px]">
        <PageHeader
          eyebrow="PUBLIC DEMO — AI EVALUATION SANDBOX"
          title="Sandbox evaluations"
          actions={<Button onClick={() => router.push("/interview")}>New evaluation</Button>}
        />

        <p className="mt-3 max-w-[70ch] text-[13px] leading-[1.7] text-ink-muted">
          This is an unauthenticated, public sandbox for trying the AI evaluation engine — anyone
          can see the evaluations run here. It is not connected to real job postings or applicants.
          If you&apos;re hiring for real, use the{" "}
          <Link href="/org" className="text-brand hover:underline">
            recruiter workspace
          </Link>{" "}
          instead, which is private to your organization.
        </p>

        {statCards.length > 0 && (
          <motion.div
            variants={staggerContainer(0.04)}
            initial="hidden"
            animate="visible"
            className="mt-8 grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(120px,1fr))]"
          >
            {statCards.map((s) => (
              <motion.div key={s.label} variants={staggerItem}>
                <GlassCard padding="sm" className="text-center">
                  <p className={cn("mono text-[22px] font-bold", s.tint)}>{s.value}</p>
                  <p className="mono mt-1 text-[10px] text-ink-subtle">{s.label}</p>
                </GlassCard>
              </motion.div>
            ))}
          </motion.div>
        )}

        <div className="mb-5 mt-8 flex flex-wrap gap-2">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              onClick={() => setFilter(f.key)}
              aria-pressed={filter === f.key}
              className={cn(
                "mono rounded-lg px-3 py-1.5 text-[12px] transition-all duration-base ease-out-expo",
                filter === f.key
                  ? "glass border-brand text-brand"
                  : "border border-transparent text-ink-muted hover:text-ink-heading",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>

        <EvaluationList loading={loading} evaluations={filteredEvals} />
      </PageShell>
    </div>
  );
}
