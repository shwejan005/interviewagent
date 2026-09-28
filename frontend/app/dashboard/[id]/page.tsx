"use client";

import { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import Navbar from "../../components/Navbar";
import {
  Alert,
  Button,
  GlassCard,
  PageHeader,
  PageShell,
  SkeletonList,
  StatusPill,
} from "../../components/ui";
import type { PillTone } from "../../components/ui";
import { staggerContainer, staggerItem } from "../../../lib/motion";

const API_BASE = "/api";

const DECISION_TONE: Record<string, PillTone> = {
  HIRE: "success",
  HOLD: "warning",
  REJECT: "error",
  PASS: "success",
  FAIL: "error",
  BORDERLINE: "warning",
};

function decisionTone(decision: string | null | undefined): PillTone {
  if (!decision) return "muted";
  return DECISION_TONE[decision.toUpperCase()] ?? "muted";
}

const PIPELINE_LABELS: Record<string, string> = {
  screening: "Resume Screening",
  technical: "Technical Interview",
  behavioral: "Behavioral Interview",
  recommendation: "Hiring Recommendation",
  committee: "Committee Decision",
};

type Report = {
  evaluation_id: number;
  candidate_name: string;
  role: string;
  status: string;
  overall_score: number | null;
  final_decision: string | null;
  pipeline: Array<{
    stage: number;
    name: string;
    agent: string;
    status: string;
    score: number | null;
    decision: string | null;
    verdict: any;
  }>;
  verdicts: Array<{
    agent_type: string;
    round_number: number;
    verdict_json: any;
    verdict_text: string;
    score: number | null;
    decision: string | null;
    confidence: number | null;
  }>;
  created_at: string;
  updated_at: string;
};

type Verdict = Report["verdicts"][number];

type VerdictRowProps = {
  verdictRecord: Verdict;
  expanded: boolean;
  onToggle: () => void;
};

function VerdictRow({ verdictRecord, expanded, onToggle }: Readonly<VerdictRowProps>) {
  const v = verdictRecord;
  const vDecision = v.decision?.toUpperCase();
  const verdict = v.verdict_json || {};
  const rationale =
    verdict.reasoning ||
    verdict.detailed_recommendation ||
    verdict.overall_assessment ||
    verdict.executive_summary;

  return (
    <motion.div variants={staggerItem}>
      <GlassCard padding="none" className="overflow-hidden">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={expanded}
          className="flex w-full flex-wrap items-center justify-between gap-3 border-none bg-transparent px-[18px] py-3.5 text-left text-inherit transition-colors duration-base ease-out-expo hover:bg-[rgba(255,255,255,0.03)]"
        >
          <span className="flex flex-wrap items-center gap-2.5">
            <span className="mono text-[11px] text-brand">STAGE {v.round_number}</span>
            <span className="text-[14px] font-semibold text-ink-heading">
              {PIPELINE_LABELS[v.agent_type] || v.agent_type}
            </span>
          </span>
          <span className="flex items-center gap-3">
            {v.score !== null && (
              <span className="mono text-[13px] font-semibold text-ink-heading">
                {v.score.toFixed(1)}/10
              </span>
            )}
            {vDecision && <StatusPill tone={decisionTone(vDecision)}>{vDecision}</StatusPill>}
            <span className="mono text-[11px] text-ink-subtle">{expanded ? "[ − ]" : "[ + ]"}</span>
          </span>
        </button>

        <AnimatePresence initial={false}>
          {expanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
              className="overflow-hidden"
            >
              <div className="flex flex-col gap-3.5 border-t border-subtle p-[18px]">
                {(verdict.strengths?.length > 0 || verdict.weaknesses?.length > 0) && (
                  <div className="grid gap-4 sm:grid-cols-2">
                    {verdict.strengths?.length > 0 && (
                      <div>
                        <p className="mono mb-1.5 text-[10px] text-[var(--color-success)]">
                          STRENGTHS
                        </p>
                        {verdict.strengths.map((s: string, i: number) => (
                          <p
                            key={`${i}-${s.slice(0, 40)}`}
                            className="mb-1 text-[12px] leading-[1.55] text-ink-muted"
                          >
                            • {s}
                          </p>
                        ))}
                      </div>
                    )}
                    {verdict.weaknesses?.length > 0 && (
                      <div>
                        <p className="mono mb-1.5 text-[10px] text-[var(--color-error)]">
                          WEAKNESSES
                        </p>
                        {verdict.weaknesses.map((w: string, i: number) => (
                          <p
                            key={`${i}-${w.slice(0, 40)}`}
                            className="mb-1 text-[12px] leading-[1.55] text-ink-muted"
                          >
                            • {w}
                          </p>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {rationale && (
                  <div>
                    <p className="mono mb-1.5 text-[10px] text-ink-subtle">RATIONALE</p>
                    <p className="whitespace-pre-wrap text-[13px] leading-[1.7] text-ink-muted">
                      {rationale}
                    </p>
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </GlassCard>
    </motion.div>
  );
}

export default function EvaluationDetailPage() {
  const router = useRouter();
  const params = useParams();
  const evalId = params.id as string;

  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedRounds, setExpandedRounds] = useState<Set<number>>(new Set());

  useEffect(() => {
    fetchReport();
  }, [evalId]);

  const fetchReport = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/evaluations/${evalId}/report`);
      if (!res.ok) throw new Error("Failed to load evaluation report.");
      const data = await res.json();
      setReport(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const toggleRound = (round: number) => {
    setExpandedRounds((prev) => {
      const next = new Set(prev);
      if (next.has(round)) next.delete(round);
      else next.add(round);
      return next;
    });
  };

  if (loading) {
    return (
      <div className="min-h-screen">
        <Navbar />
        <PageShell className="!max-w-[760px] pt-[112px]">
          <SkeletonList count={4} />
        </PageShell>
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="min-h-screen">
        <Navbar />
        <PageShell className="!max-w-[520px] pt-[112px]">
          <Alert tone="error">{error || "Evaluation not found."}</Alert>
          <div className="mt-6 flex justify-center">
            <Button variant="secondary" onClick={() => router.push("/dashboard")}>
              Back to dashboard
            </Button>
          </div>
        </PageShell>
      </div>
    );
  }

  const decision = report.final_decision?.toUpperCase() || report.status;

  return (
    <div className="min-h-screen">
      <Navbar />

      <PageShell className="!max-w-[760px] pt-[112px]">
        <button
          type="button"
          onClick={() => router.push("/dashboard")}
          className="mono mb-6 border-none bg-transparent p-0 text-[12px] text-ink-muted transition-colors duration-base hover:text-brand"
        >
          ← BACK TO DASHBOARD
        </button>

        <PageHeader
          eyebrow={`EVALUATION REPORT #${report.evaluation_id}`}
          title={report.candidate_name || "Candidate evaluation"}
          description={`${report.role} • Created ${new Date(report.created_at).toLocaleDateString()}`}
          actions={
            <div className="flex items-center gap-4">
              {report.overall_score !== null && (
                <span className="mono text-[22px] font-bold text-ink-heading">
                  {report.overall_score.toFixed(1)}/10
                </span>
              )}
              {report.final_decision && (
                <StatusPill tone={decisionTone(decision)}>{report.final_decision}</StatusPill>
              )}
            </div>
          }
        />

        <GlassCard padding="lg" className="mt-8">
          <p className="mono mb-3.5 text-[10px] text-ink-subtle">PIPELINE STAGE PROGRESS</p>
          <div className="flex flex-col">
            {report.pipeline.map((stage) => (
              <div
                key={stage.stage}
                className="flex flex-wrap items-center justify-between gap-3 border-b border-subtle py-2 last:border-b-0"
              >
                <div>
                  <span className="mono mr-2 text-[12px] text-brand">STAGE {stage.stage}</span>
                  <span className="text-[13px] text-ink-heading">{stage.name}</span>
                </div>
                <div className="flex items-center gap-3">
                  {stage.score !== null && (
                    <span className="mono text-[12px] text-ink-heading">
                      {stage.score.toFixed(1)}/10
                    </span>
                  )}
                  {stage.decision && (
                    <StatusPill tone={decisionTone(stage.decision)}>{stage.decision}</StatusPill>
                  )}
                </div>
              </div>
            ))}
          </div>
        </GlassCard>

        {report.verdicts.length > 0 && (
          <motion.section
            variants={staggerContainer(0.05)}
            initial="hidden"
            animate="visible"
            className="mt-8"
          >
            <p className="mono mb-3 text-[10px] text-ink-subtle">DETAILED VERDICTS</p>
            <div className="flex flex-col gap-2">
              {report.verdicts.map((v) => (
                <VerdictRow
                  key={v.round_number}
                  verdictRecord={v}
                  expanded={expandedRounds.has(v.round_number)}
                  onToggle={() => toggleRound(v.round_number)}
                />
              ))}
            </div>
          </motion.section>
        )}
      </PageShell>
    </div>
  );
}
