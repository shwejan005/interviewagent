"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import Navbar from "../components/Navbar";
import {
  Alert,
  Button,
  GlassCard,
  PageHeader,
  PageShell,
  ScoreRing,
  StatusPill,
} from "../components/ui";
import type { PillTone } from "../components/ui";
import { staggerContainer, staggerItem } from "../../lib/motion";

const API_BASE = "/api";

const DECISION_TONE: Record<string, PillTone> = {
  HIRE: "success",
  HOLD: "warning",
  REJECT: "error",
  FAIL: "error",
};

function decisionTone(decision: string | undefined): PillTone {
  if (!decision) return "primary";
  return DECISION_TONE[decision.toUpperCase()] ?? "primary";
}

type FinalResult = {
  decision: string;
  verdict: any;
  verdict_text: string;
  rationale?: string;
  recommendation?: any;
  recommendation_text?: string;
  overall_score?: number;
  confidence?: number;
  status: string;
} | null;

function VerdictCard({ title, agent, verdict, roundNumber }: Readonly<{ title: string; agent: string; verdict: any; roundNumber: number }>) {
  const [expanded, setExpanded] = useState(false);
  const isJson = typeof verdict === "object" && verdict !== null;
  const decision = isJson ? verdict.decision : "";
  const score = isJson ? verdict.score : null;
  const strengths = isJson ? verdict.strengths || [] : [];
  const weaknesses = isJson ? verdict.weaknesses || [] : [];
  const reasoning = isJson ? verdict.reasoning || verdict.detailed_recommendation || verdict.overall_assessment || "" : String(verdict);
  const confidence = isJson ? verdict.confidence : null;

  const tone = decisionTone(decision);

  return (
    <GlassCard padding="none" className="overflow-hidden">
      <button
        type="button"
        className="flex w-full flex-wrap items-center justify-between gap-3 border-none bg-transparent px-5 py-4 text-left text-inherit transition-colors duration-base ease-out-expo hover:bg-[rgba(255,255,255,0.03)]"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
      >
        <span className="flex flex-wrap items-center gap-3">
          <span className="mono text-[11px] text-brand">STAGE {roundNumber}</span>
          <span className="text-[14px] font-semibold text-ink-heading">{title}</span>
          <span className="text-[12px] text-ink-subtle">— {agent}</span>
        </span>
        <span className="flex items-center gap-4">
          {score !== null && score !== undefined && (
            <span className="mono text-[14px] font-bold text-ink-heading">
              {typeof score === "number" ? score.toFixed(1) : score}/10
            </span>
          )}
          {decision && <StatusPill tone={tone}>{decision.toUpperCase()}</StatusPill>}
          <span className="mono text-[11px] text-ink-subtle">{expanded ? "[ − ]" : "[ + ]"}</span>
        </span>
      </button>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
          >
            <div className="flex flex-col gap-4 border-t border-subtle px-5 py-5">
              {confidence !== null && confidence !== undefined && (
                <p className="mono text-[11px] text-ink-subtle">
                  CONFIDENCE:{" "}
                  <span className="text-ink-heading">{(confidence * 100).toFixed(0)}%</span>
                </p>
              )}

              {isJson && verdict.leadership !== undefined && (
                <div>
                  <p className="mono mb-2 text-[10px] text-ink-subtle">DIMENSION SCORES</p>
                  <div className="grid gap-2 [grid-template-columns:repeat(auto-fill,minmax(130px,1fr))]">
                    {[
                      { label: "Leadership", value: verdict.leadership },
                      { label: "Communication", value: verdict.communication },
                      { label: "Teamwork", value: verdict.teamwork },
                      { label: "Ownership", value: verdict.ownership },
                      { label: "Conflict Handling", value: verdict.conflict_handling },
                      { label: "Culture Fit", value: verdict.culture_fit },
                    ]
                      .filter((d) => d.value !== undefined)
                      .map((d) => (
                        <div key={d.label} className="glass-low rounded-lg px-2.5 py-2">
                          <p className="text-[10px] text-ink-subtle">{d.label}</p>
                          <p className="mono mt-0.5 text-[14px] font-semibold text-ink-heading">
                            {d.value}/10
                          </p>
                        </div>
                      ))}
                  </div>
                </div>
              )}

              {(strengths.length > 0 || weaknesses.length > 0) && (
                <div className="grid gap-4 sm:grid-cols-2">
                  {strengths.length > 0 && (
                    <div>
                      <p className="mono mb-1.5 text-[10px] text-[var(--color-success)]">STRENGTHS</p>
                      {strengths.map((s: string, i: number) => (
                        <p
                          key={`${i}-${s.slice(0, 40)}`}
                          className="mb-1 text-[12px] leading-[1.6] text-ink-muted"
                        >
                          • {s}
                        </p>
                      ))}
                    </div>
                  )}
                  {weaknesses.length > 0 && (
                    <div>
                      <p className="mono mb-1.5 text-[10px] text-[var(--color-error)]">WEAKNESSES</p>
                      {weaknesses.map((w: string, i: number) => (
                        <p
                          key={`${i}-${w.slice(0, 40)}`}
                          className="mb-1 text-[12px] leading-[1.6] text-ink-muted"
                        >
                          • {w}
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {reasoning && (
                <div>
                  <p className="mono mb-1.5 text-[10px] text-ink-subtle">EVALUATION RATIONALE</p>
                  <p className="whitespace-pre-wrap text-[13px] leading-[1.7] text-ink-muted">
                    {reasoning}
                  </p>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </GlassCard>
  );
}

export default function ResultPage() {
  const router = useRouter();
  const [result, setResult] = useState<FinalResult>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rejectedAt, setRejectedAt] = useState<string | null>(null);
  const [verdicts, setVerdicts] = useState<Record<string, any>>({});

  useEffect(() => {
    const v: Record<string, any> = {};
    for (const r of ["1", "2", "3"]) {
      const vd = sessionStorage.getItem(`round${r}_verdict`);
      if (vd) {
        try { v[`round${r}`] = JSON.parse(vd); } catch { v[`round${r}`] = vd; }
      }
    }
    setVerdicts(v);

    const rejAt = sessionStorage.getItem("rejected_at");
    if (rejAt) {
      setRejectedAt(rejAt);
      const rejVerdict = sessionStorage.getItem("rejection_verdict") || "{}";
      let parsed;
      try { parsed = JSON.parse(rejVerdict); } catch { parsed = { reasoning: rejVerdict }; }
      setResult({
        decision: "REJECT",
        verdict: parsed,
        verdict_text: typeof parsed === "string" ? parsed : JSON.stringify(parsed),
        status: "REJECTED",
      });
      setLoading(false);
      return;
    }

    fetchFinalDecision();
  }, []);

  const fetchFinalDecision = async () => {
    setLoading(true);
    setError(null);
    const evaluationId = sessionStorage.getItem("evaluation_id");
    if (!evaluationId) {
      setError("No evaluation found. Please start from the beginning.");
      setLoading(false);
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/final-decision?evaluation_id=${encodeURIComponent(evaluationId)}`);
      if (!res.ok) {
        let detail = "Failed to fetch final decision.";
        try { const data = await res.json(); detail = data.detail || detail; } catch {}
        if (res.status === 429) detail = "AI rate limit reached. Click 'Retry' to try again.";
        throw new Error(detail);
      }
      const data = await res.json();
      setResult(data);
    } catch (err: any) {
      setError(err.message || "Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  const handleRestart = () => {
    sessionStorage.clear();
    router.push("/interview");
  };

  if (loading) {
    return (
      <div className="min-h-screen">
        <Navbar />
        <div
          className="flex min-h-[80vh] flex-col items-center justify-center gap-4 px-6 text-center"
          aria-busy="true"
        >
          <span className="spinner" />
          <p className="mono text-[13px] text-brand">
            RUNNING RECOMMENDATION AGENT &amp; COMMITTEE EVALUATOR...
          </p>
          <p className="text-[12px] text-ink-subtle">
            Agents are reviewing all peer verdicts to form the final decision.
          </p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen">
        <Navbar />
        <PageShell className="!max-w-[520px] pt-[112px]">
          <Alert tone="error">{error}</Alert>
          <div className="mt-6 flex justify-center gap-3">
            <Button onClick={fetchFinalDecision}>Retry</Button>
            <Button variant="secondary" onClick={handleRestart}>
              Start New
            </Button>
          </div>
        </PageShell>
      </div>
    );
  }

  const decision = result?.decision?.toUpperCase() || "UNKNOWN";
  const tone = decisionTone(decision);
  const overallScore = result?.overall_score;
  const confidence = result?.confidence;
  const committeeVerdict = result?.verdict;
  const recommendation = result?.recommendation;

  const ROUND_LABELS = [
    { key: "round1", title: "Resume Screening", agent: "Screening Agent", round: 1 },
    { key: "round2", title: "Technical Assessment", agent: "Technical Agent", round: 2 },
    { key: "round3", title: "Behavioral Assessment", agent: "Behavioral Agent", round: 3 },
  ];

  const hasScore = overallScore !== null && overallScore !== undefined;
  const hasConfidence = confidence !== null && confidence !== undefined;
  const storedRole = sessionStorage.getItem("interview_role") || "Engineering Role";
  const storedName = sessionStorage.getItem("candidate_name");
  const headline = rejectedAt
    ? `Evaluation terminated at stage ${rejectedAt}`
    : "Candidate evaluation summary";

  return (
    <div className="min-h-screen">
      <Navbar />

      <PageShell className="!max-w-[760px] pt-[112px]">
        <PageHeader
          eyebrow="EVALUATION REPORT"
          title={headline}
          description={storedName ? `${storedRole} — ${storedName}` : storedRole}
        />

        <GlassCard elevation="high" padding="lg" className="mt-8 text-center">
          <p className="mono text-[11px] tracking-[0.05em] text-ink-subtle">COMMITTEE DECISION</p>
          <div className="mt-3 flex justify-center">
            <StatusPill tone={tone} className="px-5 py-2 text-[22px] font-extrabold tracking-[0.05em]">
              {decision}
            </StatusPill>
          </div>

          {(hasScore || hasConfidence) && (
            <div className="mt-6 flex flex-wrap items-center justify-center gap-10 border-t border-subtle pt-6">
              {hasScore && (
                <div className="flex flex-col items-center gap-2">
                  <ScoreRing value={Math.round(overallScore * 10)} label={`${overallScore.toFixed(1)}/10`} />
                  <p className="mono text-[10px] text-ink-subtle">OVERALL SCORE</p>
                </div>
              )}
              {hasConfidence && (
                <div className="flex flex-col items-center gap-2">
                  <ScoreRing value={Math.round(confidence * 100)} label={`${(confidence * 100).toFixed(0)}%`} />
                  <p className="mono text-[10px] text-ink-subtle">CONFIDENCE</p>
                </div>
              )}
            </div>
          )}
        </GlassCard>

        {committeeVerdict && typeof committeeVerdict === "object" && committeeVerdict.executive_summary && (
          <GlassCard padding="lg" className="mt-4">
            <p className="eyebrow mb-2">EXECUTIVE SUMMARY</p>
            <p className="text-[13px] leading-[1.7] text-ink-muted">
              {committeeVerdict.executive_summary}
            </p>
          </GlassCard>
        )}

        {committeeVerdict && typeof committeeVerdict === "object" && committeeVerdict.hiring_risks && committeeVerdict.hiring_risks.length > 0 && (
          <GlassCard padding="lg" className="mt-4">
            <p className="mono mb-2 text-[10px] text-[var(--color-warning)]">HIRING RISKS</p>
            {committeeVerdict.hiring_risks.map((risk: string, i: number) => (
              <p
                key={`${i}-${risk.slice(0, 40)}`}
                className="mb-1 text-[13px] leading-[1.6] text-ink-muted"
              >
                • {risk}
              </p>
            ))}
          </GlassCard>
        )}

        {recommendation && typeof recommendation === "object" && (
          <div className="mt-4">
            <VerdictCard
              title="Hiring Recommendation"
              agent="Recommendation Agent"
              verdict={recommendation}
              roundNumber={4}
            />
          </div>
        )}

        {committeeVerdict && typeof committeeVerdict === "object" && committeeVerdict.recommendation && (
          <GlassCard padding="lg" className="mt-4">
            <p className="eyebrow mb-2">COMMITTEE RATIONALE &amp; CONDITIONS</p>
            <p className="text-[13px] leading-[1.7] text-ink-muted">
              {committeeVerdict.recommendation}
            </p>
          </GlassCard>
        )}

        {Object.keys(verdicts).length > 0 && (
          <motion.section
            variants={staggerContainer(0.06)}
            initial="hidden"
            animate="visible"
            className="mt-8"
          >
            <p className="mono mb-3 text-[10px] text-ink-subtle">ROUND-BY-ROUND VERDICTS</p>
            <div className="flex flex-col gap-2">
              {ROUND_LABELS.filter(({ key }) => verdicts[key]).map(({ key, title, agent, round }) => (
                <motion.div key={key} variants={staggerItem}>
                  <VerdictCard
                    title={title}
                    agent={agent}
                    verdict={verdicts[key]}
                    roundNumber={round}
                  />
                </motion.div>
              ))}
            </div>
          </motion.section>
        )}

        <div className="mt-10 flex flex-wrap justify-center gap-3">
          <Button onClick={handleRestart}>Start New Evaluation</Button>
          <Button variant="secondary" onClick={() => router.push("/dashboard")}>
            View Dashboard
          </Button>
        </div>
      </PageShell>
    </div>
  );
}