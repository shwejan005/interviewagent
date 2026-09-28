"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import Navbar from "../components/Navbar";
import { useAuth } from "../../lib/auth-context";
import { ApiError } from "../../lib/api";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await login(email, password);
      router.push(searchParams.get("next") || "/jobs");
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
          WELCOME BACK
        </div>
        <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--color-text-heading)", marginBottom: 24 }}>
          Log in
        </h1>

        <form onSubmit={handleSubmit}>
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
          <div style={{ marginBottom: 20 }}>
            <label htmlFor="password" style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--color-text-muted)", marginBottom: 6, fontFamily: "var(--font-mono)" }}>
              PASSWORD
            </label>
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={{ width: "100%", padding: "10px 14px", fontSize: 14, color: "var(--color-text-heading)", background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: 6, outline: "none" }}
            />
          </div>

          {error && (
            <div style={{ padding: "10px 14px", background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: 6, fontSize: 13, color: "var(--color-error)", marginBottom: 20 }}>
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="btn-primary"
            style={{ width: "100%", padding: "12px 20px", fontSize: 14, opacity: loading ? 0.6 : 1 }}
          >
            {loading ? "Logging in..." : "Log in"}
          </button>
        </form>

        <p style={{ fontSize: 13, color: "var(--color-text-muted)", marginTop: 20, textAlign: "center" }}>
          Don&apos;t have an account? <Link href="/register" style={{ color: "var(--color-primary)" }}>Sign up</Link>
        </p>
      </main>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}

