"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Briefcase, Building2, Mail, Pencil, Plus, RotateCcw, Trash2, Users } from "lucide-react";

import Navbar from "../components/Navbar";
import {
  Button,
  ConfirmActionModal,
  EmptyState,
  GlassCard,
  Input,
  Modal,
  PageHeader,
  PageShell,
  Select,
  SkeletonList,
  StatusPill,
  Textarea,
} from "../components/ui";
import type { PillTone } from "../components/ui";
import { useAuth } from "../../lib/auth-context";
import { useActivePageRefresh } from "../../lib/use-active-page-refresh";
import { api, ApiError } from "../../lib/api";
import { notify } from "../../lib/toast";
import type { Campaign, CampaignPriority } from "../../lib/types";
import { staggerContainer, staggerItem } from "../../lib/motion";

const PRIORITY_TONE: Record<CampaignPriority, PillTone> = {
  LOW: "muted",
  MEDIUM: "primary",
  HIGH: "warning",
  URGENT: "error",
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post("/orgs", { name, slug });
      onCreated();
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to create organization.");
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
        <Button type="submit" className="self-start" loading={saving} disabled={!name || !slug}>
          {saving ? "Creating..." : "Create organization"}
        </Button>
      </form>
    </GlassCard>
  );
}

function InviteMemberModal({
  open,
  onClose,
  orgId,
}: Readonly<{ open: boolean; onClose: () => void; orgId: number }>) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("recruiter");
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    try {
      const result = await api.post<{ email_delivery: string }>(`/orgs/${orgId}/invitations`, { email, role });
      notify.success(result.email_delivery === "sent" ? "Invitation sent." : "Invitation created. Email delivery is not configured.");
      setEmail("");
      onClose();
    } catch (error) {
      notify.error(error instanceof ApiError ? error.detail : "Failed to create invitation.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} titleId="invite-member-title" maxWidthClassName="max-w-[520px]">
      <GlassCard elevation="high" padding="lg">
        <p className="eyebrow">INVITE TEAM MEMBER</p>
        <p id="invite-member-title" className="mt-2 text-[17px] font-semibold text-ink-heading">Add someone to this workspace</p>
        <form onSubmit={handleSubmit} className="mt-5 flex flex-col gap-4">
          <Input label="EMAIL" type="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="teammate@example.com" />
          <Select label="ROLE" value={role} onChange={(event) => setRole(event.target.value)}>
            <option value="recruiter">Recruiter</option>
            <option value="hiring_manager">Hiring manager</option>
            <option value="interviewer">Interviewer</option>
            <option value="org_admin">Organization admin</option>
          </Select>
          <Button type="submit" className="self-start" loading={saving}>Create invitation</Button>
        </form>
      </GlassCard>
    </Modal>
  );
}

type CampaignFormState = {
  name: string;
  description: string;
  department: string;
  hiring_manager: string;
  priority: CampaignPriority;
  status: "ACTIVE" | "CLOSED";
  target_hires: string;
  target_close_date: string;
};

const EMPTY_CAMPAIGN_FORM: CampaignFormState = {
  name: "",
  description: "",
  department: "",
  hiring_manager: "",
  priority: "MEDIUM",
  status: "ACTIVE",
  target_hires: "",
  target_close_date: "",
};

function campaignSubmitLabel(isEditing: boolean, saving: boolean): string {
  if (isEditing) return saving ? "Saving..." : "Save changes";
  return saving ? "Creating..." : "Create campaign";
}

function CampaignFormModal({
  open,
  onClose,
  orgId,
  campaign,
  onSaved,
}: Readonly<{
  open: boolean;
  onClose: () => void;
  orgId: number;
  campaign: Campaign | null;
  onSaved: () => Promise<void>;
}>) {
  const [form, setForm] = useState<CampaignFormState>(EMPTY_CAMPAIGN_FORM);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setForm(campaign ? {
      name: campaign.name,
      description: campaign.description,
      department: campaign.department,
      hiring_manager: campaign.hiring_manager,
      priority: campaign.priority,
      status: campaign.status,
      target_hires: campaign.target_hires?.toString() ?? "",
      target_close_date: campaign.target_close_date?.slice(0, 10) ?? "",
    } : EMPTY_CAMPAIGN_FORM);
  }, [campaign, open]);

  const set = <K extends keyof CampaignFormState>(key: K, value: CampaignFormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        name: form.name,
        description: form.description,
        department: form.department,
        hiring_manager: form.hiring_manager,
        priority: form.priority,
        status: form.status,
        target_hires: form.target_hires ? Number(form.target_hires) : null,
        target_close_date: form.target_close_date || null,
      };
      if (campaign) {
        await api.patch(`/orgs/${orgId}/campaigns/${campaign.id}`, payload);
      } else {
        await api.post(`/orgs/${orgId}/campaigns`, payload);
      }
      await onSaved();
      onClose();
      notify.success(campaign ? "Campaign updated." : "Campaign created.");
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to create campaign.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} titleId="campaign-form-title" maxWidthClassName="max-w-[620px]">
      <GlassCard elevation="high" padding="lg">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="eyebrow">{campaign ? "EDIT HIRING CAMPAIGN" : "NEW HIRING CAMPAIGN"}</p>
            <p id="campaign-form-title" className="mt-1 text-[17px] font-semibold text-ink-heading">
              {campaign ? "Update campaign details" : "Set up a campaign"}
            </p>
          </div>
          <Button size="sm" variant="ghost" onClick={onClose}>Close</Button>
        </div>

        <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
          <Input
            label="CAMPAIGN NAME"
            placeholder="Q4 Platform Expansion"
            required
            value={form.name}
            onChange={(e) => set("name", e.target.value)}
          />
          <Textarea
            rows={3}
            label="DESCRIPTION"
            placeholder="What is this hiring push for? Context recruiters and hiring managers should share."
            value={form.description}
            onChange={(e) => set("description", e.target.value)}
          />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input
              label="DEPARTMENT"
              placeholder="Platform Engineering"
              value={form.department}
              onChange={(e) => set("department", e.target.value)}
            />
            <Input
              label="HIRING MANAGER"
              placeholder="Priya Sharma"
              value={form.hiring_manager}
              onChange={(e) => set("hiring_manager", e.target.value)}
            />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Select
              label="PRIORITY"
              value={form.priority}
              onChange={(e) => set("priority", e.target.value as CampaignPriority)}
            >
              <option value="LOW">Low</option>
              <option value="MEDIUM">Medium</option>
              <option value="HIGH">High</option>
              <option value="URGENT">Urgent</option>
            </Select>
            <Input
              type="number"
              min={1}
              max={500}
              label="TARGET HIRES"
              placeholder="5"
              value={form.target_hires}
              onChange={(e) => set("target_hires", e.target.value)}
            />
            <Input
              type="date"
              label="TARGET CLOSE DATE"
              value={form.target_close_date}
              onChange={(e) => set("target_close_date", e.target.value)}
            />
          </div>
          {campaign && (
            <Select
              label="CAMPAIGN STATUS"
              value={form.status}
              onChange={(e) => set("status", e.target.value as CampaignFormState["status"])}
              hint={form.status === "CLOSED" ? "Closing a campaign also closes its published roles. Reopen roles individually when needed." : "Active campaigns can accept new roles and publish eligible postings."}
            >
              <option value="ACTIVE">Active</option>
              <option value="CLOSED">Closed</option>
            </Select>
          )}

          <Button type="submit" className="self-start" loading={saving} disabled={!form.name.trim()}>
            {campaignSubmitLabel(Boolean(campaign), saving)}
          </Button>
        </form>
      </GlassCard>
    </Modal>
  );
}

function StatCard({
  icon,
  label,
  value,
}: Readonly<{ icon: React.ReactNode; label: string; value: string }>) {
  return (
    <motion.div variants={staggerItem}>
      <GlassCard padding="lg" className="flex items-center gap-4">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[12px] bg-[rgba(249,115,22,0.12)] text-brand">
          {icon}
        </div>
        <div className="min-w-0">
          <p className="mono text-[10px] tracking-[0.08em] text-ink-subtle">{label}</p>
          <p className="mt-1 text-[22px] font-bold leading-none text-ink-heading">{value}</p>
        </div>
      </GlassCard>
    </motion.div>
  );
}

function CampaignCard({
  campaign,
  onOpen,
  onEdit,
  onArchive,
  onRestore,
  restoring,
}: Readonly<{
  campaign: Campaign;
  onOpen: () => void;
  onEdit: () => void;
  onArchive: () => void;
  onRestore: () => void;
  restoring: boolean;
}>) {
  const archived = Boolean(campaign.deleted_at);
  return (
    <motion.article
      variants={staggerItem}
      whileHover={{ y: -4 }}
      className="glass glass-interactive block w-full p-5 text-left"
    >
      <div className="flex items-start justify-between gap-3">
        <button type="button" onClick={onOpen} className="min-w-0 flex-1 text-left">
          <p className="truncate text-[15px] font-semibold text-ink-heading hover:text-brand">{campaign.name}</p>
          <p className="mt-1 text-[12px] text-ink-subtle">
            {campaign.department || "No department set"}
            {campaign.hiring_manager && ` · ${campaign.hiring_manager}`}
          </p>
        </button>
        <div className="flex shrink-0 items-center gap-1">
          {!archived && (
            <>
              <Button type="button" size="sm" variant="ghost" className="!h-8 !w-8 !px-0" title={`Edit ${campaign.name}`} aria-label={`Edit campaign ${campaign.name}`} onClick={onEdit}>
                <Pencil size={14} />
              </Button>
              <Button type="button" size="sm" variant="ghost" className="!h-8 !w-8 !px-0 text-[var(--color-error)]" title={`Archive ${campaign.name}`} aria-label={`Archive campaign ${campaign.name}`} onClick={onArchive}>
                <Trash2 size={14} />
              </Button>
            </>
          )}
          {archived && (
            <Button type="button" size="sm" variant="ghost" className="!h-8 !w-8 !px-0" title={`Restore ${campaign.name}`} aria-label={`Restore campaign ${campaign.name}`} onClick={onRestore} disabled={restoring}>
              <RotateCcw size={14} />
            </Button>
          )}
          <StatusPill tone={archived ? "muted" : PRIORITY_TONE[campaign.priority] ?? "muted"}>
            {archived ? "ARCHIVED" : campaign.priority}
          </StatusPill>
        </div>
      </div>

      <div className="mt-5 grid grid-cols-2 gap-3">
        <div>
          <p className="mono text-[10px] tracking-[0.08em] text-ink-subtle">ROLES</p>
          <p className="mt-0.5 text-[18px] font-bold text-ink-heading">{campaign.posting_count ?? 0}</p>
        </div>
        <div>
          <p className="mono text-[10px] tracking-[0.08em] text-ink-subtle">APPLICANTS</p>
          <p className="mt-0.5 text-[18px] font-bold text-brand">{campaign.applicant_count ?? 0}</p>
        </div>
      </div>

      <div className="mt-4 flex items-center justify-between border-t border-subtle pt-3">
        <StatusPill tone={!archived && campaign.status === "ACTIVE" ? "success" : "muted"}>
          {archived ? "ARCHIVED" : campaign.status}
        </StatusPill>
        {campaign.target_close_date && (
          <span className="mono text-[11px] text-ink-subtle">
            Target: {new Date(campaign.target_close_date).toLocaleDateString()}
          </span>
        )}
      </div>
    </motion.article>
  );
}

function CampaignResults({
  loading,
  campaigns,
  onCreate,
  onOpen,
  onEdit,
  onArchive,
  onRestore,
  restoringCampaignId,
}: Readonly<{
  loading: boolean;
  campaigns: Campaign[];
  onCreate: () => void;
  onOpen: (campaignId: number) => void;
  onEdit: (campaign: Campaign) => void;
  onArchive: (campaign: Campaign) => void;
  onRestore: (campaign: Campaign) => void;
  restoringCampaignId: number | null;
}>) {
  if (loading) return <SkeletonList count={3} />;
  if (campaigns.length === 0) {
    return (
      <EmptyState
        title="No campaigns yet"
        description="A campaign groups related roles under one hiring push — create one to get started."
        action={<Button onClick={onCreate}>Create a campaign</Button>}
      />
    );
  }

  return (
    <motion.div
      initial="hidden"
      animate="visible"
      variants={staggerContainer(0.06)}
      className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
    >
      {campaigns.map((campaign) => (
        <CampaignCard
          key={campaign.id}
          campaign={campaign}
          onOpen={() => onOpen(campaign.id)}
          onEdit={() => onEdit(campaign)}
          onArchive={() => onArchive(campaign)}
          onRestore={() => onRestore(campaign)}
          restoring={restoringCampaignId === campaign.id}
        />
      ))}
    </motion.div>
  );
}

export default function OrgHomePage() {
  const router = useRouter();
  const pathname = usePathname();
  const { actor, loading: authLoading, activeOrgId, refreshActor } = useAuth();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"ACTIVE" | "CLOSED" | "ARCHIVED">("ACTIVE");
  const [createOpen, setCreateOpen] = useState(false);
  const [editingCampaign, setEditingCampaign] = useState<Campaign | null>(null);
  const [archiveTarget, setArchiveTarget] = useState<Campaign | null>(null);
  const [archiving, setArchiving] = useState(false);
  const [restoringCampaignId, setRestoringCampaignId] = useState<number | null>(null);
  const [inviteOpen, setInviteOpen] = useState(false);

  useEffect(() => {
    if (pathname !== "/org") return;
    if (authLoading) return;
    if (!actor) {
      router.push("/login?next=/org");
      return;
    }
    if (activeOrgId) void loadCampaigns();
    else setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, actor, activeOrgId]);

  const loadCampaigns = async (showLoading = true) => {
    if (showLoading) setLoading(true);
    try {
      const data = await api.get<{ campaigns: Campaign[] }>(`/orgs/${activeOrgId}/campaigns?include_archived=true`);
      setCampaigns(data.campaigns);
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to load campaigns.");
    } finally {
      if (showLoading) setLoading(false);
    }
  };

  useActivePageRefresh(
    pathname === "/org",
    !authLoading && Boolean(actor) && Boolean(activeOrgId),
    () => loadCampaigns(false),
  );

  const handleArchiveCampaign = async () => {
    if (!activeOrgId || !archiveTarget) return;
    setArchiving(true);
    try {
      await api.delete(`/orgs/${activeOrgId}/campaigns/${archiveTarget.id}`);
      setArchiveTarget(null);
      await loadCampaigns();
      notify.success("Campaign archived. Its published roles were closed and applicant history was preserved.");
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to archive campaign.");
    } finally {
      setArchiving(false);
    }
  };

  const handleRestoreCampaign = async (campaign: Campaign) => {
    if (!activeOrgId) return;
    setRestoringCampaignId(campaign.id);
    try {
      await api.post(`/orgs/${activeOrgId}/campaigns/${campaign.id}/restore`);
      await loadCampaigns();
      notify.success("Campaign restored as closed. Reopen it and any roles you want to publish.");
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to restore campaign.");
    } finally {
      setRestoringCampaignId(null);
    }
  };

  const filtered = useMemo(
    () => campaigns.filter((campaign) => {
      if (tab === "ARCHIVED") return Boolean(campaign.deleted_at);
      if (campaign.deleted_at) return false;
      return tab === "ACTIVE" ? campaign.status === "ACTIVE" : campaign.status === "CLOSED";
    }),
    [campaigns, tab],
  );

  const totals = useMemo(
    () => ({
      roles: campaigns.filter((campaign) => !campaign.deleted_at).reduce((sum, c) => sum + (c.posting_count ?? 0), 0),
      applicants: campaigns.filter((campaign) => !campaign.deleted_at).reduce((sum, c) => sum + (c.applicant_count ?? 0), 0),
    }),
    [campaigns],
  );

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
      <PageShell className="!max-w-[1180px] pt-[112px]">
        <PageHeader
          eyebrow="RECRUITER WORKSPACE"
          title="Hiring operations"
          description="Every campaign, role, and applicant across your organization, in one place."
          actions={
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="secondary" onClick={() => setInviteOpen(true)}>
                <Mail size={15} /> Invite member
              </Button>
              <Button size="sm" onClick={() => setCreateOpen(true)}>
                <Plus size={15} /> Create a campaign
              </Button>
            </div>
          }
        />

        <motion.div
          initial="hidden"
          animate="visible"
          variants={staggerContainer(0.06)}
          className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-3"
        >
          <StatCard icon={<Building2 size={20} />} label="CAMPAIGNS" value={String(campaigns.length)} />
          <StatCard icon={<Briefcase size={20} />} label="OPEN ROLES" value={String(totals.roles)} />
          <StatCard icon={<Users size={20} />} label="TOTAL APPLICANTS" value={String(totals.applicants)} />
        </motion.div>

        <div className="mt-10 flex items-center justify-between">
          <div className="flex gap-2">
            <Button size="sm" variant={tab === "ACTIVE" ? "primary" : "secondary"} onClick={() => setTab("ACTIVE")}>
              Active ({campaigns.filter((c) => !c.deleted_at && c.status === "ACTIVE").length})
            </Button>
            <Button size="sm" variant={tab === "CLOSED" ? "primary" : "secondary"} onClick={() => setTab("CLOSED")}>
              Closed ({campaigns.filter((c) => !c.deleted_at && c.status === "CLOSED").length})
            </Button>
            <Button size="sm" variant={tab === "ARCHIVED" ? "primary" : "secondary"} onClick={() => setTab("ARCHIVED")}>
              Archived ({campaigns.filter((campaign) => Boolean(campaign.deleted_at)).length})
            </Button>
          </div>
        </div>

        <div className="mt-6">
          <CampaignResults
            loading={loading}
            campaigns={filtered}
            onCreate={() => setCreateOpen(true)}
            onOpen={(campaignId) => router.push(`/org/campaigns/${campaignId}`)}
            onEdit={setEditingCampaign}
            onArchive={setArchiveTarget}
            onRestore={(campaign) => void handleRestoreCampaign(campaign)}
            restoringCampaignId={restoringCampaignId}
          />
        </div>

        {activeOrgId !== null && (
          <CampaignFormModal
            open={createOpen}
            onClose={() => setCreateOpen(false)}
            orgId={activeOrgId}
            campaign={null}
            onSaved={loadCampaigns}
          />
        )}
        {activeOrgId !== null && (
          <CampaignFormModal
            open={editingCampaign !== null}
            onClose={() => setEditingCampaign(null)}
            orgId={activeOrgId}
            campaign={editingCampaign}
            onSaved={loadCampaigns}
          />
        )}
        <ConfirmActionModal
          open={archiveTarget !== null}
          onClose={() => setArchiveTarget(null)}
          onConfirm={() => void handleArchiveCampaign()}
          title={`Archive ${archiveTarget?.name ?? "campaign"}?`}
          description="This hides the campaign from active operations and closes its published roles. Applications, interview reports, and history are preserved. You can restore the campaign later; roles will stay closed until you reopen them."
          confirmLabel="Archive campaign"
          busy={archiving}
        />
        {activeOrgId !== null && <InviteMemberModal open={inviteOpen} onClose={() => setInviteOpen(false)} orgId={activeOrgId} />}
      </PageShell>
    </div>
  );
}
