"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { useAuth } from "../../lib/auth-context";
import { api } from "../../lib/api";
import type { JobPosting, JobRecommendation } from "../../lib/types";
import Navbar from "../components/Navbar";
import {
  Alert,
  Button,
  ButtonLink,
  EmptyState,
  Input,
  PageHeader,
  PageShell,
  SkeletonList,
} from "../components/ui";
import { staggerContainer, staggerItem } from "../../lib/motion";

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
    return (
      <motion.div
        initial="hidden"
        animate="visible"
        variants={staggerContainer(0.05)}
        className="flex flex-col gap-3"
      >
        {recommendations.map((rec) => (
          <motion.div key={rec.posting_id} variants={staggerItem}>
            <RecommendationCard rec={rec} />
          </motion.div>
        ))}
      </motion.div>
    );
  }

  if (postings.length === 0) {
    return (
      <EmptyState
        title="No open roles match your search"
        description="Try a broader keyword, or clear the location filter."
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
      {postings.map((posting) => (
        <motion.div key={posting.id} variants={staggerItem}>
          <PostingCard posting={posting} />
        </motion.div>
      ))}
    </motion.div>
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

        {error && (
          <Alert tone="error" className="mt-6">
            {error}
          </Alert>
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
