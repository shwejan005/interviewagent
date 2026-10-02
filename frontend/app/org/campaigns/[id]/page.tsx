"use client";

import { useEffect, useState } from "react";
import { usePathname, useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import { Pencil, Plus, RotateCcw, Trash2, Users, X } from "lucide-react";

import Navbar from "../../../components/Navbar";
import {
  Button,
  ConfirmActionModal,
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
import { useActivePageRefresh } from "../../../../lib/use-active-page-refresh";
import { api, ApiError } from "../../../../lib/api";
import { notify } from "../../../../lib/toast";
import type { Campaign, JobPosting, ScreeningQuestion } from "../../../../lib/types";
import { staggerContainer, staggerItem } from "../../../../lib/motion";

const POSTING_TONE: Record<string, PillTone> = {
  PUBLISHED: "success",
  CLOSED: "muted",
  DRAFT: "warning",
};

type PostingView = "OPEN" | "CLOSED" | "ARCHIVED";

type PostingFormState = {
  title: string;
  description: string;
  location: string;
  employment_type: string;
  remote_policy: string;
  currency: string;
  min_experience: string;
  max_experience: string;
  salary_min: string;
  salary_max: string;
  required_skills: string;
  screening_questions: ScreeningQuestion[];
};

const EMPTY_POSTING_FORM: PostingFormState = {
  title: "",
  description: "",
  location: "",
  employment_type: "FULL_TIME",
  remote_policy: "ONSITE",
  currency: "INR",
  min_experience: "",
  max_experience: "",
  salary_min: "",
  salary_max: "",
  required_skills: "",
  screening_questions: [],
};

function postingSubmitLabel(isEditing: boolean, saving: boolean): string {
  if (isEditing) return saving ? "Saving..." : "Save changes";
  return saving ? "Creating..." : "Create role";
}

function postingToForm(posting: JobPosting | null): PostingFormState {
  if (!posting) return { ...EMPTY_POSTING_FORM, screening_questions: [] };
  return {
    title: posting.title,
    description: posting.description,
    location: posting.location,
    employment_type: posting.employment_type,
    remote_policy: posting.remote_policy,
    currency: posting.currency,
    min_experience: posting.min_experience?.toString() ?? "",
    max_experience: posting.max_experience?.toString() ?? "",
    salary_min: posting.salary_min?.toString() ?? "",
    salary_max: posting.salary_max?.toString() ?? "",
    required_skills: posting.required_skills.join(", "),
    screening_questions: posting.screening_questions.map((question) => ({ ...question })),
  };
}

function PostingFormModal({
  open,
  onClose,
  orgId,
  campaignId,
  posting,
  onSaved,
}: Readonly<{
  open: boolean;
  onClose: () => void;
  orgId: number;
  campaignId: number;
  posting: JobPosting | null;
  onSaved: () => Promise<void>;
}>) {
  const [form, setForm] = useState<PostingFormState>(EMPTY_POSTING_FORM);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) setForm(postingToForm(posting));
  }, [open, posting]);

  const set = <K extends keyof PostingFormState>(key: K, value: PostingFormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const updateQuestion = (index: number, patch: Partial<ScreeningQuestion>) => {
    set("screening_questions", form.screening_questions.map((question, itemIndex) =>
      itemIndex === index ? { ...question, ...patch } : question,
    ));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        title: form.title,
        description: form.description,
        location: form.location,
        employment_type: form.employment_type,
        remote_policy: form.remote_policy,
        currency: form.currency,
        min_experience: form.min_experience ? Number(form.min_experience) : null,
        max_experience: form.max_experience ? Number(form.max_experience) : null,
        salary_min: form.salary_min ? Number(form.salary_min) : null,
        salary_max: form.salary_max ? Number(form.salary_max) : null,
        required_skills: form.required_skills
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        screening_questions: form.screening_questions.filter((question) => question.text.trim()).map((question) => ({
          ...question,
          key: question.key.trim(),
          text: question.text.trim(),
        })),
      };
      if (posting) {
        await api.patch(`/orgs/${orgId}/postings/${posting.id}`, payload);
      } else {
        await api.post(`/orgs/${orgId}/postings`, { campaign_id: campaignId, ...payload });
      }
      await onSaved();
      onClose();
      notify.success(posting ? "Role updated. Existing applications keep their submitted snapshot." : "Role created.");
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to create role.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} titleId="posting-form-title" maxWidthClassName="max-w-[680px]">
      <GlassCard elevation="high" padding="lg" className="max-h-[85vh] overflow-y-auto">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="eyebrow">{posting ? "EDIT ROLE" : "NEW ROLE"}</p>
            <p id="posting-form-title" className="mt-1 text-[17px] font-semibold text-ink-heading">
              {posting ? "Update this job posting" : "Add a role to this campaign"}
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
            <Input
              label="CURRENCY"
              maxLength={8}
              placeholder="INR"
              value={form.currency}
              onChange={(e) => set("currency", e.target.value.toUpperCase())}
            />
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

          <section className="border-t border-subtle pt-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="eyebrow">APPLICATION QUESTIONS</p>
                <p className="mt-1 text-[11px] text-ink-subtle">Keep each key stable when editing its wording so candidates’ saved answer mappings remain predictable.</p>
              </div>
              <Button type="button" size="sm" variant="secondary" onClick={() => set("screening_questions", [
                ...form.screening_questions,
                { key: `application_question_${form.screening_questions.length + 1}`, text: "", required: true },
              ])}>
                <Plus size={14} /> Add question
              </Button>
            </div>
            <div className="mt-4 flex flex-col gap-3">
              {form.screening_questions.map((question, index) => (
                <div key={`${question.key}-${index}`} className="grid gap-3 rounded-lg border border-subtle p-3 sm:grid-cols-[1fr_180px_auto]">
                  <Textarea
                    label={`QUESTION ${index + 1}`}
                    rows={2}
                    value={question.text}
                    onChange={(event) => updateQuestion(index, { text: event.target.value })}
                    placeholder="Describe a relevant project or decision."
                  />
                  <Input
                    label="ANSWER KEY"
                    value={question.key}
                    onChange={(event) => updateQuestion(index, { key: event.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_") })}
                  />
                  <div className="flex items-end gap-2 pb-1">
                    <label className="flex items-center gap-2 pb-2 text-[11px] text-ink-muted">
                      <input type="checkbox" checked={question.required} onChange={(event) => updateQuestion(index, { required: event.target.checked })} />
                      <span>Required</span>
                    </label>
                    <Button type="button" size="sm" variant="ghost" className="!h-8 !w-8 !px-0 text-[var(--color-error)]" aria-label={`Remove application question ${index + 1}`} title="Remove question" onClick={() => set("screening_questions", form.screening_questions.filter((_, itemIndex) => itemIndex !== index))}>
                      <X size={14} />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <Button type="submit" className="self-start" loading={saving} disabled={!form.title.trim()}>
            {postingSubmitLabel(Boolean(posting), saving)}
          </Button>
        </form>
      </GlassCard>
    </Modal>
  );
}

function PostingCard({
  posting,
  campaignActive,
  campaignArchived,
  restoring,
  onPublish,
  onEdit,
  onArchive,
  onRestore,
}: Readonly<{
  posting: JobPosting;
  campaignActive: boolean;
  campaignArchived: boolean;
  restoring: boolean;
  onPublish: (id: number, status: "PUBLISHED" | "CLOSED") => Promise<void>;
  onEdit: (posting: JobPosting) => void;
  onArchive: (posting: JobPosting) => void;
  onRestore: (posting: JobPosting) => void;
}>) {
  const archived = Boolean(posting.deleted_at);
  const canManage = !campaignArchived && !archived;
  const canPublish = campaignActive && canManage;
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
        <div className="flex shrink-0 items-center gap-1">
          {!archived && canManage && (
            <>
              <Button type="button" size="sm" variant="ghost" className="!h-8 !w-8 !px-0" title={`Edit ${posting.title}`} aria-label={`Edit role ${posting.title}`} onClick={() => onEdit(posting)}>
                <Pencil size={14} />
              </Button>
              <Button type="button" size="sm" variant="ghost" className="!h-8 !w-8 !px-0 text-[var(--color-error)]" title={`Archive ${posting.title}`} aria-label={`Archive role ${posting.title}`} onClick={() => onArchive(posting)}>
                <Trash2 size={14} />
              </Button>
            </>
          )}
          {archived && (
            <Button type="button" size="sm" variant="ghost" className="!h-8 !w-8 !px-0" title={`Restore ${posting.title}`} aria-label={`Restore role ${posting.title}`} onClick={() => onRestore(posting)} disabled={restoring || !campaignActive}>
              <RotateCcw size={14} />
            </Button>
          )}
          <StatusPill tone={archived ? "muted" : POSTING_TONE[posting.status] ?? "muted"}>
            {archived ? "ARCHIVED" : posting.status}
          </StatusPill>
        </div>
      </div>

      <div className="mt-5 flex items-center gap-2 text-[13px] text-ink-muted">
        <Users size={14} className="text-brand" />
        <span className="font-semibold text-ink-heading">{posting.applicant_count ?? 0}</span> applicants
      </div>

      <div className="mt-5 flex items-center gap-2 border-t border-subtle pt-4">
        <Link href={`/org/postings/${posting.id}`} className="btn-secondary !px-3 !py-1.5 !text-[12px] no-underline">
          Manage pipeline
        </Link>
        {canManage && posting.status === "DRAFT" && (
          <Button size="sm" variant="ghost" onClick={() => onPublish(posting.id, "PUBLISHED")} disabled={!canPublish} title={!canPublish ? "Reopen the campaign before publishing this role" : undefined}>Publish</Button>
        )}
        {canManage && posting.status === "PUBLISHED" && (
          <Button size="sm" variant="ghost" onClick={() => onPublish(posting.id, "CLOSED")}>Close</Button>
        )}
        {canManage && posting.status === "CLOSED" && (
          <Button size="sm" variant="ghost" onClick={() => onPublish(posting.id, "PUBLISHED")} disabled={!canPublish} title={!canPublish ? "Reopen the campaign before reopening this role" : undefined}>Reopen role</Button>
        )}
      </div>
    </motion.div>
  );
}

function campaignStatusTone(archived: boolean, active: boolean): PillTone {
  if (archived) return "muted";
  return active ? "success" : "warning";
}

function CampaignWorkspaceHeader({
  campaign,
  busy,
  onStatusChange,
  onArchive,
  onRestore,
  onAddRole,
}: Readonly<{
  campaign: Campaign;
  busy: boolean;
  onStatusChange: (status: "ACTIVE" | "CLOSED") => void;
  onArchive: () => void;
  onRestore: () => void;
  onAddRole: () => void;
}>) {
  const archived = Boolean(campaign.deleted_at);
  const active = !archived && campaign.status === "ACTIVE";
  return (
    <>
      <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-[26px] font-bold tracking-normal text-ink-heading">{campaign.name}</h1>
          <p className="mt-1 text-[12px] text-ink-subtle">
            {campaign.department || "No department"}
            {campaign.hiring_manager && ` · Hiring manager: ${campaign.hiring_manager}`}
          </p>
          {campaign.description && <p className="mt-3 max-w-[640px] text-[13px] leading-[1.6] text-ink-muted">{campaign.description}</p>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusPill tone={campaignStatusTone(archived, active)}>
            {archived ? "ARCHIVED" : campaign.status}
          </StatusPill>
          {archived ? (
            <Button size="sm" variant="secondary" loading={busy} onClick={onRestore}>
              <RotateCcw size={14} /> Restore campaign
            </Button>
          ) : (
            <>
              <Button size="sm" variant="secondary" loading={busy} onClick={() => onStatusChange(active ? "CLOSED" : "ACTIVE")}>
                {active ? "Close campaign" : "Reopen campaign"}
              </Button>
              <Button size="sm" variant="danger" onClick={onArchive}>
                <Trash2 size={14} /> Archive
              </Button>
            </>
          )}
          <Button size="sm" onClick={onAddRole} disabled={!active} title={!active ? "Reopen the campaign to add roles" : undefined}>
            <Plus size={15} /> Add a role
          </Button>
        </div>
      </div>

      {(archived || campaign.status === "CLOSED") && (
        <div className="mt-5 rounded-xl border border-[rgba(245,158,11,0.32)] bg-[rgba(245,158,11,0.07)] p-4 text-[12px] leading-relaxed text-ink-muted">
          {archived
            ? "This campaign is archived. Applicant history is preserved. Restore it, then reopen the campaign and individual roles you still want to hire for."
            : "This campaign is closed. Its published roles have been closed too. Reopen the campaign, then explicitly reopen any roles you still want to publish."}
        </div>
      )}
    </>
  );
}

function CampaignMetrics({ campaign, postings, totalApplicants }: Readonly<{
  campaign: Campaign;
  postings: JobPosting[];
  totalApplicants: number;
}>) {
  return (
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
  );
}

function PostingLifecycleFilters({
  view,
  postings,
  onChange,
}: Readonly<{
  view: PostingView;
  postings: JobPosting[];
  onChange: (view: PostingView) => void;
}>) {
  const openCount = postings.filter((posting) => !posting.deleted_at && posting.status !== "CLOSED").length;
  const closedCount = postings.filter((posting) => !posting.deleted_at && posting.status === "CLOSED").length;
  const archivedCount = postings.filter((posting) => Boolean(posting.deleted_at)).length;
  return (
    <div className="mb-5 flex flex-wrap gap-2">
      <Button size="sm" variant={view === "OPEN" ? "primary" : "secondary"} onClick={() => onChange("OPEN")}>Open roles ({openCount})</Button>
      <Button size="sm" variant={view === "CLOSED" ? "primary" : "secondary"} onClick={() => onChange("CLOSED")}>Closed ({closedCount})</Button>
      <Button size="sm" variant={view === "ARCHIVED" ? "primary" : "secondary"} onClick={() => onChange("ARCHIVED")}>Archived ({archivedCount})</Button>
    </div>
  );
}

function PostingResults({
  postings,
  visiblePostings,
  campaignActive,
  campaignArchived,
  restoringPostingId,
  onAddRole,
  onPublish,
  onEdit,
  onArchive,
  onRestore,
}: Readonly<{
  postings: JobPosting[];
  visiblePostings: JobPosting[];
  campaignActive: boolean;
  campaignArchived: boolean;
  restoringPostingId: number | null;
  onAddRole: () => void;
  onPublish: (id: number, status: "PUBLISHED" | "CLOSED") => Promise<void>;
  onEdit: (posting: JobPosting) => void;
  onArchive: (posting: JobPosting) => void;
  onRestore: (posting: JobPosting) => void;
}>) {
  if (postings.length === 0) {
    return (
      <EmptyState
        title="No roles yet"
        description={campaignActive ? "Add the first role to this campaign to start collecting applicants." : "No roles are attached to this campaign yet."}
        action={campaignActive ? <Button onClick={onAddRole}>Add a role</Button> : undefined}
      />
    );
  }
  if (visiblePostings.length === 0) {
    return (
      <EmptyState
        title="No roles in this view"
        description="Choose another role filter or create a role if this campaign is active."
        action={campaignActive ? <Button onClick={onAddRole}>Add a role</Button> : undefined}
      />
    );
  }
  return (
    <motion.div initial="hidden" animate="visible" variants={staggerContainer(0.06)} className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {visiblePostings.map((posting) => (
        <PostingCard
          key={posting.id}
          posting={posting}
          campaignActive={campaignActive}
          campaignArchived={campaignArchived}
          restoring={restoringPostingId === posting.id}
          onPublish={onPublish}
          onEdit={onEdit}
          onArchive={onArchive}
          onRestore={onRestore}
        />
      ))}
    </motion.div>
  );
}

function filterPostings(postings: JobPosting[], view: PostingView): JobPosting[] {
  if (view === "ARCHIVED") return postings.filter((posting) => Boolean(posting.deleted_at));
  return postings.filter((posting) => {
    if (posting.deleted_at) return false;
    return view === "OPEN" ? posting.status !== "CLOSED" : posting.status === "CLOSED";
  });
}

export default function CampaignDetailPage() {
  const params = useParams();
  const router = useRouter();
  const pathname = usePathname();
  const campaignId = Number(params.id);
  const { actor, loading: authLoading, activeOrgId } = useAuth();

  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [postings, setPostings] = useState<JobPosting[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [editingPosting, setEditingPosting] = useState<JobPosting | null>(null);
  const [archivePostingTarget, setArchivePostingTarget] = useState<JobPosting | null>(null);
  const [archivingPosting, setArchivingPosting] = useState(false);
  const [restoringPostingId, setRestoringPostingId] = useState<number | null>(null);
  const [postingView, setPostingView] = useState<PostingView>("OPEN");
  const [campaignBusy, setCampaignBusy] = useState(false);
  const [archiveCampaignOpen, setArchiveCampaignOpen] = useState(false);

  useEffect(() => {
    if (pathname !== `/org/campaigns/${campaignId}`) return;
    if (authLoading) return;
    if (!actor) {
      router.push("/login?next=/org");
      return;
    }
    if (!activeOrgId) return;
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, actor, activeOrgId, campaignId]);

  const load = async (showLoading = true) => {
    if (showLoading) setLoading(true);
    setError(null);
    try {
      const [campaignData, postingsData] = await Promise.all([
        api.get<Campaign>(`/orgs/${activeOrgId}/campaigns/${campaignId}`),
        api.get<{ postings: JobPosting[] }>(`/orgs/${activeOrgId}/postings?campaign_id=${campaignId}&include_archived=true`),
      ]);
      setCampaign(campaignData);
      setPostings(postingsData.postings);
    } catch (err) {
      const message = err instanceof ApiError ? err.detail : "Failed to load campaign.";
      setError(message);
      notify.error(message);
    } finally {
      if (showLoading) setLoading(false);
    }
  };

  useActivePageRefresh(
    pathname === `/org/campaigns/${campaignId}`,
    !authLoading && Boolean(actor) && Boolean(activeOrgId),
    () => load(false),
  );

  const handlePublish = async (postingId: number, status: "PUBLISHED" | "CLOSED") => {
    try {
      await api.post(`/orgs/${activeOrgId}/postings/${postingId}/status`, { status });
      await load();
      notify.success(status === "PUBLISHED" ? "Role reopened and published." : "Role closed. Existing applications remain available.");
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to update role status.");
    }
  };

  const handleArchivePosting = async () => {
    if (!activeOrgId || !archivePostingTarget) return;
    setArchivingPosting(true);
    try {
      await api.delete(`/orgs/${activeOrgId}/postings/${archivePostingTarget.id}`);
      setArchivePostingTarget(null);
      await load();
      notify.success("Role archived. Applicant records and reports were preserved.");
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to archive role.");
    } finally {
      setArchivingPosting(false);
    }
  };

  const handleRestorePosting = async (posting: JobPosting) => {
    if (!activeOrgId) return;
    setRestoringPostingId(posting.id);
    try {
      await api.post(`/orgs/${activeOrgId}/postings/${posting.id}/restore`);
      await load();
      notify.success("Role restored. Its status was not changed; publish it explicitly if hiring is open.");
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to restore role.");
    } finally {
      setRestoringPostingId(null);
    }
  };

  const handleCampaignStatus = async (status: "ACTIVE" | "CLOSED") => {
    if (!activeOrgId) return;
    setCampaignBusy(true);
    try {
      await api.patch(`/orgs/${activeOrgId}/campaigns/${campaignId}`, { status });
      await load();
      notify.success(status === "CLOSED"
        ? "Campaign closed. Its published roles were closed too; reopen roles individually when needed."
        : "Campaign reopened. Its roles remain closed until you reopen them.");
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to update campaign.");
    } finally {
      setCampaignBusy(false);
    }
  };

  const handleArchiveCampaign = async () => {
    if (!activeOrgId) return;
    setCampaignBusy(true);
    try {
      await api.delete(`/orgs/${activeOrgId}/campaigns/${campaignId}`);
      setArchiveCampaignOpen(false);
      await load();
      notify.success("Campaign archived. Applicant and interview history was preserved.");
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to archive campaign.");
    } finally {
      setCampaignBusy(false);
    }
  };

  const handleRestoreCampaign = async () => {
    if (!activeOrgId) return;
    setCampaignBusy(true);
    try {
      await api.post(`/orgs/${activeOrgId}/campaigns/${campaignId}/restore`);
      await load();
      notify.success("Campaign restored as closed. Reopen it and any roles you want to publish.");
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to restore campaign.");
    } finally {
      setCampaignBusy(false);
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
  const campaignArchived = Boolean(campaign.deleted_at);
  const campaignActive = !campaignArchived && campaign.status === "ACTIVE";
  const visiblePostings = filterPostings(postings, postingView);

  return (
    <div className="min-h-screen">
      <Navbar />
      <PageShell className="!max-w-[1180px] pt-[112px]">
        <Link href="/org" className="mono text-[11px] tracking-[0.08em] text-ink-subtle no-underline hover:text-brand">
          ← BACK TO CAMPAIGNS
        </Link>

        <CampaignWorkspaceHeader
          campaign={campaign}
          busy={campaignBusy}
          onStatusChange={(status) => void handleCampaignStatus(status)}
          onArchive={() => setArchiveCampaignOpen(true)}
          onRestore={() => void handleRestoreCampaign()}
          onAddRole={() => setCreateOpen(true)}
        />
        <CampaignMetrics campaign={campaign} postings={postings} totalApplicants={totalApplicants} />

        <div className="mt-8">
          <PostingLifecycleFilters view={postingView} postings={postings} onChange={setPostingView} />
          <PostingResults
            postings={postings}
            visiblePostings={visiblePostings}
            campaignActive={campaignActive}
            campaignArchived={campaignArchived}
            restoringPostingId={restoringPostingId}
            onAddRole={() => setCreateOpen(true)}
            onPublish={handlePublish}
            onEdit={setEditingPosting}
            onArchive={setArchivePostingTarget}
            onRestore={(item) => void handleRestorePosting(item)}
          />
        </div>

        {activeOrgId && (
          <PostingFormModal
            open={createOpen}
            onClose={() => setCreateOpen(false)}
            orgId={activeOrgId}
            campaignId={campaignId}
            posting={null}
            onSaved={load}
          />
        )}
        {activeOrgId && (
          <PostingFormModal
            open={editingPosting !== null}
            onClose={() => setEditingPosting(null)}
            orgId={activeOrgId}
            campaignId={campaignId}
            posting={editingPosting}
            onSaved={load}
          />
        )}
        <ConfirmActionModal
          open={archivePostingTarget !== null}
          onClose={() => setArchivePostingTarget(null)}
          onConfirm={() => void handleArchivePosting()}
          title={`Archive ${archivePostingTarget?.title ?? "role"}?`}
          description="The role will disappear from candidate job search and active role views. Applications, AI interview reports, and recruiting history remain available to your authorized team. You can restore it later; it will stay closed until you explicitly publish it."
          confirmLabel="Archive role"
          busy={archivingPosting}
        />
        <ConfirmActionModal
          open={archiveCampaignOpen}
          onClose={() => setArchiveCampaignOpen(false)}
          onConfirm={() => void handleArchiveCampaign()}
          title={`Archive ${campaign.name}?`}
          description="All published roles in this campaign will be closed and hidden from candidates. Applicant records, reports, and interview history are preserved. You can restore the campaign later; roles will remain closed until reopened individually."
          confirmLabel="Archive campaign"
          busy={campaignBusy}
        />
      </PageShell>
    </div>
  );
}
