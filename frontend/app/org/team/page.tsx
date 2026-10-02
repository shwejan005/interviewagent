"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Navbar from "../../components/Navbar";
import { Button, EmptyState, GlassCard, Input, PageHeader, PageShell, Select, SkeletonList, StatusPill } from "../../components/ui";
import { useAuth } from "../../../lib/auth-context";
import { api, ApiError } from "../../../lib/api";
import { notify } from "../../../lib/toast";

type TeamMember = {
  id: number;
  user_id: number;
  full_name: string;
  email: string;
  role_name: string;
  status: string;
  job_title?: string;
  interview_skills?: string[];
  interview_timezone?: string;
  weekly_capacity?: number;
  available_for_interviews?: boolean;
};

type TeamInvitation = {
  id: number;
  email_normalized: string;
  role_name: string;
  status: string;
  expires_at: string;
  created_at: string;
};

const TEAM_ROLES = ["recruiter", "hiring_manager", "interviewer", "org_admin"];

export default function TeamPage() {
  const router = useRouter();
  const { actor, loading: authLoading, activeOrgId } = useAuth();
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [invitations, setInvitations] = useState<TeamInvitation[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("interviewer");
  const [profileTitle, setProfileTitle] = useState("");
  const [profileSkills, setProfileSkills] = useState("");
  const [profileTimezone, setProfileTimezone] = useState("UTC");
  const [profileCapacity, setProfileCapacity] = useState(5);
  const [profileAvailable, setProfileAvailable] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingProfile, setSavingProfile] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSchedule = actor?.capabilities.includes("interview:schedule") ?? false;
  const canInvite = actor?.capabilities.includes("org:member:invite") ?? false;
  const canChangeRoles = actor?.capabilities.includes("org:member:role:set") ?? false;
  const canRemoveMembers = actor?.capabilities.includes("org:member:remove") ?? false;
  const canReadInvitations = actor?.capabilities.includes("org:settings:read") ?? false;

  const load = useCallback(async () => {
    if (!activeOrgId || !canSchedule) {
      setLoading(false);
      return;
    }
    setError(null);
    try {
      const [team, invitationData] = await Promise.all([
        api.get<{ members: TeamMember[] }>(`/orgs/${activeOrgId}/team`),
        canReadInvitations
          ? api.get<{ invitations: TeamInvitation[] }>(`/orgs/${activeOrgId}/invitations`)
          : Promise.resolve({ invitations: [] as TeamInvitation[] }),
      ]);
      setMembers(team.members);
      setInvitations(invitationData.invitations);
    } catch (requestError) {
      const message = requestError instanceof ApiError ? requestError.detail : "Unable to load the interview team.";
      setError(message);
      notify.error(message);
    } finally {
      setLoading(false);
    }
  }, [activeOrgId, canReadInvitations, canSchedule]);

  useEffect(() => {
    if (authLoading) return;
    if (!actor) {
      router.push("/login?next=/org/team");
      return;
    }
    void load();
  }, [actor, authLoading, load, router]);

  const ownMember = members.find((member) => member.user_id === actor?.user_id);
  useEffect(() => {
    if (!ownMember) return;
    setProfileTitle(ownMember.job_title || "");
    setProfileSkills((ownMember.interview_skills || []).join(", "));
    setProfileTimezone(ownMember.interview_timezone || "UTC");
    setProfileCapacity(ownMember.weekly_capacity ?? 5);
    setProfileAvailable(ownMember.available_for_interviews ?? true);
  }, [ownMember]);

  const inviteMember = async (event: FormEvent) => {
    event.preventDefault();
    if (!activeOrgId || !email.trim()) return;
    setSaving(true);
    try {
      const result = await api.post<{ email_delivery: string }>(`/orgs/${activeOrgId}/invitations`, { email: email.trim(), role });
      setEmail("");
      notify.success(result.email_delivery === "sent" ? "Invitation sent." : "Invitation created. Email delivery is not configured.");
      await load();
    } catch (requestError) {
      notify.error(requestError instanceof ApiError ? requestError.detail : "Unable to invite this teammate.");
    } finally {
      setSaving(false);
    }
  };

  const changeRole = async (member: TeamMember, nextRole: string) => {
    if (!activeOrgId || member.role_name === nextRole) return;
    try {
      await api.patch(`/orgs/${activeOrgId}/members/${member.user_id}`, { role: nextRole });
      notify.success(`${member.full_name || member.email}'s role was updated.`);
      await load();
    } catch (requestError) {
      notify.error(requestError instanceof ApiError ? requestError.detail : "Unable to change this role.");
    }
  };

  const removeMember = async (member: TeamMember) => {
    if (!activeOrgId || !window.confirm(`Remove ${member.full_name || member.email} from this organization?`)) return;
    try {
      await api.delete(`/orgs/${activeOrgId}/members/${member.user_id}`);
      notify.success("Team member removed.");
      await load();
    } catch (requestError) {
      notify.error(requestError instanceof ApiError ? requestError.detail : "Unable to remove this team member.");
    }
  };

  const saveProfile = async () => {
    if (!activeOrgId || !actor) return;
    setSavingProfile(true);
    try {
      await api.put(`/orgs/${activeOrgId}/members/${actor.user_id}/interview-profile`, {
        job_title: profileTitle.trim(),
        interview_skills: profileSkills.split(",").map((skill) => skill.trim()).filter(Boolean),
        timezone: profileTimezone.trim() || "UTC",
        weekly_capacity: profileCapacity,
        available_for_interviews: profileAvailable,
      });
      notify.success("Your interview profile was saved.");
      await load();
    } catch (requestError) {
      notify.error(requestError instanceof ApiError ? requestError.detail : "Unable to save your interview profile.");
    } finally {
      setSavingProfile(false);
    }
  };

  if (authLoading || loading) {
    return <><Navbar /><PageShell className="!max-w-[940px] pt-[112px]"><SkeletonList count={4} /></PageShell></>;
  }

  if (!canSchedule) {
    return <><Navbar /><PageShell className="!max-w-[940px] pt-[112px]"><PageHeader eyebrow="TEAM" title="Team access unavailable" /><GlassCard className="mt-6 p-5"><p className="text-[13px] text-ink-muted">Your organization role does not include interview scheduling or team assignment.</p></GlassCard></PageShell></>;
  }

  const interviewers = members.filter((member) => ["interviewer", "hiring_manager", "recruiter", "org_owner", "org_admin"].includes(member.role_name));

  return (
    <div className="min-h-screen">
      <Navbar />
      <PageShell className="!max-w-[940px] pt-[112px]">
        <PageHeader eyebrow="HIRING TEAM" title="Interview team" description="See who can take interviews and manage organization membership where your role permits. Assign an interviewer when scheduling a human round." />
        {error && <p role="alert" className="mt-4 text-[12px] text-[var(--color-error)]">{error}</p>}

        <div className={`mt-7 grid gap-4 ${canReadInvitations ? "sm:grid-cols-3" : "sm:grid-cols-2"}`}>
          <GlassCard padding="sm"><p className="eyebrow">TEAM MEMBERS</p><p className="mt-2 text-[22px] font-semibold text-ink-heading">{members.length}</p></GlassCard>
          <GlassCard padding="sm"><p className="eyebrow">INTERVIEWERS</p><p className="mt-2 text-[22px] font-semibold text-ink-heading">{interviewers.length}</p></GlassCard>
          {canReadInvitations && <GlassCard padding="sm"><p className="eyebrow">PENDING INVITATIONS</p><p className="mt-2 text-[22px] font-semibold text-ink-heading">{invitations.length}</p></GlassCard>}
        </div>

        {canInvite && (
          <GlassCard elevation="high" padding="lg" className="mt-6">
            <p className="eyebrow">ADD A TEAMMATE</p>
            <form className="mt-4 grid gap-3 sm:grid-cols-[minmax(0,1fr)_200px_auto] sm:items-end" onSubmit={(event) => void inviteMember(event)}>
              <Input type="email" label="WORK EMAIL" placeholder="teammate@example.com" value={email} onChange={(event) => setEmail(event.target.value)} required />
              <Select label="ROLE" value={role} onChange={(event) => setRole(event.target.value)}>
                {TEAM_ROLES.map((option) => <option key={option} value={option}>{option.replaceAll("_", " ")}</option>)}
              </Select>
              <Button type="submit" loading={saving}>Invite</Button>
            </form>
          </GlassCard>
        )}

        {ownMember && (
          <GlassCard elevation="high" padding="lg" className="mt-6">
            <p className="eyebrow">YOUR INTERVIEW PROFILE</p>
            <p className="mt-1 text-[11px] text-ink-subtle">Help recruiters match assignments to your skills, timezone, availability, and interview capacity.</p>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <Input label="JOB TITLE" value={profileTitle} onChange={(event) => setProfileTitle(event.target.value)} placeholder="Senior Backend Engineer" />
              <Input label="TIMEZONE" value={profileTimezone} onChange={(event) => setProfileTimezone(event.target.value)} placeholder="Asia/Kolkata" />
              <Input label="INTERVIEW SKILLS" value={profileSkills} onChange={(event) => setProfileSkills(event.target.value)} placeholder="Python, System design, Behavioral" hint="Comma-separated competency tags." />
              <Input label="MAX INTERVIEWS PER WEEK" type="number" min={0} max={40} value={profileCapacity} onChange={(event) => setProfileCapacity(Number(event.target.value))} />
            </div>
            <label className="mt-4 flex items-center gap-2 text-[12px] text-ink-muted"><input type="checkbox" checked={profileAvailable} onChange={(event) => setProfileAvailable(event.target.checked)} className="accent-[var(--color-primary)]" />Available for interview assignments</label>
            <Button size="sm" className="mt-4" loading={savingProfile} onClick={() => void saveProfile()}>Save interview profile</Button>
          </GlassCard>
        )}

        <section className="mt-8">
          <div className="flex items-center justify-between gap-3"><div><p className="eyebrow">DIRECTORY</p><h2 className="mt-1 text-[17px] font-semibold text-ink-heading">People in this organization</h2></div><StatusPill tone="muted">{members.length} members</StatusPill></div>
          <div className="mt-4 flex flex-col gap-2">
            {members.length === 0 ? <EmptyState title="No team members found" description="Invite a teammate to share interview assignments." /> : members.map((member) => (
              <GlassCard key={member.user_id} padding="sm" className="flex flex-wrap items-center justify-between gap-4">
                <div className="min-w-0"><p className="truncate text-[13px] font-semibold text-ink-heading">{member.full_name || member.email}</p><p className="mt-1 truncate text-[11px] text-ink-subtle">{member.job_title || member.email}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">{(member.interview_skills || []).map((skill) => <span key={`${member.user_id}-${skill}`} className="rounded-full border border-subtle px-2 py-0.5 text-[9px] text-ink-muted">{skill}</span>)}<span className="text-[9px] text-ink-subtle">{member.interview_timezone || "UTC"} · {member.weekly_capacity ?? 5}/week · {member.available_for_interviews === false ? "unavailable" : "available"}</span></div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {canChangeRoles ? (
                    <Select aria-label={`Role for ${member.full_name || member.email}`} value={member.role_name} onChange={(event) => void changeRole(member, event.target.value)}>
                      {[...new Set([...TEAM_ROLES, member.role_name])].map((option) => <option key={option} value={option}>{option.replaceAll("_", " ")}</option>)}
                    </Select>
                  ) : <StatusPill tone="muted">{member.role_name.replaceAll("_", " ")}</StatusPill>}
                  {canRemoveMembers && <Button size="sm" variant="ghost" onClick={() => void removeMember(member)}>Remove</Button>}
                </div>
              </GlassCard>
            ))}
          </div>
        </section>

        {canReadInvitations && (
          <section className="mt-8">
            <p className="eyebrow">INVITATIONS</p>
            <div className="mt-4 flex flex-col gap-2">
              {invitations.length === 0 ? <p className="text-[12px] text-ink-subtle">No pending invitations.</p> : invitations.map((invitation) => (
                <GlassCard key={invitation.id} padding="sm" className="flex flex-wrap items-center justify-between gap-3">
                  <div><p className="text-[12px] font-semibold text-ink-heading">{invitation.email_normalized}</p><p className="mt-1 text-[10px] text-ink-subtle">{invitation.role_name.replaceAll("_", " ")} · expires {new Date(invitation.expires_at).toLocaleDateString()}</p></div>
                  <StatusPill tone={invitation.status === "PENDING" ? "warning" : "muted"}>{invitation.status}</StatusPill>
                </GlassCard>
              ))}
            </div>
          </section>
        )}
      </PageShell>
    </div>
  );
}
