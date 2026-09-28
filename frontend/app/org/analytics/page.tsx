"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Navbar from "../../components/Navbar";
import { useAuth } from "../../../lib/auth-context";
import { api, ApiError } from "../../../lib/api";
import type { FunnelResult, SelectionRatesResult } from "../../../lib/types";

export default function AnalyticsPage() {
  const router = useRouter();
  const { actor, loading: authLoading, activeOrgId } = useAuth();
  const [funnel, setFunnel] = useState<FunnelResult | null>(null);
  const [selectionRates, setSelectionRates] = useState<SelectionRatesResult | null>(null);
  const [segmentBy, setSegmentBy] = useState<"source" | "experience_band">("source");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authLoading) return;
    if (!actor) {
      router.push("/login?next=/org/analytics");
      return;
    }
    if (!activeOrgId) return;
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, actor, activeOrgId, segmentBy]);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [funnelData, ratesData] = await Promise.all([
        api.get<FunnelResult>(`/orgs/${activeOrgId}/analytics/funnel`),
        api.get<SelectionRatesResult>(`/orgs/${activeOrgId}/analytics/selection-rates?segment_by=${segmentBy}`),
      ]);
      setFunnel(funnelData);
      setSelectionRates(ratesData);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.status === 403
            ? "Analytics requires a hiring manager, org admin, or org owner role."
            : err.detail
          : "Failed to load analytics.",
      );
    } finally {
      setLoading(false);
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

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)" }}>
      <Navbar />
      <main style={{ maxWidth: 780, margin: "0 auto", padding: "100px 24px 60px" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-primary)", letterSpacing: "0.1em", marginBottom: 8 }}>
          RECRUITER ANALYTICS
        </div>
        <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--color-text-heading)", marginBottom: 24 }}>
          Funnel & fairness
        </h1>

        {error && (
          <div style={{ padding: "10px 14px", background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: 6, fontSize: 13, color: "var(--color-error)", marginBottom: 20 }}>
            {error}
          </div>
        )}

        {funnel && (
          <div className="card-surface" style={{ padding: 24, marginBottom: 24 }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-primary)", letterSpacing: "0.05em", marginBottom: 16 }}>
              HIRING FUNNEL
            </div>
            {funnel.funnel.map((stage) => (
              <div key={stage.stage} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: "1px solid var(--color-border)" }}>
                <span style={{ fontSize: 13, color: "var(--color-text-heading)" }}>{stage.stage}</span>
                <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 13, color: "var(--color-text-muted)" }}>{stage.reached}</span>
                  {stage.conversion_from_applied !== null && (
                    <span style={{ fontSize: 12, color: "var(--color-text-subtle)" }}>
                      {(stage.conversion_from_applied * 100).toFixed(0)}% of applied
                    </span>
                  )}
                </div>
              </div>
            ))}
            <div style={{ display: "flex", gap: 16, marginTop: 12, fontSize: 12, color: "var(--color-text-subtle)" }}>
              <span>Rejected: {funnel.rejected}</span>
              <span>Withdrawn: {funnel.withdrawn}</span>
            </div>
          </div>
        )}

        {selectionRates && (
          <div className="card-surface" style={{ padding: 24 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-primary)", letterSpacing: "0.05em" }}>
                SELECTION RATE DIVERGENCE
              </div>
              <select
                value={segmentBy}
                onChange={(e) => setSegmentBy(e.target.value as "source" | "experience_band")}
                style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: 6, color: "var(--color-text-muted)", fontSize: 12, padding: "5px 8px" }}
              >
                <option value="source">By source</option>
                <option value="experience_band">By experience band</option>
              </select>
            </div>

            {selectionRates.flag_adverse_impact && (
              <div style={{ padding: "10px 14px", background: "rgba(245,158,11,0.1)", border: "1px solid rgba(245,158,11,0.2)", borderRadius: 6, fontSize: 13, color: "var(--color-warning)", marginBottom: 16 }}>
                One segment is selected at less than 80% the rate of the highest-selecting segment (ratio: {selectionRates.adverse_impact_ratio}). Review before drawing conclusions from a small sample.
              </div>
            )}

            {Object.entries(selectionRates.segments).map(([key, seg]) => (
              <div key={key} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid var(--color-border)" }}>
                <span style={{ fontSize: 13, color: "var(--color-text-heading)" }}>{key}</span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 13, color: "var(--color-text-muted)" }}>
                  {seg.selected}/{seg.total} · {(seg.selection_rate * 100).toFixed(0)}%
                </span>
              </div>
            ))}

            <p style={{ fontSize: 11, color: "var(--color-text-subtle)", marginTop: 16, lineHeight: 1.6 }}>
              {selectionRates.note}
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
