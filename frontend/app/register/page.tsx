"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import Navbar from "../components/Navbar";
import { useAuth } from "../../lib/auth-context";
import { ApiError } from "../../lib/api";

type Intent = "candidate" | "recruiter";

const COPY: Record<Intent, { eyebrow: string; heading: string; subtext: string; cta: string }> = {
  candidate: {
    eyebrow: "GET STARTED — FREE",
    heading: "Find your next role",
    subtext: "Build your profile once, get matched to roles, and apply in one click — every application pre-fills from what you enter here.",
    cta: "Create free account",
  },
  recruiter: {
    eyebrow: "GET STARTED — FREE",
    heading: "Start hiring on Evalia",
    subtext: "Create your organization, post roles, and screen candidates with AI-assisted evaluation and a real applicant pipeline.",
    cta: "Create recruiter account",
  },
};

function RegisterForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { register } = useAuth();

  const requestedIntent = searchParams.get("intent");
  const next = searchParams.get("next");
  const [intent, setIntent] = useState<Intent>(requestedIntent === "recruiter" ? "recruiter" : "candidate");

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const copy = COPY[intent];
  const loginHref = next ? `/login?next=${encodeURIComponent(next)}` : "/login";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await register(email, password, fullName);
      // A deep-link (e.g. "log in to apply to this job") always wins over the
      // persona default — the candidate already told us what they came for.
      if (next) {
        router.push(next);
      } else if (intent === "recruiter") {
        router.push("/org");
      } else {
        router.push("/profile");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)" }}>
      <Navbar />
      <main style={{ maxWidth: 440, margin: "0 auto", padding: "120px 24px 60px" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-primary)", letterSpacing: "0.1em", marginBottom: 8 }}>
          {copy.eyebrow}
        </div>

        {/* Persona selector — this is the onboarding fork: everything after
            this choice (redirect target, copy) depends on it, so it comes
            before any form field. */}
        <div
          role="tablist"
          aria-label="I am signing up as a"
          style={{ display: "flex", gap: 8, marginBottom: 20, padding: 4, background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: 8 }}
        >
          <button
            type="button"
            role="tab"
            aria-selected={intent === "candidate"}
            onClick={() => setIntent("candidate")}
            style={{
              flex: 1, padding: "10px 12px", fontSize: 13, fontWeight: 600, borderRadius: 6, border: "none", cursor: "pointer",
              background: intent === "candidate" ? "var(--color-primary)" : "transparent",
              color: intent === "candidate" ? "#0a0a0a" : "var(--color-text-muted)",
            }}
          >
            I&apos;m looking for a job
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={intent === "recruiter"}
            onClick={() => setIntent("recruiter")}
            style={{
              flex: 1, padding: "10px 12px", fontSize: 13, fontWeight: 600, borderRadius: 6, border: "none", cursor: "pointer",
              background: intent === "recruiter" ? "var(--color-primary)" : "transparent",
              color: intent === "recruiter" ? "#0a0a0a" : "var(--color-text-muted)",
            }}
          >
            I&apos;m hiring talent
          </button>
        </div>

        <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--color-text-heading)", marginBottom: 8 }}>
          {copy.heading}
        </h1>
        <p style={{ fontSize: 13, color: "var(--color-text-muted)", marginBottom: 24, lineHeight: 1.6 }}>
          {copy.subtext}
        </p>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 16 }}>
            <label htmlFor="fullName" style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--color-text-muted)", marginBottom: 6, fontFamily: "var(--font-mono)" }}>
              FULL NAME
            </label>
            <input
              id="fullName"
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Jane Doe"
              style={{ width: "100%", padding: "10px 14px", fontSize: 14, color: "var(--color-text-heading)", background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: 6, outline: "none" }}
            />
          </div>
          <div style={{ marginBottom: 16 }}>
            <label htmlFor="email" style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--color-text-muted)", marginBottom: 6, fontFamily: "var(--font-mono)" }}>
              EMAIL
            </label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={{ width: "100%", padding: "10px 14px", fontSize: 14, color: "var(--color-text-heading)", background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: 6, outline: "none" }}
            />
          </div>
          <div style={{ marginBottom: 8 }}>
            <label htmlFor="password" style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--color-text-muted)", marginBottom: 6, fontFamily: "var(--font-mono)" }}>
              PASSWORD
            </label>
            <input
              id="password"
              type="password"
              required
              minLength={12}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={{ width: "100%", padding: "10px 14px", fontSize: 14, color: "var(--color-text-heading)", background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: 6, outline: "none" }}
            />
          </div>
          <p style={{ fontSize: 11, color: "var(--color-text-subtle)", marginBottom: 20 }}>
            At least 12 characters. Length matters more than symbols.
          </p>

          {error && (
            <div style={{ padding: "10px 14px", background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: 6, fontSize: 13, color: "var(--color-error)", marginBottom: 20 }}>
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading || password.length < 12}
            className="btn-primary"
            style={{ width: "100%", padding: "12px 20px", fontSize: 14, opacity: loading || password.length < 12 ? 0.6 : 1 }}
          >
            {loading ? "Creating account..." : copy.cta}
          </button>
        </form>

        {intent === "recruiter" && (
          <p style={{ fontSize: 12, color: "var(--color-text-subtle)", marginTop: 16, lineHeight: 1.6 }}>
            One account, two hats: you can also build a candidate profile later from the same login —
            recruiting and job-seeking access are independent of each other.
          </p>
        )}

        <p style={{ fontSize: 13, color: "var(--color-text-muted)", marginTop: 20, textAlign: "center" }}>
          Already have an account? <Link href={loginHref} style={{ color: "var(--color-primary)" }}>Log in</Link>
        </p>
      </main>
    </div>
  );
}

export default function RegisterPage() {
  return (
    <Suspense fallback={null}>
      <RegisterForm />
    </Suspense>
  );
}
