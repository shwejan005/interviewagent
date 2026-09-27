"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Navbar from "../components/Navbar";

const API_BASE = "/api";

const DECISION_CLASSES: Record<string, string> = {
  HIRE: "status-tag-success",
  HOLD: "status-tag-warning",
  REJECT: "status-tag-error",
  FAIL: "status-tag-error",
};

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

  const decisionClass = DECISION_CLASSES[decision?.toUpperCase()] || "status-tag-primary";

  return (
    <div className="card-surface" style={{ padding: 0, overflow: "hidden" }}>
      <button
        type="button"
        style={{ width: "100%", padding: "16px 20px", cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center", background: "none", border: "none", textAlign: "left", font: "inherit", color: "inherit" }}
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-primary)" }}>
            STAGE {roundNumber}
          </span>
          <span style={{ fontSize: 14, fontWeight: 600, color: "var(--color-text-heading)" }}>{title}</span>
          <span style={{ fontSize: 12, color: "var(--color-text-subtle)" }}>— {agent}</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          {score !== null && (
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 14, fontWeight: 700, color: "var(--color-text-heading)" }}>
              {typeof score === 'number' ? score.toFixed(1) : score}/10
            </span>
          )}
          {decision && <span className={`status-tag ${decisionClass}`}>{decision.toUpperCase()}</span>}
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-text-subtle)", marginLeft: 8 }}>
            {expanded ? "[ - ]" : "[ + ]"}
          </span>
        </div>
      </button>

      {expanded && (
        <div style={{ padding: 20, borderTop: "1px solid var(--color-border)", display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Confidence */}
          {confidence !== null && (
            <div>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--color-text-subtle)" }}>CONFIDENCE: </span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--color-text-heading)" }}>{(confidence * 100).toFixed(0)}%</span>
            </div>
          )}

          {/* Behavioral dimensions */}
          {isJson && verdict.leadership !== undefined && (
            <div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--color-text-subtle)", marginBottom: 8 }}>DIMENSION SCORES</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))", gap: 8 }}>
                {[
                  { label: "Leadership", value: verdict.leadership },
                  { label: "Communication", value: verdict.communication },
                  { label: "Teamwork", value: verdict.teamwork },
                  { label: "Ownership", value: verdict.ownership },
                  { label: "Conflict Handling", value: verdict.conflict_handling },
                  { label: "Culture Fit", value: verdict.culture_fit },
                ].filter(d => d.value !== undefined).map((d) => (
                  <div key={d.label} style={{ padding: "8px 10px", background: "var(--color-surface)", borderRadius: 4, border: "1px solid var(--color-border)" }}>
                    <div style={{ fontSize: 10, color: "var(--color-text-subtle)" }}>{d.label}</div>
                    <div style={{ fontFamily: "var(--font-mono)", fontSize: 14, fontWeight: 600, color: "var(--color-text-heading)", marginTop: 2 }}>{d.value}/10</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Strengths & Weaknesses */}
          {(strengths.length > 0 || weaknesses.length > 0) && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              {strengths.length > 0 && (
                <div>
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--color-success)", marginBottom: 6 }}>STRENGTHS</div>
                  {strengths.map((s: string, i: number) => (
                    <div key={`${i}-${s.slice(0, 40)}`} style={{ fontSize: 12, color: "var(--color-text-muted)", lineHeight: 1.6, marginBottom: 4 }}>
                      • {s}
                    </div>
                  ))}
                </div>
              )}
              {weaknesses.length > 0 && (
                <div>
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--color-error)", marginBottom: 6 }}>WEAKNESSES</div>
                  {weaknesses.map((w: string, i: number) => (
                    <div key={`${i}-${w.slice(0, 40)}`} style={{ fontSize: 12, color: "var(--color-text-muted)", lineHeight: 1.6, marginBottom: 4 }}>
                      • {w}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Reasoning */}
          {reasoning && (
            <div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--color-text-subtle)", marginBottom: 6 }}>EVALUATION RATIONALE</div>
              <div style={{ fontSize: 13, color: "var(--color-text-muted)", lineHeight: 1.7, whiteSpace: "pre-wrap" }}>{reasoning}</div>
            </div>
          )}
        </div>
      )}
    </div>
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
      <div style={{ minHeight: "100vh", background: "var(--color-bg)" }}>
        <Navbar />
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "80vh", gap: 16 }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 13, color: "var(--color-primary)" }}>
            RUNNING RECOMMENDATION AGENT & COMMITTEE EVALUATOR...
          </div>
          <div style={{ fontSize: 12, color: "var(--color-text-subtle)" }}>
            Agents are reviewing all peer verdicts to form the final decision.
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ minHeight: "100vh", background: "var(--color-bg)" }}>
        <Navbar />
        <div style={{ maxWidth: 500, margin: "0 auto", padding: "120px 24px", textAlign: "center" }}>
          <div style={{ padding: "12px 16px", background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: 6, fontSize: 13, color: "var(--color-error)", marginBottom: 24 }}>
            {error}
          </div>
          <div style={{ display: "flex", gap: 12, justifyContent: "center" }}>
            <button className="btn-primary" onClick={fetchFinalDecision}>Retry</button>
            <button className="btn-secondary" onClick={handleRestart}>Start New</button>
          </div>
        </div>
      </div>
    );
  }

  const decision = result?.decision?.toUpperCase() || "UNKNOWN";
  const decisionClass = DECISION_CLASSES[decision] || "status-tag-primary";
  const overallScore = result?.overall_score;
  const confidence = result?.confidence;
  const committeeVerdict = result?.verdict;
  const recommendation = result?.recommendation;

  const ROUND_LABELS = [
    { key: "round1", title: "Resume Screening", agent: "Screening Agent", round: 1 },
    { key: "round2", title: "Technical Assessment", agent: "Technical Agent", round: 2 },
    { key: "round3", title: "Behavioral Assessment", agent: "Behavioral Agent", round: 3 },
  ];

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)" }}>
      <Navbar />

      <main style={{ maxWidth: 720, margin: "0 auto", padding: "100px 24px 60px" }}>
        {/* Header */}
        <div style={{ marginBottom: 32 }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-primary)", letterSpacing: "0.1em", marginBottom: 6 }}>
            EVALUATION REPORT
          </div>
          <h1 style={{ fontSize: 28, fontWeight: 700, color: "var(--color-text-heading)", marginBottom: 4 }}>
            {rejectedAt ? `Evaluation Terminated at Stage ${rejectedAt}` : "Candidate Evaluation Summary"}
          </h1>
          <p style={{ fontSize: 14, color: "var(--color-text-muted)" }}>
            {sessionStorage.getItem("interview_role") || "Engineering Role"}
            {sessionStorage.getItem("candidate_name") ? ` — ${sessionStorage.getItem("candidate_name")}` : ""}
          </p>
        </div>

        {/* Final Decision Box */}
        <div
          className="card-surface"
          style={{ padding: 28, textAlign: "center", marginBottom: 24 }}
        >
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-text-subtle)", letterSpacing: "0.05em", marginBottom: 8 }}>
            COMMITTEE DECISION
          </div>
          <div className={`status-tag ${decisionClass}`} style={{ fontSize: 32, fontWeight: 800, letterSpacing: "0.05em" }}>
            {decision}
          </div>

          <div style={{ display: "flex", justifyContent: "center", gap: 40, marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--color-border)" }}>
            {overallScore !== null && overallScore !== undefined && (
              <div>
                <div style={{ fontSize: 11, color: "var(--color-text-subtle)" }}>OVERALL SCORE</div>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 22, fontWeight: 700, color: "var(--color-primary)", marginTop: 2 }}>
                  {overallScore.toFixed(1)}/10
                </div>
              </div>
            )}
            {confidence !== null && confidence !== undefined && (
              <div>
                <div style={{ fontSize: 11, color: "var(--color-text-subtle)" }}>CONFIDENCE</div>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 22, fontWeight: 700, color: "var(--color-text-heading)", marginTop: 2 }}>
                  {(confidence * 100).toFixed(0)}%
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Executive Summary */}
        {committeeVerdict && typeof committeeVerdict === "object" && committeeVerdict.executive_summary && (
          <div className="card-surface" style={{ padding: 20, marginBottom: 16 }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--color-primary)", marginBottom: 8 }}>
              EXECUTIVE SUMMARY
            </div>
            <div style={{ fontSize: 13, color: "var(--color-text-muted)", lineHeight: 1.7 }}>
              {committeeVerdict.executive_summary}
            </div>
          </div>
        )}

        {/* Hiring Risks */}
        {committeeVerdict && typeof committeeVerdict === "object" && committeeVerdict.hiring_risks && committeeVerdict.hiring_risks.length > 0 && (
          <div className="card-surface" style={{ padding: 20, marginBottom: 16 }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--color-warning)", marginBottom: 8 }}>
              HIRING RISKS
            </div>
            {committeeVerdict.hiring_risks.map((risk: string, i: number) => (
              <div key={`${i}-${risk.slice(0, 40)}`} style={{ fontSize: 13, color: "var(--color-text-muted)", lineHeight: 1.6, marginBottom: 4 }}>
                • {risk}
              </div>
            ))}
          </div>
        )}

        {/* Recommendation */}
        {recommendation && typeof recommendation === "object" && (
          <VerdictCard
            title="Hiring Recommendation"
            agent="Recommendation Agent"
            verdict={recommendation}
            roundNumber={4}
          />
        )}

        {/* Committee Verdict */}
        {committeeVerdict && typeof committeeVerdict === "object" && committeeVerdict.recommendation && (
          <div className="card-surface" style={{ padding: 20, marginTop: 16, marginBottom: 16 }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--color-primary)", marginBottom: 8 }}>
              COMMITTEE RATIONALE & CONDITIONS
            </div>
            <div style={{ fontSize: 13, color: "var(--color-text-muted)", lineHeight: 1.7 }}>
              {committeeVerdict.recommendation}
            </div>
          </div>
        )}

        {/* Per-round Breakdown */}
        {Object.keys(verdicts).length > 0 && (
          <div style={{ marginTop: 24, marginBottom: 24 }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--color-text-subtle)", marginBottom: 12 }}>
              ROUND-BY-ROUND VERDICTS
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {ROUND_LABELS.map(({ key, title, agent, round }) => {
                if (!verdicts[key]) return null;
                return (
                  <VerdictCard
                    key={key}
                    title={title}
                    agent={agent}
                    verdict={verdicts[key]}
                    roundNumber={round}
                  />
                );
              })}
            </div>
          </div>
        )}

        {/* Actions */}
        <div style={{ display: "flex", gap: 12, justifyContent: "center", marginTop: 32 }}>
          <button className="btn-primary" onClick={handleRestart}>
            Start New Evaluation
          </button>
          <button className="btn-secondary" onClick={() => router.push("/dashboard")}>
            View Dashboard
          </button>
        </div>
      </main>
    </div>
  );
}