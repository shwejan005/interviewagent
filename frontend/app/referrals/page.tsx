"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Navbar from "../components/Navbar";
import { useAuth } from "../../lib/auth-context";
import { api, ApiError } from "../../lib/api";
import type { Referral } from "../../lib/types";

export default function ReferralsPage() {
  const router = useRouter();
  const { actor, loading: authLoading } = useAuth();
  const [referrals, setReferrals] = useState<Referral[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actingOn, setActingOn] = useState<number | null>(null);

  useEffect(() => {
    if (authLoading) return;
    if (!actor) {
      router.push("/login?next=/referrals");
      return;
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, actor]);

  const load = async () => {
    setLoading(true);
    try {
      const data = await api.get<{ referrals: Referral[] }>("/me/referrals");
      setReferrals(data.referrals);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load referrals.");
    } finally {
      setLoading(false);
    }
  };

  const handleAccept = async (id: number) => {
    setActingOn(id);
    setError(null);
    try {
      await api.post(`/me/referrals/${id}/apply`, {});
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to accept referral.");
    } finally {
      setActingOn(null);
    }
  };

  const handleDecline = async (id: number) => {
    setActingOn(id);
    setError(null);
    try {
      await api.post(`/me/referrals/${id}/decline`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to decline referral.");
    } finally {
      setActingOn(null);
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
          REFERRALS
        </div>
        <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--color-text-heading)", marginBottom: 8 }}>
          Sent to you
        </h1>
        <p style={{ fontSize: 13, color: "var(--color-text-muted)", marginBottom: 24 }}>
          A recruiter thought you&apos;d be a good fit for these roles.
        </p>

        {error && (
          <div style={{ padding: "10px 14px", background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: 6, fontSize: 13, color: "var(--color-error)", marginBottom: 20 }}>
            {error}
          </div>
        )}

        {referrals.length === 0 ? (
          <p style={{ color: "var(--color-text-muted)", fontSize: 14 }}>No referrals yet.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {referrals.map((ref) => (
              <div key={ref.id} className="card-surface" style={{ padding: 20 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 600, color: "var(--color-text-heading)" }}>{ref.posting_title}</div>
                    <div style={{ fontSize: 12, color: "var(--color-text-subtle)" }}>{ref.org_name}</div>
                  </div>
                  <span
                    className={`status-tag ${
                      ref.status === "PENDING" ? "status-tag-warning" : ref.status === "APPLIED" ? "status-tag-success" : "status-tag-muted"
                    }`}
                  >
                    {ref.status}
                  </span>
                </div>
                {ref.note && (
                  <p style={{ fontSize: 13, color: "var(--color-text-muted)", marginTop: 10, lineHeight: 1.6 }}>&ldquo;{ref.note}&rdquo;</p>
                )}
                {ref.status === "PENDING" && (
                  <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
                    <button
                      onClick={() => handleAccept(ref.id)}
                      disabled={actingOn === ref.id}
                      className="btn-primary"
                      style={{ padding: "6px 16px", fontSize: 12, opacity: actingOn === ref.id ? 0.6 : 1 }}
                    >
                      Accept & apply
                    </button>
                    <button
                      onClick={() => handleDecline(ref.id)}
                      disabled={actingOn === ref.id}
                      className="btn-secondary"
                      style={{ padding: "6px 16px", fontSize: 12, opacity: actingOn === ref.id ? 0.6 : 1 }}
                    >
                      Decline
                    </button>
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
