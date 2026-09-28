"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";

import Navbar from "./components/Navbar";
import { Button, GlassCard, ScoreRing, StatusPill } from "./components/ui";
import { useAuth } from "../lib/auth-context";
import type { Actor } from "../lib/types";
import { DUR, EASE_OUT, fadeUp, staggerContainer, staggerItem } from "../lib/motion";

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
    q: "Is Evalia for job seekers or for hiring teams?",
    a: "Both, from one account. Job seekers build a profile once, get matched to roles, and apply in one click. Hiring teams post roles, run a real applicant pipeline, and get AI-assisted screening with a bias-isolated committee decision. The same login can do either — or both — without the two sides interfering with each other.",
  },
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
    a: "Yes. Every evaluation generates a structured report with executive summaries, risk breakdowns, per-agent verdicts, and score details — visible to candidates from their application tracker, and to recruiters from their organization's applicant pipeline.",
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
    <div className="glass overflow-hidden">
      <button
        type="button"
        className="flex w-full cursor-pointer items-center justify-between gap-4 border-none bg-transparent px-5 py-4 text-left font-[inherit] text-[14px] font-medium text-ink-heading"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <span>{q}</span>
        <motion.span
          animate={{ rotate: open ? 45 : 0 }}
          transition={{ duration: DUR.base, ease: EASE_OUT }}
          className="mono shrink-0 text-[16px] leading-none text-brand"
        >
          +
        </motion.span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="answer"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: DUR.base, ease: EASE_OUT }}
            className="overflow-hidden"
          >
            <p className="border-t border-subtle px-5 py-4 text-[13px] leading-[1.7] text-ink-muted">{a}</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function SectionHeading({
  eyebrow, title, children,
}: Readonly<{ eyebrow: string; title: string; children?: React.ReactNode }>) {
  return (
    <motion.div
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, amount: 0.4 }}
      variants={staggerContainer(0.07)}
      className="mb-10 text-center"
    >
      <motion.p variants={fadeUp} className="eyebrow">
        {eyebrow}
      </motion.p>
      <motion.h2
        variants={fadeUp}
        className="mt-3 text-[clamp(24px,3.4vw,34px)] font-bold tracking-[-0.02em] text-ink-heading"
      >
        {title}
      </motion.h2>
      {children && (
        <motion.p variants={fadeUp} className="mx-auto mt-4 max-w-[62ch] text-[14px] leading-relaxed text-ink-muted">
          {children}
        </motion.p>
      )}
    </motion.div>
  );
}

const AUDIENCES = [
  {
    eyebrow: "FOR JOB SEEKERS",
    title: "Find roles that actually fit",
    points: [
      "Build your profile once — every application reuses it",
      "Get matched to roles, ranked by fit, with a plain-English explanation",
      "Track each application's real pipeline stage, not a black hole",
      "Get referred by recruiters who find your profile",
    ],
    cta: "Get started as a candidate",
    intent: "candidate" as const,
  },
  {
    eyebrow: "FOR HIRING TEAMS",
    title: "Screen faster without losing rigor",
    points: [
      "Post roles and run a real applicant pipeline, not a spreadsheet",
      "AI-assisted screening with a bias-isolated committee decision",
      "Source and rank candidates against your requirements",
      "Funnel and selection-rate analytics, built in",
    ],
    cta: "Get started as a recruiter",
    intent: "recruiter" as const,
  },
];

/** Early-return per branch rather than a nested ternary, to keep this readable
 * and to match the pattern already used for Navbar's auth-area rendering. */
function PersonaCta({
  authLoading, actor, router, showLoginHint,
}: Readonly<{
  authLoading: boolean;
  actor: Actor | null;
  router: ReturnType<typeof useRouter>;
  showLoginHint?: boolean;
}>) {
  if (authLoading) {
    return (
      <div className="flex justify-center gap-3">
        <div className="skeleton h-10 w-44" />
        <div className="skeleton h-10 w-36" />
      </div>
    );
  }

  if (!actor) {
    return (
      <>
        <div className="flex flex-wrap justify-center gap-3">
          <Button size="lg" onClick={() => router.push("/register?intent=candidate")}>
            I&apos;m looking for a job
          </Button>
          <Button size="lg" variant="secondary" onClick={() => router.push("/register?intent=recruiter")}>
            I&apos;m hiring talent
          </Button>
        </div>
        {showLoginHint && (
          <p className="mt-5 text-[12px] text-ink-subtle">
            Already have an account?{" "}
            <Link href="/login" className="text-brand hover:underline">
              Log in
            </Link>
          </p>
        )}
      </>
    );
  }

  const isRecruiter = actor.memberships.length > 0;
  const [primary, secondary] = isRecruiter
    ? ([
        { label: "Go to recruiter workspace", href: "/org" },
        { label: "Browse jobs", href: "/jobs" },
      ] as const)
    : ([
        { label: "Browse jobs", href: "/jobs" },
        { label: "Complete your profile", href: "/profile" },
      ] as const);

  return (
    <div className="flex flex-wrap justify-center gap-3">
      <Button size="lg" onClick={() => router.push(primary.href)}>
        {primary.label}
      </Button>
      <Button size="lg" variant="secondary" onClick={() => router.push(secondary.href)}>
        {secondary.label}
      </Button>
    </div>
  );
}

export default function LandingPage() {
  const router = useRouter();
  const { actor, loading: authLoading } = useAuth();

  return (
    <div className="min-h-screen">
      <Navbar />

      {/* Hero Section */}
      <section className="mx-auto max-w-[var(--max-width)] px-6 pb-20 pt-[140px] text-center">
        <motion.div initial="hidden" animate="visible" variants={staggerContainer(0.08)}>
          <motion.p variants={fadeUp} className="eyebrow">
            THE HIRING PLATFORM WITH AN AI EVALUATION ENGINE BUILT IN
          </motion.p>

          <motion.h1
            variants={fadeUp}
            className="mx-auto mt-5 max-w-[17ch] text-[clamp(38px,6.5vw,66px)] font-extrabold leading-[1.05] tracking-[-0.035em] text-ink-heading"
          >
            Hiring or job-hunting, <span className="text-gradient">built for your side</span> of the table
          </motion.h1>

          <motion.p
            variants={fadeUp}
            className="mx-auto mt-6 max-w-[64ch] text-[17px] leading-[1.7] text-ink-muted"
          >
            Candidates build one profile, get matched to roles, and track every application.
            Recruiters post roles, run a real pipeline, and screen with 5 bias-isolated AI agents
            and a final human-confirmed decision.
          </motion.p>

          <motion.div variants={fadeUp} className="mt-9">
            <PersonaCta authLoading={authLoading} actor={actor} router={router} showLoginHint />
          </motion.div>
        </motion.div>

        {/* Hero Card Preview */}
        <motion.div
          initial={{ opacity: 0, y: 28 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: EASE_OUT, delay: 0.35 }}
          className="mx-auto mt-16 max-w-[720px]"
        >
          <GlassCard elevation="high" padding="lg" className="text-left">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="mono text-[11px] tracking-[0.08em] text-ink-subtle">SAMPLE EVALUATION #1042</p>
                <p className="mt-1 text-[17px] font-semibold text-ink-heading">
                  Senior Software Engineer — AI Systems
                </p>
              </div>
              <StatusPill tone="success">HIRE</StatusPill>
            </div>

            <div className="mt-6 flex flex-wrap items-center justify-between gap-6 border-t border-subtle pt-6">
              <div className="grid flex-1 grid-cols-3 gap-x-8 gap-y-4">
                {[
                  { stage: "Screening", score: "8.5" },
                  { stage: "Technical", score: "8.0" },
                  { stage: "Behavioral", score: "8.2" },
                ].map((s) => (
                  <div key={s.stage}>
                    <p className="text-[11px] text-ink-subtle">{s.stage}</p>
                    <p className="mono mt-1 text-[18px] font-semibold text-ink-heading">
                      {s.score}
                      <span className="text-[12px] text-ink-subtle">/10</span>
                    </p>
                  </div>
                ))}
              </div>
              <ScoreRing value={82} label="Overall" size={88} />
            </div>
          </GlassCard>
        </motion.div>
      </section>

      <div className="section-divider" />

      {/* Two Audiences */}
      <section className="section-container">
        <SectionHeading eyebrow="TWO SIDES, ONE PLATFORM" title="Built for job seekers and hiring teams">
          Pick a side to get started — the same account can hold both.
        </SectionHeading>

        <motion.div
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.2 }}
          variants={staggerContainer(0.1)}
          className="grid gap-5 md:grid-cols-2"
        >
          {AUDIENCES.map((audience) => (
            <motion.div key={audience.intent} variants={staggerItem} className="flex">
              <GlassCard interactive padding="lg" className="flex w-full flex-col">
                <p className="eyebrow">{audience.eyebrow}</p>
                <h3 className="mt-3 text-[20px] font-bold text-ink-heading">{audience.title}</h3>
                <ul className="mt-5 flex-1 space-y-3">
                  {audience.points.map((point) => (
                    <li key={point} className="flex gap-3 text-[13px] leading-relaxed text-ink-muted">
                      <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-[var(--color-primary)]" />
                      <span>{point}</span>
                    </li>
                  ))}
                </ul>
                <Button
                  className="mt-7 self-start"
                  onClick={() => router.push(`/register?intent=${audience.intent}`)}
                >
                  {audience.cta}
                </Button>
              </GlassCard>
            </motion.div>
          ))}
        </motion.div>
      </section>

      <div className="section-divider" />

      {/* Stats Bar */}
      <motion.section
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, amount: 0.4 }}
        variants={staggerContainer(0.06)}
        className="mx-auto grid max-w-[var(--max-width)] grid-cols-2 gap-8 px-6 py-14 text-center md:grid-cols-4"
      >
        {STATS.map((s) => (
          <motion.div key={s.label} variants={staggerItem}>
            <p className="mono text-[clamp(28px,4vw,38px)] font-bold text-brand [text-shadow:0_0_24px_rgba(249,115,22,0.3)]">
              {s.value}
            </p>
            <p className="mt-2 text-[12px] text-ink-subtle">{s.label}</p>
          </motion.div>
        ))}
      </motion.section>

      <div className="section-divider" />

      {/* Agents Architecture */}
      <section className="section-container">
        <SectionHeading eyebrow="HOW APPLICATIONS GET SCREENED" title="Five Autonomous Agents">
          This is the AI screening engine that runs inside every application on the platform — each
          agent handles a distinct evaluation domain with isolated context boundaries. Recruiters
          configure whether it runs per posting; a human always confirms the final decision.{" "}
          <Link href="/interview" className="text-brand hover:underline">
            Try it in the public sandbox →
          </Link>
        </SectionHeading>

        <motion.div
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.15 }}
          variants={staggerContainer(0.06)}
          className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
        >
          {AGENTS.map((agent) => (
            <motion.div key={agent.title} variants={staggerItem} className="flex">
              <GlassCard interactive className="flex w-full flex-col">
                <div className="flex items-center justify-between gap-3">
                  <span className="mono text-[11px] font-semibold tracking-[0.08em] text-brand">
                    {agent.stage}
                  </span>
                  <span className="mono text-[10px] text-ink-subtle">{agent.output}</span>
                </div>
                <h3 className="mt-4 text-[15px] font-semibold text-ink-heading">{agent.title}</h3>
                <p className="mt-2 text-[13px] leading-[1.65] text-ink-muted">{agent.description}</p>
              </GlassCard>
            </motion.div>
          ))}
        </motion.div>
      </section>

      <div className="section-divider" />

      {/* Pipeline Stepper */}
      <section className="section-container">
        <SectionHeading eyebrow="PIPELINE FLOW" title="Sequential Agent Pipeline" />

        <motion.div
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.3 }}
          variants={staggerContainer(0.05)}
          className="flex flex-wrap items-center justify-center gap-2"
        >
          {PIPELINE_STEPS.map((step, idx) => (
            <React.Fragment key={step}>
              {idx > 0 && <span className="text-[13px] text-ink-subtle/60">→</span>}
              <motion.span
                variants={staggerItem}
                className={`glass-low mono rounded-lg px-3.5 py-2 text-[12px] ${
                  idx === PIPELINE_STEPS.length - 1
                    ? "border-brand text-brand shadow-glow-primary"
                    : "text-ink"
                }`}
              >
                {step}
              </motion.span>
            </React.Fragment>
          ))}
        </motion.div>
      </section>

      <div className="section-divider" />

      {/* Context Isolation Matrix */}
      <section className="section-container">
        <SectionHeading eyebrow="BIAS ISOLATION" title="Context Isolation Matrix">
          The Committee Evaluator receives peer agent evaluation output only — no resume access.
        </SectionHeading>

        <motion.div
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.2 }}
          variants={fadeUp}
          className="glass overflow-x-auto"
        >
          <table className="mono w-full border-collapse text-[13px]">
            <thead>
              <tr className="border-b border-subtle text-left">
                <th className="px-5 py-3.5 text-[10px] font-semibold tracking-[0.08em] text-ink-subtle">
                  AGENT
                </th>
                {["RESUME", "ROUND 1", "ROUND 2", "ROUND 3", "ROUND 4"].map((h) => (
                  <th
                    key={h}
                    className="px-5 py-3.5 text-center text-[10px] font-semibold tracking-[0.08em] text-ink-subtle"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {CONTEXT_MATRIX.map((row) => (
                <tr
                  key={row.agent}
                  className="border-b border-subtle transition-colors duration-fast ease-out-expo last:border-0 hover:bg-glass-low"
                >
                  <td className="px-5 py-3.5 font-medium text-ink-heading">{row.agent}</td>
                  {[row.resume, row.r1, row.r2, row.r3, row.r4].map((granted, i) => (
                    <td
                      key={`${row.agent}-col-${i}`}
                      className={`px-5 py-3.5 text-center ${
                        granted ? "text-[var(--color-success)]" : "text-ink-subtle/60"
                      }`}
                    >
                      {granted ? "YES" : "NO"}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </motion.div>
      </section>

      <div className="section-divider" />

      {/* Transparency */}
      <section className="section-container">
        <SectionHeading eyebrow="AUDITABILITY" title="Evaluation Rigor & Transparency" />

        <motion.div
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.2 }}
          variants={staggerContainer(0.07)}
          className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
        >
          {TRANSPARENCY_ITEMS.map((item) => (
            <motion.div key={item.title} variants={staggerItem} className="flex">
              <GlassCard interactive className="w-full">
                <p className="text-[14px] font-semibold text-ink-heading">{item.title}</p>
                <p className="mt-2 text-[13px] leading-[1.65] text-ink-muted">{item.text}</p>
              </GlassCard>
            </motion.div>
          ))}
        </motion.div>
      </section>

      <div className="section-divider" />

      {/* FAQ */}
      <section className="section-container !max-w-[760px]">
        <SectionHeading eyebrow="FREQUENTLY ASKED QUESTIONS" title="Common Questions" />

        <motion.div
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.1 }}
          variants={staggerContainer(0.05)}
          className="flex flex-col gap-3"
        >
          {FAQ_ITEMS.map((faq) => (
            <motion.div key={faq.q} variants={staggerItem}>
              <FAQAccordion q={faq.q} a={faq.a} />
            </motion.div>
          ))}
        </motion.div>
      </section>

      <div className="section-divider" />

      {/* CTA */}
      <motion.section
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, amount: 0.3 }}
        variants={staggerContainer(0.08)}
        className="mx-auto max-w-[640px] px-6 py-24 text-center"
      >
        <motion.h2
          variants={fadeUp}
          className="text-[clamp(26px,4vw,36px)] font-bold tracking-[-0.02em] text-ink-heading"
        >
          Ready to get started?
        </motion.h2>
        <motion.p variants={fadeUp} className="mt-3 text-[14px] text-ink-muted">
          Free to try for both candidates and hiring teams.
        </motion.p>
        <motion.div variants={fadeUp} className="mt-8">
          <PersonaCta authLoading={authLoading} actor={actor} router={router} />
        </motion.div>
      </motion.section>

      {/* Footer */}
      <footer className="mono border-t border-subtle px-6 py-9 text-center text-[11px] tracking-[0.06em] text-ink-subtle">
        EVALIA — HIRING PLATFORM WITH AN AI EVALUATION ENGINE
      </footer>
    </div>
  );
}