"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Navbar from "../components/Navbar";
import { EmptyState, PageHeader, PageShell, SkeletonList, StatusPill } from "../components/ui";
import { useAuth } from "../../lib/auth-context";
import { api, ApiError } from "../../lib/api";
import { notify } from "../../lib/toast";

type Interview = {
  id: number;
  title: string;
  scheduled_start: string;
  scheduled_end: string;
  timezone: string;
  meeting_url: string;
  status: string;
  posting_title: string;
  org_name: string;
};

export default function InterviewsPage() {
  const router = useRouter();
  const { actor, loading: authLoading } = useAuth();
  const [interviews, setInterviews] = useState<Interview[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (authLoading) return;
    if (!actor) {
      router.push("/login?next=/interviews");
      return;
    }
    api.get<{ interviews: Interview[] }>("/me/interviews")
      .then((data) => setInterviews(data.interviews))
      .catch((error) => notify.error(error instanceof ApiError ? error.detail : "Failed to load interviews."))
      .finally(() => setLoading(false));
  }, [actor, authLoading, router]);

  if (authLoading || loading) {
    return <><Navbar /><PageShell className="!max-w-[760px] pt-[112px]"><SkeletonList count={3} /></PageShell></>;
  }

  return (
    <div className="min-h-screen">
      <Navbar />
      <PageShell className="!max-w-[760px] pt-[112px]">
        <PageHeader eyebrow="INTERVIEWS" title="Your interview agenda" description="Scheduled conversations and meeting details for your applications." />
        <div className="mt-8 flex flex-col gap-3">
          {interviews.length === 0 ? (
            <EmptyState title="No interviews scheduled" description="When a hiring team schedules an interview, it will appear here." />
          ) : interviews.map((interview) => (
            <div key={interview.id} className="glass p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-[15px] font-semibold text-ink-heading">{interview.title}</p>
                  <p className="mt-1 text-[12px] text-ink-subtle">{interview.posting_title} · {interview.org_name}</p>
                </div>
                <StatusPill tone={interview.status === "SCHEDULED" ? "success" : "muted"}>{interview.status}</StatusPill>
              </div>
              <p className="mono mt-4 text-[12px] text-ink-muted">
                {new Date(interview.scheduled_start).toLocaleString()} - {new Date(interview.scheduled_end).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} ({interview.timezone})
              </p>
              {interview.meeting_url && <a className="mt-3 inline-block text-[13px] text-brand hover:underline" href={interview.meeting_url} target="_blank" rel="noreferrer">Join meeting</a>}
            </div>
          ))}
        </div>
      </PageShell>
    </div>
  );
}
