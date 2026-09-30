"use client"

import { useMemo, useState } from "react"
import Link from "next/link"
import { ArrowRight, CheckCircle2, Flame, Search, Trophy } from "lucide-react"

import { SidebarTrigger } from "@/components/ui/sidebar"

export type PrepHomeProblem = {
  id: number
  slug: string
  title: string
  prompt: string
  difficulty: string
  estimated_minutes: number
  topic_name: string
  topic_slug: string
}

export type PrepHomeTopic = { id: number; slug: string; name: string }

export type PrepDashboard = {
  total_problems: number
  solved_problems: number
  solved_problem_ids: number[]
  attempts: number
  completion_percent: number
  xp: number
  streak_days: number
  recent_submissions: Array<{ id: number; title: string; language: string; status: string; passed_tests: number; total_tests: number; created_at: string }>
  goal: { target_role: string; daily_minutes: number; days_per_week: number } | null
}

type PrepHomeProps = {
  topics: PrepHomeTopic[]
  problems: PrepHomeProblem[]
  dashboard: PrepDashboard | null
}

const DIFFICULTIES = ["ALL", "EASY", "MEDIUM", "HARD"]

function difficultyClass(difficulty: string) {
  if (difficulty === "MEDIUM") return "text-[#f0b938]"
  if (difficulty === "HARD") return "text-[#ff8585]"
  return "text-[#5be0b6]"
}

export default function PrepHome({ topics, problems, dashboard }: Readonly<PrepHomeProps>) {
  const [query, setQuery] = useState("")
  const [difficulty, setDifficulty] = useState("ALL")
  const [topic, setTopic] = useState("ALL")

  const filteredProblems = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    return problems.filter((problem) => {
      const matchesDifficulty = difficulty === "ALL" || problem.difficulty === difficulty
      const matchesTopic = topic === "ALL" || problem.topic_slug === topic
      const matchesQuery = !normalizedQuery || `${problem.title} ${problem.prompt} ${problem.topic_name}`.toLowerCase().includes(normalizedQuery)
      return matchesDifficulty && matchesTopic && matchesQuery
    })
  }, [difficulty, problems, query, topic])

  const solvedIds = new Set(dashboard?.solved_problem_ids ?? [])
  const solvedCount = dashboard?.solved_problems ?? 0
  const totalCount = dashboard?.total_problems ?? problems.length

  return (
    <div className="min-h-[calc(100vh-68px)] bg-[#08090d] text-white">
      <header className="flex h-14 items-center gap-3 border-b border-white/10 bg-[#0d0e14] px-3 sm:px-5">
        <SidebarTrigger />
        <div className="hidden h-5 w-px bg-white/10 sm:block" />
        <div>
          <p className="text-[10px] uppercase tracking-[0.16em] text-white/35">Prep</p>
          <h1 className="text-[14px] font-semibold text-white">Problem set</h1>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1280px] px-5 py-8 sm:px-8">
        <div className="flex flex-wrap items-end justify-between gap-5">
          <div>
            <p className="eyebrow">DSA PRACTICE</p>
            <h2 className="mt-2 text-[30px] font-semibold tracking-[-0.03em] text-white">Choose your next problem</h2>
            <p className="mt-2 max-w-[58ch] text-[13px] leading-[1.7] text-white/55">Work through the catalog at your pace. Every run, accepted solution, and revisit becomes part of your interview signal.</p>
          </div>
          <div className="flex items-center gap-2 text-[12px] text-white/45"><CheckCircle2 size={15} className="text-[#5be0b6]" /> {solvedCount}/{totalCount} solved</div>
        </div>

        <div className="mt-8 grid gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
          <section>
            <div className="flex flex-wrap items-center gap-3 rounded-xl border border-white/10 bg-[#11131d] p-3">
              <label className="flex min-w-[220px] flex-1 items-center gap-2 rounded-lg border border-white/10 bg-white/[0.03] px-3 text-white/45">
                <Search size={15} />
                <span className="sr-only">Search problems</span>
                <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search problems or patterns" className="w-full bg-transparent py-2 text-[12px] text-white outline-none placeholder:text-white/30" />
              </label>
              <select value={topic} onChange={(event) => setTopic(event.target.value)} className="rounded-lg border border-white/10 bg-[#1b1d25] px-3 py-2.5 text-[12px] text-white/70 outline-none"><option value="ALL">All topics</option>{topics.map((item) => <option key={item.id} value={item.slug}>{item.name}</option>)}</select>
              <div className="flex items-center gap-1 rounded-lg border border-white/10 bg-white/[0.03] p-1">{DIFFICULTIES.map((item) => <button key={item} type="button" onClick={() => setDifficulty(item)} className={`rounded-md px-2.5 py-1.5 text-[10px] font-semibold transition-colors ${difficulty === item ? "bg-white/10 text-white" : "text-white/35 hover:text-white/70"}`}>{item === "ALL" ? "All" : item}</button>)}</div>
            </div>

            <div className="mt-3 overflow-hidden rounded-xl border border-white/10 bg-[#11131d]">
              <div className="grid grid-cols-[minmax(0,1fr)_110px_90px] gap-3 border-b border-white/10 px-5 py-3 text-[10px] uppercase tracking-[0.14em] text-white/35"><span>Problem</span><span>Difficulty</span><span className="text-right">Time</span></div>
              {filteredProblems.length === 0 ? <div className="px-5 py-12 text-center text-[13px] text-white/40">No problems match those filters.</div> : filteredProblems.map((problem) => { const solved = solvedIds.has(problem.id); return <Link key={problem.id} href={`/prep?problem=${problem.id}`} className="grid w-full grid-cols-[minmax(0,1fr)_110px_90px] gap-3 border-b border-white/[0.06] px-5 py-4 text-left transition-colors last:border-0 hover:bg-white/[0.035]"><div className="min-w-0"><div className="flex items-center gap-2"><span className={`size-1.5 shrink-0 rounded-full ${solved ? "bg-[#27b98a]" : "bg-white/20"}`} /><span className="truncate text-[13px] font-semibold text-white/85">{problem.title}</span>{solved && <span className="hidden text-[10px] text-[#5be0b6] sm:inline">Solved</span>}</div><p className="mt-1 truncate pl-3.5 text-[11px] text-white/35">{problem.topic_name}</p></div><span className={`text-[11px] font-semibold ${difficultyClass(problem.difficulty)}`}>{problem.difficulty}</span><span className="text-right text-[11px] text-white/35">{problem.estimated_minutes}m</span></Link> })}
            </div>
            <p className="mt-3 text-[11px] text-white/30">Showing {filteredProblems.length} of {problems.length} problems</p>
          </section>

          <aside className="space-y-4">
            <div className="rounded-xl border border-white/10 bg-[#11131d] p-5"><p className="eyebrow">INSIGHTS</p><div className="mt-5 grid grid-cols-2 gap-3"><div className="rounded-lg bg-white/[0.035] p-3"><Trophy size={15} className="text-[#f0b938]" /><p className="mt-3 text-[10px] uppercase tracking-[0.12em] text-white/35">XP</p><p className="mt-1 text-[20px] font-semibold text-white">{dashboard?.xp ?? 0}</p></div><div className="rounded-lg bg-white/[0.035] p-3"><Flame size={15} className="text-[#ff8585]" /><p className="mt-3 text-[10px] uppercase tracking-[0.12em] text-white/35">Streak</p><p className="mt-1 text-[20px] font-semibold text-white">{dashboard?.streak_days ?? 0}d</p></div></div><div className="mt-4 rounded-lg border border-white/10 bg-white/[0.025] p-3"><p className="text-[11px] font-semibold text-white/75">{dashboard?.goal ? `${dashboard.goal.target_role} goal` : "No goal set yet"}</p><p className="mt-1 text-[11px] leading-[1.6] text-white/40">{dashboard?.goal ? `${dashboard.goal.daily_minutes} minutes/day · ${dashboard.goal.days_per_week} days/week` : "Set your target and available time to generate a plan."}</p><a href="/prep/roadmap" className="mt-3 inline-flex items-center gap-1 text-[11px] text-[#ffad72] hover:underline">{dashboard?.goal ? "Tune roadmap" : "Set goals"} <ArrowRight size={12} /></a></div></div>
            <div className="rounded-xl border border-white/10 bg-[#11131d] p-5"><p className="eyebrow">RECENT HISTORY</p><div className="mt-4 space-y-3">{dashboard?.recent_submissions?.slice(0, 4).map((submission) => <div key={submission.id} className="flex items-center justify-between gap-2"><div className="min-w-0"><p className="truncate text-[11px] text-white/70">{submission.title}</p><p className="mt-1 text-[10px] text-white/30">{submission.language} · {submission.passed_tests}/{submission.total_tests}</p></div><span className={`text-[10px] font-semibold ${submission.status === "Accepted" ? "text-[#5be0b6]" : "text-[#ff8585]"}`}>{submission.status}</span></div>) ?? <p className="text-[12px] text-white/35">No recent attempts.</p>}</div></div>
          </aside>
        </div>
      </main>
    </div>
  )
}
