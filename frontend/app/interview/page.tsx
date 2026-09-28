"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Navbar from "../components/Navbar";
import {
  Alert,
  Button,
  Input,
  PageHeader,
  PageShell,
  StageTimeline,
  Textarea,
} from "../components/ui";
import type { TimelineStage } from "../components/ui";
import { cn } from "../../lib/utils";

const API_BASE = "/api";

const ROLE_DESCRIPTIONS: Record<string, string> = {
  "SDE 1": "Entry-level software development engineer focused on coding and debugging.",
  "SDE 2": "Mid-level software engineer designing and owning features end-to-end.",
  "Senior Software Engineer": "Senior engineer leading technical design and architectural decisions.",
  "AI Engineer": "Engineer specializing in LLMs, ML frameworks, and AI systems.",
  "ML Engineer": "Engineer focused on building and deploying production ML pipelines.",
  "Backend Developer": "Developer focused on APIs, database design, and backend systems.",
  "Frontend Developer": "Developer specializing in user interfaces and web performance.",
  "Full-Stack Developer": "Developer working across frontend and backend stacks.",
  "DevOps Engineer": "Engineer focused on infrastructure, CI/CD, and system reliability.",
  "Data Scientist": "Scientist specializing in data modeling and analytical insights.",
};

const PIPELINE_STAGES: TimelineStage[] = [
  { id: "screening", label: "Screening" },
  { id: "technical", label: "Technical" },
  { id: "behavioral", label: "Behavioral" },
  { id: "recommendation", label: "Recommendation" },
  { id: "committee", label: "Committee" },
];

export default function InterviewPage() {
  const router = useRouter();
  const [resume, setResume] = useState("");
  const [role, setRole] = useState("");
  const [roles, setRoles] = useState<string[]>([]);
  const [candidateName, setCandidateName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    sessionStorage.clear();
    fetch(`${API_BASE}/roles`)
      .then((res) => res.json())
      .then((data) => setRoles(data.roles || []))
      .catch(() => setRoles(Object.keys(ROLE_DESCRIPTIONS)));
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resume.trim() || !role) return;

    setLoading(true);
    setError(null);
    sessionStorage.clear();

    try {
      const res = await fetch(`${API_BASE}/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          resume: resume.trim(),
          role,
          candidate_name: candidateName.trim(),
        }),
      });

      if (!res.ok) {
        let detail = "Failed to start interview.";
        try {
          const data = await res.json();
          detail = data.detail || detail;
        } catch {
          if (res.status === 429) detail = "AI rate limit reached. Please wait a minute and try again.";
        }
        throw new Error(detail);
      }

      const data = await res.json();

      sessionStorage.setItem("evaluation_id", String(data.evaluation_id || ""));
      sessionStorage.setItem("round1_verdict", JSON.stringify(data.verdict || {}));
      sessionStorage.setItem("round1_verdict_text", data.verdict_text || "");
      sessionStorage.setItem("round1_decision", data.decision || "");
      sessionStorage.setItem("interview_role", role);
      sessionStorage.setItem("candidate_name", candidateName.trim());

      if (data.status === "REJECTED") {
        sessionStorage.setItem("rejected_at", "1");
        sessionStorage.setItem("rejection_verdict", JSON.stringify(data.verdict || {}));
        router.push("/result");
      } else {
        sessionStorage.setItem("current_question", data.question || "");
        router.push("/round/2");
      }
    } catch (err: any) {
      setError(err.message || "Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen">
      <Navbar />

      <PageShell className="!max-w-[720px] pt-[112px]">
        <StageTimeline stages={PIPELINE_STAGES} currentIndex={0} className="mb-10" />

        <PageHeader
          eyebrow="PUBLIC SANDBOX — STAGE 1 OF 5"
          title="Try the AI evaluation engine"
        />
        <p className="mt-3 text-[14px] leading-[1.7] text-ink-muted">
          This is a public, no-signup sandbox for trying the 5-stage agent pipeline on a sample
          resume — it doesn&apos;t create a real job application. To actually apply to a role, use{" "}
          <Link href="/jobs" className="text-brand hover:underline">
            the job board
          </Link>{" "}
          instead.
        </p>

        <form onSubmit={handleSubmit} className="mt-8 flex flex-col gap-6">
          <Input
            id="candidate-name"
            label="CANDIDATE NAME (OPTIONAL)"
            value={candidateName}
            onChange={(e) => setCandidateName(e.target.value)}
            disabled={loading}
            placeholder="e.g. Jane Doe"
          />

          <fieldset className="m-0 border-none p-0">
            <legend className="field-label p-0">TARGET ROLE</legend>
            <div className="mt-2 grid gap-2 [grid-template-columns:repeat(auto-fill,minmax(200px,1fr))]">
              {roles.map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => setRole(r)}
                  disabled={loading}
                  aria-pressed={role === r}
                  className={cn(
                    "glass rounded-[var(--radius)] p-3.5 text-left transition-all duration-base ease-out-expo disabled:cursor-default",
                    role === r
                      ? "border-brand bg-[rgba(249,115,22,0.07)] shadow-glow-primary"
                      : "hover:-translate-y-0.5 hover:border-strong",
                  )}
                >
                  <span
                    className={cn(
                      "block text-[13px] font-semibold",
                      role === r ? "text-brand" : "text-ink-heading",
                    )}
                  >
                    {r}
                  </span>
                  {ROLE_DESCRIPTIONS[r] && (
                    <span className="mt-1 block text-[11px] leading-[1.45] text-ink-subtle">
                      {ROLE_DESCRIPTIONS[r]}
                    </span>
                  )}
                </button>
              ))}
            </div>
          </fieldset>

          <Textarea
            id="resume-text"
            label="RESUME / CV CONTENT"
            rows={10}
            className="min-h-[180px] leading-[1.65]"
            value={resume}
            onChange={(e) => setResume(e.target.value)}
            disabled={loading}
            placeholder="Paste candidate resume text..."
          />

          {error && <Alert tone="error">{error}</Alert>}

          <Button
            type="submit"
            size="lg"
            fullWidth
            loading={loading}
            disabled={!resume.trim() || !role}
          >
            {loading ? `Running Screening Agent for ${role}...` : "Submit Resume & Begin Evaluation"}
          </Button>
        </form>
      </PageShell>
    </div>
  );
}