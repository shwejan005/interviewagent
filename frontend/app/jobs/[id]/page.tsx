"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import Navbar from "../../components/Navbar";
import {
  Alert,
  Button,
  GlassCard,
  PageShell,
  Skeleton,
  StatusPill,
  Textarea,
} from "../../components/ui";
import { useAuth } from "../../../lib/auth-context";
import { api, ApiError } from "../../../lib/api";
import type { JobPosting } from "../../../lib/types";

type ApplicationFormQuestion = {
  key: string;
  text: string;
  required: boolean;
  prefilled_answer: string;
  is_prefilled: boolean;
};

type ApplicationForm = {
  posting_id: number;
  title: string;
  questions: ApplicationFormQuestion[];
  profile_complete: boolean;
  unanswered_count: number;
};

/** Kept out of JSX so the pluralisation does not turn into nested ternaries. */
function prefillSummary(unanswered: number): string {
  if (unanswered === 0) return "All questions are pre-filled from your profile vault.";
  if (unanswered === 1) return "1 question needs an answer.";
  return `${unanswered} questions need an answer.`;
}

function applyLabel(applying: boolean, signedIn: boolean): string {
  if (applying) return "Submitting...";
  if (signedIn) return "Submit application";
  return "Log in to apply";
}

export default function JobDetailPage() {
  const params = useParams();
  const router = useRouter();
  const postingId = params.id as string;
  const { actor, loading: authLoading } = useAuth();

  const [posting, setPosting] = useState<JobPosting | null>(null);
  const [form, setForm] = useState<ApplicationForm | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [applied, setApplied] = useState(false);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [postingId, actor]);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const postingData = await api.get<JobPosting>(`/jobs/${postingId}`);
      setPosting(postingData);

      if (actor) {
        try {
          const formData = await api.get<ApplicationForm>(`/jobs/${postingId}/application-form`);
          setForm(formData);
          const prefilled: Record<string, string> = {};
          formData.questions.forEach((q) => {
            if (q.prefilled_answer) prefilled[q.key] = q.prefilled_answer;
          });
          setAnswers(prefilled);
        } catch {
          // Application form is best-effort; posting details still render without it.
        }
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "This job posting could not be found.");
    } finally {
      setLoading(false);
    }
  };

  const handleApply = async () => {
    if (!actor) {
      router.push(`/login?next=/jobs/${postingId}`);
      return;
    }
    setApplying(true);
    setError(null);
    try {
      const payload = {
        answers: Object.entries(answers).map(([question_key, answer_text]) => ({
          question_key,
          answer_text,
        })),
      };
      await api.post(`/jobs/${postingId}/apply`, payload);
      setApplied(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to submit application.");
    } finally {
      setApplying(false);
    }
  };

  if (loading || authLoading) {
    return (
      <div className="min-h-screen">
        <Navbar />
        <PageShell className="!max-w-[720px] pt-[112px]">
          <Skeleton height={12} width="20%" />
          <Skeleton className="mt-4" height={32} width="70%" />
          <Skeleton className="mt-3" height={12} width="45%" />
          <div className="glass-low mt-7 p-6">
            <Skeleton height={10} width="100%" />
            <Skeleton className="mt-3" height={10} width="95%" />
            <Skeleton className="mt-3" height={10} width="60%" />
          </div>
        </PageShell>
      </div>
    );
  }

  if (!posting) {
    return (
      <div className="min-h-screen">
        <Navbar />
        <PageShell className="!max-w-[720px] pt-[112px]">
          <Alert tone="error">{error || "Not found."}</Alert>
          <Link href="/jobs" className="mt-5 inline-block text-[13px] text-brand hover:underline">
            ← Back to jobs
          </Link>
        </PageShell>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Navbar />
      <PageShell className="!max-w-[720px] pt-[112px]">
        <Link
          href="/jobs"
          className="mono text-[11px] tracking-[0.06em] text-ink-subtle transition-colors duration-fast ease-out-expo hover:text-brand"
        >
          ← BACK TO JOBS
        </Link>

        <h1 className="mb-1.5 mt-4 text-[clamp(24px,3.6vw,32px)] font-bold tracking-normal text-ink-heading">
          {posting.title}
        </h1>
        <p className="text-[13px] text-ink-subtle">
          {posting.org_name} · {posting.location} · {posting.remote_policy} ·{" "}
          {posting.employment_type.replace("_", " ")}
        </p>

        {posting.required_skills.length > 0 && (
          <div className="mt-5 flex flex-wrap gap-2">
            {posting.required_skills.map((skill) => (
              <StatusPill key={skill} tone="muted">
                {skill}
              </StatusPill>
            ))}
          </div>
        )}

        <GlassCard className="mt-7 whitespace-pre-wrap text-[14px] leading-[1.75] text-ink-muted">
          {posting.description || "No description provided."}
        </GlassCard>

        {applied ? (
          <Alert tone="success" className="mt-6" title="Application submitted">
            Track its progress from{" "}
            <Link href="/applications" className="font-semibold underline">
              My Applications
            </Link>
            .
          </Alert>
        ) : (
          <GlassCard elevation="high" padding="lg" className="mt-6">
            <p className="eyebrow">APPLY</p>

            {!actor && (
              <p className="mt-4 text-[13px] text-ink-muted">
                <Link href={`/login?next=/jobs/${postingId}`} className="text-brand hover:underline">
                  Log in
                </Link>{" "}
                or{" "}
                <Link href="/register" className="text-brand hover:underline">
                  sign up
                </Link>{" "}
                to apply.
              </p>
            )}

            {actor && form && form.questions.length > 0 && (
              <div className="mt-5">
                <p className="text-[12px] text-ink-subtle">{prefillSummary(form.unanswered_count)}</p>
                <div className="mt-4 flex flex-col gap-4">
                  {form.questions.map((q) => (
                    <Textarea
                      key={q.key}
                      id={`q-${q.key}`}
                      rows={2}
                      value={answers[q.key] || ""}
                      onChange={(e) => setAnswers((prev) => ({ ...prev, [q.key]: e.target.value }))}
                      label={q.text}
                      hint={q.is_prefilled ? "Pre-filled from your vault" : undefined}
                      required={q.required}
                    />
                  ))}
                </div>
              </div>
            )}

            {error && (
              <Alert tone="error" className="mt-5">
                {error}
              </Alert>
            )}

            <Button className="mt-6" size="lg" onClick={handleApply} loading={applying}>
              {applyLabel(applying, Boolean(actor))}
            </Button>
          </GlassCard>
        )}
      </PageShell>
    </div>
  );
}
