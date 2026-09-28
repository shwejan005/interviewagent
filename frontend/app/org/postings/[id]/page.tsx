"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import Navbar from "../../../components/Navbar";
import {
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
import { notify } from "../../../../lib/toast";
import type { ApplicationDetail, ApplicationEvent, ApplicationSummary, CandidateRecommendation, JobPosting } from "../../../../lib/types";
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
  onView,
}: Readonly<{
  applications: ApplicationSummary[];
  onTransition: (applicationId: number, toStage: string) => Promise<void>;
  onView: (applicationId: number) => void;
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
    <div className="overflow-x-auto border border-subtle bg-[rgba(17,18,30,0.74)]">
      <table className="w-full min-w-[820px] border-collapse text-left">
        <thead className="border-b border-subtle bg-[rgba(255,255,255,0.025)]">
          <tr className="mono text-[10px] tracking-[0.08em] text-ink-subtle">
            <th className="px-5 py-3 font-medium">CANDIDATE</th>
            <th className="px-5 py-3 font-medium">STAGE</th>
            <th className="px-5 py-3 font-medium">SOURCE</th>
            <th className="px-5 py-3 font-medium">APPLIED</th>
            <th className="px-5 py-3 font-medium">MOVE TO</th>
            <th className="px-5 py-3 font-medium" aria-label="Actions" />
          </tr>
        </thead>
        <tbody>
          {applications.map((app) => (
            <tr key={app.id} className="border-b border-subtle last:border-0 hover:bg-[rgba(255,255,255,0.025)]">
              <td className="px-5 py-4 text-[13px] font-semibold text-ink-heading">{candidateName(app)}</td>
              <td className="px-5 py-4"><StatusPill tone="primary">{app.current_stage}</StatusPill></td>
              <td className="px-5 py-4 text-[12px] text-ink-muted">{app.status}</td>
              <td className="px-5 py-4 text-[12px] text-ink-muted">{new Date(app.created_at).toLocaleDateString()}</td>
              <td className="px-5 py-3">
                <Select aria-label={`Move ${candidateName(app)} to stage`} wrapperClassName="w-[145px]" defaultValue="" onChange={(e) => {
                  if (e.target.value) onTransition(app.id, e.target.value);
                  e.target.value = "";
                }}>
                  <option value="">Select stage</option>
                  {NEXT_STAGE_OPTIONS.map((stage) => <option key={stage} value={stage}>{stage}</option>)}
                </Select>
              </td>
              <td className="px-5 py-3 text-right whitespace-nowrap">
                <Button size="sm" variant="ghost" onClick={() => onView(app.id)}>View</Button>
                <Button size="sm" variant="ghost" onClick={() => onTransition(app.id, "REJECTED")}>Reject</Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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
  const [referOpen, setReferOpen] = useState(false);
  const [selectedApplication, setSelectedApplication] = useState<{ application: ApplicationDetail; answers: unknown[]; timeline: ApplicationEvent[] } | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

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
      const message = err instanceof ApiError ? err.detail : "Failed to load posting.";
      setError(message);
      notify.error(message);
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
      notify.error(err instanceof ApiError ? err.detail : "Failed to load recommended candidates.");
    }
  };

  const handleTransition = async (applicationId: number, toStage: string) => {
    try {
      await api.post(`/orgs/${activeOrgId}/applications/${applicationId}/transition`, { to_stage: toStage });
      await load();
      notify.success(`Moved to ${toStage.replaceAll("_", " ").toLowerCase()}.`);
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to update application stage.");
    }
  };

  const loadApplication = async (applicationId: number) => {
    setDetailLoading(true);
    try {
      const detail = await api.get<{ application: ApplicationDetail; answers: unknown[]; timeline: ApplicationEvent[] }>(`/orgs/${activeOrgId}/applications/${applicationId}`);
      setSelectedApplication(detail);
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to load candidate details.");
    } finally {
      setDetailLoading(false);
    }
  };

  const handleRefer = async (e: React.FormEvent) => {
    e.preventDefault();
    setReferring(true);
    try {
      const referral = await api.post<{ email_delivery?: "sent" | "not_configured" | "failed" }>(`/orgs/${activeOrgId}/postings/${postingId}/referrals`, {
        candidate_email: referEmail,
        note: referNote,
      });
      setReferEmail("");
      setReferNote("");
      notify.success(referral.email_delivery === "sent" ? "Referral sent and emailed to the candidate." : "Referral saved. Email delivery isn't configured for this workspace.");
      setReferOpen(false);
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to send referral.");
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
          <EmptyState title="Posting unavailable" description={error || "We couldn't find that posting."} />
        </PageShell>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Navbar />
      <PageShell className="!max-w-[1180px] pt-[112px]">
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
          <div className="flex items-center gap-3">
            <StatusPill tone={posting.status === "PUBLISHED" ? "success" : "warning"}>{posting.status}</StatusPill>
            <Button size="sm" onClick={() => setReferOpen(true)}>Refer candidate</Button>
          </div>
        </div>

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
            <PipelineList applications={applications} onTransition={handleTransition} onView={loadApplication} />
          ) : (
            <RecommendedList candidates={recommended} />
          )}
        </div>

        {typeof document !== "undefined" && createPortal(
        <AnimatePresence>
          {(detailLoading || selectedApplication) && (
          <motion.dialog open aria-labelledby="candidate-detail-title" className="fixed inset-0 z-[70] flex h-full w-full max-w-none bg-transparent p-0" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.button aria-label="Close candidate details" className="h-full flex-1 cursor-default border-0 bg-black/65 backdrop-blur-[3px]" onClick={() => setSelectedApplication(null)} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
            <motion.aside className="h-full w-full max-w-[560px] overflow-y-auto border-l border-subtle bg-[var(--color-bg)] shadow-[-20px_0_60px_rgba(0,0,0,0.42)]" initial={{ opacity: 0, x: 56 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 56 }} transition={{ type: "spring", damping: 30, stiffness: 340 }}>
              <div className="sticky top-0 z-10 flex items-center justify-between border-b border-subtle bg-[var(--color-bg)] px-6 py-5">
                <div><p className="eyebrow">CANDIDATE DETAILS</p><p id="candidate-detail-title" className="mt-1 text-[15px] font-semibold text-ink-heading">{selectedApplication?.application.candidate_name || "Loading candidate"}</p></div>
                <Button size="sm" variant="ghost" onClick={() => setSelectedApplication(null)}>Close</Button>
              </div>
              {detailLoading || !selectedApplication ? <div className="p-6 text-[13px] text-ink-muted">Loading candidate profile and activity...</div> : <div className="p-6">
                <motion.div className="grid gap-5 border-b border-subtle pb-6 sm:grid-cols-2" initial="hidden" animate="visible" variants={staggerContainer(0.05)}>
                  <DetailCell label="EMAIL" value={selectedApplication.application.candidate_email || "Not available"} />
                  <DetailCell label="CURRENT STAGE" value={selectedApplication.application.current_stage} />
                  <DetailCell label="APPLICATION STATUS" value={selectedApplication.application.status} />
                  <DetailCell label="SOURCE" value={selectedApplication.application.source} />
                  <DetailCell label="APPLIED" value={new Date(selectedApplication.application.created_at).toLocaleString()} />
                </motion.div>
                <section className="mt-7"><p className="eyebrow">PIPELINE ACTIVITY</p><PipelineLifecycle events={selectedApplication.timeline} /></section>
              </div>}
            </motion.aside>
          </motion.dialog>
          )}
        </AnimatePresence>,
        document.body,
        )}

        {typeof document !== "undefined" && referOpen && createPortal(
        <dialog open aria-labelledby="referral-title" className="fixed inset-0 z-[70] flex h-full w-full max-w-none items-center justify-center bg-black/70 p-5"><GlassCard elevation="high" padding="lg" className="w-full max-w-[520px]"><div className="flex items-center justify-between gap-4"><p id="referral-title" className="eyebrow">REFER A CANDIDATE</p><Button size="sm" variant="ghost" onClick={() => setReferOpen(false)}>Close</Button></div><form onSubmit={handleRefer} className="mt-5 flex flex-col gap-4">
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
            <Button type="submit" className="self-start" loading={referring}>
              {referring ? "Sending..." : "Send referral"}
            </Button>
          </form></GlassCard></dialog>,
        document.body,
        )}
      </PageShell>
    </div>
  );
}

function DetailCell({ label, value }: Readonly<{ label: string; value: string }>) {
  return <motion.div variants={staggerItem}><p className="mono text-[10px] tracking-[0.08em] text-ink-subtle">{label}</p><p className="mt-1 text-[13px] text-ink-heading">{value}</p></motion.div>;
}

function PipelineLifecycle({ events }: Readonly<{ events: ApplicationEvent[] }>) {
  if (events.length === 0) return <p className="mt-4 text-[13px] text-ink-muted">No activity recorded yet.</p>;

  return <motion.div initial="hidden" animate="visible" variants={staggerContainer(0.08, 0.1)} className="mt-5">
    {events.map((event, index) => <motion.div key={`${event.event_type}-${event.created_at}`} variants={staggerItem} className="grid grid-cols-[minmax(0,1fr)_28px_minmax(0,1.15fr)] gap-3">
      <div className="pb-7 text-right"><p className="text-[13px] font-semibold capitalize text-ink-heading">{event.event_type.replaceAll("_", " ").toLowerCase()}</p><p className="mt-1 mono text-[10px] text-ink-subtle">{new Date(event.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</p></div>
      <div className="relative flex justify-center">{index < events.length - 1 && <motion.span className="absolute top-5 h-[calc(100%-4px)] w-px bg-[var(--color-success)]/45" initial={{ scaleY: 0 }} animate={{ scaleY: 1 }} transition={{ delay: 0.18 + index * 0.08, duration: 0.32 }} style={{ transformOrigin: "top" }} />}<motion.span className="relative z-10 mt-1 flex h-5 w-5 items-center justify-center rounded-full border border-[var(--color-success)] bg-[rgba(34,197,94,0.14)] text-[11px] font-bold text-[var(--color-success)] shadow-[0_0_18px_rgba(34,197,94,0.22)]" initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 420, damping: 18, delay: 0.12 + index * 0.08 }}>✓</motion.span></div>
      <div className="pb-7"><p className="text-[12px] text-ink-muted">{event.from_stage || "New"} <span className="px-1 text-ink-subtle">to</span> {event.to_stage || "-"}</p><p className="mt-1 text-[11px] text-ink-subtle">{new Date(event.created_at).toLocaleDateString()}</p></div>
    </motion.div>)}
  </motion.div>;
}
