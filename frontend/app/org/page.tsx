"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import Navbar from "../components/Navbar";
import {
  Alert,
  Button,
  ButtonLink,
  EmptyState,
  GlassCard,
  Input,
  PageHeader,
  PageShell,
  SkeletonList,
  StatusPill,
} from "../components/ui";
import type { PillTone } from "../components/ui";
import { useAuth } from "../../lib/auth-context";
import { api, ApiError } from "../../lib/api";
import type { Campaign, JobPosting } from "../../lib/types";
import { staggerContainer, staggerItem } from "../../lib/motion";

const POSTING_TONE: Record<string, PillTone> = {
  PUBLISHED: "success",
  CLOSED: "muted",
  DRAFT: "warning",
};

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

function CreateOrgForm({ onCreated }: Readonly<{ onCreated: () => void }>) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api.post("/orgs", { name, slug });
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to create organization.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <GlassCard elevation="high" padding="lg" className="max-w-[480px]">
      <p className="eyebrow">CREATE AN ORGANIZATION</p>
      <form onSubmit={handleSubmit} className="mt-5 flex flex-col gap-4">
        <Input
          label="COMPANY NAME"
          placeholder="Acme Robotics"
          value={name}
          onChange={(e) => {
            setName(e.target.value);
            if (!slug) setSlug(slugify(e.target.value));
          }}
        />
        <Input
          label="URL SLUG"
          placeholder="acme-robotics"
          hint="Used in your public careers URL."
          value={slug}
          onChange={(e) => setSlug(e.target.value)}
        />
        {error && <Alert tone="error">{error}</Alert>}
        <Button type="submit" className="self-start" loading={saving} disabled={!name || !slug}>
          {saving ? "Creating..." : "Create organization"}
        </Button>
      </form>
    </GlassCard>
  );
}

export default function OrgHomePage() {
  const router = useRouter();
  const { actor, loading: authLoading, activeOrgId, refreshActor } = useAuth();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [postingsByCampaign, setPostingsByCampaign] = useState<Record<number, JobPosting[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newCampaignName, setNewCampaignName] = useState("");
  const [creatingCampaign, setCreatingCampaign] = useState(false);

  useEffect(() => {
    if (authLoading) return;
    if (!actor) {
      router.push("/login?next=/org");
      return;
    }
    if (activeOrgId) loadCampaigns();
    else setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, actor, activeOrgId]);

  const loadCampaigns = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get<{ campaigns: Campaign[] }>(`/orgs/${activeOrgId}/campaigns`);
      setCampaigns(data.campaigns);
      const postings: Record<number, JobPosting[]> = {};
      await Promise.all(
        data.campaigns.map(async (c) => {
          const res = await api.get<{ postings: JobPosting[] }>(`/orgs/${activeOrgId}/postings?campaign_id=${c.id}`);
          postings[c.id] = res.postings;
        }),
      );
      setPostingsByCampaign(postings);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load campaigns.");
    } finally {
      setLoading(false);
    }
  };

  const handleCreateCampaign = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newCampaignName.trim()) return;
    setCreatingCampaign(true);
    try {
      await api.post(`/orgs/${activeOrgId}/campaigns`, { name: newCampaignName.trim() });
      setNewCampaignName("");
      await loadCampaigns();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to create campaign.");
    } finally {
      setCreatingCampaign(false);
    }
  };

  const handleCreatePosting = async (campaignId: number, title: string) => {
    if (!title.trim()) return;
    try {
      await api.post(`/orgs/${activeOrgId}/postings`, { campaign_id: campaignId, title: title.trim() });
      await loadCampaigns();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to create posting.");
    }
  };

  const handlePublish = async (postingId: number, status: string) => {
    try {
      await api.post(`/orgs/${activeOrgId}/postings/${postingId}/status`, { status });
      await loadCampaigns();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to update posting status.");
    }
  };

  if (authLoading) return null;

  if (actor?.memberships.length === 0) {
    return (
      <div className="min-h-screen">
        <Navbar />
        <PageShell className="!max-w-[760px] pt-[112px]">
          <PageHeader
            eyebrow="WELCOME TO EVALIA"
            title="Recruiter workspace"
            description="You're not part of an organization yet. Create one to start posting jobs and reviewing applicants. This workspace is separate from candidate job-seeking — the same login can do both, but they don't affect each other."
          />
          <div className="mt-8">
            <CreateOrgForm onCreated={() => refreshActor()} />
          </div>
        </PageShell>
      </div>
    );
  }

  if (!activeOrgId) {
    return (
      <div className="min-h-screen">
        <Navbar />
        <PageShell className="!max-w-[760px] pt-[112px]">
          <PageHeader
            eyebrow="RECRUITER WORKSPACE"
            title="Select an organization"
            description="Use the organization switcher in the top navigation bar to choose a workspace."
          />
        </PageShell>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Navbar />
      <PageShell className="!max-w-[820px] pt-[112px]">
        <PageHeader
          eyebrow="RECRUITER WORKSPACE"
          title="Campaigns"
          actions={
            <ButtonLink href="/org/analytics" variant="secondary" size="sm">
              Analytics
            </ButtonLink>
          }
        />

        {error && (
          <Alert tone="error" className="mt-6">
            {error}
          </Alert>
        )}

        <form onSubmit={handleCreateCampaign} className="mt-8 flex flex-wrap items-center gap-3">
          <Input
            wrapperClassName="min-w-[240px] flex-1"
            aria-label="New campaign name"
            placeholder="New campaign name (e.g. Q4 Backend Expansion)"
            value={newCampaignName}
            onChange={(e) => setNewCampaignName(e.target.value)}
          />
          <Button type="submit" loading={creatingCampaign} disabled={!newCampaignName.trim()}>
            Create campaign
          </Button>
        </form>

        <div className="mt-8">
          <CampaignList
            loading={loading}
            campaigns={campaigns}
            postingsByCampaign={postingsByCampaign}
            onPublish={handlePublish}
            onCreatePosting={handleCreatePosting}
          />
        </div>
      </PageShell>
    </div>
  );
}

type CampaignListProps = {
  loading: boolean;
  campaigns: Campaign[];
  postingsByCampaign: Record<number, JobPosting[]>;
  onPublish: (postingId: number, status: string) => Promise<void>;
  onCreatePosting: (campaignId: number, title: string) => Promise<void>;
};

function CampaignList({
  loading,
  campaigns,
  postingsByCampaign,
  onPublish,
  onCreatePosting,
}: Readonly<CampaignListProps>) {
  if (loading) return <SkeletonList count={3} />;

  if (campaigns.length === 0) {
    return (
      <EmptyState
        title="No campaigns yet"
        description="A campaign groups related roles — create one above, then add postings to it."
      />
    );
  }

  return (
    <motion.div
      initial="hidden"
      animate="visible"
      variants={staggerContainer(0.06)}
      className="flex flex-col gap-4"
    >
      {campaigns.map((campaign) => (
        <motion.div key={campaign.id} variants={staggerItem}>
          <GlassCard>
            <p className="text-[15px] font-semibold text-ink-heading">{campaign.name}</p>
            <div className="mt-3">
              {(postingsByCampaign[campaign.id] || []).map((posting) => (
                <div
                  key={posting.id}
                  className="flex flex-wrap items-center justify-between gap-3 border-b border-subtle py-3"
                >
                  <Link
                    href={`/org/postings/${posting.id}`}
                    className="text-[13px] text-ink-heading no-underline transition-colors duration-fast ease-out-expo hover:text-brand"
                  >
                    {posting.title}
                  </Link>
                  <div className="flex items-center gap-2">
                    <StatusPill tone={POSTING_TONE[posting.status] ?? "muted"}>
                      {posting.status}
                    </StatusPill>
                    {posting.status === "DRAFT" && (
                      <Button size="sm" variant="ghost" onClick={() => onPublish(posting.id, "PUBLISHED")}>
                        Publish
                      </Button>
                    )}
                    {posting.status === "PUBLISHED" && (
                      <Button size="sm" variant="ghost" onClick={() => onPublish(posting.id, "CLOSED")}>
                        Close
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
            <NewPostingRow campaignId={campaign.id} onCreate={onCreatePosting} />
          </GlassCard>
        </motion.div>
      ))}
    </motion.div>
  );
}

function NewPostingRow({
  campaignId,
  onCreate,
}: Readonly<{ campaignId: number; onCreate: (campaignId: number, title: string) => Promise<void> }>) {
  const [title, setTitle] = useState("");
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    await onCreate(campaignId, title);
    setTitle("");
    setSaving(false);
  };

  return (
    <form onSubmit={handleSubmit} className="mt-4 flex flex-wrap items-center gap-2">
      <Input
        wrapperClassName="min-w-[200px] flex-1"
        aria-label="New posting title"
        placeholder="New posting title"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />
      <Button type="submit" size="sm" variant="secondary" loading={saving} disabled={!title.trim()}>
        Add posting
      </Button>
    </form>
  );
}
