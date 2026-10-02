"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Bell, CheckCheck } from "lucide-react";
import { useAuth } from "../../lib/auth-context";
import { api } from "../../lib/api";
import type { UserNotification } from "../../lib/types";

type NotificationInbox = {
  notifications: UserNotification[];
  unread_count: number;
  has_more: boolean;
};

export default function NotificationBell({ light = false }: Readonly<{ light?: boolean }>) {
  const { actor } = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [inbox, setInbox] = useState<NotificationInbox>({ notifications: [], unread_count: 0, has_more: false });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const loadInbox = useCallback(async () => {
    if (!actor) return;
    setLoading(true);
    try {
      const response = await api.get<NotificationInbox>("/me/notifications?limit=6");
      setInbox(response);
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [actor]);

  useEffect(() => {
    if (actor) void loadInbox();
    else setInbox({ notifications: [], unread_count: 0, has_more: false });
  }, [actor, loadInbox]);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const markRead = async (notificationId: number) => {
    setInbox((current) => ({
      ...current,
      unread_count: Math.max(0, current.unread_count - (current.notifications.some((item) => item.id === notificationId && !item.read_at) ? 1 : 0)),
      notifications: current.notifications.map((item) => item.id === notificationId && !item.read_at
        ? { ...item, read_at: new Date().toISOString() }
        : item),
    }));
    try {
      await api.post(`/me/notifications/${notificationId}/read`);
    } catch {
      await loadInbox();
    }
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
      await loadInbox();
    }
  };

  if (!actor) return null;

  const buttonTone = light ? "text-[#778695] hover:bg-[#f1f4f6] hover:text-[#263342]" : "text-ink-muted hover:bg-glass-low hover:text-ink-heading";

  return (
    <div ref={wrapperRef} className="relative">
      <button
        type="button"
        aria-label={inbox.unread_count ? `Notifications, ${inbox.unread_count} unread` : "Notifications"}
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => { setOpen((value) => !value); if (!open) void loadInbox(); }}
        className={`relative rounded-lg p-2 transition-colors ${buttonTone}`}
      >
        <Bell size={17} />
        {inbox.unread_count > 0 && <span className="absolute -right-0.5 -top-0.5 flex min-h-4 min-w-4 items-center justify-center rounded-full bg-[#ef8f3c] px-1 text-[9px] font-bold text-[#132337]">{inbox.unread_count > 9 ? "9+" : inbox.unread_count}</span>}
      </button>

      {open && (
        <section
          role="dialog"
          aria-label="Notifications"
          className="absolute right-0 top-[calc(100%+10px)] z-[90] w-[min(360px,calc(100vw-32px))] overflow-hidden rounded-2xl border border-subtle bg-[#111722] shadow-[0_18px_50px_rgba(0,0,0,0.3)]"
        >
          <div className="flex items-center justify-between border-b border-subtle px-4 py-3">
            <div>
              <p className="text-[13px] font-semibold text-ink-heading">Notifications</p>
              <p className="mt-0.5 text-[10px] text-ink-subtle">{inbox.unread_count} unread</p>
            </div>
            {inbox.unread_count > 0 && <button type="button" onClick={() => void markAllRead()} className="text-[10px] font-semibold text-brand hover:underline">Mark all read</button>}
          </div>
          {loading && inbox.notifications.length === 0 ? (
            <p role="status" className="px-4 py-6 text-[12px] text-ink-subtle">Loading notifications…</p>
          ) : error && inbox.notifications.length === 0 ? (
            <p role="alert" className="px-4 py-6 text-[12px] text-ink-subtle">Notifications could not be loaded. Try again.</p>
          ) : inbox.notifications.length === 0 ? (
            <p className="px-4 py-6 text-[12px] text-ink-subtle">You’re all caught up.</p>
          ) : (
            <ul className="max-h-[360px] overflow-y-auto">
              {inbox.notifications.map((notification) => (
                <li key={notification.id} className="border-b border-subtle/70 last:border-0">
                  <Link
                    href={notification.href}
                    onClick={() => { void markRead(notification.id); setOpen(false); }}
                    className={`block px-4 py-3 transition-colors hover:bg-glass-low ${notification.read_at ? "opacity-75" : "bg-[rgba(140,198,255,0.05)]"}`}
                  >
                    <div className="flex items-start gap-3">
                      <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${notification.read_at ? "bg-transparent" : "bg-brand"}`} />
                      <span className="min-w-0 flex-1">
                        <span className="block text-[12px] font-semibold text-ink-heading">{notification.title}</span>
                        <span className="mt-1 block text-[11px] leading-relaxed text-ink-muted">{notification.body}</span>
                        <time className="mono mt-2 block text-[9px] text-ink-subtle" dateTime={notification.created_at}>{new Date(notification.created_at).toLocaleString()}</time>
                      </span>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
          <div className="border-t border-subtle px-4 py-2.5">
            <button type="button" onClick={() => { setOpen(false); router.push("/notifications"); }} className="flex w-full items-center justify-center gap-2 text-[11px] font-semibold text-brand hover:underline">
              <CheckCheck size={13} /> View all notifications{inbox.has_more ? "" : ""}
            </button>
          </div>
        </section>
      )}
    </div>
  );
}
