"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Navbar from "../components/Navbar";

const API_BASE = "/api";

const DECISION_CLASSES: Record<string, string> = {
  HIRE: "status-tag-success",
  HOLD: "status-tag-warning",
  REJECT: "status-tag-error",
};

const STATUS_CLASSES: Record<string, string> = {
  IN_PROGRESS: "status-tag-primary",
  COMPLETE: "status-tag-success",
  REJECTED: "status-tag-error",
};

type Evaluation = {
  id: number;
  candidate_name: string;
  role: string;
  status: string;
  current_round: number;
  overall_score: number | null;
  final_decision: string | null;
  created_at: string;
  updated_at: string;
  verdicts_summary?: Array<{ agent_type: string; decision: string; score: number }>;
};

type DashStats = {
  total: number;
  completed: number;
  in_progress: number;
  rejected: number;
  hired: number;
  hire_rate: number;
  avg_score: number;
};

export default function DashboardPage() {
  const router = useRouter();
  const [evaluations, setEvaluations] = useState<Evaluation[]>([]);
  const [stats, setStats] = useState<DashStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>("all");

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [evalRes, statsRes] = await Promise.all([
        fetch(`${API_BASE}/evaluations`),
        fetch(`${API_BASE}/dashboard/stats`),
      ]);

      if (evalRes.ok) {
        const evalData = await evalRes.json();
        setEvaluations(evalData.evaluations || []);
      }
      if (statsRes.ok) {
        const statsData = await statsRes.json();
        setStats(statsData);
      }
    } catch (err) {
      console.error("Failed to load dashboard:", err);
    } finally {
      setLoading(false);
    }
  };

  const filteredEvals = filter === "all"
    ? evaluations
    : evaluations.filter((e) => e.status === filter || e.final_decision === filter);

  const formatDate = (d: string) => {
    try {
      return new Date(d).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
    } catch {
      return d;
    }
  };

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)" }}>
      <Navbar />

      <main style={{ maxWidth: "var(--max-width)", margin: "0 auto", padding: "90px 24px 60px" }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8, flexWrap: "wrap", gap: 16 }}>
          <div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-primary)", letterSpacing: "0.1em", marginBottom: 4 }}>
              PUBLIC DEMO — AI EVALUATION SANDBOX
            </div>
            <h1 style={{ fontSize: 28, fontWeight: 700, color: "var(--color-text-heading)" }}>
              Sandbox evaluations
            </h1>
          </div>
          <button className="btn-primary" onClick={() => router.push("/interview")}>
            New Evaluation
          </button>
        </div>
        <p style={{ fontSize: 13, color: "var(--color-text-muted)", marginBottom: 32, lineHeight: 1.6 }}>
          This is an unauthenticated, public sandbox for trying the AI evaluation engine — anyone
          can see the evaluations run here. It is not connected to real job postings or applicants.
          If you&apos;re hiring for real, use the <Link href="/org" style={{ color: "var(--color-primary)" }}>recruiter workspace</Link> instead,
          which is private to your organization.
        </p>

        {/* Stats bar */}
        {stats && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))",
              gap: 12,
              marginBottom: 32,
            }}
          >
            {[
              { label: "Total", value: stats.total, color: "var(--color-text-heading)" },
              { label: "Completed", value: stats.completed, color: "var(--color-success)" },
              { label: "In Progress", value: stats.in_progress, color: "var(--color-primary)" },
              { label: "Rejected", value: stats.rejected, color: "var(--color-error)" },
              { label: "Hired", value: stats.hired, color: "var(--color-success)" },
              { label: "Hire Rate", value: `${stats.hire_rate}%`, color: "var(--color-primary)" },
              { label: "Avg Score", value: stats.avg_score > 0 ? stats.avg_score.toFixed(1) : "—", color: "var(--color-primary)" },
            ].map((s) => (
              <div key={s.label} className="card-surface" style={{ padding: "14px 16px", textAlign: "center" }}>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 22, fontWeight: 700, color: s.color }}>
                  {s.value}
                </div>
                <div style={{ fontSize: 10, color: "var(--color-text-subtle)", marginTop: 4, fontFamily: "var(--font-mono)" }}>
                  {s.label}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Filters */}
        <div style={{ display: "flex", gap: 8, marginBottom: 20, flexWrap: "wrap", fontFamily: "var(--font-mono)", fontSize: 12 }}>
          {[
            { key: "all", label: "ALL" },
            { key: "COMPLETE", label: "COMPLETED" },
            { key: "IN_PROGRESS", label: "IN PROGRESS" },
            { key: "REJECTED", label: "REJECTED" },
          ].map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              style={{
                padding: "6px 12px",
                color: filter === f.key ? "var(--color-primary)" : "var(--color-text-muted)",
                background: filter === f.key ? "var(--color-surface)" : "transparent",
                border: `1px solid ${filter === f.key ? "var(--color-border-hover)" : "transparent"}`,
                borderRadius: 4,
                cursor: "pointer",
                fontFamily: "inherit",
              }}
            >
              {f.label}
            </button>
          ))}
        </div>

        {/* Evaluation list */}
        {loading ? (
          <div style={{ padding: 40, textAlign: "center", fontSize: 13, color: "var(--color-text-muted)", fontFamily: "var(--font-mono)" }}>
            LOADING EVALUATIONS...
          </div>
        ) : filteredEvals.length === 0 ? (
          <div className="card-surface" style={{ padding: 40, textAlign: "center" }}>
            <div style={{ fontSize: 14, color: "var(--color-text-muted)", marginBottom: 16 }}>
              No candidate evaluations match this view.
            </div>
            <button className="btn-primary" onClick={() => router.push("/interview")}>
              Start Evaluation
            </button>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {filteredEvals.map((ev) => (
              <div
                key={ev.id}
                className="card-surface"
                style={{ padding: "16px 20px", cursor: "pointer" }}
                onClick={() => router.push(`/dashboard/${ev.id}`)}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
                      <span style={{ fontSize: 15, fontWeight: 600, color: "var(--color-text-heading)" }}>
                        {ev.candidate_name || `Evaluation #${ev.id}`}
                      </span>
                      <span className={`status-tag ${STATUS_CLASSES[ev.status] || "status-tag-muted"}`}>
                        {ev.status}
                      </span>
                    </div>
                    <div style={{ fontSize: 12, color: "var(--color-text-subtle)", fontFamily: "var(--font-mono)" }}>
                      {ev.role} • Stage {ev.current_round}/5 • {formatDate(ev.created_at)}
                    </div>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                    {ev.overall_score !== null && (
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: 16, fontWeight: 700, color: "var(--color-text-heading)" }}>
                        {ev.overall_score.toFixed(1)}/10
                      </span>
                    )}
                    {ev.final_decision && (
                      <span className={`status-tag ${DECISION_CLASSES[ev.final_decision] || "status-tag-muted"}`}>
                        {ev.final_decision}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
