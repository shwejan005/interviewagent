"use client"

import { CircleAlert, CircleCheck, LoaderCircle, LockKeyhole, Send, Terminal, Play } from "lucide-react"

import { Button } from "../components/ui"

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
  tests?: Array<{ id: number; title: string; passed: boolean; status: string; stdout: string; stderr: string; compile_output: string; is_hidden: boolean }>
}

type TestCase = { id: number; title: string; input: Record<string, unknown>; expected_output: string; explanation: string; is_hidden: boolean; position: number }

type EditorConsoleProps = {
  consoleTab: ConsoleTab
  runState: RunState
  result: ExecutionResult | null
  testCases: TestCase[]
  selectedTestCaseId: number | null
  onConsoleTabChange: (tab: ConsoleTab) => void
  onTestCaseChange: (id: number) => void
  onRun: () => void
  onSubmit: () => void
}

function ResultPanel({ runState, result }: Readonly<Pick<EditorConsoleProps, "runState" | "result">>) {
  if (runState === "running") {
    return <div className="flex items-center gap-2 text-white/45"><LoaderCircle size={14} className="animate-spin" /> Running in isolated sandbox...</div>
  }
  if (!result) return <p className="text-white/35">Run your code to see compiler and runtime output.</p>

  const accepted = result.status === "Accepted"
  return (
    <div className="space-y-3">
      <div className={`flex items-center gap-2 font-sans text-[12px] ${accepted ? "text-[#5be0b6]" : "text-[#ff8585]"}`}>
        {accepted ? <CircleCheck size={15} /> : <CircleAlert size={15} />}
        {result.status}
        <span className="ml-auto text-[10px] text-white/35">{result.time ? `${result.time}s` : ""}{result.memory ? ` · ${result.memory} KB` : ""}</span>
      </div>
      {result.compile_output && <pre className="whitespace-pre-wrap text-[#ffb3b3]">{result.compile_output}</pre>}
      {result.stderr && <pre className="whitespace-pre-wrap text-[#ffb3b3]">{result.stderr}</pre>}
      {result.stdout && <pre className="whitespace-pre-wrap text-[#a9e8ca]">{result.stdout}</pre>}
      {!result.stdout && !result.stderr && !result.compile_output && <p className="text-white/35">No output.</p>}
      {result.tests && result.tests.length > 0 && <div className="space-y-1 border-t border-white/10 pt-3">{result.tests.map((test) => <p key={test.id} className={test.passed ? "text-[#5be0b6]" : "text-[#ff8585]"}>{test.passed ? "✓" : "×"} {test.title} · {test.status}</p>)}</div>}
    </div>
  )
}

export default function EditorConsole({
  consoleTab,
  runState,
  result,
  testCases,
  selectedTestCaseId,
  onConsoleTabChange,
  onTestCaseChange,
  onRun,
  onSubmit,
}: Readonly<EditorConsoleProps>) {
  const content = consoleTab === "testcase" ? (
    <div className="flex min-h-0 flex-1 flex-col gap-3 p-4">
      <div className="flex items-center gap-2">
        {testCases.map((testCase) => <button key={testCase.id} type="button" onClick={() => onTestCaseChange(testCase.id)} className={`rounded-md px-3 py-1.5 text-[11px] ${selectedTestCaseId === testCase.id ? "bg-white/10 text-white" : "text-white/40 hover:bg-white/[0.06] hover:text-white"}`}>{testCase.title}</button>)}
      </div>
      {testCases.find((testCase) => testCase.id === selectedTestCaseId) && <div className="min-h-0 flex-1 overflow-auto rounded-md border border-white/10 bg-[#303030] p-3 font-mono text-[12px] leading-[1.6] text-white/75"><p className="mb-2 text-[10px] uppercase tracking-[0.14em] text-white/35">Input</p><pre className="whitespace-pre-wrap">{JSON.stringify(testCases.find((testCase) => testCase.id === selectedTestCaseId)?.input, null, 2)}</pre><p className="mb-2 mt-4 text-[10px] uppercase tracking-[0.14em] text-white/35">Expected output</p><pre className="whitespace-pre-wrap">{testCases.find((testCase) => testCase.id === selectedTestCaseId)?.expected_output}</pre></div>}
    </div>
  ) : (
    <div className="min-h-0 flex-1 overflow-auto p-4 font-mono text-[12px] leading-[1.7]"><ResultPanel runState={runState} result={result} /></div>
  )

  return (
    <div className="flex h-[278px] shrink-0 flex-col border-t border-black/50 bg-[#252526]">
      <div className="flex h-11 items-center gap-5 border-b border-black/40 px-4 text-[11px] font-medium text-white/45">
        <button type="button" onClick={() => onConsoleTabChange("testcase")} className={`relative h-full ${consoleTab === "testcase" ? "text-white" : "hover:text-white/75"}`}>Testcase{consoleTab === "testcase" && <span className="absolute inset-x-0 bottom-0 h-0.5 bg-[#f97316]" />}</button>
        <button type="button" onClick={() => onConsoleTabChange("result")} className={`relative h-full ${consoleTab === "result" ? "text-white" : "hover:text-white/75"}`}>Result{consoleTab === "result" && <span className="absolute inset-x-0 bottom-0 h-0.5 bg-[#f97316]" />}</button>
        <span className="ml-auto inline-flex items-center gap-1.5 text-[10px] text-white/30"><Terminal size={13} /> Sandbox console</span>
      </div>
      {content}
      <div className="flex items-center justify-between border-t border-black/40 px-4 py-3">
        <span className="inline-flex items-center gap-1.5 text-[10px] text-white/30"><LockKeyhole size={12} /> Network disabled · 2s CPU · 128 MB</span>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" onClick={onRun} loading={runState === "running"}><Play size={13} /> Run</Button>
          <Button size="sm" onClick={onSubmit} loading={runState === "running"}><Send size={13} /> Submit</Button>
        </div>
      </div>
    </div>
  )
}
