"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Navbar from "../components/Navbar";
import {
  Button,
  EmptyState,
  GlassCard,
  PageHeader,
  PageShell,
  SkeletonList,
  StatusPill,
  Textarea,
} from "../components/ui";
import { useAuth } from "../../lib/auth-context";
import { api, ApiError } from "../../lib/api";
import { notify } from "../../lib/toast";

type Topic = { id: number; slug: string; name: string; description: string; difficulty: string };
type Problem = { id: number; title: string; prompt: string; difficulty: string; estimated_minutes: number; topic_name: string };
type Roadmap = { id: number; title: string; target_role: string; nodes: Array<{ id: number; topic_name: string; status: string; position: number }> };

type SubmissionState = { problem: Problem; answer: string } | null;

export default function PrepPage() {
  const router = useRouter();
  const { actor, loading: authLoading } = useAuth();
  const [topics, setTopics] = useState<Topic[]>([]);
  const [problems, setProblems] = useState<Problem[]>([]);
  const [roadmaps, setRoadmaps] = useState<Roadmap[]>([]);
  const [selectedTopic, setSelectedTopic] = useState("");
  const [submission, setSubmission] = useState<SubmissionState>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (authLoading) return;
    if (!actor) {
      router.push("/login?next=/prep");
      return;
    }
    void load();
  }, [actor, authLoading, router]);

  useEffect(() => {
    if (!actor) return;
    const query = selectedTopic ? `?topic=${encodeURIComponent(selectedTopic)}` : "";
    api.get<{ problems: Problem[] }>(`/prep/problems${query}`)
      .then((data) => setProblems(data.problems))
      .catch((error) => notify.error(error instanceof ApiError ? error.detail : "Failed to load problems."));
  }, [actor, selectedTopic]);

  const load = async () => {
    setLoading(true);
    try {
      const [topicData, problemData, roadmapData] = await Promise.all([
        api.get<{ topics: Topic[] }>("/prep/topics"),
        api.get<{ problems: Problem[] }>("/prep/problems"),
        api.get<{ roadmaps: Roadmap[] }>("/prep/roadmaps"),
      ]);
      setTopics(topicData.topics);
      setProblems(problemData.problems);
      setRoadmaps(roadmapData.roadmaps);
    } catch (error) {
      notify.error(error instanceof ApiError ? error.detail : "Failed to load preparation suite.");
    } finally {
      setLoading(false);
    }
  };

  const createRoadmap = async () => {
    try {
      const roadmap = await api.post<Roadmap>("/prep/roadmaps", {
        target_role: "Backend Developer",
        topic_slugs: topics.slice(0, 4).map((topic) => topic.slug),
      });
      setRoadmaps((current) => [roadmap, ...current]);
      notify.success("Roadmap created.");
    } catch (error) {
      notify.error(error instanceof ApiError ? error.detail : "Failed to create roadmap.");
    }
  };

  const completeNode = async (roadmapId: number, nodeId: number) => {
    try {
      const updated = await api.post<Roadmap>(`/prep/roadmaps/${roadmapId}/nodes/${nodeId}/complete`);
      setRoadmaps((current) => current.map((roadmap) => roadmap.id === updated.id ? updated : roadmap));
    } catch (error) {
      notify.error(error instanceof ApiError ? error.detail : "Failed to update roadmap.");
    }
  };

  const submitAnswer = async () => {
    if (!submission) return;
    setSubmitting(true);
    try {
      await api.post(`/prep/problems/${submission.problem.id}/submissions`, { answer_text: submission.answer });
      notify.success("Answer recorded for review. No code was executed.");
      setSubmission(null);
    } catch (error) {
      notify.error(error instanceof ApiError ? error.detail : "Failed to record answer.");
    } finally {
      setSubmitting(false);
    }
  };

  if (authLoading || loading) {
    return <><Navbar /><PageShell className="!max-w-[1180px] pt-[112px]"><SkeletonList count={4} /></PageShell></>;
  }

  return (
    <div className="min-h-screen">
      <Navbar />
      <PageShell className="!max-w-[1180px] pt-[112px]">
        <PageHeader
          eyebrow="PREP SUITE — TEXT FIRST"
          title="Build interview-ready evidence"
          description="Follow a curated roadmap, practice reasoning, and record progress. Code execution and verified-skill claims remain disabled until an isolated sandbox and review policy are in place."
          actions={<Button onClick={createRoadmap}>Create roadmap</Button>}
        />

        <div className="mt-8 grid grid-cols-1 gap-5 lg:grid-cols-[1fr_1.4fr]">
          <GlassCard padding="lg">
            <p className="eyebrow">TOPIC GRAPH</p>
            <div className="mt-5 flex flex-col gap-2">
              {topics.map((topic) => (
                <button
                  key={topic.id}
                  type="button"
                  onClick={() => setSelectedTopic(selectedTopic === topic.slug ? "" : topic.slug)}
                  className={`rounded-lg border p-3 text-left transition-colors ${selectedTopic === topic.slug ? "border-brand bg-[rgba(249,115,22,0.08)]" : "border-subtle hover:border-strong"}`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-[13px] font-semibold text-ink-heading">{topic.name}</span>
                    <StatusPill tone="muted">{topic.difficulty}</StatusPill>
                  </div>
                  <p className="mt-1 text-[12px] leading-[1.5] text-ink-subtle">{topic.description}</p>
                </button>
              ))}
            </div>
          </GlassCard>

          <GlassCard padding="lg">
            <div className="flex items-center justify-between gap-3">
              <p className="eyebrow">PROBLEM BANK</p>
              <span className="mono text-[11px] text-ink-subtle">{problems.length} starter problems</span>
            </div>
            <div className="mt-5 flex flex-col gap-3">
              {problems.length === 0 ? <EmptyState title="No problems in this topic" description="Choose another topic." /> : problems.map((problem) => (
                <div key={problem.id} className="border-b border-subtle pb-4 last:border-0">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-[14px] font-semibold text-ink-heading">{problem.title}</p>
                      <p className="mt-1 text-[11px] text-ink-subtle">{problem.topic_name} · {problem.estimated_minutes} min</p>
                    </div>
                    <StatusPill tone={problem.difficulty === "MEDIUM" ? "warning" : "muted"}>{problem.difficulty}</StatusPill>
                  </div>
                  <p className="mt-3 text-[12px] leading-[1.6] text-ink-muted">{problem.prompt}</p>
                  <Button size="sm" variant="secondary" className="mt-3" onClick={() => setSubmission({ problem, answer: "" })}>Write response</Button>
                </div>
              ))}
            </div>
          </GlassCard>
        </div>

        <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-2">
          <GlassCard padding="lg">
            <p className="eyebrow">YOUR ROADMAPS</p>
            <div className="mt-5 flex flex-col gap-3">
              {roadmaps.length === 0 ? <EmptyState title="No roadmap yet" description="Create one to turn the topic graph into a sequence." /> : roadmaps.map((roadmap) => (
                <div key={roadmap.id} className="border-b border-subtle pb-4 last:border-0">
                  <p className="text-[14px] font-semibold text-ink-heading">{roadmap.title}</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {roadmap.nodes.map((node) => (
                      <button key={node.id} type="button" onClick={() => completeNode(roadmap.id, node.id)} className={`rounded-full border px-3 py-1.5 text-[11px] ${node.status === "COMPLETE" ? "border-success text-success" : "border-subtle text-ink-muted hover:border-brand"}`}>
                        {node.position}. {node.topic_name}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </GlassCard>

          <GlassCard padding="lg">
            <p className="eyebrow">SAFETY BOUNDARY</p>
            <p className="mt-4 text-[13px] leading-[1.7] text-ink-muted">
              Responses are stored as practice evidence and can be reviewed later. They do not execute arbitrary code, do not grant verified skills automatically, and do not change hiring recommendations without an explicit human-reviewed policy.
            </p>
          </GlassCard>
        </div>
      </PageShell>

      {submission && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/70 p-5">
          <GlassCard elevation="high" padding="lg" className="w-full max-w-[620px]">
            <p className="eyebrow">PRACTICE RESPONSE</p>
            <h2 className="mt-2 text-[18px] font-semibold text-ink-heading">{submission.problem.title}</h2>
            <Textarea className="mt-5" label="YOUR RESPONSE" rows={10} value={submission.answer} onChange={(event) => setSubmission({ ...submission, answer: event.target.value })} />
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setSubmission(null)}>Cancel</Button>
              <Button onClick={submitAnswer} loading={submitting} disabled={!submission.answer.trim()}>Record response</Button>
            </div>
          </GlassCard>
        </div>
      )}
    </div>
  );
}
