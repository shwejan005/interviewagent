"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import Navbar from "../../components/Navbar";
import { Button, GlassCard, PageHeader, PageShell, SkeletonList, StatusPill, Textarea } from "../../components/ui";
import { useAuth } from "../../../lib/auth-context";
import { api, ApiError } from "../../../lib/api";
import type { CandidateAIInterview } from "../../../lib/types";

const ACTIVE_POLL_STATUSES = new Set(["SCREENING_QUEUED", "SCREENING", "ANSWER_PROCESSING", "REPORT_PENDING"]);

export default function ApplicationAIInterviewPage() {
  const params = useParams();
  const router = useRouter();
  const applicationId = Number(params.applicationId);
  const { actor, loading: authLoading } = useAuth();
  const [interview, setInterview] = useState<CandidateAIInterview | null>(null);
  const [loading, setLoading] = useState(true);
  const [acceptedNotice, setAcceptedNotice] = useState(false);
  const [answer, setAnswer] = useState("");
  const [starting, setStarting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadInterview = useCallback(async (showLoading = false) => {
    if (!Number.isSafeInteger(applicationId) || applicationId < 1) {
      setError("This application link is invalid.");
      setLoading(false);
      return;
    }
    if (showLoading) setLoading(true);
    try {
      const response = await api.get<CandidateAIInterview>(`/me/applications/${applicationId}/ai-interview`);
      setInterview(response);
      setError(null);
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.status === 404) {
        setError("An AI interview is not available for this application yet.");
      } else {
        setError(requestError instanceof ApiError ? requestError.detail : "Unable to load this interview.");
      }
    } finally {
      if (showLoading) setLoading(false);
    }
  }, [applicationId]);

  useEffect(() => {
    if (authLoading) return;
    if (!actor) {
      router.push(`/login?next=/ai-interview/${applicationId}`);
      return;
    }
    void loadInterview(true);
  }, [actor, authLoading, applicationId, loadInterview, router]);

  useEffect(() => {
    if (!interview || !ACTIVE_POLL_STATUSES.has(interview.status)) return;
    const timer = window.setTimeout(() => void loadInterview(), 1800);
    return () => window.clearTimeout(timer);
  }, [interview, loadInterview]);

  const startInterview = async () => {
    if (!interview || !acceptedNotice) return;
    setStarting(true);
    setError(null);
    try {
      const response = await api.post<CandidateAIInterview>(`/me/applications/${applicationId}/ai-interview/start`, {
        accepted: true,
        notice_version: interview.candidate_notice_version,
        modality: "TEXT",
      });
      setInterview(response);
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.detail : "Could not start the interview.");
      await loadInterview();
    } finally {
      setStarting(false);
    }
  };

  const submitAnswer = async (event: FormEvent) => {
    event.preventDefault();
    if (!interview?.current_question || !answer.trim() || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.post(`/me/applications/${applicationId}/ai-interview/answers`, {
        turn_id: interview.current_question.id,
        answer: answer.trim(),
      });
      setAnswer("");
      setInterview({ ...interview, status: "ANSWER_PROCESSING", current_question: null, message: "Your answer is saved and being evaluated." });
      await loadInterview();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.detail : "Your answer could not be submitted. Your draft is still here.");
    } finally {
      setSubmitting(false);
    }
  };

  if (authLoading || loading) {
    return <div className="min-h-screen"><Navbar /><PageShell className="!max-w-[760px] pt-[112px]"><SkeletonList count={3} /></PageShell></div>;
  }

  if (!interview) {
    return (
      <div className="min-h-screen">
        <Navbar />
        <PageShell className="!max-w-[760px] pt-[112px]">
          <PageHeader eyebrow="APPLICATION INTERVIEW" title="Interview unavailable" />
          <GlassCard className="mt-6 p-5"><p className="text-[13px] text-ink-muted">{error || "This interview is unavailable."}</p><Link href="/applications" className="mt-4 inline-block text-[13px] font-semibold text-brand hover:underline">Back to applications</Link></GlassCard>
        </PageShell>
      </div>
    );
  }

  const currentQuestion = interview.current_question;
  const showHistory = interview.turns.filter((turn) => turn.answer_text !== null);

  return (
    <div className="min-h-screen">
      <Navbar />
      <PageShell className="!max-w-[820px] pt-[112px]">
        <Link href="/applications" className="mono text-[11px] tracking-[0.06em] text-ink-subtle hover:text-brand">← MY APPLICATIONS</Link>
        <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
          <PageHeader eyebrow="AI INTERVIEW" title="Your role-focused interview" />
          <StatusPill tone={interview.status === "REPORT_READY" ? "success" : "primary"}>{interview.status.replaceAll("_", " ")}</StatusPill>
        </div>
        <p className="mt-2 text-[13px] leading-relaxed text-ink-muted">{interview.message}</p>

        {error && <p role="alert" className="mt-4 text-[13px] text-[var(--color-error)]">{error}</p>}

        {interview.status === "INTERVIEW_READY" && (
          <GlassCard elevation="high" padding="lg" className="mt-6">
            <p className="eyebrow">BEFORE YOU START</p>
            <h2 className="mt-2 text-[17px] font-semibold text-ink-heading">This is an AI-led text interview</h2>
            <p className="mt-3 text-[13px] leading-relaxed text-ink-muted">It includes role-related technical and behavioral questions at the job’s {interview.role_level.toLowerCase()} level. Your submitted answers and their assessments will be shared with the hiring team for this application. The AI does not make the hiring decision. You can stop and return later; your progress is saved.</p>
            <p className="mt-3 text-[11px] leading-relaxed text-ink-subtle">Notice version: {interview.candidate_notice_version}. A voice interview is not enabled in this deployment, so no microphone or camera is requested.</p>
            <label className="mt-5 flex cursor-pointer items-start gap-3 text-[12px] leading-relaxed text-ink-muted">
              <input type="checkbox" checked={acceptedNotice} onChange={(event) => setAcceptedNotice(event.target.checked)} className="mt-0.5 accent-[var(--color-primary)]" />
              <span>I understand this is an AI-led interview and agree to submit my answers for evaluation for this application.</span>
            </label>
            <Button className="mt-5" loading={starting} disabled={!acceptedNotice} onClick={() => void startInterview()}>Start interview</Button>
          </GlassCard>
        )}

        {interview.status === "SCREENING_QUEUED" || interview.status === "SCREENING" ? (
          <GlassCard className="mt-6 p-5"><p className="text-[13px] text-ink-muted">Screening runs automatically after you apply. You can leave this page; your application tracker will update when it is ready.</p></GlassCard>
        ) : null}

        {interview.status === "ANSWER_PROCESSING" && (
          <GlassCard className="mt-6 p-5"><p className="text-[13px] text-ink-muted">Your answer is safely saved. The interviewer is reviewing it before asking the next question.</p></GlassCard>
        )}

        {currentQuestion && interview.status === "INTERVIEW_IN_PROGRESS" && (
          <GlassCard elevation="high" padding="lg" className="mt-6">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="eyebrow">{currentQuestion.phase} · {currentQuestion.competency_key.replaceAll("_", " ")}</p>
              <span className="mono text-[10px] text-ink-subtle">LEVEL {currentQuestion.difficulty} · {currentQuestion.question_type.replaceAll("_", " ")}</span>
            </div>
            <h2 className="mt-3 text-[18px] font-semibold leading-relaxed text-ink-heading">{currentQuestion.question_text}</h2>
            <form className="mt-5" onSubmit={submitAnswer}>
              <Textarea label="YOUR ANSWER" rows={7} maxLength={12000} value={answer} onChange={(event) => setAnswer(event.target.value)} placeholder="Explain your reasoning and relevant experience…" required />
              <div className="mt-4 flex items-center justify-between gap-3">
                <span className="text-[10px] text-ink-subtle">Your progress is saved after you submit each answer.</span>
                <Button type="submit" loading={submitting} disabled={!answer.trim()}>Submit answer</Button>
              </div>
            </form>
          </GlassCard>
        )}

        {showHistory.length > 0 && (
          <section className="mt-7">
            <p className="eyebrow">SAVED INTERVIEW PROGRESS</p>
            <div className="mt-3 flex flex-col gap-3">
              {showHistory.map((turn) => (
                <GlassCard key={turn.id} padding="sm">
                  <p className="mono text-[10px] text-ink-subtle">{turn.phase} · LEVEL {turn.difficulty}</p>
                  <p className="mt-2 text-[12px] font-semibold text-ink-heading">{turn.question_text}</p>
                  <p className="mt-2 whitespace-pre-wrap text-[12px] leading-relaxed text-ink-muted">{turn.answer_text}</p>
                </GlassCard>
              ))}
            </div>
          </section>
        )}

        {interview.status === "REPORT_PENDING" && <GlassCard className="mt-6 p-5"><p className="text-[13px] text-ink-muted">You completed the interview. The report is being prepared for recruiter review.</p></GlassCard>}
        {interview.status === "REPORT_READY" && <GlassCard className="mt-6 p-5"><p className="text-[13px] text-ink-muted">Your interview is complete and has been sent to the hiring team for human review. Check your application tracker for updates.</p></GlassCard>}
        {interview.status === "REVIEW_REQUIRED" && <GlassCard className="mt-6 p-5"><p className="text-[13px] text-ink-muted">This step needs additional review by the hiring team. A technical or AI service issue will not be treated as a failed interview.</p></GlassCard>}
      </PageShell>
    </div>
  );
}
