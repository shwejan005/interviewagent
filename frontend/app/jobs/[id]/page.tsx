"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import Navbar from "../../components/Navbar";
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
      <div style={{ minHeight: "100vh", background: "var(--color-bg)" }}>
        <Navbar />
        <main style={{ maxWidth: 680, margin: "0 auto", padding: "120px 24px" }}>
          <p style={{ color: "var(--color-text-muted)" }}>Loading...</p>
        </main>
      </div>
    );
  }

  if (!posting) {
    return (
      <div style={{ minHeight: "100vh", background: "var(--color-bg)" }}>
        <Navbar />
        <main style={{ maxWidth: 680, margin: "0 auto", padding: "120px 24px" }}>
          <p style={{ color: "var(--color-error)" }}>{error || "Not found."}</p>
          <Link href="/jobs" style={{ color: "var(--color-primary)", fontSize: 13 }}>← Back to jobs</Link>
        </main>
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)" }}>
      <Navbar />
      <main style={{ maxWidth: 680, margin: "0 auto", padding: "100px 24px 60px" }}>
        <Link href="/jobs" style={{ fontSize: 12, color: "var(--color-text-subtle)", textDecoration: "none" }}>← Back to jobs</Link>

        <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--color-text-heading)", margin: "12px 0 4px" }}>
          {posting.title}
        </h1>
        <div style={{ fontSize: 13, color: "var(--color-text-subtle)", marginBottom: 20 }}>
          {posting.org_name} · {posting.location} · {posting.remote_policy} · {posting.employment_type.replace("_", " ")}
        </div>

        {posting.required_skills.length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 20 }}>
            {posting.required_skills.map((skill) => (
              <span key={skill} className="status-tag status-tag-muted">{skill}</span>
            ))}
          </div>
        )}

        <div className="card-surface" style={{ padding: 20, marginBottom: 24, whiteSpace: "pre-wrap", fontSize: 14, color: "var(--color-text-muted)", lineHeight: 1.7 }}>
          {posting.description || "No description provided."}
        </div>

        {applied ? (
          <div style={{ padding: "16px 20px", background: "rgba(34,197,94,0.1)", border: "1px solid rgba(34,197,94,0.2)", borderRadius: 8, fontSize: 14, color: "var(--color-success)" }}>
            Application submitted. Track its progress from <Link href="/applications" style={{ color: "var(--color-success)", fontWeight: 600 }}>My Applications</Link>.
          </div>
        ) : (
          <div className="card-surface" style={{ padding: 24 }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-primary)", letterSpacing: "0.05em", marginBottom: 16 }}>
              APPLY
            </div>

            {!actor && (
              <p style={{ fontSize: 13, color: "var(--color-text-muted)", marginBottom: 16 }}>
                <Link href={`/login?next=/jobs/${postingId}`} style={{ color: "var(--color-primary)" }}>Log in</Link> or{" "}
                <Link href="/register" style={{ color: "var(--color-primary)" }}>sign up</Link> to apply.
              </p>
            )}

            {actor && form && form.questions.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <p style={{ fontSize: 12, color: "var(--color-text-subtle)", marginBottom: 12 }}>
                  {form.unanswered_count === 0
                    ? "All questions are pre-filled from your profile vault."
                    : `${form.unanswered_count} question${form.unanswered_count > 1 ? "s" : ""} need${form.unanswered_count === 1 ? "s" : ""} an answer.`}
                </p>
                {form.questions.map((q) => (
                  <div key={q.key} style={{ marginBottom: 12 }}>
                    <label htmlFor={`q-${q.key}`} style={{ display: "block", fontSize: 13, color: "var(--color-text-heading)", marginBottom: 4 }}>
                      {q.text} {q.required && <span style={{ color: "var(--color-error)" }}>*</span>}
                      {q.is_prefilled && <span style={{ fontSize: 11, color: "var(--color-success)", marginLeft: 8 }}>(from your vault)</span>}
                    </label>
                    <textarea
                      id={`q-${q.key}`}
                      rows={2}
                      value={answers[q.key] || ""}
                      onChange={(e) => setAnswers((prev) => ({ ...prev, [q.key]: e.target.value }))}
                      style={{ width: "100%", padding: "8px 12px", fontSize: 13, color: "var(--color-text-heading)", background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: 6, outline: "none", resize: "vertical" }}
                    />
                  </div>
                ))}
              </div>
            )}

            {error && (
              <div style={{ padding: "10px 14px", background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: 6, fontSize: 13, color: "var(--color-error)", marginBottom: 16 }}>
                {error}
              </div>
            )}

            <button
              onClick={handleApply}
              disabled={applying}
              className="btn-primary"
              style={{ padding: "12px 24px", fontSize: 14, opacity: applying ? 0.6 : 1 }}
            >
              {applying ? "Submitting..." : actor ? "Submit application" : "Log in to apply"}
            </button>
          </div>
        )}
      </main>
    </div>
  );
}
