"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Navbar from "../components/Navbar";
import { Button, EmptyState, GlassCard, PageHeader, PageShell } from "../components/ui";
import { useAuth } from "../../lib/auth-context";
import { ApiError, api } from "../../lib/api";
import type { UserNotification } from "../../lib/types";

type NotificationInbox = {
  notifications: UserNotification[];
  unread_count: number;
  has_more: boolean;
};

export default function NotificationsPage() {
  const router = useRouter();
  const { actor, loading: authLoading } = useAuth();
  const [inbox, setInbox] = useState<NotificationInbox>({ notifications: [], unread_count: 0, has_more: false });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);

  const load = useCallback(async (nextOffset = 0, append = false) => {
    if (!actor) return;
    setLoading(true);
    try {
      const page = await api.get<NotificationInbox>(`/me/notifications?limit=20&offset=${nextOffset}`);
      setInbox((current) => ({
        ...page,
        notifications: append ? [...current.notifications, ...page.notifications] : page.notifications,
      }));
      setOffset(nextOffset);
      setError(null);
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.detail : "Notifications could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [actor]);

  useEffect(() => {
    if (authLoading) return;
    if (!actor) {
      router.replace("/login?next=%2Fnotifications");
      return;
    }
    void load(0);
  }, [actor, authLoading, load, router]);

  const openNotification = async (notification: UserNotification) => {
    if (!notification.read_at) {
      setInbox((current) => ({
        ...current,
        unread_count: Math.max(0, current.unread_count - 1),
        notifications: current.notifications.map((item) => item.id === notification.id
          ? { ...item, read_at: new Date().toISOString() }
          : item),
      }));
      try {
        await api.post(`/me/notifications/${notification.id}/read`);
      } catch {
        await load(offset);
      }
    }
    router.push(notification.href);
  };

  const markAllRead = async () => {
    setInbox((current) => ({
      ...current,
      unread_count: 0,
      notifications: current.notifications.map((item) => ({ ...item, read_at: item.read_at || new Date().toISOString() })),
    }));
    try {
      await api.post("/me/notifications/read-all");
    } catch {
      await load(offset);
    }
  };

  return (
    <div className="min-h-screen">
      <Navbar />
      <PageShell className="!max-w-[880px] pt-[112px]">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <PageHeader eyebrow="INBOX" title="Notifications" description="Important updates for your applications and workspace." />
          {inbox.unread_count > 0 && <Button variant="secondary" onClick={() => void markAllRead()}>Mark all read</Button>}
        </div>
        <p className="mt-2 text-[12px] text-ink-subtle">{inbox.unread_count} unread</p>
        {error && <p role="alert" className="mt-5 text-[13px] text-[var(--color-error)]">{error}</p>}
        {inbox.notifications.length === 0 && !loading ? (
          <EmptyState className="mt-6" title="You’re all caught up" description="New application updates will appear here." />
        ) : (
          <div className="mt-5 flex flex-col gap-3">
            {inbox.notifications.map((notification) => (
              <button key={notification.id} type="button" onClick={() => void openNotification(notification)} className="text-left">
                <GlassCard padding="md" className={`transition-colors hover:border-strong ${notification.read_at ? "opacity-80" : "border-[rgba(140,198,255,0.3)]"}`}>
                  <div className="flex items-start gap-3">
                    <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${notification.read_at ? "bg-transparent" : "bg-brand"}`} />
                    <span className="min-w-0 flex-1">
                      <span className="block text-[13px] font-semibold text-ink-heading">{notification.title}</span>
                      <span className="mt-1 block text-[12px] leading-relaxed text-ink-muted">{notification.body}</span>
                      <time className="mono mt-3 block text-[10px] text-ink-subtle" dateTime={notification.created_at}>{new Date(notification.created_at).toLocaleString()}</time>
                    </span>
                  </div>
                </GlassCard>
              </button>
            ))}
          </div>
        )}
        {inbox.has_more && <div className="mt-6 flex justify-center"><Button variant="secondary" loading={loading} onClick={() => void load(offset + 20, true)}>Load more</Button></div>}
      </PageShell>
    </div>
  );
}
