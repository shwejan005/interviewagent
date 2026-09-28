"use client";

import { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import {
  Button,
  GlassCard,
  PageHeader,
  PageShell,
  StageTimeline,
  Textarea,
} from "../../components/ui";
import type { TimelineStage } from "../../components/ui";
import { notify } from "../../../lib/toast";

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

const PIPELINE_STAGES: TimelineStage[] = [
  { id: "screening", label: "Screening" },
  { id: "technical", label: "Technical" },
  { id: "behavioral", label: "Behavioral" },
  { id: "recommendation", label: "Recommendation" },
  { id: "committee", label: "Committee" },
];

export default function RoundPage() {
  const router = useRouter();
  const params = useParams();
  const roundId = params.id as string;
  const roundNum = Number.parseInt(roundId, 10);

  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);

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
      notify.error("No question found. Please start from the beginning.");
    }
  }, [roundId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!answer.trim()) return;

    const evaluationId = sessionStorage.getItem("evaluation_id");
    if (!evaluationId) {
      notify.error("No evaluation found. Please start from the beginning.");
      return;
    }

    setLoading(true);

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
      notify.error(err.message || "Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen">
      <PageShell className="!max-w-[720px]">
        <StageTimeline
          stages={PIPELINE_STAGES}
          currentIndex={Math.max(0, roundNum - 1)}
          className="mb-10"
        />

        <PageHeader
          eyebrow={`STAGE ${roundId} — ${meta.agent.toUpperCase()}`}
          title={meta.title}
          description={meta.subtitle}
        />

        {question && (
          <GlassCard elevation="high" padding="lg" className="mt-8">
            <p className="eyebrow mb-2">INTERVIEW QUESTION</p>
            <p className="whitespace-pre-wrap text-[14px] leading-[1.7] text-ink-heading">
              {question}
            </p>
          </GlassCard>
        )}

        <form onSubmit={handleSubmit} className="mt-8 flex flex-col gap-6">
          <Textarea
            id="candidate-answer"
            label="CANDIDATE ANSWER"
            rows={12}
            className="min-h-[220px] leading-[1.65]"
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            disabled={loading}
            placeholder="Type your response..."
          />

          <Button type="submit" size="lg" fullWidth loading={loading} disabled={!answer.trim()}>
            {loading ? "Evaluating response with agent..." : "Submit Answer"}
          </Button>
        </form>
      </PageShell>
    </div>
  );
}
