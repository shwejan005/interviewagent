"use client"

import { FormEvent, useEffect, useState } from "react"
import Link from "next/link"
import { ArrowRight, CalendarDays, CheckCircle2, Compass, Sparkles } from "lucide-react"

import { Button, GlassCard, Input, PageShell, Select, Textarea } from "../../components/ui"
import { useAuth } from "../../../lib/auth-context"
import { api, ApiError } from "../../../lib/api"
import { notify } from "../../../lib/toast"
import { usePrepCatalog } from "../prep-catalog-context"

type Goal = { id?: number; target_role: string; target_date: string | null; daily_minutes: number; days_per_week: number; current_level: string; preferred_languages: string[]; focus_topics: string[]; notes: string }
type Roadmap = { id: number; title: string; summary: string; generated_by: string; daily_minutes: number; weekly_hours: number; nodes: Array<{ id: number; position: number; topic_name: string; problem_id: number | null; item_type: string; estimated_minutes: number; rationale: string; status: string }> }
type Topic = { slug: string; name: string }
type Plan = { weekly_focus?: string[]; daily_schedule?: Array<{ day: string; activity: string; minutes: number }> }

const DEFAULT_GOAL: Goal = { target_role: "Software Engineer", target_date: "", daily_minutes: 45, days_per_week: 5, current_level: "BEGINNER", preferred_languages: ["python"], focus_topics: [], notes: "" }

export default function PrepRoadmapPage() {
  const { actor, loading: authLoading } = useAuth()
  const { refreshCatalog } = usePrepCatalog()
  const [goal, setGoal] = useState<Goal>(DEFAULT_GOAL)
  const [topics, setTopics] = useState<Topic[]>([])
  const [roadmap, setRoadmap] = useState<Roadmap | null>(null)
  const [plan, setPlan] = useState<Plan | null>(null)
  const [saving, setSaving] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [problemTopic, setProblemTopic] = useState("arrays")
  const [problemDifficulty, setProblemDifficulty] = useState("MEDIUM")
  const [generatingProblem, setGeneratingProblem] = useState(false)
  const [generatedProblem, setGeneratedProblem] = useState<{ title: string; prompt: string } | null>(null)

  useEffect(() => {
    if (authLoading || !actor) return
    Promise.all([api.get<{ goal: Goal | null }>("/prep/goals"), api.get<{ topics: Topic[] }>("/prep/topics")])
      .then(([goalResponse, topicResponse]) => {
        if (goalResponse.goal) setGoal({ ...DEFAULT_GOAL, ...goalResponse.goal })
        setTopics(topicResponse.topics)
      })
      .catch((error) => notify.error(error instanceof ApiError ? error.detail : "Failed to load roadmap setup."))
  }, [actor, authLoading])

  const update = (patch: Partial<Goal>) => setGoal((current) => ({ ...current, ...patch }))

  async function saveAndGenerate(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    try {
      const saved = await api.put<{ goal: Goal }>("/prep/goals", goal)
      setGoal({ ...DEFAULT_GOAL, ...saved.goal })
      setGenerating(true)
      const generated = await api.post<{ roadmap: Roadmap; plan: Plan }>("/prep/roadmaps/generate", {})
      setRoadmap(generated.roadmap)
      setPlan(generated.plan)
      notify.success("Your personalized roadmap is ready.")
    } catch (error) {
      notify.error(error instanceof ApiError ? error.detail : "Failed to generate roadmap.")
    } finally {
      setSaving(false)
      setGenerating(false)
    }
  }

  async function generateProblem() {
    setGeneratingProblem(true)
    try {
      const response = await api.post<{ title: string; prompt: string }>("/prep/problems/generate", { topic_slug: problemTopic, difficulty: problemDifficulty, language: "python" })
      setGeneratedProblem(response)
      await refreshCatalog()
      notify.success("A new database-backed challenge was created.")
    } catch (error) {
      notify.error(error instanceof ApiError ? error.detail : "Problem generation is unavailable right now.")
    } finally {
      setGeneratingProblem(false)
    }
  }

  if (authLoading) return null
  if (!actor) return <PageShell className="pt-12"><p className="text-white/50">Sign in to plan your preparation.</p></PageShell>

  return <div className="min-h-full bg-[#08090d] text-white"><PageShell className="!max-w-[1180px] pt-12">
    <div><p className="eyebrow">PREP ROADMAP</p><h1 className="mt-2 text-[30px] font-semibold tracking-[-0.03em] text-white">Build a plan you can actually keep</h1><p className="mt-2 max-w-[62ch] text-[13px] leading-[1.7] text-white/55">Tell us what you are aiming for and how much time you have. The planner sequences the database problem set around your real week.</p></div>
    <div className="mt-8 grid gap-5 lg:grid-cols-[0.82fr_1.18fr]">
      <GlassCard padding="lg" className="border border-white/10 bg-[#11131d]"><div className="mb-6 flex items-center gap-3"><div className="flex size-10 items-center justify-center rounded-xl bg-[#f97316]/15 text-[#ffad72]"><Compass size={19} /></div><div><p className="text-[14px] font-semibold text-white">Your constraints</p><p className="text-[11px] text-white/40">The planner uses every field below.</p></div></div><form onSubmit={saveAndGenerate} className="space-y-4"><Input label="TARGET ROLE" value={goal.target_role} onChange={(event) => update({ target_role: event.target.value })} /><div className="grid gap-4 sm:grid-cols-2"><Input label="DAILY MINUTES" type="number" min={15} max={480} value={goal.daily_minutes} onChange={(event) => update({ daily_minutes: Number(event.target.value) })} /><Input label="DAYS / WEEK" type="number" min={1} max={7} value={goal.days_per_week} onChange={(event) => update({ days_per_week: Number(event.target.value) })} /></div><div className="grid gap-4 sm:grid-cols-2"><Select label="CURRENT LEVEL" value={goal.current_level} onChange={(event) => update({ current_level: event.target.value })}><option value="BEGINNER">Beginner</option><option value="INTERMEDIATE">Intermediate</option><option value="ADVANCED">Advanced</option></Select><Input label="TARGET DATE" type="date" value={goal.target_date ?? ""} onChange={(event) => update({ target_date: event.target.value })} /></div><label className="block"><span className="field-label">FOCUS TOPICS</span><div className="mt-2 flex flex-wrap gap-2">{topics.map((topic) => { const active = goal.focus_topics.includes(topic.slug); return <button key={topic.slug} type="button" onClick={() => update({ focus_topics: active ? goal.focus_topics.filter((slug) => slug !== topic.slug) : [...goal.focus_topics, topic.slug] })} className={`rounded-full border px-3 py-1.5 text-[11px] transition-colors ${active ? "border-[#f97316]/60 bg-[#f97316]/10 text-[#ffad72]" : "border-white/10 text-white/45 hover:border-white/25 hover:text-white/70"}`}>{topic.name}</button> })}</div></label><Textarea label="NOTES FOR THE PLANNER" rows={4} placeholder="I struggle with graph traversal and want interview-style explanations..." value={goal.notes} onChange={(event) => update({ notes: event.target.value })} /><Button type="submit" loading={saving || generating} fullWidth><Sparkles size={15} /> Generate personalized roadmap</Button></form></GlassCard>
      <div className="space-y-5"><GlassCard padding="lg" className="border border-white/10 bg-[#11131d]"><div className="flex items-center justify-between"><div><p className="eyebrow">GENERATE A CHALLENGE</p><h2 className="mt-2 text-[17px] font-semibold text-white">Expand the problem bank</h2></div><Sparkles size={18} className="text-[#ffad72]" /></div><p className="mt-2 text-[12px] leading-[1.6] text-white/50">Ask the configured LLM to author a new problem, starter, harness, and hidden tests. It is saved to the same catalog as the reviewed set.</p><div className="mt-4 grid gap-3 sm:grid-cols-2"><Select label="TOPIC" value={problemTopic} onChange={(event) => setProblemTopic(event.target.value)}>{topics.map((topic) => <option key={topic.slug} value={topic.slug}>{topic.name}</option>)}</Select><Select label="DIFFICULTY" value={problemDifficulty} onChange={(event) => setProblemDifficulty(event.target.value)}><option value="EASY">Easy</option><option value="MEDIUM">Medium</option><option value="HARD">Hard</option></Select></div><Button className="mt-4" variant="secondary" onClick={generateProblem} loading={generatingProblem}><Sparkles size={14} /> Generate problem</Button>{generatedProblem && <div className="mt-4 rounded-lg border border-[#27b98a]/20 bg-[#27b98a]/[0.06] p-3"><p className="text-[12px] font-semibold text-[#5be0b6]">{generatedProblem.title}</p><p className="mt-1 text-[11px] leading-[1.6] text-white/55">{generatedProblem.prompt}</p><Link href="/prep" className="mt-2 inline-flex text-[11px] text-[#ffad72] hover:underline">Open problem set <ArrowRight size={12} /></Link></div>}</GlassCard><GlassCard padding="lg" className="border border-white/10 bg-[#11131d]"><div className="flex items-center justify-between"><div><p className="eyebrow">GENERATED PLAN</p><h2 className="mt-2 text-[19px] font-semibold text-white">{roadmap?.title ?? "Your next best sequence"}</h2></div><Sparkles size={18} className="text-[#ffad72]" /></div>{roadmap ? <><p className="mt-3 text-[13px] leading-[1.7] text-white/60">{roadmap.summary}</p><div className="mt-5 space-y-2">{roadmap.nodes.map((node) => <div key={node.id} className="flex items-start gap-3 rounded-lg border border-white/10 bg-white/[0.025] p-3"><div className="flex size-6 shrink-0 items-center justify-center rounded-full bg-[#f97316]/15 text-[11px] font-semibold text-[#ffad72]">{node.position}</div><div><p className="text-[12px] font-semibold text-white">{node.problem_id ? `Practice ${node.topic_name}` : node.topic_name}</p><p className="mt-1 text-[11px] leading-[1.5] text-white/45">{node.rationale || `${node.estimated_minutes} minutes`}</p></div><CheckCircle2 size={15} className={`ml-auto mt-1 ${node.status === "COMPLETE" ? "text-[#5be0b6]" : "text-white/20"}`} /></div>)}</div></> : <div className="flex min-h-[320px] flex-col items-center justify-center text-center text-white/35"><CalendarDays size={24} /><p className="mt-3 text-[14px] font-medium text-white/65">No plan generated yet</p><p className="mt-2 max-w-[34ch] text-[12px] leading-[1.6]">Your plan will appear here with a sequence of problems matched to your available time.</p></div>}</GlassCard>{plan?.daily_schedule && <GlassCard padding="lg" className="border border-white/10 bg-[#11131d]"><p className="eyebrow">WEEKLY RHYTHM</p><div className="mt-4 grid gap-2 sm:grid-cols-2">{plan.daily_schedule.map((day) => <div key={day.day} className="rounded-lg bg-white/[0.03] p-3"><div className="flex justify-between text-[11px] font-semibold text-white/75"><span>{day.day}</span><span className="text-white/35">{day.minutes}m</span></div><p className="mt-2 text-[11px] leading-[1.5] text-white/45">{day.activity}</p></div>)}</div></GlassCard>}</div>
    </div>
  </PageShell></div>
}
