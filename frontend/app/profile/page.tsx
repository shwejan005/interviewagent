"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import {
  BriefcaseBusiness,
  Check,
  ChevronRight,
  FileText,
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
import type { CandidateProfile, Education, Skill, WorkExperience } from "../../lib/types";
import { DUR, EASE_OUT } from "../../lib/motion";

type ProfileTab = "overview" | "experience" | "education" | "preferences";

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
  return <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[#8b98a6]">{children}</p>;
}

function InfoRow({ icon: Icon, label, value }: Readonly<{ icon: typeof MapPin; label: string; value: string }>) {
  return (
    <div className="flex items-start gap-3 border-b border-[#e8edf1] py-3 last:border-0">
      <Icon size={15} strokeWidth={1.8} className="mt-0.5 shrink-0 text-[#8294a3]" />
      <div className="min-w-0">
        <p className="text-[11px] text-[#8b98a6]">{label}</p>
        <p className="mt-0.5 break-words text-[13px] text-[#344555]">{value || "Not added"}</p>
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
    <section className={`rounded-xl border border-[#dfe6eb] bg-white shadow-[0_1px_2px_rgba(20,35,50,0.03)] ${className}`}>
      <div className="flex items-center justify-between border-b border-[#e8edf1] px-6 py-4">
        <h2 className="text-[14px] font-bold text-[#263342]">{title}</h2>
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
        <motion.div className="fixed inset-0 z-[90] flex items-center justify-center bg-[#10263a]/35 p-5 backdrop-blur-[3px]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <motion.div className="max-h-[90vh] w-full max-w-[640px] overflow-y-auto rounded-2xl border border-[#d7e0e7] bg-[#f9fbfc] p-6 shadow-[0_24px_70px_rgba(19,42,63,0.24)]" initial={{ opacity: 0, y: 14, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 8, scale: 0.98 }} transition={{ duration: DUR.base, ease: EASE_OUT }}>
            <div className="flex items-center justify-between gap-4">
              <h2 className="text-[18px] font-bold text-[#263342]">{title}</h2>
              <button type="button" onClick={onClose} aria-label="Close panel" className="rounded-lg p-2 text-[#728392] transition-colors hover:bg-[#edf2f5] hover:text-[#263342]"><X size={18} /></button>
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
  const { actor, loading: authLoading } = useAuth();
  const [profile, setProfile] = useState<CandidateProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [tab, setTab] = useState<ProfileTab>("overview");
  const [editOpen, setEditOpen] = useState(false);
  const [editSection, setEditSection] = useState<"basics" | "resume" | "experience" | "education" | null>(null);

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
    return <><Navbar variant="workspace" /><main className="min-h-screen bg-[#f5f7f9] px-6 pb-20 pt-[110px] lg:pl-[280px]"><SkeletonList count={4} /></main></>;
  }

  return (
    <div className="workspace-surface min-h-screen bg-[#f5f7f9] text-[#344555]">
      <Navbar variant="workspace" />
      <main className="min-h-screen px-4 pb-20 pt-[96px] sm:px-8 lg:ml-[232px] lg:px-10 lg:pt-[104px]">
        <div className="mx-auto max-w-[1240px]">
          <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#dfe6eb] pb-5">
            <div>
              <div className="flex items-center gap-2 text-[11px] text-[#8b98a6]"><span>My info</span><ChevronRight size={13} /><span className="font-semibold text-[#526373]">Profile</span></div>
              <h1 className="mt-3 text-[28px] font-bold tracking-[-0.02em] text-[#263342]">Profile</h1>
            </div>
            <Button size="sm" onClick={() => { setEditSection("basics"); setEditOpen(true); }}><Pencil size={14} /> Edit profile</Button>
          </div>

          <div className="mt-4 flex gap-6 overflow-x-auto border-b border-[#dfe6eb]">
            {PROFILE_TABS.map((item) => (
              <button key={item.id} type="button" onClick={() => setTab(item.id)} className={`relative whitespace-nowrap pb-3 text-[12px] transition-colors ${tab === item.id ? "font-bold text-[#17324a]" : "text-[#83909d] hover:text-[#344555]"}`}>
                {item.label}
                {tab === item.id && <motion.span layoutId="profile-tab" className="absolute inset-x-0 -bottom-px h-[2px] rounded-full bg-[#2d78a8]" transition={{ type: "spring", stiffness: 420, damping: 32 }} />}
              </button>
            ))}
          </div>

          <div className="mt-6 grid grid-cols-1 gap-5 xl:grid-cols-[280px_minmax(0,1fr)]">
            <aside className="rounded-xl border border-[#dfe6eb] bg-white shadow-[0_1px_2px_rgba(20,35,50,0.03)]">
              <div className="flex flex-col items-center border-b border-[#e8edf1] px-5 py-7 text-center">
                <div className="flex h-[76px] w-[76px] items-center justify-center rounded-2xl bg-[#17324a] text-[24px] font-bold text-white shadow-[0_10px_22px_rgba(23,50,74,0.18)]">{profileInitials}</div>
                <h2 className="mt-4 text-[17px] font-bold text-[#263342]">{profileName}</h2>
                <p className="mt-1 text-[12px] text-[#8b98a6]">{headline || "Candidate profile"}</p>
                <StatusPill tone={isDiscoverable ? "success" : "muted"} className="mt-3">{isDiscoverable ? "Discoverable" : "Private profile"}</StatusPill>
              </div>
              <div className="px-5 py-4">
                <InfoRow icon={MapPin} label="Location" value={location} />
                <InfoRow icon={BriefcaseBusiness} label="Experience" value={yearsExperience ? `${yearsExperience} years` : "Not added"} />
                <InfoRow icon={FileText} label="Resume evidence" value={resumeText ? "Added" : "Not added"} />
                <div className="mt-4 rounded-lg bg-[#f3f7fa] p-3.5">
                  <div className="flex items-center justify-between text-[11px] font-semibold text-[#526373]"><span>Profile completeness</span><span>{completeness}%</span></div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[#dfe8ee]"><motion.div className="h-full rounded-full bg-[#3f8ab8]" initial={{ scaleX: 0 }} animate={{ scaleX: completeness / 100 }} transition={{ duration: 0.7, ease: EASE_OUT }} style={{ transformOrigin: "left" }} /></div>
                </div>
              </div>
            </aside>

            <div className="min-w-0">
              {tab === "overview" && (
                <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: DUR.base, ease: EASE_OUT }} className="grid grid-cols-1 gap-5 lg:grid-cols-2">
                  <WorkspaceCard title="About" action={<button type="button" onClick={() => { setEditSection("basics"); setEditOpen(true); }} className="text-[#317aa8]" aria-label="Edit about"><Pencil size={15} /></button>} className="lg:col-span-2">
                    <p className="max-w-[760px] whitespace-pre-wrap text-[14px] leading-[1.75] text-[#526373]">{summary || "Add a short summary so hiring teams understand what you build and where you do your best work."}</p>
                  </WorkspaceCard>
                  <WorkspaceCard title="Skills" action={<button type="button" onClick={() => { setEditSection("basics"); setEditOpen(true); }} className="text-[#317aa8]" aria-label="Edit skills"><Pencil size={15} /></button>}>
                    <div className="flex flex-wrap gap-2">{profile?.skills.length ? profile.skills.map((skill: Skill) => <span key={skill.id} className={`rounded-md border px-2.5 py-1.5 text-[12px] ${skill.verified ? "border-[#a7d9bd] bg-[#effaf3] text-[#27734b]" : "border-[#dbe3e9] bg-[#f7f9fa] text-[#526373]"}`}>{skill.skill}{skill.verified && <Check size={12} className="ml-1 inline" />}</span>) : <p className="text-[13px] text-[#8b98a6]">No skills added yet.</p>}</div>
                  </WorkspaceCard>
                  <WorkspaceCard title="Resume evidence" action={<button type="button" onClick={() => { setEditSection("resume"); setEditOpen(true); }} className="text-[#317aa8]" aria-label="Edit resume"><Pencil size={15} /></button>}>
                    <div className="flex items-start gap-3"><FileText size={20} className="mt-0.5 text-[#3f8ab8]" /><div><p className="text-[13px] font-semibold text-[#344555]">{resumeText ? "Resume content saved" : "No resume content yet"}</p><p className="mt-1 text-[12px] leading-[1.55] text-[#8b98a6]">{resumeText ? `${resumeText.length.toLocaleString()} characters available for screening.` : "Add text evidence for recruiter screening."}</p></div></div>
                  </WorkspaceCard>
                  <WorkspaceCard title="Work experience" action={<button type="button" onClick={() => { setEditSection("experience"); setEditOpen(true); }} className="flex items-center gap-1 text-[12px] text-[#317aa8]"><Plus size={14} /> Add</button>} className="lg:col-span-2">
                    {profile?.experiences.length ? <div className="grid gap-0 md:grid-cols-2">{profile.experiences.map((experience: WorkExperience) => <div key={experience.id} className="flex items-start gap-3 border-b border-[#edf1f3] py-3 first:pt-0 md:even:pl-6"><div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#edf5fa] text-[#3f8ab8]"><BriefcaseBusiness size={15} /></div><div className="min-w-0"><p className="text-[13px] font-bold text-[#344555]">{experience.title}</p><p className="mt-0.5 text-[12px] text-[#71808e]">{experience.company}</p><p className="mt-1 text-[11px] text-[#9aa7b4]">{experience.start_date} – {experience.is_current ? "Present" : experience.end_date || "?"}</p></div></div>)}</div> : <p className="text-[13px] text-[#8b98a6]">Add your work history to make your profile easier to assess.</p>}
                  </WorkspaceCard>
                </motion.div>
              )}

              {tab === "experience" && <WorkspaceCard title="Work experience" action={<button type="button" onClick={() => { setEditSection("experience"); setEditOpen(true); }} className="flex items-center gap-1 text-[12px] text-[#317aa8]"><Plus size={14} /> Add experience</button>}><div className="divide-y divide-[#e8edf1]">{profile?.experiences.length ? profile.experiences.map((experience: WorkExperience) => <div key={experience.id} className="flex items-center justify-between gap-4 py-4"><div><p className="font-bold text-[#344555]">{experience.title}</p><p className="text-[13px] text-[#71808e]">{experience.company}</p><p className="mt-1 text-[11px] text-[#9aa7b4]">{experience.start_date} – {experience.is_current ? "Present" : experience.end_date || "?"}</p></div><button type="button" onClick={() => void deleteExperience(experience.id)} className="rounded-lg p-2 text-[#a2adb6] transition-colors hover:bg-[#fff1f1] hover:text-[#d6565c]" aria-label={`Remove ${experience.title}`}><Trash2 size={16} /></button></div>) : <p className="py-3 text-[13px] text-[#8b98a6]">No work experience added.</p>}</div></WorkspaceCard>}

              {tab === "education" && <WorkspaceCard title="Education" action={<button type="button" onClick={() => { setEditSection("education"); setEditOpen(true); }} className="flex items-center gap-1 text-[12px] text-[#317aa8]"><Plus size={14} /> Add education</button>}><div className="divide-y divide-[#e8edf1]">{profile?.education.length ? profile.education.map((education: Education) => <div key={education.id} className="flex items-start gap-3 py-4"><div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#f0effa] text-[#7266b1]"><GraduationCap size={16} /></div><div><p className="font-bold text-[#344555]">{education.institution}</p><p className="text-[13px] text-[#71808e]">{education.degree || "Education"}</p><p className="mt-1 text-[11px] text-[#9aa7b4]">{education.end_year ? `Completed ${education.end_year}` : "Year not added"}</p></div></div>) : <p className="py-3 text-[13px] text-[#8b98a6]">No education added.</p>}</div></WorkspaceCard>}

              {tab === "preferences" && <WorkspaceCard title="Preferences" action={<button type="button" onClick={() => { setEditSection("basics"); setEditOpen(true); }} className="text-[#317aa8]" aria-label="Edit preferences"><Pencil size={15} /></button>}><div className="grid gap-5 sm:grid-cols-2"><InfoRow icon={ShieldCheck} label="Open to work" value={openToWork ? "Yes" : "No"} /><InfoRow icon={UsersRound} label="Recruiter visibility" value={isDiscoverable ? "Discoverable" : "Private"} /><InfoRow icon={MapPin} label="Preferred location" value={location || "Any location"} /><InfoRow icon={Sparkles} label="Profile signal" value={profile?.preferences?.remote_preference || "Any work model"} /></div></WorkspaceCard>}
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
          <div className="flex flex-wrap gap-5 text-[12px] text-[#526373]"><label className="flex items-center gap-2"><input type="checkbox" checked={openToWork} onChange={(event) => setOpenToWork(event.target.checked)} /> Open to work</label><label className="flex items-center gap-2"><input type="checkbox" checked={isDiscoverable} onChange={(event) => setIsDiscoverable(event.target.checked)} /> Discoverable</label></div>
          <div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => setEditOpen(false)}>Cancel</Button><Button type="submit" loading={saving}><Save size={15} /> Save changes</Button></div>
        </form>
      </EditPanel>
      <EditPanel open={editOpen && editSection === "resume"} title="Resume evidence" onClose={() => setEditOpen(false)}>
        <form onSubmit={saveBasics} className="flex flex-col gap-4"><Textarea id="edit-resume" label="RESUME / CV CONTENT" rows={14} value={resumeText} onChange={(event) => setResumeText(event.target.value)} hint="Used as evidence for recruiter screening. It is not shown in recruiter search results." /><div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => setEditOpen(false)}>Cancel</Button><Button type="submit" loading={saving}><Save size={15} /> Save resume</Button></div></form>
      </EditPanel>
      <EditPanel open={editOpen && editSection === "experience"} title="Add work experience" onClose={() => setEditOpen(false)}>
        <form onSubmit={addExperience} className="flex flex-col gap-4"><Input label="COMPANY" required value={expCompany} onChange={(event) => setExpCompany(event.target.value)} /><Input label="TITLE" required value={expTitle} onChange={(event) => setExpTitle(event.target.value)} /><Input label="START DATE" placeholder="YYYY-MM" required value={expStart} onChange={(event) => setExpStart(event.target.value)} /><label className="flex items-center gap-2 text-[12px] text-[#526373]"><input type="checkbox" checked={expCurrent} onChange={(event) => setExpCurrent(event.target.checked)} /> Current role</label><div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => setEditOpen(false)}>Cancel</Button><Button type="submit" loading={saving}><Plus size={15} /> Add experience</Button></div></form>
      </EditPanel>
      <EditPanel open={editOpen && editSection === "education"} title="Add education" onClose={() => setEditOpen(false)}>
        <form onSubmit={addEducation} className="flex flex-col gap-4"><Input label="INSTITUTION" required value={eduInstitution} onChange={(event) => setEduInstitution(event.target.value)} /><Input label="DEGREE" value={eduDegree} onChange={(event) => setEduDegree(event.target.value)} /><Input label="END YEAR" type="number" value={eduEndYear} onChange={(event) => setEduEndYear(event.target.value)} /><div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => setEditOpen(false)}>Cancel</Button><Button type="submit" loading={saving}><Plus size={15} /> Add education</Button></div></form>
      </EditPanel>
    </div>
  );
}
