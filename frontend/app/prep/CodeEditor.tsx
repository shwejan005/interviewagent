"use client"

import dynamic from "next/dynamic"

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: () => <div className="flex h-full items-center justify-center bg-[#1e1e1e] text-[12px] text-white/40">Loading editor...</div>,
})

type CodeEditorProps = {
  language: string
  value: string
  onChange: (value: string) => void
  settings: EditorSettings
}

export type EditorSettings = {
  fontSize: number
  minimap: boolean
  wordWrap: "on" | "off"
}

export default function CodeEditor({ language, value, onChange, settings }: Readonly<CodeEditorProps>) {
  return (
    <MonacoEditor
      height="100%"
      language={language}
      theme="vs-dark"
      value={value}
      onChange={(nextValue) => onChange(nextValue ?? "")}
      options={{
        automaticLayout: true,
        bracketPairColorization: { enabled: true },
        cursorBlinking: "smooth",
        fontFamily: "Cascadia Code, Consolas, monospace",
        fontLigatures: true,
        fontSize: settings.fontSize,
        lineNumbers: "on",
        minimap: { enabled: settings.minimap },
        padding: { top: 14, bottom: 14 },
        scrollBeyondLastLine: false,
        smoothScrolling: true,
        suggest: { showMethods: true, showFunctions: true },
        tabSize: 4,
        wordWrap: settings.wordWrap,
      }}
    />
  )
}
