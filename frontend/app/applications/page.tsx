"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Navbar from "../components/Navbar";
import { useAuth } from "../../lib/auth-context";
import { api, ApiError } from "../../lib/api";
import type { ApplicationDetail, ApplicationEvent, ApplicationSummary } from "../../lib/types";

const STAGE_CLASS: Record<string, string> = {
  APPLIED: "status-tag-primary",
  SCREENING: "status-tag-primary",
  PENDING_REVIEW: "status-tag-warning",
  TECHNICAL: "status-tag-primary",
  BEHAVIORAL: "status-tag-primary",
  INTERVIEW: "status-tag-primary",
  OFFER: "status-tag-success",
  HIRED: "status-tag-success",
  REJECTED: "status-tag-error",
  WITHDRAWN: "status-tag-muted",
};

function formatDate(d: string): string {
  try {
    return new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  } catch {
    return d;
  }
}

export default function ApplicationsPage() {
  const router = useRouter();
  const { actor, loading: authLoading } = useAuth();
  const [applications, setApplications] = useState<ApplicationSummary[]>([]);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [detail, setDetail] = useState<{ application: ApplicationDetail; timeline: ApplicationEvent[] } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authLoading) return;
    if (!actor) {
      router.push("/login?next=/applications");
      return;
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, actor]);

  const load = async () => {
    setLoading(true);
    try {
      const data = await api.get<{ applications: ApplicationSummary[] }>("/me/applications");
      setApplications(data.applications);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load applications.");
    } finally {
      setLoading(false);
    }
  };

  const toggleExpand = async (id: number) => {
    if (expanded === id) {
      setExpanded(null);
      setDetail(null);
      return;
    }
    setExpanded(id);
    try {
      const data = await api.get<{ application: ApplicationDetail; timeline: ApplicationEvent[] }>(
        `/me/applications/${id}`,
      );
      setDetail(data);
    } catch {
      setDetail(null);
    }
  };

  const handleWithdraw = async (id: number) => {
    try {
      await api.post(`/me/applications/${id}/withdraw`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to withdraw.");
    }
  };

  if (authLoading || loading) {
    return (
      <div style={{ minHeight: "100vh", background: "var(--color-bg)" }}>
        <Navbar />
        <main style={{ maxWidth: 720, margin: "0 auto", padding: "120px 24px" }}>
          <p style={{ color: "var(--color-text-muted)" }}>Loading...</p>
        </main>
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)" }}>
      <Navbar />
      <main style={{ maxWidth: 720, margin: "0 auto", padding: "100px 24px 60px" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-primary)", letterSpacing: "0.1em", marginBottom: 8 }}>
          APPLICATION TRACKER
        </div>
        <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--color-text-heading)", marginBottom: 24 }}>
          Your applications
        </h1>

        {error && (
          <div style={{ padding: "10px 14px", background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: 6, fontSize: 13, color: "var(--color-error)", marginBottom: 20 }}>
            {error}
          </div>
        )}

        {applications.length === 0 ? (
          <p style={{ color: "var(--color-text-muted)", fontSize: 14 }}>
            You haven&apos;t applied anywhere yet. <Link href="/jobs" style={{ color: "var(--color-primary)" }}>Browse jobs</Link>.
          </p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {applications.map((app) => (
              <div key={app.id} className="card-surface" style={{ padding: 0, overflow: "hidden" }}>
                <button
                  type="button"
                  onClick={() => toggleExpand(app.id)}
                  style={{ width: "100%", padding: "16px 20px", display: "flex", justifyContent: "space-between", alignItems: "center", background: "none", border: "none", textAlign: "left", cursor: "pointer", color: "inherit", font: "inherit" }}
                >
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 600, color: "var(--color-text-heading)" }}>{app.posting_title}</div>
                    <div style={{ fontSize: 12, color: "var(--color-text-subtle)" }}>{app.org_name} · Applied {formatDate(app.created_at)}</div>
                  </div>
                  <span className={`status-tag ${STAGE_CLASS[app.current_stage] || "status-tag-muted"}`}>{app.current_stage}</span>
                </button>

                {expanded === app.id && (
                  <div style={{ padding: "0 20px 20px", borderTop: "1px solid var(--color-border)" }}>
                    {detail && (
                      <div style={{ marginTop: 16 }}>
                        <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--color-text-subtle)", marginBottom: 8 }}>TIMELINE</div>
                        {detail.timeline.map((event, i) => (
                          <div key={`${event.event_type}-${i}`} style={{ fontSize: 12, color: "var(--color-text-muted)", marginBottom: 4 }}>
                            {formatDate(event.created_at)} — {event.to_stage || event.event_type}
                          </div>
                        ))}
                      </div>
                    )}
                    {app.current_stage !== "WITHDRAWN" && app.current_stage !== "REJECTED" && app.current_stage !== "HIRED" && (
                      <button
                        onClick={() => handleWithdraw(app.id)}
                        className="btn-secondary"
                        style={{ marginTop: 16, padding: "6px 14px", fontSize: 12 }}
                      >
                        Withdraw application
                      </button>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
