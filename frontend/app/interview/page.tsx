"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Navbar from "../components/Navbar";

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

const PIPELINE_STAGES = [
  "1. Screening",
  "2. Technical",
  "3. Behavioral",
  "4. Recommendation",
  "5. Committee",
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
    <div style={{ minHeight: "100vh", background: "var(--color-bg)" }}>
      <Navbar />

      <main style={{ maxWidth: 680, margin: "0 auto", padding: "100px 24px 60px" }}>
        {/* Stage stepper */}
        <div style={{ display: "flex", gap: 12, marginBottom: 32, flexWrap: "wrap", fontFamily: "var(--font-mono)", fontSize: 11 }}>
          {PIPELINE_STAGES.map((s, idx) => (
            <span
              key={s}
              style={{
                color: idx === 0 ? "var(--color-primary)" : "var(--color-text-subtle)",
                fontWeight: idx === 0 ? 600 : 400,
              }}
            >
              {s}
            </span>
          ))}
        </div>

        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-primary)", letterSpacing: "0.1em", marginBottom: 8 }}>
          STAGE 1 — RESUME SCREENING
        </div>
        <h1 style={{ fontSize: 28, fontWeight: 700, color: "var(--color-text-heading)", marginBottom: 8 }}>
          Start Candidate Evaluation
        </h1>
        <p style={{ fontSize: 14, color: "var(--color-text-muted)", marginBottom: 32 }}>
          Select the target engineering role and paste the candidate&apos;s resume to initiate the 5-stage agent pipeline.
        </p>

        <form onSubmit={handleSubmit}>
          {/* Candidate Name */}
          <div style={{ marginBottom: 20 }}>
            <label htmlFor="candidate-name" style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--color-text-muted)", marginBottom: 6, fontFamily: "var(--font-mono)" }}>
              CANDIDATE NAME (OPTIONAL)
            </label>
            <input
              id="candidate-name"
              type="text"
              value={candidateName}
              onChange={(e) => setCandidateName(e.target.value)}
              disabled={loading}
              placeholder="e.g. Jane Doe"
              style={{
                width: "100%",
                padding: "10px 14px",
                fontSize: 14,
                color: "var(--color-text-heading)",
                background: "var(--color-surface)",
                border: "1px solid var(--color-border)",
                borderRadius: 6,
                outline: "none",
                fontFamily: "inherit",
              }}
            />
          </div>

          {/* Role selector */}
          <fieldset style={{ border: "none", padding: 0, margin: 0, marginBottom: 20 }}>
            <legend style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--color-text-muted)", marginBottom: 6, fontFamily: "var(--font-mono)", padding: 0 }}>
              TARGET ROLE
            </legend>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 8 }}>
              {roles.map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => setRole(r)}
                  disabled={loading}
                  className="card-surface"
                  style={{
                    padding: "12px 14px",
                    textAlign: "left",
                    cursor: loading ? "default" : "pointer",
                    borderColor: role === r ? "var(--color-primary)" : "var(--color-border)",
                    background: role === r ? "rgba(249, 115, 22, 0.05)" : "var(--color-surface)",
                  }}
                >
                  <div style={{ fontSize: 13, fontWeight: 600, color: role === r ? "var(--color-primary)" : "var(--color-text-heading)" }}>
                    {r}
                  </div>
                  {ROLE_DESCRIPTIONS[r] && (
                    <div style={{ fontSize: 11, color: "var(--color-text-subtle)", marginTop: 4, lineHeight: 1.4 }}>
                      {ROLE_DESCRIPTIONS[r]}
                    </div>
                  )}
                </button>
              ))}
            </div>
          </fieldset>

          {/* Resume text */}
          <div style={{ marginBottom: 20 }}>
            <label htmlFor="resume-text" style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--color-text-muted)", marginBottom: 6, fontFamily: "var(--font-mono)" }}>
              RESUME / CV CONTENT
            </label>
            <textarea
              id="resume-text"
              rows={10}
              value={resume}
              onChange={(e) => setResume(e.target.value)}
              disabled={loading}
              placeholder="Paste candidate resume text..."
              style={{
                width: "100%",
                padding: "12px 14px",
                fontSize: 13,
                color: "var(--color-text-heading)",
                background: "var(--color-surface)",
                border: "1px solid var(--color-border)",
                borderRadius: 6,
                outline: "none",
                resize: "vertical",
                fontFamily: "inherit",
                lineHeight: 1.6,
                minHeight: 180,
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
            disabled={loading || !resume.trim() || !role}
            className="btn-primary"
            style={{
              width: "100%",
              padding: "12px 20px",
              fontSize: 14,
              opacity: loading || !resume.trim() || !role ? 0.5 : 1,
              cursor: loading || !resume.trim() || !role ? "not-allowed" : "pointer",
            }}
          >
            {loading ? `Running Screening Agent for ${role}...` : "Submit Resume & Begin Evaluation"}
          </button>
        </form>
      </main>
    </div>
  );
}