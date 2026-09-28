"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import Navbar from "../components/Navbar";
import { Alert, Button, GlassCard, Input } from "../components/ui";
import { useAuth } from "../../lib/auth-context";
import { ApiError } from "../../lib/api";
import { fadeUp, staggerContainer } from "../../lib/motion";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const next = searchParams.get("next");
  const registerHref = next ? `/register?next=${encodeURIComponent(next)}` : "/register";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await login(email, password);
      router.push(next || "/jobs");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen">
      <Navbar />
      <main className="mx-auto w-full max-w-[440px] px-6 pb-20 pt-[132px]">
        <motion.div initial="hidden" animate="visible" variants={staggerContainer(0.07)}>
          <motion.p variants={fadeUp} className="eyebrow text-center">
            WELCOME BACK
          </motion.p>
          <motion.h1
            variants={fadeUp}
            className="mb-7 mt-2 text-center text-[28px] font-bold tracking-[-0.02em] text-ink-heading"
          >
            Log in
          </motion.h1>

          <motion.div variants={fadeUp}>
            <GlassCard elevation="high" padding="lg">
              <form onSubmit={handleSubmit} className="flex flex-col gap-5">
                <Input
                  id="email"
                  type="email"
                  label="EMAIL"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
                <Input
                  id="password"
                  type="password"
                  label="PASSWORD"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />

                {error && <Alert tone="error">{error}</Alert>}

                <Button type="submit" size="lg" fullWidth loading={loading}>
                  {loading ? "Logging in..." : "Log in"}
                </Button>
              </form>
            </GlassCard>
          </motion.div>

          <motion.p variants={fadeUp} className="mt-6 text-center text-[13px] text-ink-muted">
            Don&apos;t have an account?{" "}
            <Link href={registerHref} className="text-brand hover:underline">
              Sign up
            </Link>
          </motion.p>
        </motion.div>
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

