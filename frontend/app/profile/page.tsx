"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import Navbar from "../components/Navbar";
import {
  Button,
  GlassCard,
  Input,
  PageHeader,
  PageShell,
  SkeletonList,
  StatusPill,
  Textarea,
} from "../components/ui";
import { useAuth } from "../../lib/auth-context";
import { api, ApiError } from "../../lib/api";
import { notify } from "../../lib/toast";
import type { CandidateProfile, Education, Skill, WorkExperience } from "../../lib/types";
import { staggerContainer, staggerItem } from "../../lib/motion";

/** Native checkbox styled to match the design system. */
function Checkbox({
  label,
  checked,
  onChange,
}: Readonly<{ label: string; checked: boolean; onChange: (next: boolean) => void }>) {
  return (
    <label className="flex cursor-pointer items-center gap-2.5 text-[13px] text-ink-muted">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 cursor-pointer accent-[var(--color-primary)]"
      />
      {label}
    </label>
  );
}

function Section({ title, children }: Readonly<{ title: string; children: React.ReactNode }>) {
  return (
    <motion.div variants={staggerItem}>
      <GlassCard padding="lg">
        <p className="eyebrow">{title.toUpperCase()}</p>
        <div className="mt-5">{children}</div>
      </GlassCard>
    </motion.div>
  );
}

export default function ProfilePage() {
  const router = useRouter();
  const { actor, loading: authLoading } = useAuth();
  const [profile, setProfile] = useState<CandidateProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Form state
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

  const loadProfile = async () => {
    setLoading(true);
    try {
      const data = await api.get<CandidateProfile>("/me/profile");
      applyProfile(data);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setProfile(null); // No profile yet — the form below creates one.
      } else {
        notify.error(err instanceof ApiError ? err.detail : "Failed to load profile.");
      }
    } finally {
      setLoading(false);
    }
  };

  const applyProfile = (data: CandidateProfile) => {
    setProfile(data);
    setHeadline(data.headline);
    setSummary(data.summary);
    setResumeText(data.resume_text || "");
    setLocation(data.location);
    setYearsExperience(data.years_experience?.toString() ?? "");
    setOpenToWork(Boolean(data.open_to_work));
    setIsDiscoverable(Boolean(data.is_discoverable));
    setSkillsText(data.skills.map((s: Skill) => s.skill).join(", "));
  };

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const data = await api.put<CandidateProfile>("/me/profile", {
        headline,
        summary,
        resume_text: resumeText,
        location,
        years_experience: yearsExperience ? Number(yearsExperience) : null,
        open_to_work: openToWork,
        is_discoverable: isDiscoverable,
      });
      applyProfile(data);
      notify.success("Profile saved.");
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to save profile.");
    } finally {
      setSaving(false);
    }
  };

  const handleSaveSkills = async () => {
    setSaving(true);
    try {
      const skills = skillsText
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean)
        .map((skill) => ({ skill }));
      await api.put("/me/profile/skills", { skills });
      await loadProfile();
      notify.success("Skills updated.");
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to save skills.");
    } finally {
      setSaving(false);
    }
  };

  const handleAddExperience = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!expCompany.trim() || !expTitle.trim() || !expStart.trim()) return;
    setSaving(true);
    try {
      await api.post("/me/profile/experience", {
        company: expCompany.trim(),
        title: expTitle.trim(),
        start_date: expStart.trim(),
        is_current: expCurrent,
      });
      setExpCompany("");
      setExpTitle("");
      setExpStart("");
      setExpCurrent(false);
      await loadProfile();
      notify.success("Experience added.");
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to add experience.");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteExperience = async (id: number) => {
    try {
      await api.delete(`/me/profile/experience/${id}`);
      await loadProfile();
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to remove experience.");
    }
  };

  const handleAddEducation = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!eduInstitution.trim()) return;
    setSaving(true);
    try {
      await api.post("/me/profile/education", {
        institution: eduInstitution.trim(),
        degree: eduDegree.trim(),
        end_year: eduEndYear ? Number(eduEndYear) : null,
      });
      setEduInstitution("");
      setEduDegree("");
      setEduEndYear("");
      await loadProfile();
      notify.success("Education added.");
    } catch (err) {
      notify.error(err instanceof ApiError ? err.detail : "Failed to add education.");
    } finally {
      setSaving(false);
    }
  };

  if (authLoading || loading) {
    return (
      <div className="min-h-screen">
        <Navbar />
        <PageShell className="!max-w-[760px] pt-[112px]">
          <SkeletonList count={3} />
        </PageShell>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Navbar />
      <PageShell className="!max-w-[760px] pt-[112px]">
        <PageHeader
          eyebrow="YOUR PROFILE VAULT"
          title={profile ? "Manage your profile" : "Welcome — let's build your profile"}
          description="Fill this out once. Every job application pre-fills from it, and it gets stronger every time you apply — new questions you answer are saved back here automatically."
        />

        {!profile && (
          <p className="mt-4 text-[13px] text-ink-subtle">
            Just here to look around first?{" "}
            <Link href="/jobs" className="text-brand hover:underline">
              Skip for now and browse jobs →
            </Link>
          </p>
        )}

        <motion.div
          initial="hidden"
          animate="visible"
          variants={staggerContainer(0.07)}
          className="mt-8 flex flex-col gap-5"
        >
          <form onSubmit={handleSaveProfile}>
            <Section title="Basics">
              <div className="flex flex-col gap-5">
                <Input
                  id="headline"
                  label="HEADLINE"
                  value={headline}
                  onChange={(e) => setHeadline(e.target.value)}
                  placeholder="e.g. Senior Backend Engineer"
                />
                <Textarea
                  id="summary"
                  label="SUMMARY"
                  rows={4}
                  value={summary}
                  onChange={(e) => setSummary(e.target.value)}
                />
                <Textarea
                  id="resume-text"
                  label="RESUME / CV CONTENT"
                  rows={7}
                  value={resumeText}
                  onChange={(e) => setResumeText(e.target.value)}
                  hint="Used as evidence when a recruiter runs the screening stage for an application."
                />
                <div className="grid gap-5 sm:grid-cols-2">
                  <Input
                    id="location"
                    label="LOCATION"
                    value={location}
                    onChange={(e) => setLocation(e.target.value)}
                    placeholder="Bangalore, India"
                  />
                  <Input
                    id="years"
                    label="YEARS OF EXPERIENCE"
                    type="number"
                    min={0}
                    max={70}
                    step={0.5}
                    value={yearsExperience}
                    onChange={(e) => setYearsExperience(e.target.value)}
                  />
                </div>
                <div className="flex flex-wrap gap-6">
                  <Checkbox label="Open to work" checked={openToWork} onChange={setOpenToWork} />
                  <Checkbox
                    label="Discoverable by recruiters"
                    checked={isDiscoverable}
                    onChange={setIsDiscoverable}
                  />
                </div>
                <p className="text-[11px] leading-relaxed text-ink-subtle">
                  Discoverable is off by default. Turn it on to let recruiters find your profile in
                  searches, even before you apply anywhere.
                </p>
                <Button type="submit" className="self-start" loading={saving}>
                  {saving ? "Saving..." : "Save basics"}
                </Button>
              </div>
            </Section>
          </form>

          <Section title="Skills">
            <Input
              id="skills"
              label="COMMA-SEPARATED"
              value={skillsText}
              onChange={(e) => setSkillsText(e.target.value)}
              placeholder="Python, PostgreSQL, FastAPI"
            />
            <Button
              className="mt-4"
              size="sm"
              variant="secondary"
              onClick={handleSaveSkills}
              loading={saving}
            >
              Save skills
            </Button>
            {profile && profile.skills.length > 0 && (
              <div className="mt-5 flex flex-wrap gap-2">
                {profile.skills.map((s: Skill) => (
                  <StatusPill key={s.id} tone={s.verified ? "success" : "muted"}>
                    {s.skill}
                    {s.verified ? " ✓" : ""}
                  </StatusPill>
                ))}
              </div>
            )}
          </Section>

          <Section title="Work experience">
            {profile?.experiences.map((exp: WorkExperience) => (
              <div
                key={exp.id}
                className="flex items-center justify-between gap-4 border-b border-subtle py-3 first:pt-0"
              >
                <div className="min-w-0">
                  <p className="text-[14px] font-semibold text-ink-heading">
                    {exp.title} · {exp.company}
                  </p>
                  <p className="mono mt-0.5 text-[12px] text-ink-subtle">
                    {exp.start_date} – {exp.is_current ? "Present" : exp.end_date || "?"}
                  </p>
                </div>
                <Button size="sm" variant="ghost" onClick={() => handleDeleteExperience(exp.id)}>
                  Remove
                </Button>
              </div>
            ))}
            <form onSubmit={handleAddExperience} className="mt-5 flex flex-col gap-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <Input
                  placeholder="Company"
                  aria-label="Company"
                  value={expCompany}
                  onChange={(e) => setExpCompany(e.target.value)}
                />
                <Input
                  placeholder="Title"
                  aria-label="Title"
                  value={expTitle}
                  onChange={(e) => setExpTitle(e.target.value)}
                />
              </div>
              <div className="flex flex-wrap items-center gap-4">
                <Input
                  wrapperClassName="min-w-[200px] flex-1"
                  placeholder="Start date (YYYY-MM)"
                  aria-label="Start date"
                  value={expStart}
                  onChange={(e) => setExpStart(e.target.value)}
                />
                <Checkbox label="Current role" checked={expCurrent} onChange={setExpCurrent} />
              </div>
              <Button type="submit" size="sm" variant="secondary" className="self-start" loading={saving}>
                Add experience
              </Button>
            </form>
          </Section>

          <Section title="Education">
            {profile?.education.map((edu: Education) => (
              <div key={edu.id} className="border-b border-subtle py-3 first:pt-0">
                <p className="text-[14px] text-ink-heading">{edu.institution}</p>
                <p className="mt-0.5 text-[12px] text-ink-subtle">
                  {edu.degree} {edu.end_year ? `· ${edu.end_year}` : ""}
                </p>
              </div>
            ))}
            <form onSubmit={handleAddEducation} className="mt-5 flex flex-col gap-4">
              <div className="grid gap-4 sm:grid-cols-[2fr_1fr_1fr]">
                <Input
                  placeholder="Institution"
                  aria-label="Institution"
                  value={eduInstitution}
                  onChange={(e) => setEduInstitution(e.target.value)}
                />
                <Input
                  placeholder="Degree"
                  aria-label="Degree"
                  value={eduDegree}
                  onChange={(e) => setEduDegree(e.target.value)}
                />
                <Input
                  type="number"
                  placeholder="End year"
                  aria-label="End year"
                  value={eduEndYear}
                  onChange={(e) => setEduEndYear(e.target.value)}
                />
              </div>
              <Button type="submit" size="sm" variant="secondary" className="self-start" loading={saving}>
                Add education
              </Button>
            </form>
          </Section>
        </motion.div>
      </PageShell>
    </div>
  );
}
