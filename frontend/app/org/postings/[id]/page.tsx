"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import Navbar from "../../../components/Navbar";
import {
  Alert,
  Button,
  EmptyState,
  GlassCard,
  Input,
  PageShell,
  Select,
  SkeletonList,
  StatusPill,
  Textarea,
} from "../../../components/ui";
import { useAuth } from "../../../../lib/auth-context";
import { api, ApiError } from "../../../../lib/api";
import type { ApplicationSummary, CandidateRecommendation, JobPosting } from "../../../../lib/types";
import { staggerContainer, staggerItem } from "../../../../lib/motion";

const NEXT_STAGE_OPTIONS = ["SCREENING", "TECHNICAL", "BEHAVIORAL", "INTERVIEW", "OFFER", "HIRED"];

function formatSalaryRange(min: number | null, max: number | null): string {
  if (!min && !max) return "";
  return `${min ?? "?"} – ${max ?? "?"}`;
}

function candidateName(app: ApplicationSummary): string {
  return (app as unknown as { candidate_name?: string }).candidate_name || "Candidate";
}

function PipelineList({
  applications,
  onTransition,
}: Readonly<{
  applications: ApplicationSummary[];
  onTransition: (applicationId: number, toStage: string) => Promise<void>;
}>) {
  if (applications.length === 0) {
    return (
      <EmptyState
        title="No applicants yet"
        description="Publish the posting and share the link — applicants land here the moment they apply."
      />
    );
  }

  return (
    <motion.div
      initial="hidden"
      animate="visible"
      variants={staggerContainer(0.05)}
      className="flex flex-col gap-3"
    >
      {applications.map((app) => (
        <motion.div key={app.id} variants={staggerItem}>
          <GlassCard padding="sm">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="min-w-0">
                <p className="text-[14px] font-semibold text-ink-heading">{candidateName(app)}</p>
                <div className="mt-1.5">
                  <StatusPill tone="primary">{app.current_stage}</StatusPill>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Select
                  aria-label="Move to stage"
                  wrapperClassName="w-[150px]"
                  defaultValue=""
                  onChange={(e) => {
                    if (e.target.value) onTransition(app.id, e.target.value);
                    e.target.value = "";
                  }}
                >
                  <option value="">Move to...</option>
                  {NEXT_STAGE_OPTIONS.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </Select>
                <Button size="sm" variant="ghost" onClick={() => onTransition(app.id, "REJECTED")}>
                  Reject
                </Button>
              </div>
            </div>
          </GlassCard>
        </motion.div>
      ))}
    </motion.div>
  );
}

function RecommendedList({ candidates }: Readonly<{ candidates: CandidateRecommendation[] }>) {
  if (candidates.length === 0) {
    return (
      <EmptyState
        title="No matches yet"
        description="No discoverable candidates match this posting yet. Matches appear as more candidates opt in."
      />
    );
  }

  return (
    <motion.div
      initial="hidden"
      animate="visible"
      variants={staggerContainer(0.05)}
      className="flex flex-col gap-3"
    >
      {candidates.map((cand) => (
        <motion.div key={cand.user_id} variants={staggerItem}>
          <GlassCard padding="sm">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <p className="text-[14px] font-semibold text-ink-heading">{cand.full_name}</p>
                <p className="mt-0.5 text-[12px] text-ink-subtle">
                  {cand.headline} · {cand.location}
                </p>
              </div>
              <span className="mono shrink-0 text-[15px] font-bold text-brand">{cand.score}/10</span>
            </div>
            <p className="mt-3 text-[12px] leading-[1.65] text-ink-muted">{cand.explanation}</p>
          </GlassCard>
        </motion.div>
      ))}
    </motion.div>
  );
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
      <div className="min-h-screen">
        <Navbar />
        <PageShell className="!max-w-[820px] pt-[112px]">
          <SkeletonList count={4} />
        </PageShell>
      </div>
    );
  }

  if (!posting) {
    return (
      <div className="min-h-screen">
        <Navbar />
        <PageShell className="!max-w-[820px] pt-[112px]">
          <Alert tone="error" title="Posting unavailable">
            {error || "We couldn't find that posting."}
          </Alert>
        </PageShell>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Navbar />
      <PageShell className="!max-w-[820px] pt-[112px]">
        <Link
          href="/org"
          className="mono text-[11px] tracking-[0.08em] text-ink-subtle no-underline transition-colors duration-fast ease-out-expo hover:text-brand"
        >
          ← BACK TO CAMPAIGNS
        </Link>

        <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-[26px] font-bold tracking-normal text-ink-heading">{posting.title}</h1>
            <p className="mt-1 text-[12px] text-ink-subtle">
              {posting.location} · {posting.remote_policy} ·{" "}
              {formatSalaryRange(posting.salary_min, posting.salary_max)}
            </p>
          </div>
          <StatusPill tone={posting.status === "PUBLISHED" ? "success" : "warning"}>
            {posting.status}
          </StatusPill>
        </div>

        {error && (
          <Alert tone="error" className="mt-6">
            {error}
          </Alert>
        )}

        <div className="mt-6 flex flex-wrap gap-2">
          {Object.entries(funnel).map(([stage, count]) => (
            <StatusPill key={stage} tone="muted">
              {stage}: {count}
            </StatusPill>
          ))}
        </div>

        <div className="mt-6 flex flex-wrap gap-2">
          <Button
            size="sm"
            variant={tab === "pipeline" ? "primary" : "secondary"}
            onClick={() => setTab("pipeline")}
          >
            Applicants
          </Button>
          <Button
            size="sm"
            variant={tab === "recommended" ? "primary" : "secondary"}
            onClick={() => {
              setTab("recommended");
              if (recommended.length === 0) loadRecommended();
            }}
          >
            Recommended candidates
          </Button>
        </div>

        <div className="mt-6">
          {tab === "pipeline" ? (
            <PipelineList applications={applications} onTransition={handleTransition} />
          ) : (
            <RecommendedList candidates={recommended} />
          )}
        </div>

        <GlassCard elevation="high" padding="lg" className="mt-8">
          <p className="eyebrow">REFER A CANDIDATE</p>
          <form onSubmit={handleRefer} className="mt-5 flex flex-col gap-4">
            <Input
              type="email"
              required
              label="CANDIDATE EMAIL"
              placeholder="candidate@example.com"
              value={referEmail}
              onChange={(e) => setReferEmail(e.target.value)}
            />
            <Textarea
              rows={2}
              label="NOTE"
              hint="Optional — the candidate sees this on their referrals page."
              placeholder="Why are you referring them?"
              value={referNote}
              onChange={(e) => setReferNote(e.target.value)}
            />
            {referMessage && <Alert tone="success">{referMessage}</Alert>}
            <Button type="submit" className="self-start" loading={referring}>
              {referring ? "Sending..." : "Send referral"}
            </Button>
          </form>
        </GlassCard>
      </PageShell>
    </div>
  );
}
