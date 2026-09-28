"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "../../lib/auth-context";
import { api } from "../../lib/api";
import type { JobPosting, JobRecommendation } from "../../lib/types";
import Navbar from "../components/Navbar";

function formatSalary(min: number | null, max: number | null, currency: string): string {
  if (!min && !max) return "Not disclosed";
  const fmt = (n: number) => `${currency} ${(n / 100000).toFixed(1)}L`;
  if (min && max) return `${fmt(min)} – ${fmt(max)}`;
  return fmt((min ?? max) as number);
}

export default function JobsPage() {
  const { actor, loading: authLoading } = useAuth();
  const [tab, setTab] = useState<"recommended" | "all">("all");
  const [postings, setPostings] = useState<JobPosting[]>([]);
  const [recommendations, setRecommendations] = useState<JobRecommendation[]>([]);
  const [query, setQuery] = useState("");
  const [location, setLocation] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && actor) setTab("recommended");
  }, [authLoading, actor]);

  useEffect(() => {
    if (tab === "all") searchJobs();
    else if (tab === "recommended" && actor) loadRecommendations();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, actor]);

  const searchJobs = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (query.trim()) params.set("q", query.trim());
      if (location.trim()) params.set("location", location.trim());
      const data = await api.get<{ postings: JobPosting[] }>(`/jobs?${params.toString()}`);
      setPostings(data.postings);
    } catch {
      setError("Failed to load jobs.");
    } finally {
      setLoading(false);
    }
  };

  const loadRecommendations = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get<{ recommendations: JobRecommendation[] }>("/me/recommended-jobs");
      setRecommendations(data.recommendations);
    } catch {
      setError("Failed to load recommendations.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)" }}>
      <Navbar />
      <main style={{ maxWidth: 780, margin: "0 auto", padding: "100px 24px 60px" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-primary)", letterSpacing: "0.1em", marginBottom: 8 }}>
          JOB BOARD
        </div>
        <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--color-text-heading)", marginBottom: 24 }}>
          Find your next role
        </h1>

        {actor && (
          <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
            <button
              onClick={() => setTab("recommended")}
              className={tab === "recommended" ? "btn-primary" : "btn-secondary"}
              style={{ padding: "8px 16px", fontSize: 13 }}
            >
              Recommended for you
            </button>
            <button
              onClick={() => setTab("all")}
              className={tab === "all" ? "btn-primary" : "btn-secondary"}
              style={{ padding: "8px 16px", fontSize: 13 }}
            >
              Browse all
            </button>
          </div>
        )}

        {tab === "all" && (
          <div style={{ display: "flex", gap: 12, marginBottom: 24 }}>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && searchJobs()}
              placeholder="Search titles or descriptions..."
              style={{ flex: 2, padding: "10px 14px", fontSize: 14, color: "var(--color-text-heading)", background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: 6, outline: "none" }}
            />
            <input
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && searchJobs()}
              placeholder="Location"
              style={{ flex: 1, padding: "10px 14px", fontSize: 14, color: "var(--color-text-heading)", background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: 6, outline: "none" }}
            />
            <button onClick={searchJobs} className="btn-secondary" style={{ padding: "10px 20px", fontSize: 13 }}>
              Search
            </button>
          </div>
        )}

        {error && (
          <div style={{ padding: "10px 14px", background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: 6, fontSize: 13, color: "var(--color-error)", marginBottom: 20 }}>
            {error}
          </div>
        )}

        {loading ? (
          <p style={{ color: "var(--color-text-muted)" }}>Loading...</p>
        ) : tab === "recommended" ? (
          recommendations.length === 0 ? (
            <p style={{ color: "var(--color-text-muted)", fontSize: 14 }}>
              No recommendations yet. <Link href="/profile" style={{ color: "var(--color-primary)" }}>Complete your profile</Link> to get matched.
            </p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {recommendations.map((rec) => (
                <Link key={rec.posting_id} href={`/jobs/${rec.posting_id}`} className="card-surface" style={{ padding: 20, display: "block", textDecoration: "none" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                    <div>
                      <div style={{ fontSize: 15, fontWeight: 600, color: "var(--color-text-heading)" }}>{rec.title}</div>
                      <div style={{ fontSize: 12, color: "var(--color-text-subtle)" }}>{rec.org_name} · {rec.location} · {rec.remote_policy}</div>
                    </div>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 16, fontWeight: 700, color: "var(--color-primary)" }}>
                      {rec.score}/10
                    </span>
                  </div>
                  <p style={{ fontSize: 13, color: "var(--color-text-muted)", marginTop: 10, lineHeight: 1.6 }}>{rec.explanation}</p>
                </Link>
              ))}
            </div>
          )
        ) : postings.length === 0 ? (
          <p style={{ color: "var(--color-text-muted)", fontSize: 14 }}>No open roles match your search.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {postings.map((posting) => (
              <Link key={posting.id} href={`/jobs/${posting.id}`} className="card-surface" style={{ padding: 20, display: "block", textDecoration: "none" }}>
                <div style={{ fontSize: 15, fontWeight: 600, color: "var(--color-text-heading)" }}>{posting.title}</div>
                <div style={{ fontSize: 12, color: "var(--color-text-subtle)", marginTop: 4 }}>
                  {posting.org_name} · {posting.location} · {posting.remote_policy}
                </div>
                <div style={{ fontSize: 12, color: "var(--color-text-muted)", marginTop: 8 }}>
                  {formatSalary(posting.salary_min, posting.salary_max, posting.currency)}
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
