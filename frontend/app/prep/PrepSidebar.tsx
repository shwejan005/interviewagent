"use client"

import { BookOpen, ChevronDown, CircleCheck, FileCode2, History, ListChecks, LockKeyhole, Sparkles } from "lucide-react"
import Link from "next/link"

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarSeparator,
} from "@/components/ui/sidebar"

type Topic = { id: number; slug: string; name: string }
type Problem = { id: number; title: string; difficulty: string; topic_slug: string }
type TopicSection = { topic: Topic; problems: Problem[] }

type PrepSidebarProps = {
  topics: Topic[]
  problems: Problem[]
  topicSections: TopicSection[]
  selectedTopic: string
  selectedProblem: Problem
  openTopics: Record<string, boolean>
  onSelectTopic: (slug: string) => void
  onToggleTopic: (slug: string) => void
  onSelectProblem: (problemId: number) => void
}

export default function PrepSidebar({
  topics,
  problems,
  topicSections,
  selectedTopic,
  selectedProblem,
  openTopics,
  onSelectTopic,
  onToggleTopic,
  onSelectProblem,
}: Readonly<PrepSidebarProps>) {
  return (
    <Sidebar variant="sidebar" collapsible="offcanvas" topOffset={68}>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Workspace</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton asChild isActive><Link href="/prep"><BookOpen size={15} /> <span>Problem set</span></Link></SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton asChild><Link href="/prep/roadmap"><Sparkles size={15} /> <span>Roadmap</span></Link></SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton asChild><Link href="/prep/dashboard"><History size={15} /> <span>Insights</span></Link></SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarSeparator />

        <SidebarGroup>
          <SidebarGroupLabel>Problem set</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton isActive={!selectedTopic} onClick={() => onSelectTopic("")}>
                  <ListChecks size={15} />
                  <span>All problems</span>
                  <span className="ml-auto text-[10px] text-white/30">{problems.length}</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
              {topicSections.map(({ topic, problems: topicProblems }) => {
                const isOpen = openTopics[topic.slug] ?? true
                return (
                  <SidebarMenuItem key={topic.id}>
                    <SidebarMenuButton
                      isActive={selectedTopic === topic.slug}
                      onClick={() => onToggleTopic(topic.slug)}
                      aria-expanded={isOpen}
                      className="font-medium"
                    >
                      <ChevronDown size={14} className={`shrink-0 transition-transform ${isOpen ? "" : "-rotate-90"}`} />
                      <span className="truncate">{topic.name}</span>
                      <span className="ml-auto text-[10px] text-white/30">{topicProblems.length}</span>
                    </SidebarMenuButton>
                    {isOpen && (
                      <SidebarMenu className="ml-3 mt-1 border-l border-white/10 pl-2">
                        {topicProblems.map((problem) => (
                          <SidebarMenuItem key={problem.id}>
                                  <SidebarMenuButton isActive={problem.id === selectedProblem.id} onClick={() => onSelectProblem(problem.id)} className="py-1.5 text-[11px]">
                              {problem.id === selectedProblem.id ? <CircleCheck size={14} className="shrink-0 text-[#f97316]" /> : <FileCode2 size={14} />}
                              <span className="truncate">{problem.title}</span>
                              <span className={`ml-auto shrink-0 text-[9px] ${problem.difficulty === "MEDIUM" ? "text-[#e9ad2f]" : "text-white/35"}`}>{problem.difficulty[0]}</span>
                            </SidebarMenuButton>
                          </SidebarMenuItem>
                        ))}
                      </SidebarMenu>
                    )}
                  </SidebarMenuItem>
                )
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="border-t border-white/10">
        <div className="flex items-center justify-between px-2 py-1 text-[10px] text-white/35">
          <span>Text + code practice</span>
          <LockKeyhole size={13} />
        </div>
      </SidebarFooter>
    </Sidebar>
  )
}
