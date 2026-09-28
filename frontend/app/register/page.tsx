"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import Navbar from "../components/Navbar";
import { Button, GlassCard, Input } from "../components/ui";
import { useAuth } from "../../lib/auth-context";
import { ApiError } from "../../lib/api";
import { notify } from "../../lib/toast";
import { fadeUp, staggerContainer } from "../../lib/motion";

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

const INTENT_TABS: ReadonlyArray<{ value: Intent; label: string }> = [
  { value: "candidate", label: "I'm looking for a job" },
  { value: "recruiter", label: "I'm hiring talent" },
];

/**
 * Segmented persona switch. The active pill is a single shared-layout
 * element so it slides between tabs instead of blinking on/off.
 */
function IntentTabs({ intent, onChange }: Readonly<{ intent: Intent; onChange: (next: Intent) => void }>) {
  return (
    <div
      role="tablist"
      aria-label="I am signing up as a"
      className="glass-low flex gap-1 rounded-xl p-1"
    >
      {INTENT_TABS.map((tab) => {
        const active = intent === tab.value;
        return (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(tab.value)}
            className={`relative flex-1 rounded-lg px-3 py-2.5 text-[13px] font-semibold transition-colors duration-fast ease-out-expo ${
              active ? "text-[#0a0a0a]" : "text-ink-muted hover:text-ink"
            }`}
          >
            {active && (
              <motion.span
                layoutId="intent-tab-pill"
                transition={{ type: "spring", stiffness: 420, damping: 34 }}
                className="absolute inset-0 rounded-lg bg-[var(--color-primary)] shadow-glow-primary"
              />
            )}
            <span className="relative z-10">{tab.label}</span>
          </button>
        );
      })}
    </div>
  );
}

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

  const copy = COPY[intent];
  const loginHref = next ? `/login?next=${encodeURIComponent(next)}` : "/login";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
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
      notify.error(err instanceof ApiError ? err.detail : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen">
      <Navbar />
      <main className="mx-auto w-full max-w-[460px] px-6 pb-20 pt-[132px]">
        <motion.div initial="hidden" animate="visible" variants={staggerContainer(0.07)}>
          <motion.p variants={fadeUp} className="eyebrow text-center">
            {copy.eyebrow}
          </motion.p>

          {/* Persona selector — this is the onboarding fork: everything after
              this choice (redirect target, copy) depends on it, so it comes
              before any form field. */}
          <motion.div variants={fadeUp} className="mt-4">
            <IntentTabs intent={intent} onChange={setIntent} />
          </motion.div>

          <motion.h1
            variants={fadeUp}
            className="mt-7 text-center text-[28px] font-bold tracking-normal text-ink-heading"
          >
            {copy.heading}
          </motion.h1>
          <motion.p
            variants={fadeUp}
            className="mx-auto mb-7 mt-2.5 max-w-[42ch] text-center text-[13px] leading-[1.65] text-ink-muted"
          >
            {copy.subtext}
          </motion.p>

          <motion.div variants={fadeUp}>
            <GlassCard elevation="high" padding="lg">
              <form onSubmit={handleSubmit} className="flex flex-col gap-5">
                <Input
                  id="fullName"
                  type="text"
                  label="FULL NAME"
                  autoComplete="name"
                  placeholder="Jane Doe"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                />
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
                  autoComplete="new-password"
                  required
                  minLength={12}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  hint="At least 12 characters. Length matters more than symbols."
                />

                <Button
                  type="submit"
                  size="lg"
                  fullWidth
                  loading={loading}
                  disabled={password.length < 12}
                >
                  {loading ? "Creating account..." : copy.cta}
                </Button>
              </form>
            </GlassCard>
          </motion.div>

          {intent === "recruiter" && (
            <motion.p variants={fadeUp} className="mt-4 text-[12px] leading-[1.65] text-ink-subtle">
              One account, two hats: you can also build a candidate profile later from the same login —
              recruiting and job-seeking access are independent of each other.
            </motion.p>
          )}

          <motion.p variants={fadeUp} className="mt-6 text-center text-[13px] text-ink-muted">
            Already have an account?{" "}
            <Link href={loginHref} className="text-brand hover:underline">
              Log in
            </Link>
          </motion.p>
        </motion.div>
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
