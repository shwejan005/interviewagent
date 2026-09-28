"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import Navbar from "../../../components/Navbar";
import { useAuth } from "../../../../lib/auth-context";
import { api, ApiError } from "../../../../lib/api";
import type { ApplicationSummary, CandidateRecommendation, JobPosting } from "../../../../lib/types";

const NEXT_STAGE_OPTIONS = ["SCREENING", "TECHNICAL", "BEHAVIORAL", "INTERVIEW", "OFFER", "HIRED"];

function formatSalaryRange(min: number | null, max: number | null): string {
  if (!min && !max) return "";
  return `${min ?? "?"} – ${max ?? "?"}`;
}

export default function PostingDetailPage() {
  const params = useParams();
  const router = useRouter();
  const postingId = params.id as string;
  const { actor, loading: authLoading, activeOrgId } = useAuth();

  const [posting, setPosting] = useState<JobPosting | null>(null);
  const [applications, setApplications] = useState<ApplicationSummary[]>([]);
  const [funnel, setFunnel] = useState<Record<string, number>>({});
  const [recommended, setRecommended] = useState<CandidateRecommendation[]>([]);
  const [tab, setTab] = useState<"pipeline" | "recommended">("pipeline");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [referEmail, setReferEmail] = useState("");
  const [referNote, setReferNote] = useState("");
  const [referring, setReferring] = useState(false);
  const [referMessage, setReferMessage] = useState<string | null>(null);

  useEffect(() => {
    if (authLoading) return;
    if (!actor) {
      router.push("/login?next=/org");
      return;
    }
    if (!activeOrgId) return;
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, actor, activeOrgId, postingId]);

  const load = async () => {
    setLoading(true);
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
      setError(err instanceof ApiError ? err.detail : "Failed to load posting.");
    } finally {
      setLoading(false);
    }
  };

  const loadRecommended = async () => {
    try {
      const data = await api.get<{ candidates: CandidateRecommendation[] }>(
        `/orgs/${activeOrgId}/postings/${postingId}/recommended-candidates`,
      );
      setRecommended(data.candidates);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load recommended candidates.");
    }
  };

  const handleTransition = async (applicationId: number, toStage: string) => {
    try {
      await api.post(`/orgs/${activeOrgId}/applications/${applicationId}/transition`, { to_stage: toStage });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to update application stage.");
    }
  };

  const handleRefer = async (e: React.FormEvent) => {
    e.preventDefault();
    setReferring(true);
    setReferMessage(null);
    setError(null);
    try {
      await api.post(`/orgs/${activeOrgId}/postings/${postingId}/referrals`, {
        candidate_email: referEmail,
        note: referNote,
      });
      setReferEmail("");
      setReferNote("");
      setReferMessage("Referral sent.");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to send referral.");
    } finally {
      setReferring(false);
    }
  };

  if (authLoading || loading) {
    return (
      <div style={{ minHeight: "100vh", background: "var(--color-bg)" }}>
        <Navbar />
        <main style={{ maxWidth: 780, margin: "0 auto", padding: "120px 24px" }}>
          <p style={{ color: "var(--color-text-muted)" }}>Loading...</p>
        </main>
      </div>
    );
  }

  if (!posting) {
    return (
      <div style={{ minHeight: "100vh", background: "var(--color-bg)" }}>
        <Navbar />
        <main style={{ maxWidth: 780, margin: "0 auto", padding: "120px 24px" }}>
          <p style={{ color: "var(--color-error)" }}>{error || "Not found."}</p>
        </main>
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)" }}>
      <Navbar />
      <main style={{ maxWidth: 780, margin: "0 auto", padding: "100px 24px 60px" }}>
        <Link href="/org" style={{ fontSize: 12, color: "var(--color-text-subtle)", textDecoration: "none" }}>← Back to campaigns</Link>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", margin: "12px 0 24px" }}>
          <div>
            <h1 style={{ fontSize: 24, fontWeight: 700, color: "var(--color-text-heading)" }}>{posting.title}</h1>
            <div style={{ fontSize: 12, color: "var(--color-text-subtle)" }}>
              {posting.location} · {posting.remote_policy} · {formatSalaryRange(posting.salary_min, posting.salary_max)}
            </div>
          </div>
          <span className={`status-tag ${posting.status === "PUBLISHED" ? "status-tag-success" : "status-tag-warning"}`}>
            {posting.status}
          </span>
        </div>

        {error && (
          <div style={{ padding: "10px 14px", background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: 6, fontSize: 13, color: "var(--color-error)", marginBottom: 20 }}>
            {error}
          </div>
        )}

        {/* Funnel summary */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 24 }}>
          {Object.entries(funnel).map(([stage, count]) => (
            <span key={stage} className="status-tag status-tag-muted">{stage}: {count}</span>
          ))}
        </div>

        <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
          <button onClick={() => setTab("pipeline")} className={tab === "pipeline" ? "btn-primary" : "btn-secondary"} style={{ padding: "8px 16px", fontSize: 13 }}>
            Applicants
          </button>
          <button
            onClick={() => {
              setTab("recommended");
              if (recommended.length === 0) loadRecommended();
            }}
            className={tab === "recommended" ? "btn-primary" : "btn-secondary"}
            style={{ padding: "8px 16px", fontSize: 13 }}
          >
            Recommended candidates
          </button>
        </div>

        {tab === "pipeline" ? (
          applications.length === 0 ? (
            <p style={{ color: "var(--color-text-muted)", fontSize: 14 }}>No applicants yet.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 32 }}>
              {applications.map((app) => (
                <div key={app.id} className="card-surface" style={{ padding: 16, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 600, color: "var(--color-text-heading)" }}>
                      {(app as unknown as { candidate_name?: string }).candidate_name || "Candidate"}
                    </div>
                    <span className="status-tag status-tag-primary" style={{ marginTop: 4, display: "inline-block" }}>{app.current_stage}</span>
                  </div>
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <select
                      aria-label="Move to stage"
                      defaultValue=""
                      onChange={(e) => {
                        if (e.target.value) handleTransition(app.id, e.target.value);
                        e.target.value = "";
                      }}
                      style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: 6, color: "var(--color-text-muted)", fontSize: 12, padding: "6px 8px" }}
                    >
                      <option value="">Move to...</option>
                      {NEXT_STAGE_OPTIONS.map((s) => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>
                    <button onClick={() => handleTransition(app.id, "REJECTED")} className="btn-secondary" style={{ padding: "6px 12px", fontSize: 12 }}>
                      Reject
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )
        ) : (
          <div style={{ marginBottom: 32 }}>
            {recommended.length === 0 ? (
              <p style={{ color: "var(--color-text-muted)", fontSize: 14 }}>
                No discoverable candidates match this posting yet.
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {recommended.map((cand) => (
                  <div key={cand.user_id} className="card-surface" style={{ padding: 16 }}>
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <div>
                        <div style={{ fontSize: 14, fontWeight: 600, color: "var(--color-text-heading)" }}>{cand.full_name}</div>
                        <div style={{ fontSize: 12, color: "var(--color-text-subtle)" }}>{cand.headline} · {cand.location}</div>
                      </div>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: 15, fontWeight: 700, color: "var(--color-primary)" }}>{cand.score}/10</span>
                    </div>
                    <p style={{ fontSize: 12, color: "var(--color-text-muted)", marginTop: 8, lineHeight: 1.6 }}>{cand.explanation}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="card-surface" style={{ padding: 24 }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-primary)", letterSpacing: "0.05em", marginBottom: 16 }}>
            REFER A CANDIDATE
          </div>
          <form onSubmit={handleRefer} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <input
              type="email"
              required
              placeholder="candidate@example.com"
              value={referEmail}
              onChange={(e) => setReferEmail(e.target.value)}
              style={{ padding: "10px 14px", fontSize: 14, color: "var(--color-text-heading)", background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: 6, outline: "none" }}
            />
            <textarea
              rows={2}
              placeholder="Why are you referring them? (optional)"
              value={referNote}
              onChange={(e) => setReferNote(e.target.value)}
              style={{ padding: "10px 14px", fontSize: 14, color: "var(--color-text-heading)", background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: 6, outline: "none", resize: "vertical" }}
            />
            {referMessage && <p style={{ fontSize: 12, color: "var(--color-success)" }}>{referMessage}</p>}
            <button type="submit" disabled={referring} className="btn-primary" style={{ padding: "10px 20px", fontSize: 13, alignSelf: "flex-start" }}>
              {referring ? "Sending..." : "Send referral"}
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}
