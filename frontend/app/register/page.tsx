"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Navbar from "../components/Navbar";
import { useAuth } from "../../lib/auth-context";
import { ApiError } from "../../lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const { register } = useAuth();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await register(email, password, fullName);
      router.push("/jobs");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)" }}>
      <Navbar />
      <main style={{ maxWidth: 420, margin: "0 auto", padding: "120px 24px 60px" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-primary)", letterSpacing: "0.1em", marginBottom: 8 }}>
          GET STARTED — FREE
        </div>
        <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--color-text-heading)", marginBottom: 8 }}>
          Create your account
        </h1>
        <p style={{ fontSize: 13, color: "var(--color-text-muted)", marginBottom: 24 }}>
          Try Evalia free — build your profile, discover matched roles, and track every application in one place.
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
            {loading ? "Creating account..." : "Create free account"}
          </button>
        </form>

        <p style={{ fontSize: 13, color: "var(--color-text-muted)", marginTop: 20, textAlign: "center" }}>
          Already have an account? <Link href="/login" style={{ color: "var(--color-primary)" }}>Log in</Link>
        </p>
      </main>
    </div>
  );
}
