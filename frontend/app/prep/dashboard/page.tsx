"use client"

import { useEffect, useState } from "react"
import { usePathname } from "next/navigation"
import Link from "next/link"
import { ArrowRight, CheckCircle2, Flame, Gauge, Target, Trophy } from "lucide-react"

import { GlassCard, PageShell, SkeletonList } from "../../components/ui"
import { useAuth } from "../../../lib/auth-context"
import { useActivePageRefresh } from "../../../lib/use-active-page-refresh"
import { api, ApiError } from "../../../lib/api"
import { notify } from "../../../lib/toast"

type TopicProgress = { slug: string; name: string; total: number; solved: number }
type Dashboard = {
  total_problems: number
  solved_problems: number
  solved_problem_ids: number[]
  attempts: number
  completion_percent: number
  xp: number
  streak_days: number
  by_topic: TopicProgress[]
  recent_submissions: Array<{ id: number; title: string; language: string; status: string; passed_tests: number; total_tests: number; created_at: string }>
  goal: { target_role: string; daily_minutes: number; days_per_week: number } | null
}

function Stat({ label, value, icon: Icon, accent }: Readonly<{ label: string; value: string | number; icon: typeof Target; accent: string }>) {
  return <GlassCard padding="md" className="border border-white/10 bg-[#11131d]"><div className={`mb-4 flex size-9 items-center justify-center rounded-lg ${accent}`}><Icon size={17} /></div><p className="text-[11px] uppercase tracking-[0.16em] text-white/40">{label}</p><p className="mt-1 text-[28px] font-semibold text-white">{value}</p></GlassCard>
}

export default function PrepDashboardPage() {
  const pathname = usePathname()
  const { actor, loading: authLoading } = useAuth()
  const [dashboard, setDashboard] = useState<Dashboard | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (authLoading || !actor) return
    if (pathname !== "/prep/dashboard") return
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [actor, authLoading])

  async function load(showLoading = true) {
    if (showLoading) setLoading(true)
    try {
      setDashboard(await api.get<Dashboard>("/prep/me/dashboard"))
    } catch (error) {
      notify.error(error instanceof ApiError ? error.detail : "Failed to load progress dashboard.")
    } finally {
      if (showLoading) setLoading(false)
    }
  }

  useActivePageRefresh(
    pathname === "/prep/dashboard",
    !authLoading && Boolean(actor),
    () => load(false),
  )

  if (authLoading || loading) return <PageShell className="pt-12"><SkeletonList count={3} /></PageShell>
  if (!actor || !dashboard) return <PageShell className="pt-12"><p className="text-white/50">Sign in to view your prep progress.</p></PageShell>

  return <div className="min-h-full bg-[#08090d] text-white"><PageShell className="!max-w-[1180px] pt-12">
    <div className="flex flex-wrap items-end justify-between gap-5"><div><p className="eyebrow">PREP DASHBOARD</p><h1 className="mt-2 text-[30px] font-semibold tracking-[-0.03em] text-white">Your practice signal</h1><p className="mt-2 max-w-[58ch] text-[13px] leading-[1.7] text-white/55">A private view of what you have attempted, solved, and still need to revisit.</p></div><div className="flex gap-2"><ButtonLink href="/prep" variant="secondary">Problem set <ArrowRight size={14} /></ButtonLink><ButtonLink href="/prep/roadmap">Open roadmap <ArrowRight size={14} /></ButtonLink></div></div>
    <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4"><Stat label="Solved" value={`${dashboard.solved_problems}/${dashboard.total_problems}`} icon={CheckCircle2} accent="bg-[#27b98a]/15 text-[#5be0b6]" /><Stat label="Completion" value={`${dashboard.completion_percent}%`} icon={Gauge} accent="bg-[#f97316]/15 text-[#ffad72]" /><Stat label="XP earned" value={dashboard.xp} icon={Trophy} accent="bg-[#e9ad2f]/15 text-[#f0b938]" /><Stat label="Streak" value={`${dashboard.streak_days}d`} icon={Flame} accent="bg-[#e15b5b]/15 text-[#ff8585]" /></div>
    <div className="mt-5 grid gap-5 lg:grid-cols-[1.05fr_0.95fr]"><GlassCard padding="lg" className="border border-white/10 bg-[#11131d]"><div className="flex items-center justify-between"><div><p className="eyebrow">PATTERN MASTERY</p><h2 className="mt-2 text-[18px] font-semibold text-white">Progress by topic</h2></div><Target size={18} className="text-white/35" /></div><div className="mt-6 space-y-5">{dashboard.by_topic.map((topic) => { const percent = topic.total ? Math.round((topic.solved / topic.total) * 100) : 0; return <div key={topic.slug}><div className="flex items-center justify-between text-[12px]"><span className="text-white/75">{topic.name}</span><span className="text-white/40">{topic.solved}/{topic.total}</span></div><div className="mt-2 h-2 overflow-hidden rounded-full bg-white/[0.06]"><div className="h-full rounded-full bg-[#f97316] transition-all" style={{ width: `${percent}%` }} /></div></div> })}</div></GlassCard><GlassCard padding="lg" className="border border-white/10 bg-[#11131d]"><p className="eyebrow">RECENT ATTEMPTS</p><h2 className="mt-2 text-[18px] font-semibold text-white">Your latest runs</h2><div className="mt-5 space-y-2">{dashboard.recent_submissions.length === 0 ? <p className="py-8 text-[13px] text-white/45">No runs yet. Pick a problem and make the first attempt.</p> : dashboard.recent_submissions.map((submission) => <div key={submission.id} className="flex items-center justify-between gap-3 rounded-lg border border-white/10 bg-white/[0.025] px-3 py-3"><div><p className="text-[12px] font-medium text-white/80">{submission.title}</p><p className="mt-1 text-[10px] text-white/35">{submission.language} · {submission.passed_tests}/{submission.total_tests} tests</p></div><span className={`text-[11px] font-semibold ${submission.status === "Accepted" ? "text-[#5be0b6]" : "text-[#ff8585]"}`}>{submission.status}</span></div>)}</div></GlassCard></div>
    <GlassCard padding="md" className="mt-5 flex flex-wrap items-center justify-between gap-4 border border-[#f97316]/20 bg-[#f97316]/[0.06]"><div><p className="text-[13px] font-semibold text-white">{dashboard.goal ? `${dashboard.goal.target_role} plan · ${dashboard.goal.daily_minutes} minutes/day` : "Set a goal to get a plan that fits your week"}</p><p className="mt-1 text-[12px] text-white/50">{dashboard.goal ? "Your roadmap uses this goal to sequence the next problems." : "Tell Evalia your target role, level, and available time."}</p></div><ButtonLink href="/prep/roadmap" variant="secondary">{dashboard.goal ? "Tune roadmap" : "Set goals"}</ButtonLink></GlassCard>
  </PageShell></div>
}

function ButtonLink({ href, children, variant = "primary" }: Readonly<{ href: string; children: React.ReactNode; variant?: "primary" | "secondary" }>) {
  return <Link href={href} className={`inline-flex items-center gap-2 rounded-[10px] px-4 py-2.5 text-[12px] font-semibold transition-colors ${variant === "secondary" ? "border border-white/10 bg-white/[0.04] text-white/75 hover:bg-white/[0.08]" : "bg-[#f97316] text-[#17100a] hover:bg-[#fb923c]"}`}>{children}</Link>
}
