"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Navbar from "../components/Navbar";
import { Button, EmptyState, GlassCard, PageShell } from "../components/ui";
import { useAuth } from "../../lib/auth-context";
import { api, ApiError } from "../../lib/api";
import { notify } from "../../lib/toast";

function InviteForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { actor, loading: authLoading } = useAuth();
  const [loading, setLoading] = useState(false);
  const token = params.get("token") || "";
  const invitePath = `/invite?token=${token}`;
  const loginPath = `/login?next=${encodeURIComponent(invitePath)}`;

  const accept = async () => {
    setLoading(true);
    try {
      await api.post("/auth/invitations/accept", { token });
      notify.success("Invitation accepted.");
      router.push("/org");
    } catch (error) {
      notify.error(error instanceof ApiError ? error.detail : "Could not accept invitation.");
    } finally {
      setLoading(false);
    }
  };

  if (authLoading) return null;
  if (!actor) {
    return (
      <div className="min-h-screen">
        <Navbar />
        <PageShell className="!max-w-[560px] pt-[132px]">
          <EmptyState
            title="Log in to accept this invitation"
            description="Use the email address that received the invitation, then open this link again."
            action={<Button onClick={() => router.push(loginPath)}>Log in</Button>}
          />
        </PageShell>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Navbar />
      <PageShell className="!max-w-[560px] pt-[132px]">
        <GlassCard elevation="high" padding="lg">
          <p className="eyebrow">ORGANIZATION INVITATION</p>
          <h1 className="mt-3 text-[26px] font-bold text-ink-heading">Join your hiring team</h1>
          <p className="mt-3 text-[13px] leading-[1.7] text-ink-muted">
            Accept this invitation to add the organization workspace to your account.
          </p>
          <Button className="mt-6" size="lg" onClick={accept} loading={loading} disabled={!token}>
            Accept invitation
          </Button>
        </GlassCard>
      </PageShell>
    </div>
  );
}

export default function InvitePage() {
  return (
    <Suspense fallback={null}>
      <InviteForm />
    </Suspense>
  );
}
