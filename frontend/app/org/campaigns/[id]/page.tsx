"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import { Plus, Users } from "lucide-react";

import Navbar from "../../../components/Navbar";
import {
  Button,
  EmptyState,
  GlassCard,
  Input,
  Modal,
  PageShell,
  Select,
  SkeletonList,
  StatusPill,
  Textarea,
} from "../../../components/ui";
import type { PillTone } from "../../../components/ui";
import { useAuth } from "../../../../lib/auth-context";
import { api, ApiError } from "../../../../lib/api";
import { notify } from "../../../../lib/toast";
import type { Campaign, JobPosting } from "../../../../lib/types";
import { staggerContainer, staggerItem } from "../../../../lib/motion";

const POSTING_TONE: Record<string, PillTone> = {
  PUBLISHED: "success",
  CLOSED: "muted",
  DRAFT: "warning",
};

type PostingFormState = {
  title: string;
  description: string;
  location: string;
  employment_type: string;
  remote_policy: string;
  min_experience: string;
  max_experience: string;
  salary_min: string;
  salary_max: string;
  required_skills: string;
};

const EMPTY_POSTING_FORM: PostingFormState = {
  title: "",
  description: "",
  location: "",
  employment_type: "FULL_TIME",
  remote_policy: "ONSITE",
  min_experience: "",
  max_experience: "",
  salary_min: "",
  salary_max: "",
  required_skills: "",
};

function CreatePostingModal({
  open,
  onClose,
  orgId,
  campaignId,
  onCreated,
}: Readonly<{ open: boolean; onClose: () => void; orgId: number; campaignId: number; onCreated: () => Promise<void> }>) {
  const [form, setForm] = useState<PostingFormState>(EMPTY_POSTING_FORM);
  const [saving, setSaving] = useState(false);

  const set = <K extends keyof PostingFormState>(key: K, value: PostingFormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post(`/orgs/${orgId}/postings`, {
        campaign_id: campaignId,
        title: form.title,
        description: form.description,
        location: form.location,
        employment_type: form.employment_type,
        remote_policy: form.remote_policy,
        min_experience: form.min_experience ? Number(form.min_experience) : null,
        max_experience: form.max_experience ? Number(form.max_experience) : null,
        salary_min: form.salary_min ? Number(form.salary_min) : null,
        salary_max: form.salary_max ? Number(form.salary_max) : null,
        required_skills: form.required_skills
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      });
      setForm(EMPTY_POSTING_FORM);
      await onCreated();
      onClose();
      notify.success("Role created.");
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to create role.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} titleId="create-posting-title" maxWidthClassName="max-w-[640px]">
      <GlassCard elevation="high" padding="lg" className="max-h-[85vh] overflow-y-auto">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="eyebrow">NEW ROLE</p>
            <p id="create-posting-title" className="mt-1 text-[17px] font-semibold text-ink-heading">
              Add a role to this campaign
            </p>
          </div>
          <Button size="sm" variant="ghost" onClick={onClose}>Close</Button>
        </div>

        <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
          <Input
            label="ROLE TITLE"
            placeholder="Senior Backend Engineer"
            required
            value={form.title}
            onChange={(e) => set("title", e.target.value)}
          />
          <Textarea
            rows={4}
            label="DESCRIPTION"
            placeholder="Responsibilities, requirements, and what makes this role compelling."
            value={form.description}
            onChange={(e) => set("description", e.target.value)}
          />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Input
              label="LOCATION"
              placeholder="Bengaluru, India"
              value={form.location}
              onChange={(e) => set("location", e.target.value)}
            />
            <Select
              label="EMPLOYMENT TYPE"
              value={form.employment_type}
              onChange={(e) => set("employment_type", e.target.value)}
            >
              <option value="FULL_TIME">Full-time</option>
              <option value="PART_TIME">Part-time</option>
              <option value="CONTRACT">Contract</option>
              <option value="INTERNSHIP">Internship</option>
            </Select>
            <Select
              label="WORK MODEL"
              value={form.remote_policy}
              onChange={(e) => set("remote_policy", e.target.value)}
            >
              <option value="ONSITE">Onsite</option>
              <option value="HYBRID">Hybrid</option>
              <option value="REMOTE">Remote</option>
            </Select>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
            <Input
              type="number"
              min={0}
              label="MIN EXP (YRS)"
              value={form.min_experience}
              onChange={(e) => set("min_experience", e.target.value)}
            />
            <Input
              type="number"
              min={0}
              label="MAX EXP (YRS)"
              value={form.max_experience}
              onChange={(e) => set("max_experience", e.target.value)}
            />
            <Input
              type="number"
              min={0}
              label="SALARY MIN"
              value={form.salary_min}
              onChange={(e) => set("salary_min", e.target.value)}
            />
            <Input
              type="number"
              min={0}
              label="SALARY MAX"
              value={form.salary_max}
              onChange={(e) => set("salary_max", e.target.value)}
            />
          </div>
          <Input
            label="REQUIRED SKILLS"
            placeholder="Python, PostgreSQL, System Design"
            hint="Comma-separated. Used for candidate matching."
            value={form.required_skills}
            onChange={(e) => set("required_skills", e.target.value)}
          />

          <Button type="submit" className="self-start" loading={saving} disabled={!form.title.trim()}>
            {saving ? "Creating..." : "Create role"}
          </Button>
        </form>
      </GlassCard>
    </Modal>
  );
}

function PostingCard({
  posting,
  onPublish,
}: Readonly<{ posting: JobPosting; onPublish: (id: number, status: string) => Promise<void> }>) {
  return (
    <motion.div variants={staggerItem} whileHover={{ y: -4 }} className="glass p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <Link
            href={`/org/postings/${posting.id}`}
            className="truncate text-[15px] font-semibold text-ink-heading no-underline hover:text-brand"
          >
            {posting.title}
          </Link>
          <p className="mt-1 text-[12px] text-ink-subtle">{posting.location || "Location not set"} · {posting.remote_policy}</p>
        </div>
        <StatusPill tone={POSTING_TONE[posting.status] ?? "muted"}>{posting.status}</StatusPill>
      </div>

      <div className="mt-5 flex items-center gap-2 text-[13px] text-ink-muted">
        <Users size={14} className="text-brand" />
        <span className="font-semibold text-ink-heading">{posting.applicant_count ?? 0}</span> applicants
      </div>

      <div className="mt-5 flex items-center gap-2 border-t border-subtle pt-4">
        <Link href={`/org/postings/${posting.id}`} className="btn-secondary !px-3 !py-1.5 !text-[12px] no-underline">
          Manage pipeline
        </Link>
        {posting.status === "DRAFT" && (
          <Button size="sm" variant="ghost" onClick={() => onPublish(posting.id, "PUBLISHED")}>Publish</Button>
        )}
        {posting.status === "PUBLISHED" && (
          <Button size="sm" variant="ghost" onClick={() => onPublish(posting.id, "CLOSED")}>Close</Button>
        )}
      </div>
    </motion.div>
  );
}

export default function CampaignDetailPage() {
  const params = useParams();
  const router = useRouter();
  const campaignId = Number(params.id);
  const { actor, loading: authLoading, activeOrgId } = useAuth();

  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [postings, setPostings] = useState<JobPosting[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  useEffect(() => {
    if (authLoading) return;
    if (!actor) {
      router.push("/login?next=/org");
      return;
    }
    if (!activeOrgId) return;
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, actor, activeOrgId, campaignId]);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [campaignData, postingsData] = await Promise.all([
        api.get<Campaign>(`/orgs/${activeOrgId}/campaigns/${campaignId}`),
        api.get<{ postings: JobPosting[] }>(`/orgs/${activeOrgId}/postings?campaign_id=${campaignId}`),
      ]);
      setCampaign(campaignData);
      setPostings(postingsData.postings);
    } catch (err) {
      const message = err instanceof ApiError ? err.detail : "Failed to load campaign.";
      setError(message);
      notify.error(message);
    } finally {
      setLoading(false);
    }
  };

  const handlePublish = async (postingId: number, status: string) => {
    try {
      await api.post(`/orgs/${activeOrgId}/postings/${postingId}/status`, { status });
      await load();
      notify.success(status === "PUBLISHED" ? "Role published." : "Role closed.");
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to update role status.");
    }
  };

  if (authLoading || loading) {
    return (
      <div className="min-h-screen">
        <Navbar />
        <PageShell className="!max-w-[1180px] pt-[112px]">
          <SkeletonList count={4} />
        </PageShell>
      </div>
    );
  }

  if (!campaign) {
    return (
      <div className="min-h-screen">
        <Navbar />
        <PageShell className="!max-w-[1180px] pt-[112px]">
          <EmptyState title="Campaign unavailable" description={error || "We couldn't find that campaign."} />
        </PageShell>
      </div>
    );
  }

  const totalApplicants = postings.reduce((sum, p) => sum + (p.applicant_count ?? 0), 0);

  return (
    <div className="min-h-screen">
      <Navbar />
      <PageShell className="!max-w-[1180px] pt-[112px]">
        <Link href="/org" className="mono text-[11px] tracking-[0.08em] text-ink-subtle no-underline hover:text-brand">
          ← BACK TO CAMPAIGNS
        </Link>

        <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-[26px] font-bold tracking-normal text-ink-heading">{campaign.name}</h1>
            <p className="mt-1 text-[12px] text-ink-subtle">
              {campaign.department || "No department"}
              {campaign.hiring_manager && ` · Hiring manager: ${campaign.hiring_manager}`}
            </p>
            {campaign.description && <p className="mt-3 max-w-[640px] text-[13px] leading-[1.6] text-ink-muted">{campaign.description}</p>}
          </div>
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus size={15} /> Add a role
          </Button>
        </div>

        <motion.div initial="hidden" animate="visible" variants={staggerContainer(0.06)} className="mt-8 flex flex-wrap gap-3">
          <motion.div variants={staggerItem}><StatusPill tone="muted">ROLES: {postings.length}</StatusPill></motion.div>
          <motion.div variants={staggerItem}><StatusPill tone="primary">APPLICANTS: {totalApplicants}</StatusPill></motion.div>
          {campaign.target_hires && <motion.div variants={staggerItem}><StatusPill tone="success">TARGET HIRES: {campaign.target_hires}</StatusPill></motion.div>}
          {campaign.target_close_date && (
            <motion.div variants={staggerItem}>
              <StatusPill tone="warning">TARGET DATE: {new Date(campaign.target_close_date).toLocaleDateString()}</StatusPill>
            </motion.div>
          )}
        </motion.div>

        <div className="mt-8">
          {postings.length === 0 ? (
            <EmptyState
              title="No roles yet"
              description="Add the first role to this campaign to start collecting applicants."
              action={<Button onClick={() => setCreateOpen(true)}>Add a role</Button>}
            />
          ) : (
            <motion.div
              initial="hidden"
              animate="visible"
              variants={staggerContainer(0.06)}
              className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
            >
              {postings.map((posting) => (
                <PostingCard key={posting.id} posting={posting} onPublish={handlePublish} />
              ))}
            </motion.div>
          )}
        </div>

        {activeOrgId && (
          <CreatePostingModal
            open={createOpen}
            onClose={() => setCreateOpen(false)}
            orgId={activeOrgId}
            campaignId={campaignId}
            onCreated={load}
          />
        )}
      </PageShell>
    </div>
  );
}
