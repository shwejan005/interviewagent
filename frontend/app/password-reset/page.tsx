"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import Navbar from "../components/Navbar";
import { Button, GlassCard, Input } from "../components/ui";
import { ApiError, api } from "../../lib/api";

function PasswordResetForm() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const [email, setEmail] = useState(searchParams.get("email") || "");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [complete, setComplete] = useState(false);

  const handleRequest = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const result = await api.post<{ message: string }>(
        "/auth/password-reset/request",
        { email: email.trim() },
        { skipAuth: true },
      );
      setMessage(result.message);
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.detail : "The request could not be completed.");
    } finally {
      setLoading(false);
    }
  };

  const handleReset = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!token || loading) return;
    if (password !== confirmPassword) {
      setError("The passwords do not match.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const result = await api.post<{ message: string }>(
        "/auth/password-reset/confirm",
        { token, new_password: password },
        { skipAuth: true },
      );
      setMessage(result.message);
      setComplete(true);
      window.history.replaceState(null, "", "/password-reset");
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.detail : "The password could not be updated.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen">
      <Navbar />
      <main className="mx-auto w-full max-w-[460px] px-6 pb-20 pt-[132px]">
        <p className="eyebrow text-center">ACCOUNT SECURITY</p>
        <h1 className="mb-7 mt-2 text-center text-[28px] font-bold text-ink-heading">{token || complete ? "Choose a new password" : "Reset your password"}</h1>
        <GlassCard elevation="high" padding="lg">
          {error && <p role="alert" className="mb-4 rounded-xl border border-[rgba(239,68,68,0.25)] bg-[rgba(239,68,68,0.08)] p-3 text-[12px] text-[var(--color-error)]">{error}</p>}
          {token && !complete ? (
            <form onSubmit={handleReset} className="flex flex-col gap-4">
              <p className="text-[13px] leading-relaxed text-ink-muted">Choose a new password with at least 12 characters. Reset links expire after one hour and can be used once.</p>
              <Input
                id="new-password"
                type="password"
                label="NEW PASSWORD"
                autoComplete="new-password"
                minLength={12}
                maxLength={256}
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                hint="At least 12 characters. Length matters more than symbols."
              />
              <Input
                id="confirm-password"
                type="password"
                label="CONFIRM NEW PASSWORD"
                autoComplete="new-password"
                minLength={12}
                maxLength={256}
                required
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
              />
              <Button type="submit" fullWidth loading={loading} disabled={password.length < 12 || confirmPassword.length < 12}>Update password</Button>
              <Link href="/login" className="text-center text-[12px] text-brand hover:underline">Back to log in</Link>
            </form>
          ) : complete ? (
            <div role="status" aria-live="polite" className="flex flex-col gap-4">
              <p className="text-[13px] leading-relaxed text-ink-muted">{message}</p>
              <Link href="/login" className="btn-primary inline-flex justify-center no-underline">Continue to log in</Link>
            </div>
          ) : (
            <form onSubmit={handleRequest} className="flex flex-col gap-4">
              <p className="text-[13px] leading-relaxed text-ink-muted">Enter the address for your account. If an eligible account exists, reset instructions will be sent. This response does not reveal whether an account exists.</p>
              <Input
                id="reset-email"
                type="email"
                label="EMAIL"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
              {message && <p role="status" aria-live="polite" className="text-[12px] text-ink-muted">{message}</p>}
              <Button type="submit" fullWidth loading={loading}>Send reset instructions</Button>
              <Link href="/login" className="text-center text-[12px] text-brand hover:underline">Back to log in</Link>
            </form>
          )}
        </GlassCard>
      </main>
    </div>
  );
}

export default function PasswordResetPage() {
  return <Suspense fallback={null}><PasswordResetForm /></Suspense>;
}
