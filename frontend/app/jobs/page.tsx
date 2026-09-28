"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "../../lib/auth-context";
import { api } from "../../lib/api";
import type { JobPosting, JobRecommendation } from "../../lib/types";
import Navbar from "../components/Navbar";
import {
  Button,
  ButtonLink,
  EmptyState,
  Input,
  PageHeader,
  PageShell,
  SkeletonList,
} from "../components/ui";
import { notify } from "../../lib/toast";

type Tab = "recommended" | "all";

function formatSalary(min: number | null, max: number | null, currency: string): string {
  if (!min && !max) return "Not disclosed";
  const fmt = (n: number) => `${currency} ${(n / 100000).toFixed(1)}L`;
  if (min && max) return `${fmt(min)} – ${fmt(max)}`;
  return fmt((min ?? max) as number);
}

const CARD_CLASS =
  "glass glass-interactive block p-5 no-underline";

function RecommendationCard({ rec }: Readonly<{ rec: JobRecommendation }>) {
  return (
    <Link href={`/jobs/${rec.posting_id}`} className={CARD_CLASS}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-[15px] font-semibold text-ink-heading">{rec.title}</p>
          <p className="mt-1 text-[12px] text-ink-subtle">
            {rec.org_name} · {rec.location} · {rec.remote_policy}
          </p>
        </div>
        <span className="mono shrink-0 text-[17px] font-bold text-brand">{rec.score}/10</span>
      </div>
      <p className="mt-3 text-[13px] leading-[1.65] text-ink-muted">{rec.explanation}</p>
    </Link>
  );
}

function PostingCard({ posting }: Readonly<{ posting: JobPosting }>) {
  return (
    <Link href={`/jobs/${posting.id}`} className={CARD_CLASS}>
      <p className="text-[15px] font-semibold text-ink-heading">{posting.title}</p>
      <p className="mt-1 text-[12px] text-ink-subtle">
        {posting.org_name} · {posting.location} · {posting.remote_policy}
      </p>
      <p className="mono mt-3 text-[12px] text-ink-muted">
        {formatSalary(posting.salary_min, posting.salary_max, posting.currency)}
      </p>
    </Link>
  );
}

interface ResultsProps {
  loading: boolean;
  tab: Tab;
  recommendations: JobRecommendation[];
  postings: JobPosting[];
}

/**
 * Split out of the page so each state is an early return — the original
 * three-level nested ternary was unreadable and tripped the lint rule.
 */
function JobsResults({ loading, tab, recommendations, postings }: Readonly<ResultsProps>) {
  if (loading) return <SkeletonList count={4} />;

  if (tab === "recommended") {
    if (recommendations.length === 0) {
      return (
        <EmptyState
          title="No recommendations yet"
          description="Complete your profile so we can match you against open roles."
          action={<ButtonLink href="/profile">Complete your profile</ButtonLink>}
        />
      );
    }
    return <RecommendationTable recommendations={recommendations} />;
  }

  if (postings.length === 0) {
    return (
      <EmptyState
        title="No open roles match your search"
        description="Try a broader keyword, or clear the location filter."
      />
    );
  }

  return <PostingTable postings={postings} />;
}

function RecommendationTable({ recommendations }: Readonly<{ recommendations: JobRecommendation[] }>) {
  return (
    <div className="overflow-x-auto border border-subtle bg-[rgba(17,18,30,0.74)]">
      <table className="w-full min-w-[700px] border-collapse text-left">
        <thead className="border-b border-subtle bg-[rgba(255,255,255,0.025)]"><tr className="mono text-[10px] tracking-[0.08em] text-ink-subtle"><th className="px-5 py-3">ROLE</th><th className="px-5 py-3">COMPANY</th><th className="px-5 py-3">LOCATION</th><th className="px-5 py-3">MATCH</th><th className="px-5 py-3">WHY IT FITS</th></tr></thead>
        <tbody>{recommendations.map((rec) => <tr key={rec.posting_id} className="border-b border-subtle last:border-0 hover:bg-[rgba(255,255,255,0.025)]"><td className="px-5 py-4"><Link href={`/jobs/${rec.posting_id}`} className="text-[13px] font-semibold text-ink-heading no-underline hover:text-brand">{rec.title}</Link></td><td className="px-5 py-4 text-[12px] text-ink-muted">{rec.org_name}</td><td className="px-5 py-4 text-[12px] text-ink-muted">{rec.location} · {rec.remote_policy}</td><td className="mono px-5 py-4 text-[14px] font-bold text-brand">{rec.score}/10</td><td className="max-w-[260px] px-5 py-4 text-[12px] leading-[1.5] text-ink-muted">{rec.explanation}</td></tr>)}</tbody>
      </table>
    </div>
  );
}

function PostingTable({ postings }: Readonly<{ postings: JobPosting[] }>) {
  return (
    <div className="overflow-x-auto border border-subtle bg-[rgba(17,18,30,0.74)]">
      <table className="w-full min-w-[700px] border-collapse text-left">
        <thead className="border-b border-subtle bg-[rgba(255,255,255,0.025)]"><tr className="mono text-[10px] tracking-[0.08em] text-ink-subtle"><th className="px-5 py-3">ROLE</th><th className="px-5 py-3">COMPANY</th><th className="px-5 py-3">LOCATION</th><th className="px-5 py-3">WORK MODEL</th><th className="px-5 py-3">COMPENSATION</th></tr></thead>
        <tbody>{postings.map((posting) => <tr key={posting.id} className="border-b border-subtle last:border-0 hover:bg-[rgba(255,255,255,0.025)]"><td className="px-5 py-4"><Link href={`/jobs/${posting.id}`} className="text-[13px] font-semibold text-ink-heading no-underline hover:text-brand">{posting.title}</Link></td><td className="px-5 py-4 text-[12px] text-ink-muted">{posting.org_name}</td><td className="px-5 py-4 text-[12px] text-ink-muted">{posting.location}</td><td className="px-5 py-4 text-[12px] text-ink-muted">{posting.remote_policy}</td><td className="mono px-5 py-4 text-[12px] text-ink-muted">{formatSalary(posting.salary_min, posting.salary_max, posting.currency)}</td></tr>)}</tbody>
      </table>
    </div>
  );
}

export default function JobsPage() {
  const { actor, loading: authLoading } = useAuth();
  const [tab, setTab] = useState<Tab>("all");
  const [postings, setPostings] = useState<JobPosting[]>([]);
  const [recommendations, setRecommendations] = useState<JobRecommendation[]>([]);
  const [query, setQuery] = useState("");
  const [location, setLocation] = useState("");
  const [loading, setLoading] = useState(true);

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
    try {
      const params = new URLSearchParams();
      if (query.trim()) params.set("q", query.trim());
      if (location.trim()) params.set("location", location.trim());
      const data = await api.get<{ postings: JobPosting[] }>(`/jobs?${params.toString()}`);
      setPostings(data.postings);
    } catch {
      notify.error("Failed to load jobs.");
    } finally {
      setLoading(false);
    }
  };

  const loadRecommendations = async () => {
    setLoading(true);
    try {
      const data = await api.get<{ recommendations: JobRecommendation[] }>("/me/recommended-jobs");
      setRecommendations(data.recommendations);
    } catch {
      notify.error("Failed to load recommendations.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen">
      <Navbar />
      <PageShell className="!max-w-[820px] pt-[112px]">
        <PageHeader eyebrow="JOB BOARD" title="Find your next role" />

        {actor && (
          <div className="mt-8 flex gap-2">
            <Button
              size="sm"
              variant={tab === "recommended" ? "primary" : "secondary"}
              onClick={() => setTab("recommended")}
            >
              Recommended for you
            </Button>
            <Button
              size="sm"
              variant={tab === "all" ? "primary" : "secondary"}
              onClick={() => setTab("all")}
            >
              Browse all
            </Button>
          </div>
        )}

        {tab === "all" && (
          <div className="mt-6 flex flex-wrap items-end gap-3">
            <Input
              wrapperClassName="min-w-[220px] flex-[2]"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && searchJobs()}
              placeholder="Search titles or descriptions..."
              aria-label="Search titles or descriptions"
            />
            <Input
              wrapperClassName="min-w-[150px] flex-1"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && searchJobs()}
              placeholder="Location"
              aria-label="Location"
            />
            <Button variant="secondary" onClick={searchJobs}>
              Search
            </Button>
          </div>
        )}

        <div className="mt-8">
          <JobsResults
            loading={loading}
            tab={tab}
            recommendations={recommendations}
            postings={postings}
          />
        </div>
      </PageShell>
    </div>
  );
}
