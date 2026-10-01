"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import Navbar from "../components/Navbar";
import {
  Button,
  ButtonLink,
  EmptyState,
  PageHeader,
  PageShell,
  SkeletonList,
  StatusPill,
} from "../components/ui";
import type { PillTone } from "../components/ui";
import { useAuth } from "../../lib/auth-context";
import { api, ApiError } from "../../lib/api";
import { notify } from "../../lib/toast";
import type { ApplicationDetail, ApplicationEvent, ApplicationSummary } from "../../lib/types";
import { EASE_OUT, staggerContainer, staggerItem } from "../../lib/motion";

const STAGE_TONE: Record<string, PillTone> = {
  APPLIED: "primary",
  SCREENING: "primary",
  AI_INTERVIEW: "primary",
  PENDING_REVIEW: "warning",
  TECHNICAL: "primary",
  BEHAVIORAL: "primary",
  INTERVIEW: "primary",
  OFFER: "success",
  HIRED: "success",
  REJECTED: "error",
  WITHDRAWN: "muted",
};

/** Stages where the application is finished and withdrawal is meaningless. */
const TERMINAL_STAGES = new Set(["WITHDRAWN", "REJECTED", "HIRED"]);

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

  useEffect(() => {
    if (authLoading) return;
    if (!actor) {
      router.push("/login?next=/applications");
      return;
    }
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, actor]);

  const load = async () => {
    setLoading(true);
    try {
      const data = await api.get<{ applications: ApplicationSummary[] }>("/me/applications");
      setApplications(data.applications);
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to load applications.");
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
      notify.success("Application withdrawn.");
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to withdraw.");
    }
  };

  if (authLoading || loading) {
    return (
      <div className="min-h-screen">
        <Navbar />
        <PageShell className="!max-w-[760px] pt-[112px]">
          <SkeletonList count={4} />
        </PageShell>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Navbar />
      <PageShell className="!max-w-[760px] pt-[112px]">
        <PageHeader eyebrow="APPLICATION TRACKER" title="Your applications" />

        <div className="mt-8">
          {applications.length === 0 ? (
            <EmptyState
              title="No applications yet"
              description="Once you apply to a role it shows up here, with its live pipeline stage."
              action={<ButtonLink href="/jobs">Browse jobs</ButtonLink>}
            />
          ) : (
            <motion.div
              initial="hidden"
              animate="visible"
              variants={staggerContainer(0.05)}
              className="flex flex-col gap-3"
            >
              {applications.map((app) => {
                const open = expanded === app.id;
                return (
                  <motion.div key={app.id} variants={staggerItem} className="glass overflow-hidden">
                    <button
                      type="button"
                      onClick={() => toggleExpand(app.id)}
                      aria-expanded={open}
                      className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left transition-colors duration-fast ease-out-expo hover:bg-glass-low"
                    >
                      <span className="min-w-0">
                        <span className="block text-[14px] font-semibold text-ink-heading">
                          {app.posting_title}
                        </span>
                        <span className="mt-0.5 block text-[12px] text-ink-subtle">
                          {app.org_name} · Applied {formatDate(app.created_at)}
                        </span>
                        {app.ai_interview_status && (
                          <span className="mt-1 block text-[11px] text-ink-muted">
                            AI interview: {app.ai_interview_status.replaceAll("_", " ").toLowerCase()}
                          </span>
                        )}
                      </span>
                      <StatusPill tone={STAGE_TONE[app.current_stage] ?? "muted"}>
                        {app.current_stage}
                      </StatusPill>
                    </button>

                    <AnimatePresence initial={false}>
                      {open && (
                        <motion.div
                          initial={{ opacity: 0, y: -6 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, y: -6 }}
                          transition={{ duration: 0.2, ease: EASE_OUT }}
                        >
                          <div className="border-t border-subtle px-5 pb-5 pt-4">
                            {app.ai_interview_status === "INTERVIEW_READY" && (
                              <Link href={`/ai-interview/${app.id}`} className="btn-primary mb-5 inline-flex no-underline">
                                Start AI interview
                              </Link>
                            )}
                            {["INTERVIEW_IN_PROGRESS", "ANSWER_PROCESSING"].includes(app.ai_interview_status || "") && (
                              <Link href={`/ai-interview/${app.id}`} className="btn-primary mb-5 inline-flex no-underline">
                                Continue AI interview
                              </Link>
                            )}
                            {detail && (
                              <>
                                <p className="mono text-[10px] tracking-[0.08em] text-ink-subtle">TIMELINE</p>
                                <ol className="mt-3 flex flex-col gap-2">
                                  {detail.timeline.map((event, i) => (
                                    <li
                                      key={`${event.event_type}-${i}`}
                                      className="flex gap-3 text-[12px] text-ink-muted"
                                    >
                                      <span className="mono shrink-0 text-ink-subtle">
                                        {formatDate(event.created_at)}
                                      </span>
                                      <span>{event.to_stage || event.event_type}</span>
                                    </li>
                                  ))}
                                </ol>
                              </>
                            )}
                            {!TERMINAL_STAGES.has(app.current_stage) && (
                              <Button
                                className="mt-5"
                                size="sm"
                                variant="secondary"
                                onClick={() => handleWithdraw(app.id)}
                              >
                                Withdraw application
                              </Button>
                            )}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </motion.div>
                );
              })}
            </motion.div>
          )}
        </div>
      </PageShell>
    </div>
  );
}
