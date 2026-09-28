"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";

import { useAuth } from "../../lib/auth-context";
import type { Actor, Membership } from "../../lib/types";
import { DUR, EASE_OUT } from "../../lib/motion";

const GUEST_LINKS = [
  { href: "/", label: "Overview" },
  { href: "/jobs", label: "Jobs" },
];

const CANDIDATE_LINKS = [
  { href: "/jobs", label: "Jobs" },
  { href: "/applications", label: "Applications" },
  { href: "/referrals", label: "Referrals" },
  { href: "/profile", label: "Profile" },
];

const RECRUITER_LINKS = [
  { href: "/org", label: "Overview" },
  { href: "/org/referrals", label: "Referrals" },
  { href: "/org/analytics", label: "Analytics" },
];

const INDICATOR_CLASS =
  "absolute -bottom-px left-0 right-0 h-[2px] rounded-full bg-[var(--color-primary)] shadow-glow-primary";
const INDICATOR_SPRING = { type: "spring", stiffness: 420, damping: 34 } as const;

function NavLink({ href, label, active }: Readonly<{ href: string; label: string; active: boolean }>) {
  return (
    <Link
      href={href}
      className={`relative py-2 text-[13px] transition-colors duration-fast ease-out-expo ${
        active ? "font-semibold text-ink-heading" : "text-ink-muted hover:text-ink-heading"
      }`}
    >
      {label}
      {/* Shared layoutId slides the underline between links rather than
          blinking it out and back in. */}
      {active && <motion.span layoutId="nav-active-indicator" className={INDICATOR_CLASS} transition={INDICATOR_SPRING} />}
    </Link>
  );
}

function DesktopAuthArea({
  loading, actor, activeOrgId, activeMembership, switchOrg, handleLogout,
}: Readonly<{
  loading: boolean;
  actor: Actor | null;
  activeOrgId: number | null;
  activeMembership: Membership | undefined;
  switchOrg: (orgId: number | null) => void;
  handleLogout: () => void;
}>) {
  if (loading) {
    return <div className="skeleton h-7 w-28" />;
  }

  if (!actor) {
    return (
      <>
        <Link
          href="/register?intent=recruiter"
          className="text-[13px] text-ink-muted transition-colors duration-fast ease-out-expo hover:text-ink-heading"
        >
          For recruiters
        </Link>
        <Link
          href="/login"
          className="text-[13px] text-ink-muted transition-colors duration-fast ease-out-expo hover:text-ink-heading"
        >
          Log in
        </Link>
        <Link href="/register?intent=candidate" className="btn-primary !px-4 !py-1.5 !text-[12px]">
          Sign up
        </Link>
      </>
    );
  }

  return (
    <>
      {actor.memberships.length > 0 && (
        <select
          aria-label="Active organization"
          value={activeOrgId ?? ""}
          onChange={(e) => switchOrg(e.target.value ? Number(e.target.value) : null)}
          className="field !w-auto !py-1.5 !text-[12px] [&>option]:bg-[var(--color-bg-muted)]"
        >
          <option value="">Personal</option>
          {actor.memberships.map((m) => (
            <option key={m.org_id} value={m.org_id}>
              {m.org_name} ({m.role_name})
            </option>
          ))}
        </select>
      )}
      <span className="mono text-[12px] text-ink-subtle">
        {actor.full_name || actor.email}
        {activeMembership ? ` · ${activeMembership.role_name}` : ""}
      </span>
      <button onClick={handleLogout} className="btn-secondary !px-4 !py-1.5 !text-[12px]">
        Log out
      </button>
    </>
  );
}

export default function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const { actor, loading, logout, switchOrg, activeOrgId } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  // The bar stays near-invisible over the hero and thickens into glass once
  // there is content behind it to separate from.
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // Declared before the early return below so hook order stays stable.
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  // Don't show navbar during active interview rounds
  if (pathname.startsWith("/round/")) return null;

  const activeMembership = actor?.memberships.find((m) => m.org_id === activeOrgId);
  const recruiterMode = Boolean(actor && activeMembership);
  let links = GUEST_LINKS;
  if (actor) links = recruiterMode ? RECRUITER_LINKS : CANDIDATE_LINKS;
  const orgActive = pathname.startsWith("/org");

  const handleLogout = () => {
    logout();
    router.push("/");
  };

  return (
    <nav
      className={`fixed inset-x-0 top-0 z-50 border-b transition-all duration-base ease-out-expo ${
        scrolled
          ? "border-subtle bg-[rgba(7,8,16,0.72)] backdrop-blur-[16px] backdrop-saturate-150"
          : "border-transparent bg-transparent"
      }`}
    >
      <div className="mx-auto flex h-14 max-w-[var(--max-width)] items-center justify-between px-6">
        {/* Brand */}
        <Link href="/" className="group flex items-center gap-2.5">
          <span className="mono text-[14px] font-bold tracking-normal text-brand transition-[text-shadow] duration-base ease-out-expo group-hover:[text-shadow:0_0_16px_rgba(249,115,22,0.6)]">
            EVALIA
          </span>
          <span className="text-[12px] text-ink-subtle/50">/</span>
          <span className="mono text-[12px] text-ink-subtle">v2.0</span>
        </Link>

        {/* Desktop Links */}
        <div className="hidden items-center gap-7 md:flex">
          {links.map((link) => (
            <NavLink key={link.href} href={link.href} label={link.label} active={pathname === link.href} />
          ))}
          {actor && actor.memberships.length > 0 && !recruiterMode && (
            <Link
              href="/org"
              className={`relative py-2 text-[13px] transition-colors duration-fast ease-out-expo ${
                orgActive ? "font-semibold text-brand" : "text-ink-muted hover:text-ink-heading"
              }`}
            >
              Recruiter workspace
              {orgActive && (
                <motion.span layoutId="nav-active-indicator" className={INDICATOR_CLASS} transition={INDICATOR_SPRING} />
              )}
            </Link>
          )}
        </div>

        {/* Auth area */}
        <div className="hidden items-center gap-3 md:flex">
          <DesktopAuthArea
            loading={loading}
            actor={actor}
            activeOrgId={activeOrgId}
            activeMembership={activeMembership}
            switchOrg={switchOrg}
            handleLogout={handleLogout}
          />
        </div>

        {/* Mobile toggle */}
        <button
          className="mono cursor-pointer border-none bg-transparent text-[13px] text-ink md:hidden"
          onClick={() => setMobileOpen(!mobileOpen)}
          aria-expanded={mobileOpen}
          aria-label={mobileOpen ? "Close menu" : "Open menu"}
        >
          {mobileOpen ? "CLOSE" : "MENU"}
        </button>
      </div>

      {/* Mobile Drawer — absolutely positioned so the entrance is a transform
          rather than an animated height, which would relayout every frame. */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            key="drawer"
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: DUR.base, ease: EASE_OUT }}
            className="absolute inset-x-0 top-full flex flex-col gap-3 border-b border-subtle bg-[rgba(7,8,16,0.92)] px-6 py-5 backdrop-blur-[20px] backdrop-saturate-150 md:hidden"
          >
            {links.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className={`text-[14px] ${pathname === link.href ? "text-brand" : "text-ink"}`}
              >
                {link.label}
              </Link>
            ))}
            {actor && actor.memberships.length > 0 && !recruiterMode && (
              <Link href="/org" className="text-[14px] text-ink">
                Recruiter workspace
              </Link>
            )}
            {actor ? (
              <button
                onClick={handleLogout}
                className="cursor-pointer border-none bg-transparent p-0 text-left text-[14px] text-[var(--color-error)]"
              >
                Log out
              </button>
            ) : (
              <>
                <Link href="/register?intent=recruiter" className="text-[14px] text-ink">
                  For recruiters
                </Link>
                <Link href="/login" className="text-[14px] text-ink">
                  Log in
                </Link>
                <Link href="/register?intent=candidate" className="text-[14px] text-brand">
                  Sign up
                </Link>
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </nav>
  );
}
