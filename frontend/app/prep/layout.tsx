"use client"

import { Suspense, useEffect, useMemo, useState, type ReactNode } from "react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"

import Navbar from "../components/Navbar"
import { useAuth } from "../../lib/auth-context"
import { api, ApiError } from "../../lib/api"
import { notify } from "../../lib/toast"
import PrepSidebar from "./PrepSidebar"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"

type Topic = { id: number; slug: string; name: string; description: string; difficulty: string }
type Problem = { id: number; slug: string; title: string; difficulty: string; topic_slug: string; topic_name: string }

export default function PrepLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <Suspense fallback={<div className="min-h-screen bg-[#08090d]"><Navbar /></div>}>
      <PrepLayoutContent>{children}</PrepLayoutContent>
    </Suspense>
  )
}

function PrepLayoutContent({ children }: Readonly<{ children: ReactNode }>) {
  const { actor, loading: authLoading } = useAuth()
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const [topics, setTopics] = useState<Topic[]>([])
  const [problems, setProblems] = useState<Problem[]>([])
  const [openTopics, setOpenTopics] = useState<Record<string, boolean>>({})
  const [loading, setLoading] = useState(true)

  const selectedProblemId = Number(searchParams.get("problem")) || null
  const selectedProblem = useMemo(
    () => problems.find((problem) => problem.id === selectedProblemId) ?? problems[0] ?? null,
    [problems, selectedProblemId],
  )
  const selectedTopic = searchParams.get("topic") ?? ""
  const topicSections = useMemo(
    () => topics.map((topic) => ({ topic, problems: problems.filter((problem) => problem.topic_slug === topic.slug) })),
    [topics, problems],
  )

  useEffect(() => {
    if (authLoading) return
    if (!actor) {
      router.push(`/login?next=${encodeURIComponent(pathname)}`)
      return
    }
    api.get<{ topics: Topic[]; problems: Problem[] }>("/prep/catalog")
      .then((catalog) => {
        setTopics(catalog.topics)
        setProblems(catalog.problems)
      })
      .catch((error) => notify.error(error instanceof ApiError ? error.detail : "Failed to load prep navigation."))
      .finally(() => setLoading(false))
  }, [actor, authLoading, pathname, router])

  useEffect(() => {
    if (!topics.length) return
    setOpenTopics((current) => Object.keys(current).length ? current : Object.fromEntries(topics.map((topic) => [topic.slug, true])))
  }, [topics])

  function selectTopic(slug: string) {
    if (pathname === "/prep") {
      router.push(slug ? `/prep?topic=${encodeURIComponent(slug)}` : "/prep")
    }
  }

  function selectProblem(problemId: number) {
    router.push(`/prep?problem=${problemId}`)
  }

  if (authLoading || loading || !selectedProblem) {
    return (
      <div className="min-h-screen bg-[#08090d] text-white">
        <Navbar />
        <div className="flex min-h-[calc(100vh-68px)] items-center justify-center pt-[68px] text-[13px] text-white/45">
          Loading prep workspace...
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#08090d] text-white">
      <Navbar />
      <div className="pt-[68px]">
        <SidebarProvider defaultOpen className="min-h-[calc(100vh-68px)]">
          <PrepSidebar
            topics={topics}
            problems={problems}
            topicSections={topicSections}
            selectedTopic={selectedTopic}
            selectedProblem={selectedProblem}
            openTopics={openTopics}
            onSelectTopic={selectTopic}
            onToggleTopic={(slug) => setOpenTopics((current) => ({ ...current, [slug]: !(current[slug] ?? true) }))}
            onSelectProblem={selectProblem}
          />
          <SidebarInset className="min-h-[calc(100vh-68px)] min-w-0">{children}</SidebarInset>
        </SidebarProvider>
      </div>
    </div>
  )
}
