"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Navbar from "../components/Navbar";
import { useAuth } from "../../lib/auth-context";
import { api, ApiError } from "../../lib/api";
import type { CandidateProfile, Education, Skill, WorkExperience } from "../../lib/types";

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "10px 14px",
  fontSize: 14,
  color: "var(--color-text-heading)",
  background: "var(--color-surface)",
  border: "1px solid var(--color-border)",
  borderRadius: 6,
  outline: "none",
};

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: 12,
  fontWeight: 600,
  color: "var(--color-text-muted)",
  marginBottom: 6,
  fontFamily: "var(--font-mono)",
};

function Section({ title, children }: Readonly<{ title: string; children: React.ReactNode }>) {
  return (
    <div className="card-surface" style={{ padding: 24, marginBottom: 20 }}>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-primary)", letterSpacing: "0.05em", marginBottom: 16 }}>
        {title.toUpperCase()}
      </div>
      {children}
    </div>
  );
}

export default function ProfilePage() {
  const router = useRouter();
  const { actor, loading: authLoading } = useAuth();
  const [profile, setProfile] = useState<CandidateProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  // Form state
  const [headline, setHeadline] = useState("");
  const [summary, setSummary] = useState("");
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
      router.push("/login");
      return;
    }
    loadProfile();
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
        setError(err instanceof ApiError ? err.detail : "Failed to load profile.");
      }
    } finally {
      setLoading(false);
    }
  };

  const applyProfile = (data: CandidateProfile) => {
    setProfile(data);
    setHeadline(data.headline);
    setSummary(data.summary);
    setLocation(data.location);
    setYearsExperience(data.years_experience?.toString() ?? "");
    setOpenToWork(Boolean(data.open_to_work));
    setIsDiscoverable(Boolean(data.is_discoverable));
    setSkillsText(data.skills.map((s: Skill) => s.skill).join(", "));
  };

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const data = await api.put<CandidateProfile>("/me/profile", {
        headline,
        summary,
        location,
        years_experience: yearsExperience ? Number(yearsExperience) : null,
        open_to_work: openToWork,
        is_discoverable: isDiscoverable,
      });
      applyProfile(data);
      setMessage("Profile saved.");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to save profile.");
    } finally {
      setSaving(false);
    }
  };

  const handleSaveSkills = async () => {
    setSaving(true);
    setError(null);
    try {
      const skills = skillsText
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean)
        .map((skill) => ({ skill }));
      await api.put("/me/profile/skills", { skills });
      await loadProfile();
      setMessage("Skills updated.");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to save skills.");
    } finally {
      setSaving(false);
    }
  };

  const handleAddExperience = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!expCompany.trim() || !expTitle.trim() || !expStart.trim()) return;
    setSaving(true);
    setError(null);
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
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to add experience.");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteExperience = async (id: number) => {
    try {
      await api.delete(`/me/profile/experience/${id}`);
      await loadProfile();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to remove experience.");
    }
  };

  const handleAddEducation = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!eduInstitution.trim()) return;
    setSaving(true);
    setError(null);
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
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to add education.");
    } finally {
      setSaving(false);
    }
  };

  if (authLoading || loading) {
    return (
      <div style={{ minHeight: "100vh", background: "var(--color-bg)" }}>
        <Navbar />
        <main style={{ maxWidth: 720, margin: "0 auto", padding: "120px 24px" }}>
          <p style={{ color: "var(--color-text-muted)" }}>Loading your profile...</p>
        </main>
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)" }}>
      <Navbar />
      <main style={{ maxWidth: 720, margin: "0 auto", padding: "100px 24px 60px" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-primary)", letterSpacing: "0.1em", marginBottom: 8 }}>
          YOUR PROFILE VAULT
        </div>
        <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--color-text-heading)", marginBottom: 8 }}>
          {profile ? "Manage your profile" : "Build your profile"}
        </h1>
        <p style={{ fontSize: 13, color: "var(--color-text-muted)", marginBottom: 24, lineHeight: 1.6 }}>
          Fill this out once. Every job application pre-fills from it, and it
          gets stronger every time you apply — new questions you answer are
          saved back here automatically.
        </p>

        {message && (
          <div style={{ padding: "10px 14px", background: "rgba(34,197,94,0.1)", border: "1px solid rgba(34,197,94,0.2)", borderRadius: 6, fontSize: 13, color: "var(--color-success)", marginBottom: 20 }}>
            {message}
          </div>
        )}
        {error && (
          <div style={{ padding: "10px 14px", background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: 6, fontSize: 13, color: "var(--color-error)", marginBottom: 20 }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSaveProfile}>
          <Section title="Basics">
            <div style={{ marginBottom: 16 }}>
              <label htmlFor="headline" style={labelStyle}>HEADLINE</label>
              <input id="headline" style={inputStyle} value={headline} onChange={(e) => setHeadline(e.target.value)} placeholder="e.g. Senior Backend Engineer" />
            </div>
            <div style={{ marginBottom: 16 }}>
              <label htmlFor="summary" style={labelStyle}>SUMMARY</label>
              <textarea id="summary" rows={4} style={{ ...inputStyle, resize: "vertical" }} value={summary} onChange={(e) => setSummary(e.target.value)} />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
              <div>
                <label htmlFor="location" style={labelStyle}>LOCATION</label>
                <input id="location" style={inputStyle} value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Bangalore, India" />
              </div>
              <div>
                <label htmlFor="years" style={labelStyle}>YEARS OF EXPERIENCE</label>
                <input id="years" type="number" min={0} max={70} step={0.5} style={inputStyle} value={yearsExperience} onChange={(e) => setYearsExperience(e.target.value)} />
              </div>
            </div>
            <div style={{ display: "flex", gap: 24, marginBottom: 8 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--color-text-muted)" }}>
                <input type="checkbox" checked={openToWork} onChange={(e) => setOpenToWork(e.target.checked)} />
                Open to work
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--color-text-muted)" }}>
                <input type="checkbox" checked={isDiscoverable} onChange={(e) => setIsDiscoverable(e.target.checked)} />
                Discoverable by recruiters
              </label>
            </div>
            <p style={{ fontSize: 11, color: "var(--color-text-subtle)", marginBottom: 16 }}>
              Discoverable is off by default. Turn it on to let recruiters find your profile in searches, even before you apply anywhere.
            </p>
            <button type="submit" disabled={saving} className="btn-primary" style={{ padding: "10px 20px", fontSize: 13, opacity: saving ? 0.6 : 1 }}>
              {saving ? "Saving..." : "Save basics"}
            </button>
          </Section>
        </form>

        <Section title="Skills">
          <label htmlFor="skills" style={labelStyle}>COMMA-SEPARATED</label>
          <input
            id="skills"
            style={{ ...inputStyle, marginBottom: 12 }}
            value={skillsText}
            onChange={(e) => setSkillsText(e.target.value)}
            placeholder="Python, PostgreSQL, FastAPI"
          />
          <button onClick={handleSaveSkills} disabled={saving} className="btn-secondary" style={{ padding: "8px 16px", fontSize: 13 }}>
            Save skills
          </button>
          {profile && profile.skills.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 16 }}>
              {profile.skills.map((s: Skill) => (
                <span key={s.id} className={`status-tag ${s.verified ? "status-tag-success" : "status-tag-muted"}`}>
                  {s.skill}{s.verified ? " ✓" : ""}
                </span>
              ))}
            </div>
          )}
        </Section>

        <Section title="Work experience">
          {profile?.experiences.map((exp: WorkExperience) => (
            <div key={exp.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 0", borderBottom: "1px solid var(--color-border)" }}>
              <div>
                <div style={{ fontSize: 14, color: "var(--color-text-heading)", fontWeight: 600 }}>{exp.title} · {exp.company}</div>
                <div style={{ fontSize: 12, color: "var(--color-text-subtle)" }}>
                  {exp.start_date} – {exp.is_current ? "Present" : exp.end_date || "?"}
                </div>
              </div>
              <button onClick={() => handleDeleteExperience(exp.id)} className="btn-secondary" style={{ padding: "4px 10px", fontSize: 12 }}>
                Remove
              </button>
            </div>
          ))}
          <form onSubmit={handleAddExperience} style={{ marginTop: 16, display: "grid", gap: 12 }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <input style={inputStyle} placeholder="Company" value={expCompany} onChange={(e) => setExpCompany(e.target.value)} />
              <input style={inputStyle} placeholder="Title" value={expTitle} onChange={(e) => setExpTitle(e.target.value)} />
            </div>
            <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
              <input style={{ ...inputStyle, flex: 1 }} placeholder="Start date (YYYY-MM)" value={expStart} onChange={(e) => setExpStart(e.target.value)} />
              <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "var(--color-text-muted)", whiteSpace: "nowrap" }}>
                <input type="checkbox" checked={expCurrent} onChange={(e) => setExpCurrent(e.target.checked)} />
                Current role
              </label>
            </div>
            <button type="submit" disabled={saving} className="btn-secondary" style={{ padding: "8px 16px", fontSize: 13, justifySelf: "start" }}>
              Add experience
            </button>
          </form>
        </Section>

        <Section title="Education">
          {profile?.education.map((edu: Education) => (
            <div key={edu.id} style={{ padding: "8px 0", borderBottom: "1px solid var(--color-border)" }}>
              <div style={{ fontSize: 14, color: "var(--color-text-heading)" }}>{edu.institution}</div>
              <div style={{ fontSize: 12, color: "var(--color-text-subtle)" }}>{edu.degree} {edu.end_year ? `· ${edu.end_year}` : ""}</div>
            </div>
          ))}
          <form onSubmit={handleAddEducation} style={{ marginTop: 16, display: "grid", gridTemplateColumns: "2fr 1fr 1fr", gap: 12 }}>
            <input style={inputStyle} placeholder="Institution" value={eduInstitution} onChange={(e) => setEduInstitution(e.target.value)} />
            <input style={inputStyle} placeholder="Degree" value={eduDegree} onChange={(e) => setEduDegree(e.target.value)} />
            <input style={inputStyle} type="number" placeholder="End year" value={eduEndYear} onChange={(e) => setEduEndYear(e.target.value)} />
            <button type="submit" disabled={saving} className="btn-secondary" style={{ padding: "8px 16px", fontSize: 13, gridColumn: "1 / -1", justifySelf: "start" }}>
              Add education
            </button>
          </form>
        </Section>
      </main>
    </div>
  );
}
