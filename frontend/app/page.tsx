"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import Navbar from "./components/Navbar";

const AGENTS = [
  {
    stage: "STAGE 1",
    title: "Resume Screening Agent",
    description: "Parses technical skills, experience depth, and education against target role criteria.",
    output: "Screening Verdict & Score",
  },
  {
    stage: "STAGE 2",
    title: "Technical Interview Agent",
    description: "Evaluates technical depth, algorithmic clarity, and architectural understanding.",
    output: "Technical Verdict & Score",
  },
  {
    stage: "STAGE 3",
    title: "Behavioral Interview Agent",
    description: "Evaluates STAR responses for leadership, ownership, teamwork, and culture fit.",
    output: "Behavioral Verdict & Score",
  },
  {
    stage: "STAGE 4",
    title: "Hiring Recommendation Agent",
    description: "Synthesizes previous round verdicts into a comprehensive hiring recommendation with risk analysis.",
    output: "Recommendation & Risks",
  },
  {
    stage: "FINAL STAGE",
    title: "Committee Evaluator",
    description: "Makes the final HIRE, HOLD, or REJECT decision using only peer agent outputs. Resume is excluded to eliminate bias.",
    output: "Final Decision & Summary",
  },
];

const PIPELINE_STEPS = [
  "Candidate Resume",
  "Screening Agent",
  "Technical Agent",
  "Behavioral Agent",
  "Recommendation Agent",
  "Committee Evaluator",
  "Final Decision",
];

const STATS = [
  { value: "5", label: "Autonomous Agents" },
  { value: "4", label: "Evaluation Rounds" },
  { value: "7", label: "Validated Agent Executions" },
  { value: "JSON", label: "Schema-Validated Verdicts" },
];

const TRANSPARENCY_ITEMS = [
  { title: "Explicit Reasoning", text: "Every agent details the exact evidence and rationale behind its evaluation." },
  { title: "Evidence Tracking", text: "Scores are backed by candidate statements and resume claims." },
  { title: "Confidence Scoring", text: "Every evaluation includes a self-reported confidence score (0 to 1); this is not yet a calibrated probability of correctness." },
  { title: "Multi-Dimension Rubric", text: "Evaluated on technical, behavioral, and architectural competency." },
];

const FAQ_ITEMS = [
  {
    q: "How does the committee evaluator eliminate bias?",
    a: "The Committee Evaluator does not receive the candidate's resume or raw personal details. It reviews only the structured evaluation outputs from peer agents, ensuring the decision evaluates the interview evidence alone.",
  },
  {
    q: "What architecture powers the system?",
    a: "Evalia runs 5 specialized CrewAI agents behind a configurable LLM provider (Gemini by default). Each agent enforces a validated Pydantic JSON schema, persisted to PostgreSQL or a local SQLite fallback.",
  },
  {
    q: "What roles can be evaluated?",
    a: "Evalia supports 10 engineering roles including SDE 1, SDE 2, Senior Engineer, AI Engineer, ML Engineer, Backend, Frontend, Full-Stack, DevOps, and Data Scientist.",
  },
  {
    q: "Can evaluations be exported or reviewed?",
    a: "Yes. Every evaluation generates a structured report with executive summaries, risk breakdowns, per-agent verdicts, and score details accessible via the dashboard.",
  },
];

const CONTEXT_MATRIX = [
  { agent: "Screening Agent", resume: true, r1: false, r2: false, r3: false, r4: false },
  { agent: "Technical Agent", resume: true, r1: true, r2: false, r3: false, r4: false },
  { agent: "Behavioral Agent", resume: true, r1: true, r2: true, r3: false, r4: false },
  { agent: "Recommendation Agent", resume: false, r1: true, r2: true, r3: true, r4: false },
  { agent: "Committee Evaluator", resume: false, r1: true, r2: true, r3: true, r4: true },
];

function FAQAccordion({ q, a }: Readonly<{ q: string; a: string }>) {
  const [open, setOpen] = useState(false);
  return (
    <div className="card-surface" style={{ padding: 0 }}>
      <button
        type="button"
        style={{ width: "100%", padding: "16px 20px", cursor: "pointer", background: "none", border: "none", textAlign: "left", font: "inherit", color: "inherit" }}
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontSize: 14, fontWeight: 500, color: "var(--color-text-heading)" }}>{q}</span>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--color-text-subtle)", marginLeft: 16 }}>
            {open ? "[ - ]" : "[ + ]"}
          </span>
        </div>
        {open && (
          <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--color-border)", fontSize: 13, color: "var(--color-text-muted)", lineHeight: 1.7, textAlign: "left" }}>
            {a}
          </div>
        )}
      </button>
    </div>
  );
}

export default function LandingPage() {
  const router = useRouter();

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)" }}>
      <Navbar />

      {/* Hero Section */}
      <section style={{ padding: "120px 24px 70px", maxWidth: "var(--max-width)", margin: "0 auto", textAlign: "center" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-primary)", letterSpacing: "0.1em", marginBottom: 16 }}>
          MULTI-AGENT INTERVIEW EVALUATION SYSTEM
        </div>

        <h1
          style={{
            fontSize: "clamp(32px, 5vw, 56px)",
            fontWeight: 800,
            lineHeight: 1.1,
            letterSpacing: "-0.03em",
            color: "var(--color-text-heading)",
            marginBottom: 20,
            maxWidth: 800,
            marginLeft: "auto",
            marginRight: "auto",
          }}
        >
          Multi-agent candidate evaluation with auditability and bias isolation
        </h1>

        <p
          style={{
            fontSize: 16,
            color: "var(--color-text-muted)",
            maxWidth: 600,
            margin: "0 auto 32px",
            lineHeight: 1.7,
          }}
        >
          Five specialized AI agents conduct resume screening, technical testing, behavioral assessment, and independent committee deliberation.
        </p>

        <div style={{ display: "flex", gap: 12, justifyContent: "center" }}>
          <button className="btn-primary" onClick={() => router.push("/interview")}>
            Start Evaluation
          </button>
          <button className="btn-secondary" onClick={() => router.push("/dashboard")}>
            Open Dashboard
          </button>
        </div>

        {/* Hero Card Preview */}
        <div
          className="card-surface"
          style={{
            marginTop: 56,
            padding: 24,
            textAlign: "left",
            maxWidth: 680,
            marginLeft: "auto",
            marginRight: "auto",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
            <div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-text-subtle)", letterSpacing: "0.05em" }}>
                SAMPLE EVALUATION #1042
              </div>
              <div style={{ fontSize: 16, fontWeight: 600, color: "var(--color-text-heading)", marginTop: 2 }}>
                Senior Software Engineer — AI Systems
              </div>
            </div>
            <span className="status-tag status-tag-success">HIRE</span>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, borderTop: "1px solid var(--color-border)", paddingTop: 16 }}>
            {[
              { stage: "Screening", score: "8.5/10" },
              { stage: "Technical", score: "8.0/10" },
              { stage: "Behavioral", score: "8.2/10" },
              { stage: "Overall", score: "8.2/10" },
            ].map((s) => (
              <div key={s.stage}>
                <div style={{ fontSize: 11, color: "var(--color-text-subtle)" }}>{s.stage}</div>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 15, fontWeight: 600, color: "var(--color-text-heading)", marginTop: 4 }}>
                  {s.score}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className="section-divider" />

      {/* Stats Bar */}
      <section style={{ padding: "40px 24px", maxWidth: "var(--max-width)", margin: "0 auto", display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 24, textAlign: "center" }}>
        {STATS.map((s) => (
          <div key={s.label}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 28, fontWeight: 700, color: "var(--color-primary)" }}>
              {s.value}
            </div>
            <div style={{ fontSize: 12, color: "var(--color-text-subtle)", marginTop: 4 }}>
              {s.label}
            </div>
          </div>
        ))}
      </section>

      <div className="section-divider" />

      {/* Agents Architecture */}
      <section className="section-container">
        <div style={{ marginBottom: 40, textAlign: "center" }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-primary)", letterSpacing: "0.1em", marginBottom: 8 }}>
            ARCHITECTURE
          </div>
          <h2 style={{ fontSize: 28, fontWeight: 700, color: "var(--color-text-heading)" }}>
            Five Autonomous Agents
          </h2>
          <p style={{ fontSize: 14, color: "var(--color-text-muted)", marginTop: 6 }}>
            Each agent handles a distinct evaluation domain with isolated context boundaries.
          </p>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 16 }}>
          {AGENTS.map((agent) => (
            <div key={agent.title} className="card-surface" style={{ padding: 20 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-primary)" }}>
                  {agent.stage}
                </span>
                <span style={{ fontSize: 11, color: "var(--color-text-subtle)", fontFamily: "var(--font-mono)" }}>
                  {agent.output}
                </span>
              </div>
              <h3 style={{ fontSize: 15, fontWeight: 600, color: "var(--color-text-heading)", marginBottom: 6 }}>
                {agent.title}
              </h3>
              <p style={{ fontSize: 13, color: "var(--color-text-muted)", lineHeight: 1.6 }}>
                {agent.description}
              </p>
            </div>
          ))}
        </div>
      </section>

      <div className="section-divider" />

      {/* Pipeline Stepper */}
      <section className="section-container">
        <div style={{ marginBottom: 32, textAlign: "center" }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-primary)", letterSpacing: "0.1em", marginBottom: 8 }}>
            PIPELINE FLOW
          </div>
          <h2 style={{ fontSize: 24, fontWeight: 700, color: "var(--color-text-heading)" }}>
            Sequential Agent Pipeline
          </h2>
        </div>

        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center", alignItems: "center" }}>
          {PIPELINE_STEPS.map((step, idx) => (
            <React.Fragment key={step}>
              {idx > 0 && <span style={{ color: "var(--color-border)", fontSize: 12 }}>→</span>}
              <div
                style={{
                  padding: "8px 14px",
                  background: "var(--color-surface)",
                  border: "1px solid var(--color-border)",
                  borderRadius: 6,
                  fontFamily: "var(--font-mono)",
                  fontSize: 12,
                  color: idx === PIPELINE_STEPS.length - 1 ? "var(--color-primary)" : "var(--color-text)",
                }}
              >
                {step}
              </div>
            </React.Fragment>
          ))}
        </div>
      </section>

      <div className="section-divider" />

      {/* Context Isolation Matrix */}
      <section className="section-container">
        <div style={{ marginBottom: 32, textAlign: "center" }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-primary)", letterSpacing: "0.1em", marginBottom: 8 }}>
            BIAS ISOLATION
          </div>
          <h2 style={{ fontSize: 24, fontWeight: 700, color: "var(--color-text-heading)" }}>
            Context Isolation Matrix
          </h2>
          <p style={{ fontSize: 14, color: "var(--color-text-muted)", marginTop: 6 }}>
            The Committee Evaluator receives peer agent evaluation output only — no resume access.
          </p>
        </div>

        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, fontFamily: "var(--font-mono)" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--color-border)", textAlign: "left" }}>
                <th style={{ padding: "10px 16px", color: "var(--color-text-subtle)", fontSize: 11 }}>AGENT</th>
                <th style={{ padding: "10px 16px", color: "var(--color-text-subtle)", fontSize: 11, textAlign: "center" }}>RESUME</th>
                <th style={{ padding: "10px 16px", color: "var(--color-text-subtle)", fontSize: 11, textAlign: "center" }}>ROUND 1</th>
                <th style={{ padding: "10px 16px", color: "var(--color-text-subtle)", fontSize: 11, textAlign: "center" }}>ROUND 2</th>
                <th style={{ padding: "10px 16px", color: "var(--color-text-subtle)", fontSize: 11, textAlign: "center" }}>ROUND 3</th>
                <th style={{ padding: "10px 16px", color: "var(--color-text-subtle)", fontSize: 11, textAlign: "center" }}>ROUND 4</th>
              </tr>
            </thead>
            <tbody>
              {CONTEXT_MATRIX.map((row) => (
                <tr key={row.agent} style={{ borderBottom: "1px solid var(--color-border)" }}>
                  <td style={{ padding: "12px 16px", color: "var(--color-text-heading)", fontWeight: 500 }}>{row.agent}</td>
                  <td style={{ padding: "12px 16px", textAlign: "center", color: row.resume ? "var(--color-success)" : "var(--color-text-subtle)" }}>{row.resume ? "YES" : "NO"}</td>
                  <td style={{ padding: "12px 16px", textAlign: "center", color: row.r1 ? "var(--color-success)" : "var(--color-text-subtle)" }}>{row.r1 ? "YES" : "NO"}</td>
                  <td style={{ padding: "12px 16px", textAlign: "center", color: row.r2 ? "var(--color-success)" : "var(--color-text-subtle)" }}>{row.r2 ? "YES" : "NO"}</td>
                  <td style={{ padding: "12px 16px", textAlign: "center", color: row.r3 ? "var(--color-success)" : "var(--color-text-subtle)" }}>{row.r3 ? "YES" : "NO"}</td>
                  <td style={{ padding: "12px 16px", textAlign: "center", color: row.r4 ? "var(--color-success)" : "var(--color-text-subtle)" }}>{row.r4 ? "YES" : "NO"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="section-divider" />

      {/* Transparency */}
      <section className="section-container">
        <div style={{ marginBottom: 32, textAlign: "center" }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-primary)", letterSpacing: "0.1em", marginBottom: 8 }}>
            AUDITABILITY
          </div>
          <h2 style={{ fontSize: 24, fontWeight: 700, color: "var(--color-text-heading)" }}>
            Evaluation Rigor & Transparency
          </h2>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 16 }}>
          {TRANSPARENCY_ITEMS.map((item) => (
            <div key={item.title} className="card-surface" style={{ padding: 20 }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: "var(--color-text-heading)", marginBottom: 6 }}>
                {item.title}
              </div>
              <div style={{ fontSize: 13, color: "var(--color-text-muted)", lineHeight: 1.6 }}>
                {item.text}
              </div>
            </div>
          ))}
        </div>
      </section>

      <div className="section-divider" />

      {/* FAQ */}
      <section className="section-container" style={{ maxWidth: 720 }}>
        <div style={{ marginBottom: 32, textAlign: "center" }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-primary)", letterSpacing: "0.1em", marginBottom: 8 }}>
            FREQUENTLY ASKED QUESTIONS
          </div>
          <h2 style={{ fontSize: 24, fontWeight: 700, color: "var(--color-text-heading)" }}>
            Common Questions
          </h2>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {FAQ_ITEMS.map((faq) => (
            <FAQAccordion key={faq.q} q={faq.q} a={faq.a} />
          ))}
        </div>
      </section>

      <div className="section-divider" />

      {/* CTA */}
      <section style={{ padding: "80px 24px", textAlign: "center", maxWidth: 600, margin: "0 auto" }}>
        <h2 style={{ fontSize: 28, fontWeight: 700, color: "var(--color-text-heading)", marginBottom: 12 }}>
          Ready to run an evaluation?
        </h2>
        <p style={{ fontSize: 14, color: "var(--color-text-muted)", marginBottom: 24 }}>
          Upload a candidate resume and evaluate across all 5 autonomous agent rounds.
        </p>
        <button className="btn-primary" onClick={() => router.push("/interview")}>
          Start Evaluation
        </button>
      </section>

      {/* Footer */}
      <footer style={{ borderTop: "1px solid var(--color-border)", padding: "32px 24px", textAlign: "center", fontSize: 12, color: "var(--color-text-subtle)", fontFamily: "var(--font-mono)" }}>
        EVALIA SYSTEM — MULTI-AGENT INTERVIEW PIPELINE
      </footer>
    </div>
  );
}