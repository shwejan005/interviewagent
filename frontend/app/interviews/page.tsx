"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Navbar from "../components/Navbar";
import { EmptyState, PageHeader, PageShell, SkeletonList, StatusPill } from "../components/ui";
import type { PillTone } from "../components/ui";
import { useAuth } from "../../lib/auth-context";
import { api, ApiError } from "../../lib/api";
import { notify } from "../../lib/toast";

type AgendaItem = {
  id: number | string;
  application_id?: number;
  kind?: "AI" | "HUMAN";
  title: string;
  scheduled_start: string | null;
  scheduled_end: string | null;
  timezone: string;
  meeting_url: string;
  join_href?: string | null;
  can_join?: boolean;
  room_opens_at?: string | null;
  status: string;
  phase?: string;
  modality?: "TEXT" | "VOICE";
  invitation_expires_at?: string | null;
  updated_at?: string;
  created_at?: string;
  posting_title: string;
  org_name: string;
};

const AI_STATUS_COPY: Record<string, string> = {
  SCREENING_QUEUED: "Your application was received. The automatic minimum-criteria and evidence checks are running; you do not need to schedule anything.",
  SCREENING: "The hiring criteria are being checked. If the evidence passes, the AI interview invitation will become joinable here automatically.",
  INTERVIEW_READY: "Your AI interviewer is ready. Join from this page; no recruiter scheduling step is needed.",
  INTERVIEW_IN_PROGRESS: "Continue your voice interview. Your submitted answers are saved.",
  ANSWER_PROCESSING: "Your answer is saved and being reviewed before the next text question appears.",
  REPORT_PENDING: "Interview complete. Your report is being prepared for the hiring team.",
  REPORT_READY: "Interview complete. Your report is with the hiring team for review.",
  REVIEW_REQUIRED: "The hiring team is reviewing an interview service or evidence issue. This will not be treated as a failed interview.",
};

function statusTone(status: string): PillTone {
  if (status === "SCHEDULED" || status === "INTERVIEW_READY") return "success";
  if (status === "REVIEW_REQUIRED") return "warning";
  return "muted";
}

function AIInterviewAgendaItem({ item }: Readonly<{ item: AgendaItem }>) {
  const joinLabel = item.status === "INTERVIEW_READY" ? "Join AI interview" : "Resume AI interview";
  return (
    <>
      <p className="mt-3 text-[12px] text-ink-muted">{AI_STATUS_COPY[item.status] || "Your AI interview status is available here."}</p>
      {item.can_join && item.join_href && <Link className="btn-primary mt-4 inline-flex no-underline" href={item.join_href}>{joinLabel}</Link>}
      {item.status === "INTERVIEW_READY" && <p className="mt-2 text-[10px] text-ink-subtle">Voice answers · questions shown as text · camera off{item.invitation_expires_at ? ` · join before ${new Date(item.invitation_expires_at).toLocaleString()}` : ""}</p>}
      {item.status === "EXPIRED" && <p className="mt-3 text-[11px] text-[var(--color-warning)]">The invitation window closed. The hiring team can send a new invitation.</p>}
    </>
  );
}

function HumanInterviewAgendaItem({ item, onJoin }: Readonly<{ item: AgendaItem; onJoin: (href: string) => void }>) {
  return (
    <>
      {item.scheduled_start && item.scheduled_end && <p className="mono mt-4 text-[12px] text-ink-muted">{new Date(item.scheduled_start).toLocaleString()} - {new Date(item.scheduled_end).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} ({item.timezone})</p>}
      {item.meeting_url && <a className="mt-3 inline-block text-[13px] text-brand hover:underline" href={item.meeting_url} target="_blank" rel="noreferrer">Join meeting</a>}
      {!item.meeting_url && item.can_join && item.join_href && <button type="button" className="btn-primary mt-4 inline-flex" onClick={() => onJoin(item.join_href!)}>Join in-app interview</button>}
      {!item.meeting_url && !item.can_join && item.status === "SCHEDULED" && <p className="mt-3 text-[11px] text-ink-subtle">In-app room opens 15 minutes before the scheduled start{item.room_opens_at ? ` (${new Date(item.room_opens_at).toLocaleString()})` : ""}.</p>}
      {!item.meeting_url && item.status !== "SCHEDULED" && <p className="mt-3 text-[11px] text-ink-subtle">This interview is not currently joinable.</p>}
    </>
  );
}

function AgendaCard({ item, onJoin }: Readonly<{ item: AgendaItem; onJoin: (href: string) => void }>) {
  const isAI = item.kind === "AI";
  return (
    <div className="glass p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[15px] font-semibold text-ink-heading">{isAI ? "AI interview" : item.title}</p>
            {isAI && <StatusPill tone="primary">AI-LED</StatusPill>}
          </div>
          <p className="mt-1 text-[12px] text-ink-subtle">{item.posting_title} · {item.org_name}</p>
        </div>
        <StatusPill tone={statusTone(item.status)}>{item.status.replaceAll("_", " ")}</StatusPill>
      </div>
      {isAI ? <AIInterviewAgendaItem item={item} /> : <HumanInterviewAgendaItem item={item} onJoin={onJoin} />}
    </div>
  );
}

export default function InterviewsPage() {
  const router = useRouter();
  const { actor, loading: authLoading } = useAuth();
  const [interviews, setInterviews] = useState<AgendaItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (authLoading) return;
    if (!actor) {
      router.push("/login?next=/interviews");
      return;
    }
    api.get<{ interviews: AgendaItem[] }>("/me/interviews")
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
        <PageHeader eyebrow="INTERVIEWS" title="Your interview agenda" description="AI interview invitations and scheduled conversations for your applications. Join an AI interview here as soon as screening is complete." />
        <div className="mt-8 flex flex-col gap-3">
          {interviews.length === 0 ? (
            <EmptyState title="No interviews yet" description="Once your application clears automatic screening, the AI interview invitation will appear here. Human interviews scheduled by the hiring team will appear here too." />
          ) : interviews.map((interview) => <AgendaCard key={`${interview.kind || "HUMAN"}-${interview.id}`} item={interview} onJoin={(href) => router.push(href)} />)}
        </div>
      </PageShell>
    </div>
  );
}
