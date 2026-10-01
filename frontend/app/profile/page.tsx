"use client";

import { ChangeEvent, FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import {
  BriefcaseBusiness,
  Check,
  ChevronRight,
  FileText,
  FileUp,
  GraduationCap,
  MapPin,
  Pencil,
  Plus,
  Save,
  ShieldCheck,
  Sparkles,
  Trash2,
  UsersRound,
  X,
} from "lucide-react";

import Navbar from "../components/Navbar";
import { Button, Input, SkeletonList, StatusPill, Textarea } from "../components/ui";
import { useAuth } from "../../lib/auth-context";
import { api, ApiError } from "../../lib/api";
import { notify } from "../../lib/toast";
import type {
  CandidateProfile,
  Education,
  ResumeImportRequest,
  ResumeParseResponse,
  ResumeParsedEducation,
  ResumeParsedSkill,
  ResumeParsedWorkExperience,
  Skill,
  WorkExperience,
} from "../../lib/types";
import { DUR, EASE_OUT } from "../../lib/motion";

type ProfileTab = "overview" | "experience" | "education" | "preferences";

type ResumeDraft = Omit<ResumeImportRequest, "skills" | "work_experiences" | "education"> & {
  skills: Array<ResumeParsedSkill & { clientId: string }>;
  work_experiences: Array<ResumeParsedWorkExperience & { clientId: string }>;
  education: Array<ResumeParsedEducation & { clientId: string }>;
};

let draftSequence = 0;

function createDraftId(): string {
  return typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `draft-${++draftSequence}`;
}

function createResumeDraft(parsed: ResumeParseResponse): ResumeDraft {
  return {
    ...parsed.parsed,
    resume_text: parsed.raw_text,
    skills: parsed.parsed.skills.map((skill) => ({ ...skill, clientId: createDraftId() })),
    work_experiences: parsed.parsed.work_experiences.map((experience) => ({ ...experience, clientId: createDraftId() })),
    education: parsed.parsed.education.map((education) => ({ ...education, clientId: createDraftId() })),
  };
}

const PROFILE_TABS: Array<{ id: ProfileTab; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "experience", label: "Experience" },
  { id: "education", label: "Education" },
  { id: "preferences", label: "Preferences" },
];

function initials(name: string, email: string): string {
  const source = name || email || "U";
  return source.split(/\s+/).slice(0, 2).map((part) => part[0]?.toUpperCase() || "").join("") || "U";
}

function FieldLabel({ children }: Readonly<{ children: React.ReactNode }>) {
  return <p className="mono text-[10px] font-bold uppercase tracking-[0.12em] text-ink-subtle">{children}</p>;
}

function InfoRow({ icon: Icon, label, value }: Readonly<{ icon: typeof MapPin; label: string; value: string }>) {
  return (
    <div className="flex items-start gap-3 border-b border-subtle py-3 last:border-0">
      <Icon size={15} strokeWidth={1.8} className="mt-0.5 shrink-0 text-ink-subtle" />
      <div className="min-w-0">
        <p className="text-[11px] text-ink-subtle">{label}</p>
        <p className="mt-0.5 break-words text-[13px] text-ink-muted">{value || "Not added"}</p>
      </div>
    </div>
  );
}

function WorkspaceCard({
  title,
  action,
  children,
  className = "",
}: Readonly<{ title: string; action?: React.ReactNode; children: React.ReactNode; className?: string }>) {
  return (
    <section className={`glass overflow-hidden ${className}`}>
      <div className="flex items-center justify-between border-b border-subtle px-6 py-4">
        <h2 className="text-[14px] font-bold text-ink-heading">{title}</h2>
        {action}
      </div>
      <div className="px-6 py-5">{children}</div>
    </section>
  );
}

function EditPanel({
  open,
  title,
  onClose,
  children,
}: Readonly<{ open: boolean; title: string; onClose: () => void; children: React.ReactNode }>) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/70 p-5 backdrop-blur-[3px]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <motion.div className="glass-high max-h-[90vh] w-full max-w-[640px] overflow-y-auto p-6" initial={{ opacity: 0, y: 14, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 8, scale: 0.98 }} transition={{ duration: DUR.base, ease: EASE_OUT }}>
            <div className="flex items-center justify-between gap-4">
              <h2 className="text-[18px] font-bold text-ink-heading">{title}</h2>
              <button type="button" onClick={onClose} aria-label="Close panel" className="rounded-lg p-2 text-ink-subtle transition-colors hover:bg-glass-low hover:text-ink-heading"><X size={18} /></button>
            </div>
            <div className="mt-6">{children}</div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export default function ProfilePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { actor, loading: authLoading } = useAuth();
  const [profile, setProfile] = useState<CandidateProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [tab, setTab] = useState<ProfileTab>("overview");
  const [editOpen, setEditOpen] = useState(false);
  const [editSection, setEditSection] = useState<"basics" | "resume" | "resume-import" | "experience" | "education" | null>(null);

  const [headline, setHeadline] = useState("");
  const [summary, setSummary] = useState("");
  const [resumeText, setResumeText] = useState("");
  const [location, setLocation] = useState("");
  const [yearsExperience, setYearsExperience] = useState("");
  const [openToWork, setOpenToWork] = useState(true);
  const [isDiscoverable, setIsDiscoverable] = useState(false);
  const [skillsText, setSkillsText] = useState("");
  const [expCompany, setExpCompany] = useState("");
  const [expTitle, setExpTitle] = useState("");
  const [expStart, setExpStart] = useState("");
  const [expCurrent, setExpCurrent] = useState(false);
  const [eduInstitution, setEduInstitution] = useState("");
  const [eduDegree, setEduDegree] = useState("");
  const [eduEndYear, setEduEndYear] = useState("");
  const [resumeDraft, setResumeDraft] = useState<ResumeDraft | null>(null);
  const [resumeParsing, setResumeParsing] = useState(false);
  const resumeInputRef = useRef<HTMLInputElement>(null);

  const navigateBackToApply = (isReady: boolean) => {
    const next = searchParams.get("next");
    if (isReady && next && next.startsWith("/") && !next.startsWith("//")) router.push(next);
  };

  useEffect(() => {
    if (authLoading) return;
    if (!actor) {
      router.push("/login?next=/profile");
      return;
    }
    void loadProfile();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, actor]);

  const applyProfile = (data: CandidateProfile) => {
    setProfile(data);
    setHeadline(data.headline);
    setSummary(data.summary);
    setResumeText(data.resume_text || "");
    setLocation(data.location);
    setYearsExperience(data.years_experience?.toString() ?? "");
    setOpenToWork(Boolean(data.open_to_work));
    setIsDiscoverable(Boolean(data.is_discoverable));
    setSkillsText(data.skills.map((skill: Skill) => skill.skill).join(", "));
  };

  const loadProfile = async () => {
    setLoading(true);
    try {
      applyProfile(await api.get<CandidateProfile>("/me/profile"));
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) setProfile(null);
      else notify.error(error instanceof ApiError ? error.detail : "Failed to load profile.");
    } finally {
      setLoading(false);
    }
  };

  const handleResumeFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    setResumeParsing(true);
    try {
      const response = await api.upload<ResumeParseResponse>("/me/resume/parse", file);
      setResumeDraft(createResumeDraft(response));
      setEditSection("resume-import");
      setEditOpen(true);
      notify.success("Resume parsed. Review the suggested fields before saving.");
    } catch (error) {
      notify.error(error instanceof ApiError ? error.detail : "Could not parse this resume.");
    } finally {
      setResumeParsing(false);
    }
  };

  const updateResumeDraft = <K extends keyof ResumeDraft>(key: K, value: ResumeDraft[K]) => {
    setResumeDraft((current) => (current ? { ...current, [key]: value } : current));
  };

  const updateResumeExperience = (index: number, patch: Partial<ResumeParsedWorkExperience>) => {
    setResumeDraft((current) => current ? {
      ...current,
      work_experiences: current.work_experiences.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item),
    } : current);
  };

  const updateResumeEducation = (index: number, patch: Partial<ResumeParsedEducation>) => {
    setResumeDraft((current) => current ? {
      ...current,
      education: current.education.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item),
    } : current);
  };

  const updateResumeSkill = (index: number, patch: Partial<ResumeParsedSkill>) => {
    setResumeDraft((current) => current ? {
      ...current,
      skills: current.skills.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item),
    } : current);
  };

  const saveImportedResume = async (event: FormEvent) => {
    event.preventDefault();
    if (!resumeDraft) return;
    setSaving(true);
    try {
      const payload: ResumeImportRequest = {
        ...resumeDraft,
        skills: resumeDraft.skills.filter((skill) => skill.skill.trim()).map(({ clientId, ...skill }) => skill),
        work_experiences: resumeDraft.work_experiences.map(({ clientId, ...experience }) => experience),
        education: resumeDraft.education.map(({ clientId, ...education }) => education),
      };
      applyProfile(await api.post<CandidateProfile>("/me/resume/import", payload));
      await loadProfile();
      setEditOpen(false);
      setResumeDraft(null);
      notify.success("Profile imported and saved.");
      const profileReady = Boolean(payload.resume_text.trim() || (payload.headline.trim() && payload.skills.length + payload.work_experiences.length > 0));
      navigateBackToApply(profileReady);
    } catch (error) {
      notify.error(error instanceof ApiError ? error.detail : "Failed to save imported profile.");
    } finally {
      setSaving(false);
    }
  };

  const saveBasics = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    try {
      applyProfile(await api.put<CandidateProfile>("/me/profile", {
        headline, summary, resume_text: resumeText, location,
        years_experience: yearsExperience ? Number(yearsExperience) : null,
        open_to_work: openToWork, is_discoverable: isDiscoverable,
      }));
      await api.put("/me/profile/skills", {
        skills: skillsText.split(",").map((skill) => skill.trim()).filter(Boolean).map((skill) => ({ skill })),
      });
      await loadProfile();
      notify.success("Profile updated.");
      setEditOpen(false);
      const hasSkillsOrExperience = skillsText.split(",").some((skill) => skill.trim()) || experienceCount > 0;
      navigateBackToApply(Boolean(resumeText.trim() || (headline.trim() && hasSkillsOrExperience)));
    } catch (error) {
      notify.error(error instanceof ApiError ? error.detail : "Failed to save profile.");
    } finally {
      setSaving(false);
    }
  };

  const addExperience = async (event: FormEvent) => {
    event.preventDefault();
    if (!expCompany.trim() || !expTitle.trim() || !expStart.trim()) return;
    setSaving(true);
    try {
      await api.post("/me/profile/experience", { company: expCompany.trim(), title: expTitle.trim(), start_date: expStart.trim(), is_current: expCurrent });
      setExpCompany(""); setExpTitle(""); setExpStart(""); setExpCurrent(false);
      await loadProfile();
      notify.success("Experience added.");
      setEditOpen(false);
    } catch (error) {
      notify.error(error instanceof ApiError ? error.detail : "Failed to add experience.");
    } finally { setSaving(false); }
  };

  const addEducation = async (event: FormEvent) => {
    event.preventDefault();
    if (!eduInstitution.trim()) return;
    setSaving(true);
    try {
      await api.post("/me/profile/education", { institution: eduInstitution.trim(), degree: eduDegree.trim(), end_year: eduEndYear ? Number(eduEndYear) : null });
      setEduInstitution(""); setEduDegree(""); setEduEndYear("");
      await loadProfile();
      notify.success("Education added.");
      setEditOpen(false);
    } catch (error) {
      notify.error(error instanceof ApiError ? error.detail : "Failed to add education.");
    } finally { setSaving(false); }
  };

  const deleteExperience = async (id: number) => {
    try {
      await api.delete(`/me/profile/experience/${id}`);
      await loadProfile();
    } catch (error) { notify.error(error instanceof ApiError ? error.detail : "Failed to remove experience."); }
  };

  const profileName = actor?.full_name || actor?.email || "Your profile";
  const profileInitials = initials(profileName, actor?.email || "");
  const skillCount = profile?.skills.length || 0;
  const experienceCount = profile?.experiences.length || 0;
  const completeness = useMemo(() => {
    const checks = [headline, summary, resumeText, location, yearsExperience, skillCount > 0 ? "skills" : "", experienceCount > 0 ? "experience" : ""];
    return Math.round((checks.filter(Boolean).length / checks.length) * 100);
  }, [experienceCount, headline, location, resumeText, skillCount, summary, yearsExperience]);

  if (authLoading || loading) {
    return <><Navbar /><main className="min-h-screen px-6 pb-20 pt-[112px]"><SkeletonList count={4} /></main></>;
  }

  return (
    <div className="min-h-screen">
      <Navbar />
      <main className="min-h-screen px-4 pb-20 pt-[112px] sm:px-8">
        <div className="mx-auto max-w-[1180px]">
          <div className="flex flex-wrap items-start justify-between gap-4 border-b border-subtle pb-5">
            <div>
              <div className="flex items-center gap-2 text-[11px] text-ink-subtle"><span>My info</span><ChevronRight size={13} /><span className="font-semibold text-ink-muted">Profile</span></div>
              <h1 className="mt-3 text-[28px] font-bold tracking-normal text-ink-heading">Profile</h1>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <input
                ref={resumeInputRef}
                type="file"
                accept=".pdf,.docx,.txt"
                className="hidden"
                onChange={(event) => void handleResumeFileChange(event)}
              />
              <Button size="sm" variant="secondary" loading={resumeParsing} onClick={() => resumeInputRef.current?.click()}>
                <FileUp size={14} /> {resumeParsing ? "Parsing resume..." : "Import resume"}
              </Button>
              <Button size="sm" onClick={() => { setEditSection("basics"); setEditOpen(true); }}><Pencil size={14} /> Edit profile</Button>
            </div>
          </div>

          <div className="mt-4 flex gap-6 overflow-x-auto border-b border-subtle">
            {PROFILE_TABS.map((item) => (
              <button key={item.id} type="button" onClick={() => setTab(item.id)} className={`relative whitespace-nowrap pb-3 text-[12px] transition-colors ${tab === item.id ? "font-bold text-ink-heading" : "text-ink-subtle hover:text-ink"}`}>
                {item.label}
                {tab === item.id && <motion.span layoutId="profile-tab" className="absolute inset-x-0 -bottom-px h-[2px] rounded-full bg-brand shadow-glow-primary" transition={{ type: "spring", stiffness: 420, damping: 32 }} />}
              </button>
            ))}
          </div>

          <div className="mt-6 grid grid-cols-1 gap-5 xl:grid-cols-[280px_minmax(0,1fr)]">
            <aside className="glass overflow-hidden">
              <div className="flex flex-col items-center border-b border-subtle px-5 py-7 text-center">
                <div className="flex h-[76px] w-[76px] items-center justify-center rounded-2xl bg-[rgba(249,115,22,0.14)] text-[24px] font-bold text-brand shadow-glow-primary">{profileInitials}</div>
                <h2 className="mt-4 text-[17px] font-bold text-ink-heading">{profileName}</h2>
                <p className="mt-1 text-[12px] text-ink-subtle">{headline || "Candidate profile"}</p>
                <StatusPill tone={isDiscoverable ? "success" : "muted"} className="mt-3">{isDiscoverable ? "Discoverable" : "Private profile"}</StatusPill>
              </div>
              <div className="px-5 py-4">
                <InfoRow icon={MapPin} label="Location" value={location} />
                <InfoRow icon={BriefcaseBusiness} label="Experience" value={yearsExperience ? `${yearsExperience} years` : "Not added"} />
                <InfoRow icon={FileText} label="Resume evidence" value={resumeText ? "Added" : "Not added"} />
                <div className="mt-4 rounded-lg bg-glass-low p-3.5">
                  <div className="flex items-center justify-between text-[11px] font-semibold text-ink-muted"><span>Profile completeness</span><span>{completeness}%</span></div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-glass-mid"><motion.div className="h-full rounded-full bg-brand" initial={{ scaleX: 0 }} animate={{ scaleX: completeness / 100 }} transition={{ duration: 0.7, ease: EASE_OUT }} style={{ transformOrigin: "left" }} /></div>
                </div>
              </div>
            </aside>

            <div className="min-w-0">
              {tab === "overview" && (
                <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: DUR.base, ease: EASE_OUT }} className="grid grid-cols-1 gap-5 lg:grid-cols-2">
                  <WorkspaceCard title="About" action={<button type="button" onClick={() => { setEditSection("basics"); setEditOpen(true); }} className="text-brand" aria-label="Edit about"><Pencil size={15} /></button>} className="lg:col-span-2">
                    <p className="max-w-[760px] whitespace-pre-wrap text-[14px] leading-[1.75] text-ink-muted">{summary || "Add a short summary so hiring teams understand what you build and where you do your best work."}</p>
                  </WorkspaceCard>
                  <WorkspaceCard title="Skills" action={<button type="button" onClick={() => { setEditSection("basics"); setEditOpen(true); }} className="text-brand" aria-label="Edit skills"><Pencil size={15} /></button>}>
                    <div className="flex flex-wrap gap-2">{profile?.skills.length ? profile.skills.map((skill: Skill) => <span key={skill.id} className={`rounded-md border px-2.5 py-1.5 text-[12px] ${skill.verified ? "border-[rgba(34,197,94,0.35)] bg-[rgba(34,197,94,0.1)] text-[var(--color-success)]" : "border-subtle bg-glass-low text-ink-muted"}`}>{skill.skill}{skill.verified && <Check size={12} className="ml-1 inline" />}</span>) : <p className="text-[13px] text-ink-subtle">No skills added yet.</p>}</div>
                  </WorkspaceCard>
                  <WorkspaceCard title="Resume evidence" action={<button type="button" onClick={() => { setEditSection("resume"); setEditOpen(true); }} className="text-brand" aria-label="Edit resume"><Pencil size={15} /></button>}>
                    <div className="flex items-start gap-3"><FileText size={20} className="mt-0.5 text-brand" /><div><p className="text-[13px] font-semibold text-ink-heading">{resumeText ? "Resume content saved" : "No resume content yet"}</p><p className="mt-1 text-[12px] leading-[1.55] text-ink-subtle">{resumeText ? `${resumeText.length.toLocaleString()} characters available for screening.` : "Add text evidence for recruiter screening."}</p></div></div>
                  </WorkspaceCard>
                  <WorkspaceCard title="Work experience" action={<button type="button" onClick={() => { setEditSection("experience"); setEditOpen(true); }} className="flex items-center gap-1 text-[12px] text-brand"><Plus size={14} /> Add</button>} className="lg:col-span-2">
                    {profile?.experiences.length ? <div className="grid gap-0 md:grid-cols-2">{profile.experiences.map((experience: WorkExperience) => <div key={experience.id} className="flex items-start gap-3 border-b border-subtle py-3 first:pt-0 md:even:pl-6"><div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[rgba(249,115,22,0.12)] text-brand"><BriefcaseBusiness size={15} /></div><div className="min-w-0"><p className="text-[13px] font-bold text-ink-heading">{experience.title}</p><p className="mt-0.5 text-[12px] text-ink-muted">{experience.company}</p><p className="mt-1 text-[11px] text-ink-subtle">{experience.start_date} – {experience.is_current ? "Present" : experience.end_date || "?"}</p></div></div>)}</div> : <p className="text-[13px] text-ink-subtle">Add your work history to make your profile easier to assess.</p>}
                  </WorkspaceCard>
                </motion.div>
              )}

              {tab === "experience" && <WorkspaceCard title="Work experience" action={<button type="button" onClick={() => { setEditSection("experience"); setEditOpen(true); }} className="flex items-center gap-1 text-[12px] text-brand"><Plus size={14} /> Add experience</button>}><div className="divide-y divide-subtle">{profile?.experiences.length ? profile.experiences.map((experience: WorkExperience) => <div key={experience.id} className="flex items-center justify-between gap-4 py-4"><div><p className="font-bold text-ink-heading">{experience.title}</p><p className="text-[13px] text-ink-muted">{experience.company}</p><p className="mt-1 text-[11px] text-ink-subtle">{experience.start_date} – {experience.is_current ? "Present" : experience.end_date || "?"}</p></div><button type="button" onClick={() => void deleteExperience(experience.id)} className="rounded-lg p-2 text-ink-subtle transition-colors hover:bg-[rgba(239,68,68,0.12)] hover:text-[var(--color-error)]" aria-label={`Remove ${experience.title}`}><Trash2 size={16} /></button></div>) : <p className="py-3 text-[13px] text-ink-subtle">No work experience added.</p>}</div></WorkspaceCard>}

              {tab === "education" && <WorkspaceCard title="Education" action={<button type="button" onClick={() => { setEditSection("education"); setEditOpen(true); }} className="flex items-center gap-1 text-[12px] text-brand"><Plus size={14} /> Add education</button>}><div className="divide-y divide-subtle">{profile?.education.length ? profile.education.map((education: Education) => <div key={education.id} className="flex items-start gap-3 py-4"><div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[rgba(99,102,241,0.14)] text-[var(--color-accent-indigo)]"><GraduationCap size={16} /></div><div><p className="font-bold text-ink-heading">{education.institution}</p><p className="text-[13px] text-ink-muted">{education.degree || "Education"}</p><p className="mt-1 text-[11px] text-ink-subtle">{education.end_year ? `Completed ${education.end_year}` : "Year not added"}</p></div></div>) : <p className="py-3 text-[13px] text-ink-subtle">No education added.</p>}</div></WorkspaceCard>}

              {tab === "preferences" && <WorkspaceCard title="Preferences" action={<button type="button" onClick={() => { setEditSection("basics"); setEditOpen(true); }} className="text-brand" aria-label="Edit preferences"><Pencil size={15} /></button>}><div className="grid gap-5 sm:grid-cols-2"><InfoRow icon={ShieldCheck} label="Open to work" value={openToWork ? "Yes" : "No"} /><InfoRow icon={UsersRound} label="Recruiter visibility" value={isDiscoverable ? "Discoverable" : "Private"} /><InfoRow icon={MapPin} label="Preferred location" value={location || "Any location"} /><InfoRow icon={Sparkles} label="Profile signal" value={profile?.preferences?.remote_preference || "Any work model"} /></div></WorkspaceCard>}
            </div>
          </div>
        </div>
      </main>

      <EditPanel open={editOpen && editSection === "basics"} title="Edit profile basics" onClose={() => setEditOpen(false)}>
        <form onSubmit={saveBasics} className="flex flex-col gap-4">
          <Input id="edit-headline" label="HEADLINE" value={headline} onChange={(event) => setHeadline(event.target.value)} placeholder="Senior Backend Engineer" />
          <Textarea id="edit-summary" label="SUMMARY" rows={4} value={summary} onChange={(event) => setSummary(event.target.value)} />
          <Input id="edit-skills" label="SKILLS" value={skillsText} onChange={(event) => setSkillsText(event.target.value)} hint="Separate skills with commas." />
          <div className="grid gap-4 sm:grid-cols-2"><Input id="edit-location" label="LOCATION" value={location} onChange={(event) => setLocation(event.target.value)} /><Input id="edit-years" label="YEARS OF EXPERIENCE" type="number" min={0} max={70} step={0.5} value={yearsExperience} onChange={(event) => setYearsExperience(event.target.value)} /></div>
          <div className="flex flex-wrap gap-5 text-[12px] text-ink-muted"><label className="flex items-center gap-2"><input type="checkbox" checked={openToWork} onChange={(event) => setOpenToWork(event.target.checked)} /> Open to work</label><label className="flex items-center gap-2"><input type="checkbox" checked={isDiscoverable} onChange={(event) => setIsDiscoverable(event.target.checked)} /> Discoverable</label></div>
          <div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => setEditOpen(false)}>Cancel</Button><Button type="submit" loading={saving}><Save size={15} /> Save changes</Button></div>
        </form>
      </EditPanel>
      <EditPanel open={editOpen && editSection === "resume"} title="Resume evidence" onClose={() => setEditOpen(false)}>
        <form onSubmit={saveBasics} className="flex flex-col gap-4"><Textarea id="edit-resume" label="RESUME / CV CONTENT" rows={14} value={resumeText} onChange={(event) => setResumeText(event.target.value)} hint="Used as evidence for recruiter screening. It is not shown in recruiter search results." /><div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => setEditOpen(false)}>Cancel</Button><Button type="submit" loading={saving}><Save size={15} /> Save resume</Button></div></form>
      </EditPanel>
      <EditPanel open={editOpen && editSection === "resume-import"} title="Review imported resume" onClose={() => setEditOpen(false)}>
        {resumeDraft && (
          <form onSubmit={saveImportedResume} className="flex flex-col gap-5">
            <div className="rounded-lg border border-[rgba(249,115,22,0.25)] bg-[rgba(249,115,22,0.08)] px-4 py-3 text-[12px] leading-relaxed text-ink-muted">
              Review every suggested field before saving. The parsed resume is only a draft until you confirm it.
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Input label="HEADLINE" value={resumeDraft.headline} onChange={(event) => updateResumeDraft("headline", event.target.value)} />
              <Input label="LOCATION" value={resumeDraft.location} onChange={(event) => updateResumeDraft("location", event.target.value)} />
              <Input label="PHONE" value={resumeDraft.phone} onChange={(event) => updateResumeDraft("phone", event.target.value)} />
              <Input label="YEARS OF EXPERIENCE" type="number" min={0} max={70} step={0.5} value={resumeDraft.years_experience ?? ""} onChange={(event) => updateResumeDraft("years_experience", event.target.value ? Number(event.target.value) : null)} />
              <Input label="WORK AUTHORIZATION" value={resumeDraft.work_authorization} onChange={(event) => updateResumeDraft("work_authorization", event.target.value)} wrapperClassName="sm:col-span-2" />
            </div>
            <Textarea label="SUMMARY" rows={4} value={resumeDraft.summary} onChange={(event) => updateResumeDraft("summary", event.target.value)} />
            <div>
              <div className="flex items-center justify-between gap-3"><FieldLabel>SKILLS</FieldLabel><button type="button" className="text-[11px] font-semibold text-brand" onClick={() => updateResumeDraft("skills", [...resumeDraft.skills, { skill: "", years: null, clientId: createDraftId() }])}><Plus size={13} className="mr-1 inline" /> Add skill</button></div>
              <div className="mt-2 flex flex-col gap-2">
                {resumeDraft.skills.map((skill, index) => (
                  <div key={skill.clientId} className="flex items-end gap-2">
                    <Input wrapperClassName="min-w-0 flex-1" aria-label={`Imported skill ${index + 1}`} value={skill.skill} onChange={(event) => updateResumeSkill(index, { skill: event.target.value })} />
                    <Input wrapperClassName="w-[110px]" aria-label={`Years for ${skill.skill || "skill"}`} type="number" min={0} max={70} step={0.5} value={skill.years ?? ""} onChange={(event) => updateResumeSkill(index, { years: event.target.value ? Number(event.target.value) : null })} />
                    <button type="button" aria-label={`Remove skill ${skill.skill || index + 1}`} className="mb-1 rounded-lg p-2 text-ink-subtle hover:bg-[rgba(239,68,68,0.12)] hover:text-[var(--color-error)]" onClick={() => updateResumeDraft("skills", resumeDraft.skills.filter((_, itemIndex) => itemIndex !== index))}><Trash2 size={15} /></button>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <div className="flex items-center justify-between gap-3"><FieldLabel>WORK EXPERIENCE</FieldLabel><button type="button" className="text-[11px] font-semibold text-brand" onClick={() => updateResumeDraft("work_experiences", [...resumeDraft.work_experiences, { company: "", title: "", location: "", start_date: "", end_date: null, is_current: false, description: "", clientId: createDraftId() }])}><Plus size={13} className="mr-1 inline" /> Add experience</button></div>
              <div className="mt-2 flex flex-col gap-3">
                {resumeDraft.work_experiences.map((experience, index) => (
                  <div key={experience.clientId} className="rounded-lg border border-subtle bg-glass-low p-3">
                    <div className="mb-3 flex items-center justify-between"><p className="text-[12px] font-bold text-ink-muted">Experience {index + 1}</p><button type="button" aria-label={`Remove experience ${index + 1}`} className="rounded-lg p-2 text-ink-subtle hover:bg-[rgba(239,68,68,0.12)] hover:text-[var(--color-error)]" onClick={() => updateResumeDraft("work_experiences", resumeDraft.work_experiences.filter((_, itemIndex) => itemIndex !== index))}><Trash2 size={15} /></button></div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <Input label="COMPANY" value={experience.company} onChange={(event) => updateResumeExperience(index, { company: event.target.value })} />
                      <Input label="TITLE" value={experience.title} onChange={(event) => updateResumeExperience(index, { title: event.target.value })} />
                      <Input label="LOCATION" value={experience.location} onChange={(event) => updateResumeExperience(index, { location: event.target.value })} />
                      <Input label="START DATE" placeholder="YYYY-MM" value={experience.start_date} onChange={(event) => updateResumeExperience(index, { start_date: event.target.value })} />
                      <Input label="END DATE" placeholder="YYYY-MM" value={experience.end_date || ""} onChange={(event) => updateResumeExperience(index, { end_date: event.target.value || null })} />
                      <label className="flex items-center gap-2 self-end pb-2 text-[12px] text-ink-muted"><input type="checkbox" checked={experience.is_current} onChange={(event) => updateResumeExperience(index, { is_current: event.target.checked, end_date: event.target.checked ? null : experience.end_date })} /> Current role</label>
                    </div>
                    <Textarea wrapperClassName="mt-3" label="DESCRIPTION" rows={3} value={experience.description} onChange={(event) => updateResumeExperience(index, { description: event.target.value })} />
                  </div>
                ))}
              </div>
            </div>
            <div>
              <div className="flex items-center justify-between gap-3"><FieldLabel>EDUCATION</FieldLabel><button type="button" className="text-[11px] font-semibold text-brand" onClick={() => updateResumeDraft("education", [...resumeDraft.education, { institution: "", degree: "", field: "", start_year: null, end_year: null, clientId: createDraftId() }])}><Plus size={13} className="mr-1 inline" /> Add education</button></div>
              <div className="mt-2 flex flex-col gap-3">
                {resumeDraft.education.map((education, index) => (
                  <div key={education.clientId} className="rounded-lg border border-subtle bg-glass-low p-3">
                    <div className="mb-3 flex items-center justify-between"><p className="text-[12px] font-bold text-ink-muted">Education {index + 1}</p><button type="button" aria-label={`Remove education ${index + 1}`} className="rounded-lg p-2 text-ink-subtle hover:bg-[rgba(239,68,68,0.12)] hover:text-[var(--color-error)]" onClick={() => updateResumeDraft("education", resumeDraft.education.filter((_, itemIndex) => itemIndex !== index))}><Trash2 size={15} /></button></div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <Input label="INSTITUTION" value={education.institution} onChange={(event) => updateResumeEducation(index, { institution: event.target.value })} />
                      <Input label="DEGREE" value={education.degree} onChange={(event) => updateResumeEducation(index, { degree: event.target.value })} />
                      <Input label="FIELD" value={education.field} onChange={(event) => updateResumeEducation(index, { field: event.target.value })} />
                      <Input label="END YEAR" type="number" value={education.end_year ?? ""} onChange={(event) => updateResumeEducation(index, { end_year: event.target.value ? Number(event.target.value) : null })} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <Textarea label="RESUME EVIDENCE" rows={8} value={resumeDraft.resume_text} onChange={(event) => updateResumeDraft("resume_text", event.target.value)} />
            <div className="flex justify-end gap-2 border-t border-subtle pt-4"><Button type="button" variant="secondary" onClick={() => setEditOpen(false)}>Cancel</Button><Button type="submit" loading={saving}><Save size={15} /> Save profile</Button></div>
          </form>
        )}
      </EditPanel>
      <EditPanel open={editOpen && editSection === "experience"} title="Add work experience" onClose={() => setEditOpen(false)}>
        <form onSubmit={addExperience} className="flex flex-col gap-4"><Input label="COMPANY" required value={expCompany} onChange={(event) => setExpCompany(event.target.value)} /><Input label="TITLE" required value={expTitle} onChange={(event) => setExpTitle(event.target.value)} /><Input label="START DATE" placeholder="YYYY-MM" required value={expStart} onChange={(event) => setExpStart(event.target.value)} /><label className="flex items-center gap-2 text-[12px] text-ink-muted"><input type="checkbox" checked={expCurrent} onChange={(event) => setExpCurrent(event.target.checked)} /> Current role</label><div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => setEditOpen(false)}>Cancel</Button><Button type="submit" loading={saving}><Plus size={15} /> Add experience</Button></div></form>
      </EditPanel>
      <EditPanel open={editOpen && editSection === "education"} title="Add education" onClose={() => setEditOpen(false)}>
        <form onSubmit={addEducation} className="flex flex-col gap-4"><Input label="INSTITUTION" required value={eduInstitution} onChange={(event) => setEduInstitution(event.target.value)} /><Input label="DEGREE" value={eduDegree} onChange={(event) => setEduDegree(event.target.value)} /><Input label="END YEAR" type="number" value={eduEndYear} onChange={(event) => setEduEndYear(event.target.value)} /><div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => setEditOpen(false)}>Cancel</Button><Button type="submit" loading={saving}><Plus size={15} /> Add education</Button></div></form>
      </EditPanel>
    </div>
  );
}
