"use client"

import { useEffect, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import { CheckCircle2, Edit3, Flag, ShieldCheck } from "lucide-react"

import Navbar from "../../components/Navbar"
import { Button, GlassCard, PageHeader, PageShell, SkeletonList, Textarea } from "../../components/ui"
import { useAuth } from "../../../lib/auth-context"
import { api, ApiError } from "../../../lib/api"
import { notify } from "../../../lib/toast"

type ReviewPacket = {
  evaluation: { id: number; candidate_name: string; role: string; status: string; final_decision: string | null }
  verdicts: Array<{ agent_type: string; round_number: number; decision: string | null; score: number | null; verdict_json: Record<string, unknown> }>
  actions: Array<{ id: number; action: string; note: string; actor_user_id: number; created_at: string }>
  review_state: string
  rubric_version: string
  review_guidance: string
}

export default function ReviewPage() {
  const { actor, loading: authLoading } = useAuth()
  const router = useRouter()
  const params = useParams()
  const evaluationId = String(params.id)
  const [packet, setPacket] = useState<ReviewPacket | null>(null)
  const [note, setNote] = useState("")
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (authLoading || !actor) return
    api.get<ReviewPacket>(`/review/evaluations/${evaluationId}`)
      .then(setPacket)
      .catch((error) => notify.error(error instanceof ApiError ? error.detail : "Failed to load review packet."))
      .finally(() => setLoading(false))
  }, [actor, authLoading, evaluationId])

  async function act(action: "APPROVE" | "CORRECT" | "ESCALATE") {
    setSaving(true)
    try {
      const response = await api.post<{ action: ReviewPacket["actions"][number]; review_state: string }>(`/review/evaluations/${evaluationId}/actions`, { action, note, correction: {} })
      setPacket((current) => current ? { ...current, actions: [...current.actions, response.action], review_state: response.review_state } : current)
      setNote("")
      notify.success(`Review marked ${action.toLowerCase()}.`)
    } catch (error) {
      notify.error(error instanceof ApiError ? error.detail : "Failed to save review action.")
    } finally {
      setSaving(false)
    }
  }

  if (authLoading || loading) return <><Navbar /><PageShell className="pt-[112px]"><SkeletonList count={4} /></PageShell></>
  if (!actor || !packet) return <><Navbar /><PageShell className="pt-[112px]"><p className="text-ink-muted">This review packet is unavailable.</p></PageShell></>

  return <div className="min-h-screen"><Navbar /><PageShell className="!max-w-[900px] pt-[112px]">
    <button type="button" onClick={() => router.back()} className="mono mb-6 border-none bg-transparent p-0 text-[12px] text-ink-muted hover:text-brand">← BACK</button>
    <PageHeader eyebrow={`HUMAN REVIEW · ${packet.rubric_version}`} title={packet.evaluation.candidate_name || "Candidate evaluation"} description={`${packet.evaluation.role} · ${packet.review_guidance}`} actions={<span className="inline-flex items-center gap-2 text-[12px] text-ink-muted"><ShieldCheck size={16} /> {packet.review_state}</span>} />
    <div className="mt-8 grid gap-5 lg:grid-cols-[1fr_300px]">
      <div className="space-y-3">{packet.verdicts.map((verdict) => { const json = verdict.verdict_json || {}; const rationale = json.reasoning || json.detailed_recommendation || json.overall_assessment || json.executive_summary; return <GlassCard key={`${verdict.agent_type}-${verdict.round_number}`} padding="lg"><div className="flex items-center justify-between gap-3"><div><p className="mono text-[10px] text-brand">STAGE {verdict.round_number}</p><h2 className="mt-1 text-[15px] font-semibold text-ink-heading">{verdict.agent_type}</h2></div><div className="flex items-center gap-3 text-[12px]">{verdict.score !== null && <span className="mono text-ink-heading">{verdict.score.toFixed(1)}/10</span>}<span className="rounded-full border border-subtle px-2 py-1 text-ink-muted">{verdict.decision || "REVIEW"}</span></div></div><p className="mt-4 text-[13px] leading-[1.7] text-ink-muted">{String(rationale || "No rationale recorded.")}</p><div className="mt-4 flex flex-wrap gap-2 text-[11px] text-ink-subtle"><span>Evidence-linked review required</span><span>·</span><span>Raw model output preserved</span></div></GlassCard> })}</div>
      <aside className="space-y-4"><GlassCard padding="md"><p className="eyebrow">REVIEW ACTION</p><Textarea className="mt-4" label="NOTE" rows={5} placeholder="Record the evidence or correction..." value={note} onChange={(event) => setNote(event.target.value)} /><div className="mt-4 grid gap-2"><Button onClick={() => void act("APPROVE")} loading={saving}><CheckCircle2 size={15} /> Approve</Button><Button variant="secondary" onClick={() => void act("CORRECT")} loading={saving}><Edit3 size={15} /> Correct</Button><Button variant="danger" onClick={() => void act("ESCALATE")} loading={saving}><Flag size={15} /> Escalate</Button></div></GlassCard><GlassCard padding="md"><p className="eyebrow">ACTION HISTORY</p><div className="mt-4 space-y-3">{packet.actions.length === 0 ? <p className="text-[12px] text-ink-muted">No human action recorded yet.</p> : packet.actions.map((action) => <div key={action.id} className="border-b border-subtle pb-3 last:border-0"><p className="text-[12px] font-semibold text-ink-heading">{action.action}</p><p className="mt-1 text-[11px] text-ink-subtle">{action.note || "No note"}</p></div>)}</div></GlassCard></aside>
    </div>
  </PageShell></div>
}
