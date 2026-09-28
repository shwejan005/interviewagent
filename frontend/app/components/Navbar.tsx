"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "../../lib/auth-context";
import type { Actor, Membership } from "../../lib/types";

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
  if (loading) return null;

  if (!actor) {
    return (
      <>
        <Link href="/register?intent=recruiter" style={{ fontSize: 13, color: "var(--color-text-muted)", textDecoration: "none" }}>
          For recruiters
        </Link>
        <Link href="/login" style={{ fontSize: 13, color: "var(--color-text-muted)", textDecoration: "none" }}>
          Log in
        </Link>
        <Link href="/register?intent=candidate" className="btn-primary" style={{ padding: "6px 14px", fontSize: 12 }}>
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
          style={{
            background: "var(--color-surface)",
            border: "1px solid var(--color-border)",
            borderRadius: 6,
            color: "var(--color-text-muted)",
            fontSize: 12,
            padding: "5px 8px",
          }}
        >
          <option value="">Personal</option>
          {actor.memberships.map((m) => (
            <option key={m.org_id} value={m.org_id}>
              {m.org_name} ({m.role_name})
            </option>
          ))}
        </select>
      )}
      <span style={{ fontSize: 12, color: "var(--color-text-subtle)", fontFamily: "var(--font-mono)" }}>
        {actor.full_name || actor.email}
        {activeMembership ? ` · ${activeMembership.role_name}` : ""}
      </span>
      <button onClick={handleLogout} className="btn-secondary" style={{ padding: "6px 14px", fontSize: 12 }}>
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

  // Don't show navbar during active interview rounds
  if (pathname.startsWith("/round/")) return null;

  const links = actor ? CANDIDATE_LINKS : GUEST_LINKS;
  const activeMembership = actor?.memberships.find((m) => m.org_id === activeOrgId);

  const handleLogout = () => {
    logout();
    router.push("/");
  };

  return (
    <nav
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        zIndex: 50,
        background: "rgba(9, 10, 15, 0.85)",
        backdropFilter: "blur(12px)",
        borderBottom: "1px solid var(--color-border)",
      }}
    >
      <div
        style={{
          maxWidth: "var(--max-width)",
          margin: "0 auto",
          padding: "0 24px",
          height: 56,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        {/* Brand */}
        <Link
          href="/"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            textDecoration: "none",
          }}
        >
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 14,
              fontWeight: 700,
              color: "var(--color-primary)",
              letterSpacing: "-0.02em",
            }}
          >
            EVALIA
          </span>
          <span style={{ color: "var(--color-border)", fontSize: 12 }}>/</span>
          <span style={{ fontSize: 12, color: "var(--color-text-subtle)", fontFamily: "var(--font-mono)" }}>
            v2.0
          </span>
        </Link>

        {/* Desktop Links */}
        <div className="hidden md:flex" style={{ alignItems: "center", gap: 24 }}>
          {links.map((link) => {
            const isActive = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                style={{
                  fontSize: 13,
                  fontWeight: isActive ? 600 : 400,
                  color: isActive ? "var(--color-text-heading)" : "var(--color-text-muted)",
                  textDecoration: "none",
                  transition: "color var(--transition-fast)",
                }}
              >
                {link.label}
              </Link>
            );
          })}
          {actor && actor.memberships.length > 0 && (
            <Link
              href="/org"
              style={{
                fontSize: 13,
                fontWeight: pathname.startsWith("/org") ? 600 : 400,
                color: pathname.startsWith("/org") ? "var(--color-primary)" : "var(--color-text-muted)",
                textDecoration: "none",
              }}
            >
              Recruiter
            </Link>
          )}
        </div>

        {/* Auth area */}
        <div className="hidden md:flex" style={{ alignItems: "center", gap: 12 }}>
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
          className="md:hidden"
          onClick={() => setMobileOpen(!mobileOpen)}
          style={{
            background: "none",
            border: "none",
            color: "var(--color-text)",
            fontSize: 13,
            cursor: "pointer",
            fontFamily: "var(--font-mono)",
          }}
        >
          {mobileOpen ? "CLOSE" : "MENU"}
        </button>
      </div>

      {/* Mobile Drawer */}
      {mobileOpen && (
        <div
          className="md:hidden"
          style={{
            background: "var(--color-bg)",
            borderBottom: "1px solid var(--color-border)",
            padding: "16px 24px",
            display: "flex",
            flexDirection: "column",
            gap: 12,
          }}
        >
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              onClick={() => setMobileOpen(false)}
              style={{
                fontSize: 14,
                color: pathname === link.href ? "var(--color-primary)" : "var(--color-text)",
                textDecoration: "none",
              }}
            >
              {link.label}
            </Link>
          ))}
          {actor && actor.memberships.length > 0 && (
            <Link
              href="/org"
              onClick={() => setMobileOpen(false)}
              style={{ fontSize: 14, color: "var(--color-text)", textDecoration: "none" }}
            >
              Recruiter
            </Link>
          )}
          {actor ? (
            <button
              onClick={() => {
                setMobileOpen(false);
                handleLogout();
              }}
              style={{ fontSize: 14, color: "var(--color-error)", background: "none", border: "none", textAlign: "left", padding: 0, cursor: "pointer" }}
            >
              Log out
            </button>
          ) : (
            <>
              <Link href="/register?intent=recruiter" onClick={() => setMobileOpen(false)} style={{ fontSize: 14, color: "var(--color-text)", textDecoration: "none" }}>
                For recruiters
              </Link>
              <Link href="/login" onClick={() => setMobileOpen(false)} style={{ fontSize: 14, color: "var(--color-text)", textDecoration: "none" }}>
                Log in
              </Link>
              <Link href="/register?intent=candidate" onClick={() => setMobileOpen(false)} style={{ fontSize: 14, color: "var(--color-primary)", textDecoration: "none" }}>
                Sign up
              </Link>
            </>
          )}
        </div>
      )}
    </nav>
  );
}
