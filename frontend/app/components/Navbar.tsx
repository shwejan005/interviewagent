"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import {
  BarChart3,
  BookOpen,
  BriefcaseBusiness,
  CalendarDays,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  FileText,
  Home,
  LogOut,
  Menu,
  Settings,
  UserRound,
  UsersRound,
  X,
} from "lucide-react";

import { useAuth } from "../../lib/auth-context";
import type { Actor, Membership } from "../../lib/types";
import { DUR, EASE_OUT } from "../../lib/motion";
import NotificationBell from "./NotificationBell";

const GUEST_LINKS = [
  { href: "/", label: "Overview" },
  { href: "/jobs", label: "Jobs" },
];

const CANDIDATE_LINKS = [
  { href: "/jobs", label: "Jobs" },
  { href: "/prep", label: "Prep" },
  { href: "/applications", label: "Applications" },
  { href: "/interviews", label: "Interviews" },
  { href: "/referrals", label: "Referrals" },
  { href: "/profile", label: "Profile" },
];

const RECRUITER_LINKS = [
  { href: "/org", label: "Overview" },
  { href: "/org/referrals", label: "Referrals" },
  { href: "/org/analytics", label: "Analytics" },
];

const INDICATOR_SPRING = { type: "spring", stiffness: 420, damping: 34 } as const;

function initials(actor: Actor | null): string {
  const source = actor?.full_name || actor?.email || "U";
  return source
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || "")
    .join("") || "U";
}

function AccountMenu({
  actor,
  activeMembership,
  light = false,
  onLogout,
}: Readonly<{
  actor: Actor;
  activeMembership?: Membership;
  light?: boolean;
  onLogout: () => void;
}>) {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const profileHref = "/profile";
  const settingsHref = activeMembership ? "/org" : "/profile";

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  return (
    <div ref={wrapperRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-haspopup="menu"
        className={`group flex items-center gap-2 rounded-xl border px-2.5 py-1.5 text-left transition-all duration-fast ease-out-expo ${
          light
            ? "border-[#dbe2e9] bg-white text-[#263342] shadow-[0_1px_2px_rgba(21,32,43,0.04)] hover:border-[#bfcbd7] hover:shadow-[0_8px_20px_rgba(21,32,43,0.08)]"
            : "border-subtle bg-glass-low text-ink-heading hover:border-strong hover:bg-glass-mid"
        }`}
      >
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#0e2941] text-[11px] font-bold text-white shadow-sm">
          {initials(actor)}
        </span>
        <span className="hidden min-w-0 sm:block">
          <span className={`block max-w-[150px] truncate text-[12px] font-semibold ${light ? "text-[#263342]" : "text-ink-heading"}`}>
            {actor.full_name || actor.email}
          </span>
          <span className={`block max-w-[150px] truncate text-[11px] ${light ? "text-[#8b98a6]" : "text-ink-subtle"}`}>
            {actor.email}
          </span>
        </span>
        <ChevronDown size={15} className={`ml-1 transition-transform duration-fast ${open ? "rotate-180" : ""} ${light ? "text-[#7d8a98]" : "text-ink-subtle"}`} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.98 }}
            transition={{ duration: DUR.fast, ease: EASE_OUT }}
            role="menu"
            className={`absolute right-0 top-[calc(100%+10px)] z-[80] w-[218px] overflow-hidden rounded-2xl border p-1.5 shadow-[0_16px_40px_rgba(15,29,43,0.18)] ${light ? "border-[#dbe2e9] bg-white" : "border-subtle bg-[#121725]"}`}
          >
            <div className={`px-3 py-2 text-[11px] ${light ? "text-[#8b98a6]" : "text-ink-subtle"}`}>
              {activeMembership ? activeMembership.role_name.replaceAll("_", " ") : "Personal account"}
            </div>
            <button type="button" role="menuitem" onClick={() => { setOpen(false); router.push(profileHref); }} className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] transition-colors ${light ? "text-[#384858] hover:bg-[#f3f6f8]" : "text-ink-muted hover:bg-glass-low hover:text-ink-heading"}`}>
              <UserRound size={16} /> Profile
            </button>
            <button type="button" role="menuitem" onClick={() => { setOpen(false); router.push(settingsHref); }} className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] transition-colors ${light ? "text-[#384858] hover:bg-[#f3f6f8]" : "text-ink-muted hover:bg-glass-low hover:text-ink-heading"}`}>
              <Settings size={16} /> Settings
            </button>
            <div className={`my-1 border-t ${light ? "border-[#e7edf1]" : "border-subtle"}`} />
            <button type="button" role="menuitem" onClick={() => { setOpen(false); onLogout(); }} className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] transition-colors ${light ? "text-[#e5484d] hover:bg-[#fff1f1]" : "text-[var(--color-error)] hover:bg-[rgba(239,68,68,0.1)]"}`}>
              <LogOut size={16} /> Log out
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function NavLink({ href, label, active }: Readonly<{ href: string; label: string; active: boolean }>) {
  return (
    <Link href={href} className={`relative py-2 text-[13px] transition-colors duration-fast ease-out-expo ${active ? "font-semibold text-ink-heading" : "text-ink-muted hover:text-ink-heading"}`}>
      {label}
      {active && <motion.span layoutId="nav-active-indicator" className="absolute -bottom-px left-0 right-0 h-[2px] rounded-full bg-[var(--color-primary)] shadow-glow-primary" transition={INDICATOR_SPRING} />}
    </Link>
  );
}

function WorkspaceLink({ href, label, icon: Icon, active }: Readonly<{ href: string; label: string; icon: typeof Home; active: boolean }>) {
  return (
    <Link href={href} className={`group flex items-center gap-3 rounded-lg px-3 py-2.5 text-[13px] transition-all duration-fast ease-out-expo ${active ? "bg-[#253c53] text-white shadow-[inset_3px_0_0_#8cc6ff]" : "text-[#aebdca] hover:bg-[#1c3044] hover:text-white"}`}>
      <Icon size={16} strokeWidth={1.8} className={active ? "text-[#b9ddff]" : "text-[#8093a3] group-hover:text-[#c8d9e8]"} />
      <span>{label}</span>
      {active && <motion.span layoutId="workspace-nav-dot" className="ml-auto h-1.5 w-1.5 rounded-full bg-[#8cc6ff]" />}
    </Link>
  );
}

function WorkspaceNavbar() {
  const pathname = usePathname();
  const router = useRouter();
  const { actor, logout, activeOrgId } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const activeMembership = actor?.memberships.find((membership) => membership.org_id === activeOrgId);

  const handleLogout = () => {
    logout();
    router.push("/");
  };

  const groups = [
    {
      label: "GENERAL",
      links: [
        { href: "/jobs", label: "Home", icon: Home },
        { href: "/jobs", label: "People", icon: UsersRound },
      ],
    },
    {
      label: "MY INFO",
      links: [
        { href: "/profile", label: "Profile", icon: UserRound },
        { href: "/applications", label: "Applications", icon: BriefcaseBusiness },
        { href: "/interviews", label: "Interviews", icon: CalendarDays },
        { href: "/prep", label: "Preparation", icon: BookOpen },
        { href: "/referrals", label: "Referrals", icon: FileText },
      ],
    },
    ...(activeMembership ? [{ label: "MANAGE", links: [
      { href: "/org", label: "Workspace", icon: UsersRound },
      ...(actor?.capabilities.includes("interview:schedule") ? [{ href: "/org/team", label: "Team", icon: UsersRound }] : []),
      { href: "/org/analytics", label: "Analytics", icon: BarChart3 },
    ] }] : []),
  ];

  const navigation = (
    <div className="flex h-full flex-col px-3 py-4">
      <Link href="/" className="flex items-center gap-2 px-3 py-3 text-white">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#ef8f3c] text-[13px] font-black text-[#132337]">E</span>
        <span className="text-[15px] font-bold tracking-[0.02em]">EVALIA</span>
      </Link>
      <div className="mt-5 flex items-center gap-2 rounded-lg border border-[#2a4258] bg-[#142a3f] px-3 py-2.5 text-[12px] font-semibold text-[#dcebf5]">
        <UsersRound size={15} className="text-[#9dccf2]" />
        <span>Candidate workspace</span>
        <ChevronDown size={14} className="ml-auto text-[#7e99af]" />
      </div>
      <div className="mt-7 flex flex-1 flex-col gap-6">
        {groups.map((group) => (
          <div key={group.label}>
            <p className="px-3 pb-2 text-[9px] font-bold tracking-[0.16em] text-[#718696]">{group.label}</p>
            <div className="flex flex-col gap-1">
              {group.links.map((link) => <WorkspaceLink key={`${group.label}-${link.href}-${link.label}`} {...link} active={pathname === link.href || (link.href !== "/" && pathname.startsWith(link.href))} />)}
            </div>
          </div>
        ))}
      </div>
      <div className="border-t border-[#294257] pt-3">
        <Link href="/" className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-[12px] text-[#aebdca] transition-colors hover:bg-[#1c3044] hover:text-white"><CircleHelp size={16} /> Help center</Link>
        <div className="mt-4 flex items-center gap-2 px-3">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[#294a64] text-[11px] font-bold text-white">{initials(actor)}</span>
          <span className="min-w-0"><span className="block truncate text-[12px] font-semibold text-white">{actor?.full_name || actor?.email}</span><span className="block truncate text-[10px] text-[#8093a3]">{actor?.email}</span></span>
        </div>
      </div>
    </div>
  );

  return (
    <>
      <aside className="fixed inset-y-0 left-0 z-[60] hidden w-[232px] bg-[#10263a] lg:block">{navigation}</aside>
      <header className="fixed inset-x-0 top-0 z-50 flex h-[68px] items-center justify-between border-b border-[#e1e7ec] bg-white/95 px-4 shadow-[0_1px_4px_rgba(20,35,50,0.04)] backdrop-blur lg:left-[232px] lg:px-8">
        <button type="button" className="flex items-center gap-2 text-[#263342] lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Open workspace navigation"><Menu size={20} /><span className="text-[14px] font-bold">EVALIA</span></button>
        <div className="hidden items-center gap-2 text-[12px] text-[#7b8996] lg:flex"><span className="font-semibold text-[#263342]">Profile</span><ChevronRight size={13} /><span>Overview</span></div>
        <div className="ml-auto flex items-center gap-4"><NotificationBell light />{actor && <AccountMenu actor={actor} activeMembership={activeMembership} light onLogout={handleLogout} />}</div>
      </header>
      <AnimatePresence>
        {mobileOpen && <motion.div className="fixed inset-0 z-[80] bg-[#10263a] lg:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: DUR.fast, ease: EASE_OUT }}><button type="button" className="absolute right-4 top-4 rounded-lg p-2 text-white" onClick={() => setMobileOpen(false)} aria-label="Close workspace navigation"><X size={22} /></button>{navigation}</motion.div>}
      </AnimatePresence>
    </>
  );
}

function DefaultNavbar() {
  const pathname = usePathname();
  const router = useRouter();
  const { actor, loading, logout, activeOrgId } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  useEffect(() => setMobileOpen(false), [pathname]);
  if (pathname.startsWith("/round/")) return null;

  const activeMembership = actor?.memberships.find((membership) => membership.org_id === activeOrgId);
  const recruiterMode = Boolean(actor && activeMembership);
  let links = GUEST_LINKS;
  if (actor && recruiterMode && actor.capabilities.includes("interview:schedule")) {
    links = [...RECRUITER_LINKS, { href: "/org/team", label: "Team" }];
  } else if (actor && recruiterMode) {
    links = RECRUITER_LINKS;
  } else if (actor) {
    links = CANDIDATE_LINKS;
  }
  const handleLogout = () => { logout(); router.push("/"); };
  let accountControls;
  if (loading) {
    accountControls = <div className="skeleton h-8 w-24" />;
  } else if (actor) {
    accountControls = <AccountMenu actor={actor} activeMembership={activeMembership} onLogout={handleLogout} />;
  } else {
    accountControls = <><Link href="/login" className="text-[13px] text-ink-muted hover:text-ink-heading">Log in</Link><Link href="/register?intent=candidate" className="btn-primary !px-4 !py-2 !text-[12px]">Sign up</Link></>;
  }

  return (
    <nav className={`fixed inset-x-0 top-0 z-50 border-b transition-all duration-base ease-out-expo ${scrolled ? "border-subtle bg-[rgba(7,8,16,0.84)] backdrop-blur-[16px]" : "border-transparent bg-transparent"}`}>
      <div className="mx-auto flex h-16 max-w-[var(--max-width)] items-center gap-8 px-6">
        <Link href="/" className="group flex shrink-0 items-center gap-2"><span className="mono text-[14px] font-bold text-brand">EVALIA</span><span className="text-[11px] text-ink-subtle/50">/</span><span className="mono text-[11px] text-ink-subtle">v2.0</span></Link>
        <div className="hidden min-w-0 flex-1 items-center justify-center gap-7 md:flex">{links.map((link) => <NavLink key={link.href} href={link.href} label={link.label} active={pathname === link.href || (link.href !== "/" && pathname.startsWith(link.href))} />)}</div>
        <div className="ml-auto flex shrink-0 items-center gap-3">{actor && <NotificationBell />}{accountControls}</div>
        <button className="rounded-lg p-2 text-ink md:hidden" onClick={() => setMobileOpen((value) => !value)} aria-expanded={mobileOpen} aria-label={mobileOpen ? "Close menu" : "Open menu"}>{mobileOpen ? <X size={19} /> : <Menu size={19} />}</button>
      </div>
      <AnimatePresence>{mobileOpen && <motion.div className="absolute inset-x-0 top-full flex flex-col gap-3 border-b border-subtle bg-[rgba(7,8,16,0.96)] px-6 py-5 backdrop-blur-[20px] md:hidden" initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: DUR.base, ease: EASE_OUT }}>{links.map((link) => <Link key={link.href} href={link.href} className={`text-[14px] ${pathname === link.href ? "text-brand" : "text-ink"}`}>{link.label}</Link>)}{actor ? <button onClick={handleLogout} className="text-left text-[14px] text-[var(--color-error)]">Log out</button> : <Link href="/login" className="text-[14px] text-ink">Log in</Link>}</motion.div>}</AnimatePresence>
    </nav>
  );
}

export default function Navbar({ variant = "default" }: Readonly<{ variant?: "default" | "workspace" }>) {
  return variant === "workspace" ? <WorkspaceNavbar /> : <DefaultNavbar />;
}
