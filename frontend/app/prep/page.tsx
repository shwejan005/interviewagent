"use client"

import { Suspense, useEffect, useMemo, useState } from "react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import {
  ChevronRight,
  CircleCheck,
  FileCode2,
  History,
  Lightbulb,
  RotateCcw,
  Settings2,
} from "lucide-react"

import CodeEditor, { type EditorSettings } from "./CodeEditor"
import { usePrepCatalog, type PrepCatalogProblem, type PrepCatalogTestCase, type PrepLanguageKey } from "./prep-catalog-context"
import { useAuth } from "../../lib/auth-context"
import { useActivePageRefresh } from "../../lib/use-active-page-refresh"
import { api, ApiError } from "../../lib/api"
import {
  SidebarTrigger,
} from "@/components/ui/sidebar"
import { notify } from "../../lib/toast"
import EditorConsole from "./EditorConsole"
import PrepHome, { type PrepDashboard } from "./PrepHome"

type Problem = PrepCatalogProblem
type Roadmap = { id: number; title: string; target_role: string; nodes: Array<{ id: number; topic_name: string; status: string; position: number }> }
type LanguageKey = PrepLanguageKey
type TestCase = PrepCatalogTestCase
type Submission = { id: number; language: string; status: string; passed: boolean | number; passed_tests: number; total_tests: number; runtime_ms: number | null; memory_kb: number | null; created_at: string }
type WorkspaceTab = "description" | "solutions" | "submissions"
type ConsoleTab = "testcase" | "result"
type RunState = "idle" | "running" | "complete" | "error"
type ExecutionResult = {
  language: string
  status: string
  stdout: string
  stderr: string
  compile_output: string
  time: string | null
  memory: number | null
  passed?: boolean
  passed_tests?: number
  total_tests?: number
  tests?: Array<{ id: number; title: string; passed: boolean; status: string; stdout: string; stderr: string; compile_output: string; time: string | null; memory: number | null; is_hidden: boolean; input?: Record<string, unknown>; expected_output?: string }>
}

const LANGUAGES: Array<{ value: LanguageKey; label: string; monaco: string }> = [
  { value: "python", label: "Python 3", monaco: "python" },
  { value: "javascript", label: "JavaScript", monaco: "javascript" },
  { value: "typescript", label: "TypeScript", monaco: "typescript" },
  { value: "java", label: "Java", monaco: "java" },
  { value: "cpp", label: "C++", monaco: "cpp" },
]

function starterFor(problem: Problem, language: LanguageKey): string {
  return problem.starter_code?.[language] ?? `// ${problem.title}\n// No starter is configured for this language yet.\n`
}

function difficultyClass(difficulty: string) {
  if (difficulty === "MEDIUM") return "border-[#d99a22]/50 bg-[#d99a22]/10 text-[#f0b938]"
  if (difficulty === "HARD") return "border-[#e15b5b]/50 bg-[#e15b5b]/10 text-[#ff8585]"
  return "border-[#27b98a]/50 bg-[#27b98a]/10 text-[#5be0b6]"
}

function PrepPageContent() {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const { actor, loading: authLoading } = useAuth()
  const { topics, problems } = usePrepCatalog()
  const [dashboard, setDashboard] = useState<PrepDashboard | null>(null)
  const [selectedProblemId, setSelectedProblemId] = useState<number | null>(null)
  const [workspaceTab, setWorkspaceTab] = useState<WorkspaceTab>("description")
  const [consoleTab, setConsoleTab] = useState<ConsoleTab>("testcase")
  const [language, setLanguage] = useState<LanguageKey>("python")
  const [selectedTestCaseId, setSelectedTestCaseId] = useState<number | null>(null)
  const [code, setCode] = useState("")
  const [result, setResult] = useState<ExecutionResult | null>(null)
  const [submissions, setSubmissions] = useState<Submission[]>([])
  const [runState, setRunState] = useState<RunState>("idle")
  const [loading, setLoading] = useState(true)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [editorSettings, setEditorSettings] = useState<EditorSettings>({ fontSize: 13, minimap: false, wordWrap: "on" })

  const selectedProblem = useMemo(
    () => problems.find((problem) => problem.id === selectedProblemId) ?? null,
    [problems, selectedProblemId],
  )
  const selectedLanguage = LANGUAGES.find((entry) => entry.value === language) ?? LANGUAGES[0]
  const fileExtension = { python: "py", javascript: "js", typescript: "ts", java: "java", cpp: "cpp" }[language]
  useEffect(() => {
    if (pathname !== "/prep" || authLoading) return
    if (!actor) {
      router.push("/login?next=/prep")
      return
    }
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [actor, authLoading, router])

  useEffect(() => {
    const problemId = Number(searchParams.get("problem"))
    setSelectedProblemId(Number.isFinite(problemId) && problemId > 0 ? problemId : null)
  }, [searchParams])

  useEffect(() => {
    if (selectedProblem && selectedProblem.id !== selectedProblemId) setSelectedProblemId(selectedProblem.id)
  }, [selectedProblem, selectedProblemId])

  useEffect(() => {
    if (!selectedProblem) return
    const nextLanguage = selectedProblem.available_languages?.includes(language)
      ? language
      : (selectedProblem.available_languages?.[0] ?? "python")
    if (nextLanguage !== language) setLanguage(nextLanguage)
    setSelectedTestCaseId(selectedProblem.test_cases?.[0]?.id ?? null)
    setCode(starterFor(selectedProblem, nextLanguage))
    setResult(null)
    setRunState("idle")
    setSubmissions([])
  }, [selectedProblem?.id])

  useEffect(() => {
    if (!selectedProblem) return
    setCode(starterFor(selectedProblem, language))
    setResult(null)
    setRunState("idle")
  }, [language])

  useEffect(() => {
    if (!selectedProblem || workspaceTab !== "submissions") return
    api.get<{ submissions: Submission[] }>(`/prep/problems/${selectedProblem.id}/submissions`)
      .then((data) => setSubmissions(data.submissions))
      .catch((error) => notify.error(error instanceof ApiError ? error.detail : "Failed to load submission history."))
  }, [selectedProblem?.id, workspaceTab])

  async function load(showLoading = true) {
    if (showLoading) setLoading(true)
    try {
      setDashboard(await api.get<PrepDashboard>("/prep/me/dashboard"))
    } catch (error) {
      notify.error(error instanceof ApiError ? error.detail : "Failed to load preparation workspace.")
    } finally {
      if (showLoading) setLoading(false)
    }
  }

  useActivePageRefresh(
    pathname === "/prep",
    !authLoading && Boolean(actor),
    () => load(false),
  )

  function resetEditor() {
    if (!selectedProblem) return
    setCode(starterFor(selectedProblem, language))
    setResult(null)
    setRunState("idle")
    setConsoleTab("testcase")
  }

  async function runCode(mode: "run" | "submit") {
    if (!selectedProblem || !code.trim()) return
    setRunState("running")
    setConsoleTab("result")
    try {
      const execution = await api.post<ExecutionResult>("/prep/execute", {
        problem_id: selectedProblem.id,
        test_case_id: mode === "run" ? selectedTestCaseId : undefined,
        mode,
        language,
        source_code: code,
      })
      setResult(execution)
      setRunState(execution.status === "Accepted" ? "complete" : "error")
      if (mode === "submit" && execution.status === "Accepted") {
        notify.success("Solution accepted by the sandbox.")
        void api.get<PrepDashboard>("/prep/me/dashboard").then(setDashboard).catch(() => {})
      }
    } catch (error) {
      const detail = error instanceof ApiError ? error.detail : "The sandbox could not run this submission."
      setResult({ language, status: "Unavailable", stdout: "", stderr: detail, compile_output: "", time: null, memory: null })
      setRunState("error")
    }
  }

  if (authLoading || loading) {
    return (
      <div className="flex min-h-[calc(100vh-68px)] items-center justify-center bg-[#08090d] text-[13px] text-white/45">
        Loading problem set...
      </div>
    )
  }

  if (!selectedProblem) {
    return <PrepHome topics={topics} problems={problems} dashboard={dashboard} />
  }

  return (
    <div className="min-h-[calc(100vh-68px)] bg-[#08090d] text-white">
            <header className="flex h-14 shrink-0 items-center justify-between border-b border-white/10 bg-[#0d0e14] px-3 sm:px-5">
              <div className="flex min-w-0 items-center gap-3">
                <SidebarTrigger />
                <div className="hidden h-5 w-px bg-white/10 sm:block" />
                <div className="min-w-0">
                  <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.16em] text-white/35"><span>Prep</span><ChevronRight size={12} /><span>{selectedProblem.topic_name}</span></div>
                  <h1 className="truncate text-[14px] font-semibold text-white">{selectedProblem.title}</h1>
                </div>
              </div>
              <div className="relative flex items-center gap-2">
                <button type="button" aria-label="Reset editor" onClick={resetEditor} className="flex size-8 items-center justify-center rounded-md text-white/45 transition-colors hover:bg-white/10 hover:text-white" title="Reset editor"><RotateCcw size={15} /></button>
                <button type="button" aria-label="Editor settings" aria-expanded={settingsOpen} onClick={() => setSettingsOpen((open) => !open)} className={`flex size-8 items-center justify-center rounded-md transition-colors ${settingsOpen ? "bg-white/10 text-white" : "text-white/45 hover:bg-white/10 hover:text-white"}`} title="Editor settings"><Settings2 size={15} /></button>
                {settingsOpen && (
                  <div className="absolute right-0 top-10 z-30 w-[250px] rounded-lg border border-white/10 bg-[#252526] p-4 shadow-[0_16px_40px_rgba(0,0,0,0.45)]">
                    <div className="flex items-center justify-between">
                      <p className="text-[12px] font-semibold text-white">Editor settings</p>
                      <button type="button" onClick={() => setSettingsOpen(false)} className="text-[11px] text-white/40 hover:text-white">Close</button>
                    </div>
                    <label className="mt-4 block text-[11px] text-white/55">
                      Font size <span className="float-right text-white/35">{editorSettings.fontSize}px</span>
                      <input type="range" min="11" max="18" step="1" value={editorSettings.fontSize} onChange={(event) => setEditorSettings((current) => ({ ...current, fontSize: Number(event.target.value) }))} className="mt-2 w-full accent-[#f97316]" />
                    </label>
                    <label className="mt-4 flex items-center justify-between text-[11px] text-white/55">
                      <span>Minimap</span>
                      <input type="checkbox" checked={editorSettings.minimap} onChange={(event) => setEditorSettings((current) => ({ ...current, minimap: event.target.checked }))} className="size-4 accent-[#f97316]" />
                    </label>
                    <label className="mt-4 flex items-center justify-between text-[11px] text-white/55">
                      <span>Word wrap</span>
                      <select value={editorSettings.wordWrap} onChange={(event) => setEditorSettings((current) => ({ ...current, wordWrap: event.target.value as EditorSettings["wordWrap"] }))} className="rounded border border-white/10 bg-[#303030] px-2 py-1 text-[11px] text-white/75 outline-none">
                        <option value="on">On</option>
                        <option value="off">Off</option>
                      </select>
                    </label>
                  </div>
                )}
              </div>
            </header>

            <div className="grid min-h-[calc(100vh-124px)] grid-cols-1 xl:grid-cols-[minmax(360px,0.9fr)_minmax(540px,1.1fr)]">
              <section className="min-h-[560px] overflow-y-auto border-b border-white/10 bg-[#111217] xl:border-b-0 xl:border-r" aria-label="Problem description">
                <div className="flex items-center gap-5 border-b border-white/10 px-5 pt-4 text-[12px] font-medium text-white/45 sm:px-7">
                  {(["description", "solutions", "submissions"] as WorkspaceTab[]).map((tab) => (
                    <button key={tab} type="button" onClick={() => setWorkspaceTab(tab)} className={`relative pb-3 capitalize transition-colors ${workspaceTab === tab ? "text-white" : "hover:text-white/75"}`}>
                      {tab}
                      {workspaceTab === tab && <span className="absolute inset-x-0 bottom-0 h-0.5 bg-[#f97316]" />}
                    </button>
                  ))}
                </div>

                {workspaceTab === "description" && (
                  <div className="space-y-7 px-5 py-6 sm:px-7">
                    <div>
                      <div className="flex flex-wrap items-center gap-3">
                        <h2 className="text-[22px] font-semibold tracking-[-0.02em] text-white">{selectedProblem.title}</h2>
                        <span className={`rounded-full border px-2.5 py-1 text-[10px] font-semibold ${difficultyClass(selectedProblem.difficulty)}`}>{selectedProblem.difficulty}</span>
                        <span className="text-[11px] text-white/35">{selectedProblem.estimated_minutes} min</span>
                      </div>
                      <div className="mt-3 flex items-center gap-4 text-[11px] text-white/40"><span className="inline-flex items-center gap-1.5"><CircleCheck size={13} className="text-[#27b98a]" /> Practice</span><span className="inline-flex items-center gap-1.5"><Lightbulb size={13} className="text-[#e9ad2f]" /> Pattern focus</span></div>
                    </div>

                    <p className="whitespace-pre-line text-[13px] leading-[1.8] text-white/70">{selectedProblem.prompt}</p>

                    <div className="space-y-4">
                      {selectedProblem.test_cases.map((example, index) => (
                        <div key={example.id}>
                          <p className="mb-2 text-[12px] font-semibold text-white">{example.title || `Example ${index + 1}`}</p>
                          <div className="rounded-lg border border-white/10 bg-[#1b1c21] px-4 py-3 font-mono text-[12px] leading-[1.7] text-white/75"><p><span className="text-white/35">Input:</span> {JSON.stringify(example.input)}</p><p><span className="text-white/35">Expected:</span> {example.expected_output}</p>{example.explanation && <p className="mt-1 text-white/40">{example.explanation}</p>}</div>
                        </div>
                      ))}
                    </div>

                    <div>
                      <p className="mb-3 text-[12px] font-semibold text-white">Constraints</p>
                      <ul className="space-y-2 text-[12px] leading-[1.6] text-white/60">{selectedProblem.constraints.map((constraint) => <li key={constraint} className="flex gap-2"><span className="mt-2 size-1 shrink-0 rounded-full bg-white/45" />{constraint}</li>)}</ul>
                    </div>

                    <div className="border-l-2 border-[#f97316]/60 bg-[#f97316]/[0.06] px-4 py-3"><p className="flex items-center gap-2 text-[11px] font-semibold text-[#ffad72]"><Lightbulb size={14} /> Pattern hint</p><p className="mt-1 text-[12px] leading-[1.6] text-white/60">{selectedProblem.hint}</p></div>
                  </div>
                )}
                {workspaceTab === "solutions" && (
                  <div className="space-y-6 px-5 py-6 sm:px-7">
                    <div><p className="eyebrow">LEARNING NOTES</p><h2 className="mt-2 text-[18px] font-semibold text-white">How to think about this problem</h2><p className="mt-3 text-[13px] leading-[1.75] text-white/65">{selectedProblem.hint}</p></div>
                    <div><p className="mb-3 text-[12px] font-semibold text-white">Expected concepts</p><div className="flex flex-wrap gap-2">{selectedProblem.expected_concepts.map((concept) => <span key={concept} className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[11px] text-white/60">{concept}</span>)}</div></div>
                    <div className="rounded-lg border border-white/10 bg-white/[0.03] p-4"><p className="text-[12px] font-semibold text-white">Explain it out loud</p><p className="mt-2 text-[12px] leading-[1.7] text-white/55">After an accepted run, explain the invariant, complexity, and one trade-off before moving on.</p></div>
                  </div>
                )}
                {workspaceTab === "submissions" && (
                  <div className="space-y-3 px-5 py-6 sm:px-7">{submissions.length === 0 ? <div className="flex min-h-[360px] flex-col items-center justify-center text-center text-white/40"><History size={20} /><p className="mt-3 text-[14px] font-medium text-white/70">No submissions yet</p><p className="mt-2 text-[12px]">Run or submit a database test case to build your history.</p></div> : submissions.map((submission) => <div key={submission.id} className="flex items-center justify-between gap-4 rounded-lg border border-white/10 bg-white/[0.03] px-4 py-3"><div><p className={`text-[12px] font-semibold ${submission.status === "Accepted" ? "text-[#5be0b6]" : "text-[#ff8585]"}`}>{submission.status}</p><p className="mt-1 text-[11px] text-white/40">{submission.language} · {submission.passed_tests}/{submission.total_tests} tests · {new Date(submission.created_at).toLocaleString()}</p></div><span className="text-[11px] text-white/35">{submission.runtime_ms ? `${submission.runtime_ms}s` : ""}</span></div>)}</div>
                )}
              </section>

              <section className="flex min-h-[640px] min-w-0 flex-col bg-[#1e1e1e]" aria-label="Code editor and compiler">
                <div className="flex h-11 shrink-0 items-center justify-between border-b border-black/40 bg-[#252526] px-3">
                  <div className="flex min-w-0 items-center gap-2"><div className="flex items-center gap-2 border-r border-white/10 pr-3 text-[11px] text-white/75"><FileCode2 size={14} className="text-[#5ca9e6]" /> solution.{fileExtension}</div><span className="text-[10px] text-white/30">Unsaved changes</span></div>
                  <label className="flex items-center gap-2 text-[11px] text-white/45"><span className="hidden sm:inline">Language</span><select value={language} onChange={(event) => setLanguage(event.target.value as LanguageKey)} className="rounded border border-white/10 bg-[#303031] px-2 py-1 text-[11px] text-white/80 outline-none">{LANGUAGES.filter((entry) => selectedProblem.available_languages.includes(entry.value)).map((entry) => <option key={entry.value} value={entry.value}>{entry.label}</option>)}</select></label>
                </div>

                <div className="min-h-[360px] flex-1"><CodeEditor language={selectedLanguage.monaco} value={code} onChange={setCode} settings={editorSettings} /></div>

                <EditorConsole
                  consoleTab={consoleTab}
                  runState={runState}
                  result={result}
                  testCases={selectedProblem.test_cases}
                  selectedTestCaseId={selectedTestCaseId}
                  onConsoleTabChange={setConsoleTab}
                  onTestCaseChange={setSelectedTestCaseId}
                  onRun={() => void runCode("run")}
                  onSubmit={() => void runCode("submit")}
                />
              </section>
            </div>
    </div>
  )
}

export default function PrepPage() {
  return (
    <Suspense fallback={<div className="min-h-[calc(100vh-68px)] bg-[#08090d]" />}>
      <PrepPageContent />
    </Suspense>
  )
}
