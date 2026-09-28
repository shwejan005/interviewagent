"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Navbar from "../components/Navbar";
import { useAuth } from "../../lib/auth-context";
import { api, ApiError } from "../../lib/api";
import type { Campaign, JobPosting } from "../../lib/types";

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
    <div className="card-surface" style={{ padding: 24, maxWidth: 480 }}>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-primary)", letterSpacing: "0.05em", marginBottom: 16 }}>
        CREATE AN ORGANIZATION
      </div>
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: 12 }}>
          <input
            style={inputStyle}
            placeholder="Company name"
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              if (!slug) setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, ""));
            }}
          />
        </div>
        <div style={{ marginBottom: 12 }}>
          <input
            style={inputStyle}
            placeholder="url-slug"
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
          />
        </div>
        {error && <p style={{ fontSize: 12, color: "var(--color-error)", marginBottom: 12 }}>{error}</p>}
        <button type="submit" disabled={saving || !name || !slug} className="btn-primary" style={{ padding: "10px 20px", fontSize: 13 }}>
          {saving ? "Creating..." : "Create organization"}
        </button>
      </form>
    </div>
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

  if (actor && actor.memberships.length === 0) {
    return (
      <div style={{ minHeight: "100vh", background: "var(--color-bg)" }}>
        <Navbar />
        <main style={{ maxWidth: 720, margin: "0 auto", padding: "100px 24px 60px" }}>
          <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--color-text-heading)", marginBottom: 8 }}>
            Recruiter workspace
          </h1>
          <p style={{ fontSize: 13, color: "var(--color-text-muted)", marginBottom: 24 }}>
            You&apos;re not part of an organization yet. Create one to start posting jobs.
          </p>
          <CreateOrgForm onCreated={() => refreshActor()} />
        </main>
      </div>
    );
  }

  if (!activeOrgId) {
    return (
      <div style={{ minHeight: "100vh", background: "var(--color-bg)" }}>
        <Navbar />
        <main style={{ maxWidth: 720, margin: "0 auto", padding: "100px 24px 60px" }}>
          <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--color-text-heading)", marginBottom: 16 }}>
            Select an organization
          </h1>
          <p style={{ fontSize: 13, color: "var(--color-text-muted)" }}>
            Use the organization switcher in the top navigation bar to choose a workspace.
          </p>
        </main>
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)" }}>
      <Navbar />
      <main style={{ maxWidth: 780, margin: "0 auto", padding: "100px 24px 60px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24 }}>
          <div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-primary)", letterSpacing: "0.1em", marginBottom: 8 }}>
              RECRUITER WORKSPACE
            </div>
            <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--color-text-heading)" }}>Campaigns</h1>
          </div>
          <Link href="/org/analytics" className="btn-secondary" style={{ padding: "8px 16px", fontSize: 13 }}>
            Analytics
          </Link>
        </div>

        {error && (
          <div style={{ padding: "10px 14px", background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: 6, fontSize: 13, color: "var(--color-error)", marginBottom: 20 }}>
            {error}
          </div>
        )}

        <form onSubmit={handleCreateCampaign} style={{ display: "flex", gap: 8, marginBottom: 24 }}>
          <input
            style={{ ...inputStyle, flex: 1 }}
            placeholder="New campaign name (e.g. Q4 Backend Expansion)"
            value={newCampaignName}
            onChange={(e) => setNewCampaignName(e.target.value)}
          />
          <button type="submit" disabled={creatingCampaign} className="btn-primary" style={{ padding: "10px 20px", fontSize: 13 }}>
            Create campaign
          </button>
        </form>

        {loading ? (
          <p style={{ color: "var(--color-text-muted)" }}>Loading...</p>
        ) : campaigns.length === 0 ? (
          <p style={{ color: "var(--color-text-muted)", fontSize: 14 }}>No campaigns yet.</p>
        ) : (
          campaigns.map((campaign) => (
            <div key={campaign.id} className="card-surface" style={{ padding: 20, marginBottom: 16 }}>
              <div style={{ fontSize: 15, fontWeight: 600, color: "var(--color-text-heading)", marginBottom: 12 }}>
                {campaign.name}
              </div>
              {(postingsByCampaign[campaign.id] || []).map((posting) => (
                <div key={posting.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 0", borderBottom: "1px solid var(--color-border)" }}>
                  <Link href={`/org/postings/${posting.id}`} style={{ fontSize: 13, color: "var(--color-text-heading)", textDecoration: "none" }}>
                    {posting.title}
                  </Link>
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <span className={`status-tag ${posting.status === "PUBLISHED" ? "status-tag-success" : posting.status === "CLOSED" ? "status-tag-muted" : "status-tag-warning"}`}>
                      {posting.status}
                    </span>
                    {posting.status === "DRAFT" && (
                      <button onClick={() => handlePublish(posting.id, "PUBLISHED")} className="btn-secondary" style={{ padding: "4px 10px", fontSize: 11 }}>
                        Publish
                      </button>
                    )}
                    {posting.status === "PUBLISHED" && (
                      <button onClick={() => handlePublish(posting.id, "CLOSED")} className="btn-secondary" style={{ padding: "4px 10px", fontSize: 11 }}>
                        Close
                      </button>
                    )}
                  </div>
                </div>
              ))}
              <NewPostingRow campaignId={campaign.id} onCreate={handleCreatePosting} />
            </div>
          ))
        )}
      </main>
    </div>
  );
}

function NewPostingRow({ campaignId, onCreate }: Readonly<{ campaignId: number; onCreate: (campaignId: number, title: string) => Promise<void> }>) {
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
    <form onSubmit={handleSubmit} style={{ display: "flex", gap: 8, marginTop: 12 }}>
      <input
        style={{ ...inputStyle, flex: 1 }}
        placeholder="New posting title"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />
      <button type="submit" disabled={saving || !title.trim()} className="btn-secondary" style={{ padding: "8px 16px", fontSize: 12 }}>
        Add posting
      </button>
    </form>
  );
}
