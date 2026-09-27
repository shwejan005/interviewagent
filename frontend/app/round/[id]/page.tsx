"use client";

import { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";

const API_BASE = "/api";

const ROUND_META: Record<string, { title: string; subtitle: string; agent: string }> = {
  "2": {
    title: "Technical Assessment",
    subtitle: "Answer the technical questions below. The agent evaluates technical depth, correctness, and reasoning.",
    agent: "Technical Interview Agent",
  },
  "3": {
    title: "Behavioral Assessment",
    subtitle: "Respond using the STAR methodology (Situation, Task, Action, Result) demonstrating leadership, ownership, and teamwork.",
    agent: "Behavioral Interview Agent",
  },
};

const PIPELINE_STAGES = [
  "1. Screening",
  "2. Technical",
  "3. Behavioral",
  "4. Recommendation",
  "5. Committee",
];

function stageColor(stageIndex: number, currentRound: number): string {
  if (stageIndex === currentRound) return "var(--color-primary)";
  if (stageIndex < currentRound) return "var(--color-text-heading)";
  return "var(--color-text-subtle)";
}

export default function RoundPage() {
  const router = useRouter();
  const params = useParams();
  const roundId = params.id as string;
  const roundNum = Number.parseInt(roundId, 10);

  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const meta = ROUND_META[roundId] || {
    title: `Round ${roundId}`,
    subtitle: "Answer the question below.",
    agent: `Agent ${roundId}`,
  };

  useEffect(() => {
    const storedQuestion = sessionStorage.getItem("current_question");
    if (storedQuestion) {
      setQuestion(storedQuestion);
    } else {
      setError("No question found. Please start from the beginning.");
    }
  }, [roundId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!answer.trim()) return;

    const evaluationId = sessionStorage.getItem("evaluation_id");
    if (!evaluationId) {
      setError("No evaluation found. Please start from the beginning.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await fetch(
        `${API_BASE}/round/${roundId}/answer?evaluation_id=${encodeURIComponent(evaluationId)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ answer: answer.trim() }),
        }
      );

      if (!res.ok) {
        let detail = "Failed to submit answer.";
        try {
          const data = await res.json();
          detail = data.detail || detail;
        } catch {
          if (res.status === 429) detail = "AI rate limit reached. Please wait a minute and try again.";
        }
        throw new Error(detail);
      }

      const data = await res.json();

      sessionStorage.setItem(`round${roundId}_verdict`, JSON.stringify(data.verdict || {}));
      sessionStorage.setItem(`round${roundId}_verdict_text`, data.verdict_text || "");
      sessionStorage.setItem(`round${roundId}_decision`, data.decision || "");

      if (data.status === "REJECTED") {
        sessionStorage.setItem("rejected_at", roundId);
        sessionStorage.setItem("rejection_verdict", JSON.stringify(data.verdict || {}));
        router.push("/result");
      } else if (data.status === "COMPLETE") {
        router.push("/result");
      } else if (data.next_round) {
        sessionStorage.setItem("current_question", data.question || "");
        router.push(`/round/${data.next_round}`);
      }
    } catch (err: any) {
      setError(err.message || "Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)" }}>
      <main style={{ maxWidth: 680, margin: "0 auto", padding: "60px 24px" }}>
        {/* Pipeline stepper */}
        <div style={{ display: "flex", gap: 12, marginBottom: 32, flexWrap: "wrap", fontFamily: "var(--font-mono)", fontSize: 11 }}>
          {PIPELINE_STAGES.map((s, idx) => (
            <span
              key={s}
              style={{
                color: stageColor(idx + 1, roundNum),
                fontWeight: idx + 1 === roundNum ? 600 : 400,
              }}
            >
              {s}
            </span>
          ))}
        </div>

        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-primary)", letterSpacing: "0.1em", marginBottom: 8 }}>
          STAGE {roundId} — {meta.agent.toUpperCase()}
        </div>

        <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--color-text-heading)", marginBottom: 8 }}>
          {meta.title}
        </h1>
        <p style={{ fontSize: 14, color: "var(--color-text-muted)", marginBottom: 24, lineHeight: 1.6 }}>
          {meta.subtitle}
        </p>

        {/* Question display */}
        {question && (
          <div
            className="card-surface"
            style={{
              padding: 20,
              marginBottom: 24,
              borderColor: "var(--color-border-hover)",
            }}
          >
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-primary)", marginBottom: 8, letterSpacing: "0.05em" }}>
              INTERVIEW QUESTION
            </div>
            <div style={{ fontSize: 14, color: "var(--color-text-heading)", lineHeight: 1.7, whiteSpace: "pre-wrap" }}>
              {question}
            </div>
          </div>
        )}

        {/* Answer form */}
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 20 }}>
            <label htmlFor="candidate-answer" style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--color-text-muted)", marginBottom: 6, fontFamily: "var(--font-mono)" }}>
              CANDIDATE ANSWER
            </label>
            <textarea
              id="candidate-answer"
              rows={12}
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              disabled={loading}
              placeholder="Type your response..."
              style={{
                width: "100%",
                padding: "14px 16px",
                fontSize: 13,
                color: "var(--color-text-heading)",
                background: "var(--color-surface)",
                border: "1px solid var(--color-border)",
                borderRadius: 6,
                outline: "none",
                resize: "vertical",
                fontFamily: "inherit",
                lineHeight: 1.6,
                minHeight: 200,
              }}
            />
          </div>

          {error && (
            <div style={{ padding: "10px 14px", background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: 6, fontSize: 13, color: "var(--color-error)", marginBottom: 20 }}>
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !answer.trim()}
            className="btn-primary"
            style={{
              width: "100%",
              padding: "12px 20px",
              fontSize: 14,
              opacity: loading || !answer.trim() ? 0.5 : 1,
              cursor: loading || !answer.trim() ? "not-allowed" : "pointer",
            }}
          >
            {loading ? "Evaluating response with agent..." : "Submit Answer"}
          </button>
        </form>
      </main>
    </div>
  );
}
