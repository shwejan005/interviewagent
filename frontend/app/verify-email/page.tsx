"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import Navbar from "../components/Navbar";
import { Button, GlassCard, Input } from "../components/ui";
import { ApiError, api } from "../../lib/api";

type PageState = "verifying" | "verified" | "invalid" | "resend";

function VerifyEmailForm() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const requestedEmail = searchParams.get("email") || "";
  const next = searchParams.get("next");
  const processedToken = useRef<string | null>(null);
  const [email, setEmail] = useState(requestedEmail);
  const [state, setState] = useState<PageState>(token ? "verifying" : "resend");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!token || processedToken.current === token) return;
    processedToken.current = token;
    setState("verifying");
    api.post<{ message: string }>("/auth/verify-email", { token }, { skipAuth: true })
      .then((result) => {
        setMessage(result.message);
        setState("verified");
      })
      .catch((requestError: unknown) => {
        setError(requestError instanceof ApiError ? requestError.detail : "This verification link could not be checked.");
        setState("invalid");
      });
  }, [token]);

  const handleResend = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const result = await api.post<{ message: string }>(
        "/auth/email-verification/resend",
        { email: email.trim() },
        { skipAuth: true },
      );
      setMessage(result.message);
      setState("resend");
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.detail : "The request could not be completed.");
    } finally {
      setLoading(false);
    }
  };

  const loginHref = next ? `/login?next=${encodeURIComponent(next)}` : "/login";

  return (
    <div className="min-h-screen">
      <Navbar />
      <main className="mx-auto w-full max-w-[460px] px-6 pb-20 pt-[132px]">
        <p className="eyebrow text-center">ACCOUNT SECURITY</p>
        <h1 className="mb-7 mt-2 text-center text-[28px] font-bold text-ink-heading">Verify your email</h1>
        <GlassCard elevation="high" padding="lg">
          {state === "verifying" ? (
            <p role="status" aria-live="polite" className="text-[13px] text-ink-muted">Checking your one-time verification link…</p>
          ) : null}
          {state === "verified" ? (
            <div role="status" aria-live="polite" className="flex flex-col gap-4">
              <p className="text-[13px] leading-relaxed text-ink-muted">{message}</p>
              <Link href={loginHref} className="btn-primary inline-flex justify-center no-underline">Continue to log in</Link>
            </div>
          ) : null}
          {state === "invalid" ? (
            <div className="mb-4 rounded-xl border border-[rgba(239,68,68,0.25)] bg-[rgba(239,68,68,0.08)] p-3 text-[12px] text-[var(--color-error)]" role="alert">
              {error || "This link has expired or was already used. Request a new one below."}
            </div>
          ) : null}
          {state !== "verified" && state !== "verifying" ? (
            <form onSubmit={handleResend} className="flex flex-col gap-4">
              <p className="text-[13px] leading-relaxed text-ink-muted">Enter the address used to register. If it needs verification, we’ll send a fresh link. This response does not reveal whether an account exists.</p>
              <Input
                id="verification-email"
                type="email"
                label="EMAIL"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
              {message && <p role="status" aria-live="polite" className="text-[12px] text-ink-muted">{message}</p>}
              {error && state !== "invalid" && <p role="alert" className="text-[12px] text-[var(--color-error)]">{error}</p>}
              <Button type="submit" fullWidth loading={loading}>Resend verification link</Button>
              <Link href={loginHref} className="text-center text-[12px] text-brand hover:underline">Back to log in</Link>
            </form>
          ) : null}
        </GlassCard>
      </main>
    </div>
  );
}

export default function VerifyEmailPage() {
  return <Suspense fallback={null}><VerifyEmailForm /></Suspense>;
}
