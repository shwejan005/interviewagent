"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { usePathname, useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { Plus, Save, Trash2 } from "lucide-react";
import Navbar from "../../../components/Navbar";
import {
  Button,
  DateTimePicker,
  dateKey,
  EmptyState,
  GlassCard,
  Input,
  PageShell,
  Select,
  SkeletonList,
  StatusPill,
  Textarea,
} from "../../../components/ui";
import type { PillTone } from "../../../components/ui";
import { useAuth } from "../../../../lib/auth-context";
import { useActivePageRefresh } from "../../../../lib/use-active-page-refresh";
import { api, ApiError } from "../../../../lib/api";
import { notify } from "../../../../lib/toast";
import type {
  ApplicationDetail,
  ApplicationEvent,
  ApplicationReportResponse,
  ApplicationSummary,
  CandidateRecommendation,
  CriteriaDraft,
  CriteriaResponse,
  JobPosting,
  PostingCriterion,
} from "../../../../lib/types";
import { staggerContainer, staggerItem } from "../../../../lib/motion";

const NEXT_STAGE_OPTIONS: Record<string, string[]> = {
  APPLIED: ["SCREENING"],
  SCREENING: ["TECHNICAL"],
  AI_INTERVIEW: ["INTERVIEW"],
  PENDING_REVIEW: [],
  TECHNICAL: ["BEHAVIORAL", "INTERVIEW"],
  BEHAVIORAL: ["INTERVIEW", "OFFER"],
  INTERVIEW: ["OFFER"],
  OFFER: ["HIRED"],
};

type RecruiterAIInterviewStatus = {
  status: string;
  phase: string;
  rubric_version: string;
  role_level: string;
  screening_result: {
    decision?: string;
    score?: number;
    constraint_gaps?: string[];
    minimum_criteria?: {
      status: string;
      checks: Array<{ criterion_key: string; requirement?: string; state: string; reason: string }>;
    };
  };
  error_code: string | null;
  turns: Array<{ sequence_no: number; phase: string; question_type: string; question_text: string; answer_text: string | null; difficulty: number; assessment: { summary?: string } }>;
};

type InterviewTeamMember = {
  user_id: number;
  full_name: string;
  email: string;
  role_name: string;
  interview_skills?: string[];
  weekly_capacity?: number;
  scheduled_this_week?: number;
  available_for_interviews?: boolean;
};
type ScheduledInterview = {
  id: number;
  title: string;
  scheduled_start: string;
  scheduled_end: string;
  timezone: string;
  status: string;
  meeting_url: string;
  participants: Array<{ user_id: number; full_name: string; participant_role: string }>;
  scorecard_summary?: {
    submitted: number;
    expected: number;
    complete: boolean;
    hidden_until_complete: boolean;
    interview_evidence?: Array<{ sequence_no: number; phase: string; competency_key: string; question: string; answer: string | null; assessment: { evidence_quote?: string; summary?: string } }>;
    screening_evidence?: Array<{ criterion_key: string; status: string; quote?: string }>;
    scorecards: Array<{
      interviewer_user_id: number;
      recommendation: "ADVANCE" | "HOLD";
      notes: string;
      ratings: Array<{ key: string; label: string; score: number; evidence: string }>;
    }>;
  };
};

type DecisionTarget = "TECHNICAL" | "BEHAVIORAL" | "INTERVIEW" | "OFFER";

function nextHumanStageOptions(interviews: ScheduledInterview[] = []): DecisionTarget[] {
  const completed = [...interviews]
    .filter((interview) => interview.status === "COMPLETED")
    .sort((left, right) => Date.parse(right.scheduled_start) - Date.parse(left.scheduled_start));
  const lastTitle = completed[0]?.title.toLowerCase() || "";
  if (!lastTitle) return ["TECHNICAL"];
  if (lastTitle.includes("technical")) return ["BEHAVIORAL", "INTERVIEW"];
  if (lastTitle.includes("behavioral")) return ["INTERVIEW", "OFFER"];
  return ["OFFER"];
}

function reportSuggestedAction(report: ApplicationReportResponse | null, interviews: ScheduledInterview[] = []): "PROMOTE" | "HOLD" {
  const completed = [...interviews]
    .filter((interview) => interview.status === "COMPLETED" && interview.scorecard_summary?.complete)
    .sort((left, right) => Date.parse(right.scheduled_start) - Date.parse(left.scheduled_start))[0];
  if (completed?.scorecard_summary?.scorecards.length) {
    return completed.scorecard_summary.scorecards.every((scorecard) => scorecard.recommendation === "ADVANCE") ? "PROMOTE" : "HOLD";
  }
  return report?.interview_details.fit_nudge?.suggested_action || "HOLD";
}

function aiInterviewStatusTone(status: string): PillTone {
  if (status === "REVIEW_REQUIRED") return "warning";
  if (status === "REPORT_READY") return "success";
  return "primary";
}

function useRecruiterInterviewPolling(
  orgId: number | null,
  applicationId: number | undefined,
  status: RecruiterAIInterviewStatus | null,
  setStatus: (status: RecruiterAIInterviewStatus) => void,
  setReport: (report: ApplicationReportResponse) => void,
) {
  useEffect(() => {
    if (!orgId || !applicationId || !status) return;
    const activeStatuses = new Set(["SCREENING_QUEUED", "SCREENING", "INTERVIEW_READY", "INTERVIEW_IN_PROGRESS", "ANSWER_PROCESSING", "REPORT_PENDING"]);
    if (!activeStatuses.has(status.status)) return;
    const delay = status.status === "INTERVIEW_READY" || status.status === "INTERVIEW_IN_PROGRESS" ? 10000 : 2500;
    let disposed = false;
    const timer = window.setTimeout(async () => {
      try {
        const next = await api.get<RecruiterAIInterviewStatus>(`/orgs/${orgId}/applications/${applicationId}/ai-interview`);
        if (disposed) return;
        setStatus(next);
        if (next.status === "REPORT_READY") {
          const report = await api.get<ApplicationReportResponse>(`/orgs/${orgId}/applications/${applicationId}/report`);
          if (!disposed) setReport(report);
        }
      } catch {
        // The report may not be persisted yet; preserve the last known pipeline state.
      }
    }, delay);
    return () => {
      disposed = true;
      window.clearTimeout(timer);
    };
  }, [applicationId, orgId, setReport, setStatus, status]);
}

function formatSalaryRange(min: number | null, max: number | null): string {
  if (!min && !max) return "";
  return `${min ?? "?"} – ${max ?? "?"}`;
}

function candidateName(app: ApplicationSummary): string {
  return (app as unknown as { candidate_name?: string }).candidate_name || "Candidate";
}

function PipelineList({
  applications,
  onTransition,
  onView,
}: Readonly<{
  applications: ApplicationSummary[];
  onTransition: (applicationId: number, toStage: string) => Promise<void>;
  onView: (applicationId: number) => void;
}>) {
  if (applications.length === 0) {
    return (
      <EmptyState
        title="No applicants yet"
        description="Publish the posting and share the link — applicants land here the moment they apply."
      />
    );
  }

  return (
    <div className="overflow-x-auto border border-subtle bg-[rgba(17,18,30,0.74)]">
      <table className="w-full min-w-[820px] border-collapse text-left">
        <thead className="border-b border-subtle bg-[rgba(255,255,255,0.025)]">
          <tr className="mono text-[10px] tracking-[0.08em] text-ink-subtle">
            <th className="px-5 py-3 font-medium">CANDIDATE</th>
            <th className="px-5 py-3 font-medium">STAGE</th>
            <th className="px-5 py-3 font-medium">AI SCREEN / INTERVIEW</th>
            <th className="px-5 py-3 font-medium">SOURCE</th>
            <th className="px-5 py-3 font-medium">APPLIED</th>
            <th className="px-5 py-3 font-medium">MOVE TO</th>
            <th className="px-5 py-3 font-medium" aria-label="Actions" />
          </tr>
        </thead>
        <tbody>
          {applications.map((app) => (
            <tr key={app.id} className="border-b border-subtle last:border-0 hover:bg-[rgba(255,255,255,0.025)]">
              <td className="px-5 py-4 text-[13px] font-semibold text-ink-heading">{candidateName(app)}</td>
              <td className="px-5 py-4"><StatusPill tone="primary">{app.current_stage}</StatusPill></td>
              <td className="px-5 py-4 text-[11px] text-ink-muted">{app.ai_interview_status?.replaceAll("_", " ") || "Queued on apply"}</td>
              <td className="px-5 py-4 text-[12px] text-ink-muted">{app.status}</td>
              <td className="px-5 py-4 text-[12px] text-ink-muted">{new Date(app.created_at).toLocaleDateString()}</td>
              <td className="px-5 py-3">
                {app.current_stage === "PENDING_REVIEW" ? <span className="text-[10px] text-ink-subtle">Use report decision</span> : (
                  <Select aria-label={`Move ${candidateName(app)} to stage`} wrapperClassName="w-[145px]" defaultValue="" onChange={(e) => {
                    if (e.target.value) void onTransition(app.id, e.target.value);
                    e.target.value = "";
                  }}>
                    <option value="">Select stage</option>
                    {(NEXT_STAGE_OPTIONS[app.current_stage] || []).map((stage) => <option key={stage} value={stage}>{stage}</option>)}
                  </Select>
                )}
              </td>
              <td className="px-5 py-3 text-right whitespace-nowrap">
                <Button size="sm" variant="ghost" onClick={() => onView(app.id)}>View</Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RecommendedList({ candidates }: Readonly<{ candidates: CandidateRecommendation[] }>) {
  if (candidates.length === 0) {
    return (
      <EmptyState
        title="No matches yet"
        description="No discoverable candidates match this posting yet. Matches appear as more candidates opt in."
      />
    );
  }

  return (
    <motion.div
      initial="hidden"
      animate="visible"
      variants={staggerContainer(0.05)}
      className="flex flex-col gap-3"
    >
      {candidates.map((cand) => (
        <motion.div key={cand.user_id} variants={staggerItem}>
          <GlassCard padding="sm">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <p className="text-[14px] font-semibold text-ink-heading">{cand.full_name}</p>
                <p className="mt-0.5 text-[12px] text-ink-subtle">
                  {cand.headline} · {cand.location}
                </p>
              </div>
              <span className="mono shrink-0 text-[15px] font-bold text-brand">{cand.score}/10</span>
            </div>
            <p className="mt-3 text-[12px] leading-[1.65] text-ink-muted">{cand.explanation}</p>
          </GlassCard>
        </motion.div>
      ))}
    </motion.div>
  );
}

function CriteriaEditor({
  draft,
  loading,
  saving,
  onSave,
  onChange,
}: Readonly<{
  draft: CriteriaDraft | null;
  loading: boolean;
  saving: boolean;
  onSave: () => Promise<void>;
  onChange: (draft: CriteriaDraft) => void;
}>) {
  if (loading) return <SkeletonList count={3} />;
  if (!draft) return <EmptyState title="Criteria unavailable" description="We couldn't load evaluation criteria for this posting." />;

  const totalWeight = draft.competencies.reduce((total, competency) => total + Number(competency.weight || 0), 0);
  const updateCompetency = (index: number, patch: Partial<PostingCriterion>) => {
    onChange({
      ...draft,
      competencies: draft.competencies.map((competency, itemIndex) => itemIndex === index ? { ...competency, ...patch } : competency),
    });
  };

  return (
    <GlassCard padding="lg" className="max-w-[860px]">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-subtle pb-5">
        <div>
          <p className="eyebrow">INTERVIEW RUBRIC</p>
          <h2 className="mt-2 text-[19px] font-semibold text-ink-heading">Evaluation criteria</h2>
          <p className="mt-1 max-w-[600px] text-[12px] leading-relaxed text-ink-muted">Define what the interview should measure. Completed interviews generate a weighted report against this rubric.</p>
          <p className="mt-2 max-w-[600px] text-[11px] leading-relaxed text-ink-subtle">This policy is used automatically for every new application after you publish it. No per-applicant screen or interview invitation is required.</p>
        </div>
        <span className={`mono rounded-full border px-3 py-1 text-[11px] ${Math.abs(totalWeight - 100) < 0.01 ? "border-[rgba(34,197,94,0.35)] text-[var(--color-success)]" : "border-[rgba(245,158,11,0.4)] text-[var(--color-warning)]"}`}>
          {totalWeight.toFixed(0)}% total weight
        </span>
      </div>

      <div className="mt-6 flex flex-col gap-4">
        {draft.competencies.map((competency, index) => (
          <div key={`${competency.key}-${index}`} className="border border-subtle bg-[rgba(255,255,255,0.025)] p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <p className="mono text-[10px] tracking-[0.08em] text-ink-subtle">COMPETENCY {index + 1}</p>
              <button type="button" aria-label={`Remove ${competency.label || "competency"}`} className="rounded-lg p-2 text-ink-subtle transition-colors hover:bg-[rgba(239,68,68,0.12)] hover:text-[var(--color-error)]" onClick={() => onChange({ ...draft, competencies: draft.competencies.filter((_, itemIndex) => itemIndex !== index) })}>
                <Trash2 size={15} />
              </button>
            </div>
            <div className="grid gap-3 sm:grid-cols-[1fr_1fr_130px_110px]">
              <Input label="LABEL" value={competency.label} onChange={(event) => updateCompetency(index, { label: event.target.value })} />
              <Input label="KEY" value={competency.key} onChange={(event) => updateCompetency(index, { key: event.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_") })} />
              <Input label="WEIGHT %" type="number" min={0.1} max={100} step={1} value={competency.weight} onChange={(event) => updateCompetency(index, { weight: Number(event.target.value) })} />
              <Select label="CATEGORY" value={competency.category || "TECHNICAL"} onChange={(event) => updateCompetency(index, { category: event.target.value as PostingCriterion["category"] })}>
                <option value="TECHNICAL">Technical</option>
                <option value="BEHAVIORAL">Behavioral</option>
              </Select>
            </div>
            <Textarea wrapperClassName="mt-3" label="DESCRIPTION" rows={2} value={competency.description} onChange={(event) => updateCompetency(index, { description: event.target.value })} />
          </div>
        ))}
      </div>

      <Button type="button" size="sm" variant="secondary" className="mt-4" onClick={() => onChange({ ...draft, competencies: [...draft.competencies, { key: `competency_${draft.competencies.length + 1}`, label: "New competency", weight: 10, description: "", category: "TECHNICAL" }] })}>
        <Plus size={14} /> Add competency
      </Button>

      <div className="mt-6 grid gap-4 border-t border-subtle pt-6 sm:grid-cols-[1fr_160px]">
        <Textarea label="CUSTOM QUESTIONS" rows={5} value={draft.custom_questions.join("\n")} hint="One question per line." onChange={(event) => onChange({ ...draft, custom_questions: event.target.value.split("\n") })} />
        <Input label="PASS THRESHOLD" type="number" min={0} max={10} step={0.1} value={draft.pass_threshold} onChange={(event) => onChange({ ...draft, pass_threshold: Number(event.target.value) })} />
      </div>
      <div className="mt-5 grid gap-3 border-t border-subtle pt-5 sm:grid-cols-2">
        <Select aria-label="TARGET ROLE LEVEL" label="TARGET ROLE LEVEL" value={draft.interview_settings.role_level} onChange={(event) => onChange({ ...draft, interview_settings: { ...draft.interview_settings, role_level: event.target.value as CriteriaDraft["interview_settings"]["role_level"] } })}>
          <option value="ENTRY">Entry level</option>
          <option value="MID">Mid level</option>
          <option value="SENIOR">Senior level</option>
        </Select>
        <Input label="TECHNICAL QUESTIONS" type="number" min={1} max={5} step={1} value={draft.interview_settings.technical_question_count} onChange={(event) => onChange({ ...draft, interview_settings: { ...draft.interview_settings, technical_question_count: Number(event.target.value) } })} />
        <Input label="BEHAVIORAL QUESTIONS" type="number" min={1} max={4} step={1} value={draft.interview_settings.behavioral_question_count} onChange={(event) => onChange({ ...draft, interview_settings: { ...draft.interview_settings, behavioral_question_count: Number(event.target.value) } })} />
        <Input label="MAX FOLLOW-UPS / QUESTION" type="number" min={0} max={2} step={1} value={draft.interview_settings.max_followups_per_question} onChange={(event) => onChange({ ...draft, interview_settings: { ...draft.interview_settings, max_followups_per_question: Number(event.target.value) } })} />
        <Input label="AI INVITATION WINDOW (DAYS)" type="number" min={1} max={30} step={1} value={draft.interview_settings.invitation_window_days} hint="Candidates can join any time before this deadline." onChange={(event) => onChange({ ...draft, interview_settings: { ...draft.interview_settings, invitation_window_days: Number(event.target.value) } })} />
      </div>
      <div className="mt-6 flex justify-end border-t border-subtle pt-5">
        <Button size="sm" loading={saving} onClick={() => void onSave()}><Save size={14} /> Save criteria</Button>
      </div>
    </GlassCard>
  );
}

function InterviewReport({
  loading,
  report,
}: Readonly<{ loading: boolean; report: ApplicationReportResponse | null }>) {
  if (loading) return <p className="mt-4 text-[13px] text-ink-muted">Loading report...</p>;
  if (!report) return <p className="mt-4 text-[13px] leading-relaxed text-ink-muted">No report yet. It will appear automatically when the interview pipeline completes.</p>;

  const details = report.interview_details;
  const fitNudge = details.fit_nudge;
  let fitTone: PillTone = "muted";
  if (fitNudge && ["STRONG_FIT", "LIKELY_FIT"].includes(fitNudge.band)) fitTone = "success";
  else if (fitNudge?.band === "UNLIKELY_FIT") fitTone = "warning";

  return (
    <div className="mt-4">
      {fitNudge && (
        <div className="mb-4 rounded-xl border border-brand/25 bg-[rgba(249,115,22,0.055)] p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="mono text-[9px] tracking-[0.12em] text-brand">ADVISORY FIT NUDGE · HUMAN DECISION REQUIRED</p>
              <p className="mt-2 text-[17px] font-semibold text-ink-heading">{fitNudge.band.replaceAll("_", " ")}</p>
              <p className="mt-1 text-[11px] leading-relaxed text-ink-muted">{fitNudge.summary}</p>
            </div>
            <StatusPill tone={fitTone}>{fitNudge.suggested_action}</StatusPill>
          </div>
          <p className="mt-3 text-[9px] text-ink-subtle">Evidence coverage: {fitNudge.evidence_coverage_percent}% · Advisory is unvalidated and is not a probability or hiring decision.</p>
        </div>
      )}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-subtle pb-4">
        <div><p className="text-[12px] text-ink-subtle">RECOMMENDATION</p><p className="mt-1 text-[17px] font-semibold text-ink-heading">{report.recommendation}</p></div>
        <div className="text-right"><p className="text-[12px] text-ink-subtle">WEIGHTED SCORE</p><p className="mt-1 mono text-[17px] font-bold text-brand">{report.overall_weighted_score === null ? "—" : `${report.overall_weighted_score}/10`}</p></div>
      </div>
      {report.overall_weighted_score !== null && <p className="mt-2 text-[10px] text-ink-subtle">Descriptive weighted average across assessed competencies only; adaptive paths have not been calibrated for candidate ranking.</p>}
      <div className="mt-4 flex flex-col gap-3">
        {report.competency_scores.map((score) => (
          <div key={score.key} className="border-b border-subtle pb-3 last:border-0">
            <div className="flex items-center justify-between gap-3"><p className="text-[12px] font-semibold text-ink-heading">{score.label}</p><span className="mono text-[12px] text-brand">{score.score === null ? "—" : `${score.score}/10`}</span></div>
            <p className="mt-1 text-[11px] leading-relaxed text-ink-muted">{score.evidence}</p>
          </div>
        ))}
      </div>
      {(details.requirements_coverage || []).length > 0 && (
        <div className="mt-5 border-t border-subtle pt-5">
          <p className="eyebrow">JOB REQUIREMENTS COVERAGE</p>
          <div className="mt-3 flex flex-col gap-3">
            {details.requirements_coverage?.map((item) => (
              <article key={`${item.kind}-${item.key}`} className="rounded-lg border border-subtle bg-[rgba(255,255,255,0.025)] p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-[12px] font-semibold text-ink-heading">{item.label}</p>
                  <span className="mono text-[9px] text-ink-subtle">{item.status.replaceAll("_", " ")}{typeof item.score === "number" ? ` · ${item.score}/10` : ""}</span>
                </div>
                <p className="mt-2 whitespace-pre-wrap text-[11px] leading-relaxed text-ink-muted">{item.evidence}</p>
                {item.resume_evidence && <blockquote className="mt-2 border-l-2 border-brand pl-3 text-[10px] italic text-ink-subtle">Resume evidence: “{item.resume_evidence}”</blockquote>}
              </article>
            ))}
          </div>
        </div>
      )}
      {(details.resume_claims || []).length > 0 && (
        <div className="mt-5 border-t border-subtle pt-5">
          <p className="eyebrow">RESUME CLAIMS CHECK</p>
          <div className="mt-3 flex flex-col gap-2">
            {details.resume_claims?.map((claim) => <div key={claim.claim} className="rounded-lg border border-subtle p-3">
              <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-[11px] font-semibold text-ink-heading">{claim.claim}</p><span className="mono text-[9px] text-brand">{claim.status.replaceAll("_", " ")}</span></div>
              {claim.resume_evidence && <p className="mt-2 text-[10px] text-ink-subtle">Resume: “{claim.resume_evidence}”</p>}
              <p className="mt-1 text-[10px] leading-relaxed text-ink-muted">Interview: {claim.interview_evidence}</p>
            </div>)}
          </div>
        </div>
      )}
      {((details.strengths || []).length > 0 || (details.concerns || []).length > 0) && (
        <div className="mt-5 grid gap-4 border-t border-subtle pt-5 sm:grid-cols-2">
          <div><p className="eyebrow">EVIDENCE-BASED STRENGTHS</p>{(details.strengths || []).map((item) => <p key={`${item.turn_sequence}-${item.text}`} className="mt-2 text-[11px] leading-relaxed text-ink-muted">{item.text}{item.evidence_quote ? ` · “${item.evidence_quote}”` : ""}</p>)}</div>
          <div><p className="eyebrow">AREAS TO PROBE</p>{(details.concerns || []).map((item) => <p key={`${item.turn_sequence}-${item.text}`} className="mt-2 text-[11px] leading-relaxed text-[var(--color-warning)]">{item.text}{item.evidence_quote ? ` · “${item.evidence_quote}”` : ""}</p>)}</div>
        </div>
      )}
      {(details.next_round_focus || []).length > 0 && <div className="mt-5 rounded-lg border border-subtle p-3"><p className="eyebrow">SUGGESTED NEXT-ROUND FOCUS</p>{details.next_round_focus?.map((item) => <p key={`${item.requirement}-${item.status}`} className="mt-2 text-[11px] text-ink-muted">{item.requirement} · {item.status.replaceAll("_", " ").toLowerCase()}</p>)}</div>}
      {report.interview_details?.screening && (
        <div className="mt-5 rounded-lg border border-subtle bg-[rgba(255,255,255,0.025)] p-4">
          <p className="eyebrow">AUTOMATED SCREENING</p>
          <p className="mt-2 text-[12px] text-ink-muted">
            {report.interview_details.screening.decision || "Completed"} · Policy {report.interview_details.screening.policy_version || report.rubric_version}
            {typeof report.interview_details.screening.score === "number" ? ` · ${report.interview_details.screening.score}/10` : ""}
          </p>
          {(report.interview_details.screening.constraint_gaps || []).map((gap, index) => (
            <p key={`${index}-${gap}`} className="mt-1 text-[11px] text-[var(--color-warning)]">{gap}</p>
          ))}
          {(report.interview_details.screening.evidence || []).map((evidence, index) => (
            <p key={`${index}-${evidence.criterion_key}`} className="mt-2 text-[10px] text-ink-subtle">
              {evidence.criterion_key.replaceAll("_", " ")} · {evidence.status}
              {evidence.quote ? ` · “${evidence.quote}”` : ""}
              {evidence.rationale ? ` — ${evidence.rationale}` : ""}
            </p>
          ))}
        </div>
      )}
      {(report.interview_details?.interview?.turns?.length || 0) > 0 && (
        <div className="mt-5 border-t border-subtle pt-5">
          <div className="flex items-center justify-between gap-3">
            <p className="eyebrow">INTERVIEW EVIDENCE</p>
            <span className="mono text-[10px] text-ink-subtle">
              {report.interview_details.interview?.role_level || "MID"} LEVEL · {report.interview_details.interview?.turn_count || 0} TURNS
            </span>
          </div>
          <div className="mt-3 flex flex-col gap-3">
            {report.interview_details.interview?.turns?.map((turn) => (
              <article key={turn.sequence_no} className="rounded-lg border border-subtle bg-[rgba(255,255,255,0.025)] p-3">
                <p className="mono text-[10px] text-ink-subtle">
                  {turn.phase} · {turn.competency_key.replaceAll("_", " ")} · LEVEL {turn.difficulty} · {turn.question_type.replaceAll("_", " ")} · {turn.answer_source || "TEXT"} ANSWER
                </p>
                <p className="mt-2 text-[12px] font-semibold text-ink-heading">{turn.question}</p>
                {turn.answer && <p className="mt-2 whitespace-pre-wrap text-[11px] leading-relaxed text-ink-muted">{turn.answer}</p>}
                {typeof turn.assessment.score === "number" && <p className="mt-2 mono text-[10px] text-brand">Evidence rating: {turn.assessment.score}/10</p>}
                {turn.assessment.summary && <p className="mt-2 text-[11px] leading-relaxed text-ink-muted">Assessment: {turn.assessment.summary}</p>}
                {turn.assessment.evidence_quote && <blockquote className="mt-2 border-l-2 border-brand pl-3 text-[11px] italic text-ink-muted">“{turn.assessment.evidence_quote}”</blockquote>}
                {turn.assessment.gaps?.map((gap, index) => <p key={`${index}-${gap}`} className="mt-1 text-[10px] text-[var(--color-warning)]">Evidence gap: {gap}</p>)}
              </article>
            ))}
          </div>
          <p className="mt-3 text-[10px] text-ink-subtle">Advisory AI assessment only. A human reviewer owns the hiring decision.</p>
        </div>
      )}
    </div>
  );
}

export default function PostingDetailPage() {
  const params = useParams();
  const router = useRouter();
  const pathname = usePathname();
  const postingId = params.id as string;
  const { actor, loading: authLoading, activeOrgId } = useAuth();

  const [posting, setPosting] = useState<JobPosting | null>(null);
  const [applications, setApplications] = useState<ApplicationSummary[]>([]);
  const [funnel, setFunnel] = useState<Record<string, number>>({});
  const [recommended, setRecommended] = useState<CandidateRecommendation[]>([]);
  const [tab, setTab] = useState<"pipeline" | "recommended" | "criteria">("pipeline");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [referEmail, setReferEmail] = useState("");
  const [referNote, setReferNote] = useState("");
  const [referring, setReferring] = useState(false);
  const [referOpen, setReferOpen] = useState(false);
  const [selectedApplication, setSelectedApplication] = useState<{ application: ApplicationDetail; answers: unknown[]; timeline: ApplicationEvent[]; interviews?: ScheduledInterview[] } | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [scheduleStart, setScheduleStart] = useState("");
  const [scheduleEnd, setScheduleEnd] = useState("");
  const [teamMembers, setTeamMembers] = useState<InterviewTeamMember[]>([]);
  const [interviewerUserIds, setInterviewerUserIds] = useState<number[]>([]);
  const postingSkills = (posting?.required_skills || []).map((skill) => skill.toLowerCase());
  const assignableInterviewers = teamMembers
    .filter((member) => ["interviewer", "hiring_manager", "recruiter", "org_owner", "org_admin"].includes(member.role_name))
    .map((member) => ({
      ...member,
      skillMatches: (member.interview_skills || []).filter((skill) => postingSkills.some((required) => required.includes(skill.toLowerCase()) || skill.toLowerCase().includes(required))).length,
    }))
    .sort((left, right) => right.skillMatches - left.skillMatches
      || Number(right.available_for_interviews !== false) - Number(left.available_for_interviews !== false)
      || (left.scheduled_this_week ?? 0) - (right.scheduled_this_week ?? 0)
      || (right.weekly_capacity ?? 5) - (left.weekly_capacity ?? 5));
  const [scheduling, setScheduling] = useState(false);
  const [criteriaDraft, setCriteriaDraft] = useState<CriteriaDraft | null>(null);
  const [criteriaLoading, setCriteriaLoading] = useState(false);
  const [criteriaSaving, setCriteriaSaving] = useState(false);
  const [applicationReport, setApplicationReport] = useState<ApplicationReportResponse | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [aiInterviewStatus, setAIInterviewStatus] = useState<RecruiterAIInterviewStatus | null>(null);
  const [screeningOverrideReason, setScreeningOverrideReason] = useState("");
  const [approvingScreeningOverride, setApprovingScreeningOverride] = useState(false);
  const [reportDecisionReason, setReportDecisionReason] = useState("");
  const [reportDecisionTarget, setReportDecisionTarget] = useState<DecisionTarget>("TECHNICAL");
  const [reportDecisionAction, setReportDecisionAction] = useState<"PROMOTE" | "HOLD" | "REJECT" | null>(null);

  useEffect(() => {
    if (pathname !== `/org/postings/${postingId}`) return;
    if (authLoading) return;
    if (!actor) {
      router.push("/login?next=/org");
      return;
    }
    if (!activeOrgId) return;
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, actor, activeOrgId, postingId]);

  useRecruiterInterviewPolling(activeOrgId, selectedApplication?.application.id, aiInterviewStatus, setAIInterviewStatus, setApplicationReport);

  useEffect(() => {
    if (!activeOrgId || !actor?.capabilities.includes("interview:schedule")) return;
    api.get<{ members: InterviewTeamMember[] }>(`/orgs/${activeOrgId}/team`)
      .then((data) => setTeamMembers(data.members))
      .catch(() => setTeamMembers([]));
  }, [activeOrgId, actor]);

  const load = async (showLoading = true) => {
    if (showLoading) setLoading(true);
    setError(null);
    try {
      const [postingData, appsData] = await Promise.all([
        api.get<JobPosting>(`/orgs/${activeOrgId}/postings/${postingId}`),
        api.get<{ applications: ApplicationSummary[]; funnel: { by_stage: Record<string, number> } }>(
          `/orgs/${activeOrgId}/postings/${postingId}/applications`,
        ),
      ]);
      setPosting(postingData);
      setApplications(appsData.applications as unknown as ApplicationSummary[]);
      setFunnel(appsData.funnel.by_stage);
    } catch (err) {
      const message = err instanceof ApiError ? err.detail : "Failed to load posting.";
      setError(message);
      notify.error(message);
    } finally {
      if (showLoading) setLoading(false);
    }
  };

  useActivePageRefresh(
    pathname === `/org/postings/${postingId}`,
    !authLoading && Boolean(actor) && Boolean(activeOrgId),
    () => load(false),
  );

  const loadRecommended = async () => {
    try {
      const data = await api.get<{ candidates: CandidateRecommendation[] }>(
        `/orgs/${activeOrgId}/postings/${postingId}/recommended-candidates`,
      );
      setRecommended(data.candidates);
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to load recommended candidates.");
    }
  };

  const loadCriteria = async () => {
    if (!activeOrgId) return;
    setCriteriaLoading(true);
    try {
      const data = await api.get<CriteriaResponse>(`/orgs/${activeOrgId}/postings/${postingId}/criteria`);
      setCriteriaDraft({
        competencies: data.competencies,
        custom_questions: data.custom_questions,
        pass_threshold: data.pass_threshold,
        interview_settings: data.interview_settings || { role_level: "MID", technical_question_count: 2, behavioral_question_count: 2, max_followups_per_question: 1, invitation_window_days: 7 },
      });
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to load evaluation criteria.");
    } finally {
      setCriteriaLoading(false);
    }
  };

  const saveCriteria = async () => {
    if (!activeOrgId || !criteriaDraft) return;
    setCriteriaSaving(true);
    try {
      const data = await api.put<CriteriaResponse>(`/orgs/${activeOrgId}/postings/${postingId}/criteria`, {
        ...criteriaDraft,
        custom_questions: criteriaDraft.custom_questions.map((question) => question.trim()).filter(Boolean),
      });
      setCriteriaDraft({ competencies: data.competencies, custom_questions: data.custom_questions, pass_threshold: data.pass_threshold, interview_settings: data.interview_settings || { role_level: "MID", technical_question_count: 2, behavioral_question_count: 2, max_followups_per_question: 1, invitation_window_days: 7 } });
      notify.success("Evaluation criteria saved.");
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to save evaluation criteria.");
    } finally {
      setCriteriaSaving(false);
    }
  };

  const renderTabContent = () => {
    if (tab === "criteria") {
      return <CriteriaEditor draft={criteriaDraft} loading={criteriaLoading} saving={criteriaSaving} onChange={setCriteriaDraft} onSave={saveCriteria} />;
    }
    if (tab === "pipeline") {
      return <PipelineList applications={applications} onTransition={handleTransition} onView={loadApplication} />;
    }
    return <RecommendedList candidates={recommended} />;
  };

  const handleTransition = async (applicationId: number, toStage: string) => {
    try {
      await api.post(`/orgs/${activeOrgId}/applications/${applicationId}/transition`, { to_stage: toStage });
      await load();
      notify.success(`Moved to ${toStage.replaceAll("_", " ").toLowerCase()}.`);
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to update application stage.");
    }
  };

  const loadAIInterviewStatus = async (applicationId: number) => {
    try {
      setAIInterviewStatus(await api.get<RecruiterAIInterviewStatus>(`/orgs/${activeOrgId}/applications/${applicationId}/ai-interview`));
    } catch (error) {
      setAIInterviewStatus(null);
      if (!(error instanceof ApiError && error.status === 404)) {
        notify.error(error instanceof ApiError ? error.detail : "Failed to load interview status.");
      }
    }
  };

  const loadApplicationReport = async (applicationId: number) => {
    try {
      setApplicationReport(await api.get<ApplicationReportResponse>(`/orgs/${activeOrgId}/applications/${applicationId}/report`));
    } catch (error) {
      setApplicationReport(null);
      if (!(error instanceof ApiError && error.status === 404)) {
        notify.error(error instanceof ApiError ? error.detail : "Failed to load interview report.");
      }
    } finally {
      setReportLoading(false);
    }
  };

  const loadApplication = async (applicationId: number) => {
    setDetailLoading(true);
    setReportLoading(true);
    setApplicationReport(null);
    setAIInterviewStatus(null);
    setScreeningOverrideReason("");
    try {
      const detail = await api.get<{ application: ApplicationDetail; answers: unknown[]; timeline: ApplicationEvent[]; interviews?: ScheduledInterview[] }>(`/orgs/${activeOrgId}/applications/${applicationId}`);
      setReportDecisionTarget(nextHumanStageOptions(detail.interviews)[0] || "TECHNICAL");
      setSelectedApplication(detail);
      await Promise.all([loadAIInterviewStatus(applicationId), loadApplicationReport(applicationId)]);
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to load candidate details.");
      setReportLoading(false);
    } finally {
      setDetailLoading(false);
    }
  };

  const approveScreeningException = async () => {
    if (!selectedApplication || screeningOverrideReason.trim().length < 10) return;
    setApprovingScreeningOverride(true);
    try {
      await api.post(`/orgs/${activeOrgId}/applications/${selectedApplication.application.id}/ai-interview/approve-screening-exception`, {
        reason: screeningOverrideReason.trim(),
      });
      notify.success("Interview approved after human review. The candidate will be notified.");
      await loadApplication(selectedApplication.application.id);
      await load();
    } catch (error) {
      notify.error(error instanceof ApiError ? error.detail : "Could not approve the screening exception.");
    } finally {
      setApprovingScreeningOverride(false);
    }
  };

  const rejectScreeningException = async () => {
    if (!selectedApplication || screeningOverrideReason.trim().length < 10) return;
    setApprovingScreeningOverride(true);
    try {
      await api.post(`/orgs/${activeOrgId}/applications/${selectedApplication.application.id}/transition`, {
        to_stage: "REJECTED",
        note: screeningOverrideReason.trim(),
      });
      notify.success("Screening exception reviewed and rejected with a recorded reason.");
      await loadApplication(selectedApplication.application.id);
      await load(false);
    } catch (error) {
      notify.error(error instanceof ApiError ? error.detail : "Could not reject this screening exception.");
    } finally {
      setApprovingScreeningOverride(false);
    }
  };

  const submitReportDecision = async (action: "PROMOTE" | "HOLD" | "REJECT") => {
    if (!selectedApplication) return;
    setReportDecisionAction(action);
    try {
      await api.post(`/orgs/${activeOrgId}/applications/${selectedApplication.application.id}/decision`, {
        action,
        ...(action === "PROMOTE" ? {
          target_stage: reportDecisionTarget,
          scheduled_start: reportDecisionTarget === "OFFER" ? null : (scheduleStart ? new Date(scheduleStart).toISOString() : null),
          scheduled_end: reportDecisionTarget === "OFFER" ? null : (scheduleEnd ? new Date(scheduleEnd).toISOString() : null),
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
          interviewer_user_ids: reportDecisionTarget === "OFFER" ? [] : interviewerUserIds,
        } : {}),
        reason: reportDecisionReason.trim(),
      });
      const messages = {
        PROMOTE: "Candidate promoted to the next round.",
        HOLD: "Candidate placed on hold.",
        REJECT: "Candidate rejected with a recorded reason.",
      };
      notify.success(messages[action]);
      setReportDecisionReason("");
      await loadApplication(selectedApplication.application.id);
      await load(false);
    } catch (decisionError) {
      notify.error(decisionError instanceof ApiError ? decisionError.detail : "Could not save the recruiter decision.");
    } finally {
      setReportDecisionAction(null);
    }
  };

  const handleRefer = async (e: React.FormEvent) => {
    e.preventDefault();
    setReferring(true);
    try {
      const referral = await api.post<{ email_delivery?: "sent" | "not_configured" | "failed" }>(`/orgs/${activeOrgId}/postings/${postingId}/referrals`, {
        candidate_email: referEmail,
        note: referNote,
      });
      setReferEmail("");
      setReferNote("");
      notify.success(referral.email_delivery === "sent" ? "Referral sent and emailed to the candidate." : "Referral saved. Email delivery isn't configured for this workspace.");
      setReferOpen(false);
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to send referral.");
    } finally {
      setReferring(false);
    }
  };

  const handleSchedule = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!selectedApplication || !scheduleStart || !scheduleEnd || !actor) return;
    setScheduling(true);
    try {
      await api.post(`/orgs/${activeOrgId}/applications/${selectedApplication.application.id}/interviews`, {
        title: "Interview",
        scheduled_start: new Date(scheduleStart).toISOString(),
        scheduled_end: new Date(scheduleEnd).toISOString(),
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        interviewer_user_ids: interviewerUserIds.length ? interviewerUserIds : [actor.user_id],
      });
      notify.success("Interview scheduled.");
      setScheduleStart("");
      setScheduleEnd("");
      setInterviewerUserIds([]);
      await loadApplication(selectedApplication.application.id);
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to schedule interview.");
    } finally {
      setScheduling(false);
    }
  };

  if (authLoading || loading) {
    return (
      <div className="min-h-screen">
        <Navbar />
        <PageShell className="!max-w-[820px] pt-[112px]">
          <SkeletonList count={4} />
        </PageShell>
      </div>
    );
  }

  if (!posting) {
    return (
      <div className="min-h-screen">
        <Navbar />
        <PageShell className="!max-w-[820px] pt-[112px]">
          <EmptyState title="Posting unavailable" description={error || "We couldn't find that posting."} />
        </PageShell>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Navbar />
      <PageShell className="!max-w-[1180px] pt-[112px]">
        <Link
          href="/org"
          className="mono text-[11px] tracking-[0.08em] text-ink-subtle no-underline transition-colors duration-fast ease-out-expo hover:text-brand"
        >
          ← BACK TO CAMPAIGNS
        </Link>

        <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-[26px] font-bold tracking-normal text-ink-heading">{posting.title}</h1>
            <p className="mt-1 text-[12px] text-ink-subtle">
              {posting.location} · {posting.remote_policy} ·{" "}
              {formatSalaryRange(posting.salary_min, posting.salary_max)}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <StatusPill tone={posting.status === "PUBLISHED" ? "success" : "warning"}>{posting.status}</StatusPill>
            <Button size="sm" onClick={() => setReferOpen(true)}>Refer candidate</Button>
          </div>
        </div>

        <div className="mt-6 flex flex-wrap gap-2">
          {Object.entries(funnel).map(([stage, count]) => (
            <StatusPill key={stage} tone="muted">
              {stage}: {count}
            </StatusPill>
          ))}
        </div>

        <div className="mt-5 rounded-xl border border-subtle bg-[rgba(255,255,255,0.025)] p-4">
          <p className="mono text-[9px] tracking-[0.1em] text-brand">AUTOMATIC MINIMUM-CRITERIA GATE</p>
          <p className="mt-2 text-[11px] leading-relaxed text-ink-muted">
            {posting.min_experience !== null ? `Minimum experience: ${posting.min_experience} years. ` : "No minimum experience configured. "}
            {posting.required_skills.length ? `Must-have skills: ${posting.required_skills.join(", ")}. ` : "No must-have skills configured. "}
            Explicit mismatches and unclear evidence go to human review; the system does not auto-reject candidates.
          </p>
        </div>

        <div className="mt-6 flex flex-wrap gap-2">
          <Button
            size="sm"
            variant={tab === "pipeline" ? "primary" : "secondary"}
            onClick={() => setTab("pipeline")}
          >
            Applicants
          </Button>
          <Button
            size="sm"
            variant={tab === "recommended" ? "primary" : "secondary"}
            onClick={() => {
              setTab("recommended");
              if (recommended.length === 0) void loadRecommended();
            }}
          >
            Recommended candidates
          </Button>
          <Button
            size="sm"
            variant={tab === "criteria" ? "primary" : "secondary"}
            onClick={() => {
              setTab("criteria");
              if (!criteriaDraft) void loadCriteria();
            }}
          >
            Evaluation criteria
          </Button>
        </div>

        <div className="mt-6">{renderTabContent()}</div>

        {typeof document !== "undefined" && createPortal(
        <AnimatePresence>
          {(detailLoading || selectedApplication) && (
          <motion.dialog open aria-labelledby="candidate-detail-title" className="fixed inset-0 z-[70] flex h-full w-full max-w-none bg-transparent p-0" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.button aria-label="Close candidate details" className="h-full flex-1 cursor-default border-0 bg-black/65 backdrop-blur-[3px]" onClick={() => setSelectedApplication(null)} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
            <motion.aside className="h-full w-full max-w-[560px] overflow-y-auto border-l border-subtle bg-[var(--color-bg)] shadow-[-20px_0_60px_rgba(0,0,0,0.42)]" initial={{ opacity: 0, x: 56 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 56 }} transition={{ type: "spring", damping: 30, stiffness: 340 }}>
              <div className="sticky top-0 z-10 flex items-center justify-between border-b border-subtle bg-[var(--color-bg)] px-6 py-5">
                <div><p className="eyebrow">CANDIDATE DETAILS</p><p id="candidate-detail-title" className="mt-1 text-[15px] font-semibold text-ink-heading">{selectedApplication?.application.candidate_name || "Loading candidate"}</p></div>
                <Button size="sm" variant="ghost" onClick={() => setSelectedApplication(null)}>Close</Button>
              </div>
              {detailLoading || !selectedApplication ? <div className="p-6 text-[13px] text-ink-muted">Loading candidate profile and activity...</div> : <div className="p-6">
                <motion.div className="grid gap-5 border-b border-subtle pb-6 sm:grid-cols-2" initial="hidden" animate="visible" variants={staggerContainer(0.05)}>
                  <DetailCell label="EMAIL" value={selectedApplication.application.candidate_email || "Not available"} />
                  <DetailCell label="CURRENT STAGE" value={selectedApplication.application.current_stage} />
                  <DetailCell label="APPLICATION STATUS" value={selectedApplication.application.status} />
                  <DetailCell label="SOURCE" value={selectedApplication.application.source} />
                  <DetailCell label="APPLIED" value={new Date(selectedApplication.application.created_at).toLocaleString()} />
                </motion.div>
                <section className="mt-7"><p className="eyebrow">PIPELINE ACTIVITY</p><PipelineLifecycle events={selectedApplication.timeline} /></section>
                {aiInterviewStatus && (
                  <section className="mt-7 border-t border-subtle pt-6">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <p className="eyebrow">AUTOMATIC SCREENING & AI INTERVIEW</p>
                      <StatusPill tone={aiInterviewStatusTone(aiInterviewStatus.status)}>
                        {aiInterviewStatus.status.replaceAll("_", " ")}
                      </StatusPill>
                    </div>
                    <p className="mt-2 text-[11px] text-ink-subtle">Policy {aiInterviewStatus.rubric_version} · {aiInterviewStatus.role_level} level · {aiInterviewStatus.turns.length} persisted turns</p>
                    {aiInterviewStatus.screening_result.decision && <p className="mt-2 text-[12px] text-ink-muted">Screening: {aiInterviewStatus.screening_result.decision}{typeof aiInterviewStatus.screening_result.score === "number" ? ` · ${aiInterviewStatus.screening_result.score}/10` : ""}</p>}
                    {aiInterviewStatus.screening_result.minimum_criteria && (
                      <div className="mt-3 rounded-lg border border-subtle bg-[rgba(255,255,255,0.025)] p-3">
                        <p className="mono text-[9px] tracking-[0.1em] text-ink-subtle">RECRUITER-DEFINED MINIMUM CRITERIA · {aiInterviewStatus.screening_result.minimum_criteria.status.replaceAll("_", " ")}</p>
                        {aiInterviewStatus.screening_result.minimum_criteria.checks.map((check) => <p key={check.criterion_key} className="mt-2 text-[10px] text-ink-muted">{check.requirement || check.criterion_key.replaceAll("_", " ")} · {check.state.replaceAll("_", " ")} — {check.reason}</p>)}
                      </div>
                    )}
                    {aiInterviewStatus.screening_result.constraint_gaps?.map((gap, index) => <p key={`${index}-${gap}`} className="mt-1 text-[11px] text-[var(--color-warning)]">{gap}</p>)}
                    {aiInterviewStatus.error_code && <p className="mt-2 text-[11px] text-[var(--color-warning)]">{aiInterviewStatus.error_code}: recruiter review is required. Technical/model failures are not treated as candidate failures.</p>}
                    {aiInterviewStatus.status === "SCREENING_QUEUED" && <p className="mt-2 text-[11px] text-ink-muted">Screening starts automatically; no per-candidate action is needed.</p>}
                    {aiInterviewStatus.status === "REVIEW_REQUIRED" && selectedApplication.application.current_stage === "PENDING_REVIEW" && (
                      <div className="mt-4 border-t border-subtle pt-4">
                        <p className="text-[12px] font-semibold text-ink-heading">Human exception review</p>
                        <p className="mt-1 text-[11px] leading-relaxed text-ink-muted">If the evidence is sufficient after review, approve the candidate to continue to the AI interview. Record why; this does not make a hiring decision.</p>
                        <Textarea label="REVIEW RATIONALE (REQUIRED)" rows={3} value={screeningOverrideReason} onChange={(event) => setScreeningOverrideReason(event.target.value)} />
                        <div className="mt-3 flex flex-wrap gap-2">
                          <Button size="sm" loading={approvingScreeningOverride} disabled={screeningOverrideReason.trim().length < 10} onClick={() => void approveScreeningException()}>Approve interview after review</Button>
                          <Button size="sm" variant="ghost" loading={approvingScreeningOverride} disabled={screeningOverrideReason.trim().length < 10} onClick={() => void rejectScreeningException()}>Reject after review</Button>
                        </div>
                      </div>
                    )}
                  </section>
                )}
                <section className="mt-7 border-t border-subtle pt-6">
                  <p className="eyebrow">INTERVIEW REPORT</p>
                  <InterviewReport loading={reportLoading} report={applicationReport} />
                </section>
                {applicationReport && selectedApplication.application.current_stage === "PENDING_REVIEW" && (
                  <section className="mt-7 border-t border-subtle pt-6">
                    <p className="eyebrow">RECRUITER DECISION</p>
                    <p className="mt-2 text-[12px] leading-relaxed text-ink-muted">The report is advisory. Review the cited evidence, then decide whether to promote the candidate, hold for more review, or reject with a reason.</p>
                    <p className="mt-2 text-[11px] text-ink-subtle">Suggested action: {reportSuggestedAction(applicationReport, selectedApplication.interviews)}{applicationReport.interview_details.fit_nudge ? ` · ${applicationReport.interview_details.fit_nudge.band.replaceAll("_", " ").toLowerCase()}` : " · based on the completed human panel"}</p>
                    <Select label="NEXT PIPELINE STEP" value={reportDecisionTarget} onChange={(event) => setReportDecisionTarget(event.target.value as DecisionTarget)}>
                      {nextHumanStageOptions(selectedApplication.interviews).map((stage) => <option key={stage} value={stage}>{stage === "OFFER" ? "Offer decision" : `${stage.replaceAll("_", " ")} interview`}</option>)}
                    </Select>
                    <Textarea
                      label="DECISION REASON"
                      rows={3}
                      value={reportDecisionReason}
                      onChange={(event) => setReportDecisionReason(event.target.value)}
                      hint="Required for hold, rejection, or a decision that differs from the evidence recommendation."
                    />
                    {reportDecisionTarget !== "OFFER" && <div className="mt-4 grid gap-3 sm:grid-cols-2">
                      <DateTimePicker label="NEXT-ROUND START" value={scheduleStart} onChange={setScheduleStart} placeholder="Choose a time" minDate={dateKey()} />
                      <DateTimePicker label="NEXT-ROUND END" value={scheduleEnd} onChange={setScheduleEnd} placeholder="Choose an end time" minDatetime={scheduleStart || undefined} minDatetimeLabel={scheduleStart || undefined} />
                    </div>}
                    {reportDecisionTarget !== "OFFER" && assignableInterviewers.length > 0 && (
                      <div className="mt-4">
                        <Select
                          aria-label="ASSIGN NEXT-ROUND INTERVIEWERS"
                          label="ASSIGN NEXT-ROUND INTERVIEWERS"
                          multiple
                          value={interviewerUserIds.map(String)}
                          onChange={(event) => setInterviewerUserIds(Array.from(event.target.selectedOptions, (option) => Number(option.value)))}
                        >
                          {assignableInterviewers.map((member, index) => <option key={member.user_id} value={member.user_id} disabled={member.available_for_interviews === false || (member.scheduled_this_week ?? 0) >= (member.weekly_capacity ?? 5)}>{member.full_name || member.email} · {member.skillMatches ? `${member.skillMatches} skill matches` : member.role_name.replaceAll("_", " ")}{index === 0 && member.skillMatches ? " · suggested" : ""}{member.available_for_interviews === false ? " · unavailable" : ""} · {member.scheduled_this_week ?? 0}/{member.weekly_capacity ?? 5} this week</option>)}
                        </Select>
                        <p className="mt-1 text-[10px] text-ink-subtle">Select one or more teammates; if none are selected, you will be assigned.</p>
                      </div>
                    )}
                    <div className="mt-4 flex flex-wrap gap-2">
                      <Button size="sm" loading={reportDecisionAction === "PROMOTE"} disabled={Boolean(reportDecisionAction) || (reportDecisionTarget !== "OFFER" && (!scheduleStart || !scheduleEnd || new Date(scheduleEnd) <= new Date(scheduleStart))) || (reportSuggestedAction(applicationReport, selectedApplication.interviews) !== "PROMOTE" && reportDecisionReason.trim().length < 10)} onClick={() => void submitReportDecision("PROMOTE")}>{reportDecisionTarget === "OFFER" ? "Advance to offer" : `Promote and schedule ${reportDecisionTarget.toLowerCase()} round`}</Button>
                      <Button size="sm" variant="secondary" loading={reportDecisionAction === "HOLD"} disabled={Boolean(reportDecisionAction) || reportDecisionReason.trim().length < 10} onClick={() => void submitReportDecision("HOLD")}>Hold for review</Button>
                      <Button size="sm" variant="ghost" loading={reportDecisionAction === "REJECT"} disabled={Boolean(reportDecisionAction) || reportDecisionReason.trim().length < 10} onClick={() => void submitReportDecision("REJECT")}>Reject</Button>
                    </div>
                  </section>
                )}
                <section className="mt-7 border-t border-subtle pt-6">
                  <p className="eyebrow">SCHEDULE HUMAN INTERVIEW</p>
                  {(selectedApplication.interviews || []).length > 0 && (
                    <div className="mt-4 flex flex-col gap-2">
                      {selectedApplication.interviews?.map((interview) => {
                        const opensAt = Date.parse(interview.scheduled_start) - 15 * 60 * 1000;
                        const closesAt = Date.parse(interview.scheduled_end) + 30 * 60 * 1000;
                        const canJoin = interview.status === "SCHEDULED" && Date.now() >= opensAt && Date.now() <= closesAt;
                        return <div key={interview.id} className="rounded-lg border border-subtle p-3">
                          <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-[12px] font-semibold text-ink-heading">{interview.title}</p><StatusPill tone={interview.status === "SCHEDULED" ? "success" : "muted"}>{interview.status}</StatusPill></div>
                          <p className="mt-1 text-[10px] text-ink-muted">{new Date(interview.scheduled_start).toLocaleString()} · {interview.timezone}</p>
                          <p className="mt-1 text-[10px] text-ink-subtle">Assigned: {interview.participants.filter((participant) => participant.participant_role === "INTERVIEWER").map((participant) => participant.full_name).join(", ") || "No interviewer listed"}</p>
                          {interview.scorecard_summary && <p className="mt-1 text-[10px] text-ink-subtle">Scorecards: {interview.scorecard_summary.submitted}/{interview.scorecard_summary.expected}{interview.scorecard_summary.hidden_until_complete ? " · other ratings hidden until panel submits" : " · panel review ready"}</p>}
                          {interview.scorecard_summary?.complete && <div className="mt-3 flex flex-col gap-2 border-t border-subtle pt-3">
                            {(interview.scorecard_summary.screening_evidence || []).length > 0 && <div className="rounded-md border border-subtle p-2"><p className="eyebrow">SCREENING EVIDENCE</p>{interview.scorecard_summary.screening_evidence?.map((evidence) => <p key={evidence.criterion_key} className="mt-1 text-[9px] text-ink-muted">{evidence.criterion_key.replaceAll("_", " ")} · {evidence.status}{evidence.quote ? ` · “${evidence.quote}”` : ""}</p>)}</div>}
                            {(interview.scorecard_summary.interview_evidence || []).map((turn) => <div key={turn.sequence_no} className="rounded-md border border-subtle p-2"><p className="mono text-[9px] text-ink-subtle">TURN {turn.sequence_no} · {turn.competency_key.replaceAll("_", " ")}</p><p className="mt-1 text-[10px] font-semibold text-ink-heading">{turn.question}</p>{turn.answer && <p className="mt-1 text-[9px] text-ink-muted">Candidate: {turn.answer}</p>}{turn.assessment.evidence_quote && <p className="mt-1 text-[9px] italic text-ink-subtle">Grounded evidence: “{turn.assessment.evidence_quote}”</p>}</div>)}
                            {interview.scorecard_summary.scorecards.map((scorecard) => <div key={scorecard.interviewer_user_id} className="rounded-md bg-[rgba(255,255,255,0.025)] p-2">
                              <p className="mono text-[9px] text-brand">{scorecard.recommendation} · INTERVIEWER {scorecard.interviewer_user_id}</p>
                              <div className="mt-1 flex flex-wrap gap-2">{scorecard.ratings.map((rating) => <span key={rating.key} className="text-[9px] text-ink-muted">{rating.label}: {rating.score}/5</span>)}</div>
                              {scorecard.notes && <p className="mt-2 text-[10px] leading-relaxed text-ink-muted">{scorecard.notes}</p>}
                            </div>)}
                          </div>}
                          {interview.meeting_url ? <a className="mt-2 inline-block text-[11px] text-brand hover:underline" href={interview.meeting_url} target="_blank" rel="noreferrer">Join external meeting</a> : <Button size="sm" variant="secondary" className="mt-2" disabled={!canJoin} onClick={() => router.push(`/meeting/${interview.id}`)}>{canJoin ? "Join in-app call" : "Room opens 15 minutes before start"}</Button>}
                        </div>;
                      })}
                    </div>
                  )}
                  <form onSubmit={handleSchedule} className="mt-4 flex flex-col gap-3">
                    {teamMembers.length > 0 && (
                      <Select
                        aria-label="ASSIGN INTERVIEWERS"
                        label="ASSIGN INTERVIEWERS"
                        multiple
                        value={interviewerUserIds.map(String)}
                        onChange={(event) => setInterviewerUserIds(Array.from(event.target.selectedOptions, (option) => Number(option.value)))}
                      >
                        {assignableInterviewers.map((member, index) => <option key={member.user_id} value={member.user_id} disabled={member.available_for_interviews === false || (member.scheduled_this_week ?? 0) >= (member.weekly_capacity ?? 5)}>{member.full_name || member.email} · {member.skillMatches ? `${member.skillMatches} skill matches` : member.role_name.replaceAll("_", " ")}{index === 0 && member.skillMatches ? " · suggested" : ""}{member.available_for_interviews === false ? " · unavailable" : ""} · {member.scheduled_this_week ?? 0}/{member.weekly_capacity ?? 5} this week</option>)}
                      </Select>
                    )}
                    <p className="text-[10px] text-ink-subtle">Select one or more teammates. If none are selected, you will be assigned.</p>
                    <DateTimePicker
                      label="START"
                      value={scheduleStart}
                      onChange={setScheduleStart}
                      placeholder="Select interview start"
                      minDate={dateKey()}
                    />
                    <DateTimePicker
                      label="END"
                      value={scheduleEnd}
                      onChange={setScheduleEnd}
                      placeholder="Select interview end"
                      minDatetime={scheduleStart || undefined}
                      minDatetimeLabel={scheduleStart || undefined}
                    />
                    <Button type="submit" size="sm" className="self-start" loading={scheduling}>Schedule interview</Button>
                  </form>
                </section>
              </div>}
            </motion.aside>
          </motion.dialog>
          )}
        </AnimatePresence>,
        document.body,
        )}

        {typeof document !== "undefined" && referOpen && createPortal(
        <dialog open aria-labelledby="referral-title" className="fixed inset-0 z-[70] flex h-full w-full max-w-none items-center justify-center bg-black/70 p-5"><GlassCard elevation="high" padding="lg" className="w-full max-w-[520px]"><div className="flex items-center justify-between gap-4"><p id="referral-title" className="eyebrow">REFER A CANDIDATE</p><Button size="sm" variant="ghost" onClick={() => setReferOpen(false)}>Close</Button></div><form onSubmit={handleRefer} className="mt-5 flex flex-col gap-4">
            <Input
              type="email"
              required
              label="CANDIDATE EMAIL"
              placeholder="candidate@example.com"
              value={referEmail}
              onChange={(e) => setReferEmail(e.target.value)}
            />
            <Textarea
              rows={2}
              label="NOTE"
              hint="Optional — the candidate sees this on their referrals page."
              placeholder="Why are you referring them?"
              value={referNote}
              onChange={(e) => setReferNote(e.target.value)}
            />
            <Button type="submit" className="self-start" loading={referring}>
              {referring ? "Sending..." : "Send referral"}
            </Button>
          </form></GlassCard></dialog>,
        document.body,
        )}
      </PageShell>
    </div>
  );
}

function DetailCell({ label, value }: Readonly<{ label: string; value: string }>) {
  return <motion.div variants={staggerItem}><p className="mono text-[10px] tracking-[0.08em] text-ink-subtle">{label}</p><p className="mt-1 text-[13px] text-ink-heading">{value}</p></motion.div>;
}

function PipelineLifecycle({ events }: Readonly<{ events: ApplicationEvent[] }>) {
  if (events.length === 0) return <p className="mt-4 text-[13px] text-ink-muted">No activity recorded yet.</p>;

  return <motion.div initial="hidden" animate="visible" variants={staggerContainer(0.08, 0.1)} className="mt-5">
    {events.map((event, index) => <motion.div key={`${event.event_type}-${event.created_at}`} variants={staggerItem} className="grid grid-cols-[minmax(0,1fr)_28px_minmax(0,1.15fr)] gap-3">
      <div className="pb-7 text-right"><p className="text-[13px] font-semibold capitalize text-ink-heading">{event.event_type.replaceAll("_", " ").toLowerCase()}</p><p className="mt-1 mono text-[10px] text-ink-subtle">{new Date(event.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</p></div>
      <div className="relative flex justify-center">{index < events.length - 1 && <motion.span className="absolute top-5 h-[calc(100%-4px)] w-px bg-[var(--color-success)]/45" initial={{ scaleY: 0 }} animate={{ scaleY: 1 }} transition={{ delay: 0.18 + index * 0.08, duration: 0.32 }} style={{ transformOrigin: "top" }} />}<motion.span className="relative z-10 mt-1 flex h-5 w-5 items-center justify-center rounded-full border border-[var(--color-success)] bg-[rgba(34,197,94,0.14)] text-[11px] font-bold text-[var(--color-success)] shadow-[0_0_18px_rgba(34,197,94,0.22)]" initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 420, damping: 18, delay: 0.12 + index * 0.08 }}>✓</motion.span></div>
      <div className="pb-7"><p className="text-[12px] text-ink-muted">{event.from_stage || "New"} <span className="px-1 text-ink-subtle">to</span> {event.to_stage || "-"}</p><p className="mt-1 text-[11px] text-ink-subtle">{new Date(event.created_at).toLocaleDateString()}</p></div>
    </motion.div>)}
  </motion.div>;
}
