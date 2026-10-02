"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import Navbar from "../../components/Navbar";
import { EmptyState, PageHeader, PageShell, SkeletonList, StatusPill } from "../../components/ui";
import { useAuth } from "../../../lib/auth-context";
import { api, ApiError } from "../../../lib/api";
import { notify } from "../../../lib/toast";
import type { Referral } from "../../../lib/types";

function referralTone(status: Referral["status"]): "success" | "warning" | "muted" {
  if (status === "APPLIED") return "success";
  if (status === "DECLINED") return "warning";
  return "muted";
}

export default function RecruiterReferralsPage() {
  const router = useRouter();
  const { actor, activeOrgId, loading: authLoading } = useAuth();
  const [referrals, setReferrals] = useState<Referral[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (authLoading) return;
    if (!actor) {
      router.push("/login?next=/org/referrals");
      return;
    }
    if (!activeOrgId) {
      router.push("/org");
      return;
    }
    void loadReferrals();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, actor, activeOrgId]);

  const loadReferrals = async () => {
    setLoading(true);
    try {
      const data = await api.get<{ referrals: Referral[] }>(`/orgs/${activeOrgId}/referrals`);
      setReferrals(data.referrals);
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to load referrals.");
    } finally {
      setLoading(false);
    }
  };

  let content = <ReferralTable referrals={referrals} />;
  if (loading) content = <SkeletonList count={4} />;
  if (!loading && referrals.length === 0) {
    content = <EmptyState title="No referrals sent" description="Referrals created from a job pipeline will appear here." />;
  }

  return (
    <div className="min-h-screen">
      <Navbar />
      <PageShell className="!max-w-[1180px] pt-[112px]">
        <PageHeader eyebrow="RECRUITER WORKSPACE" title="Referral ledger" description="Track every referral sent from this organization and its candidate response." />
        <div className="mt-8">{content}</div>
      </PageShell>
    </div>
  );
}

function ReferralTable({ referrals }: Readonly<{ referrals: Referral[] }>) {
  return <div className="overflow-x-auto border border-subtle bg-[rgba(17,18,30,0.74)]"><table className="w-full min-w-[720px] border-collapse text-left"><thead className="border-b border-subtle bg-[rgba(255,255,255,0.025)]"><tr className="mono text-[10px] tracking-[0.08em] text-ink-subtle"><th className="px-5 py-3">CANDIDATE</th><th className="px-5 py-3">ROLE</th><th className="px-5 py-3">NOTE</th><th className="px-5 py-3">STATUS</th><th className="px-5 py-3">SENT</th></tr></thead><tbody>{referrals.map((referral) => <tr key={referral.id} className="border-b border-subtle last:border-0 hover:bg-[rgba(255,255,255,0.025)]"><td className="px-5 py-4 text-[13px] font-medium text-ink-heading">{referral.candidate_email}</td><td className="px-5 py-4 text-[12px] text-ink-muted">{referral.posting_title || `Posting #${referral.posting_id}`}</td><td className="max-w-[280px] truncate px-5 py-4 text-[12px] text-ink-muted">{referral.note || "-"}</td><td className="px-5 py-4"><StatusPill tone={referralTone(referral.status)}>{referral.status}</StatusPill></td><td className="px-5 py-4 text-[12px] text-ink-muted">{new Date(referral.created_at).toLocaleDateString()}</td></tr>)}</tbody></table></div>;
}