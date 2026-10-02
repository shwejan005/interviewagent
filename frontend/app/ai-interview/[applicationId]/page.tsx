"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import Navbar from "../../components/Navbar";
import { Button, GlassCard, PageHeader, PageShell, SkeletonList, StatusPill, Textarea } from "../../components/ui";
import { useAuth } from "../../../lib/auth-context";
import { api, ApiError } from "../../../lib/api";
import type { CandidateAIInterview } from "../../../lib/types";

const ACTIVE_POLL_STATUSES = new Set(["SCREENING_QUEUED", "SCREENING", "ANSWER_PROCESSING", "REPORT_PENDING"]);
const DRAFT_RETENTION_MS = 7 * 24 * 60 * 60 * 1000;

type SpeechRecognitionResultLike = { isFinal: boolean; length: number; [index: number]: { transcript: string } };
type SpeechRecognitionEventLike = { resultIndex: number; results: ArrayLike<SpeechRecognitionResultLike> };
type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};
type SpeechRecognitionConstructorLike = new () => SpeechRecognitionLike;

function speechRecognitionConstructor(): SpeechRecognitionConstructorLike | undefined {
  const speechWindow = window as Window & {
    SpeechRecognition?: SpeechRecognitionConstructorLike;
    webkitSpeechRecognition?: SpeechRecognitionConstructorLike;
  };
  return speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition;
}

function answerDraftKey(userId: number, applicationId: number, turnId: number): string {
  return `evalia:ai-draft:${userId}:${applicationId}:${turnId}`;
}

function readLocalAnswerDraft(key: string): { text: string; updatedAt: number } | null {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { text?: unknown; updatedAt?: unknown };
    if (typeof parsed.text !== "string" || typeof parsed.updatedAt !== "number") return null;
    if (Date.now() - parsed.updatedAt > DRAFT_RETENTION_MS) {
      window.localStorage.removeItem(key);
      return null;
    }
    return { text: parsed.text, updatedAt: parsed.updatedAt };
  } catch {
    return null;
  }
}

export default function ApplicationAIInterviewPage() {
  const params = useParams();
  const router = useRouter();
  const applicationId = Number(params.applicationId);
  const { actor, loading: authLoading } = useAuth();
  const [interview, setInterview] = useState<CandidateAIInterview | null>(null);
  const [loading, setLoading] = useState(true);
  const [acceptedNotice, setAcceptedNotice] = useState(false);
  const [answer, setAnswer] = useState("");
  const [answerMode, setAnswerMode] = useState<"VOICE" | "TEXT">("VOICE");
  const [listening, setListening] = useState(false);
  const [speechSupported, setSpeechSupported] = useState(false);
  const [repeatNotice, setRepeatNotice] = useState(false);
  const [hydratedDraftKey, setHydratedDraftKey] = useState<string | null>(null);
  const [draftSaveState, setDraftSaveState] = useState<"saved" | "saving" | "device-only">("saved");
  const [starting, setStarting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const draftSaveQueue = useRef<Promise<void>>(Promise.resolve());
  const draftTimerRef = useRef<number | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const finalTranscriptRef = useRef("");

  useEffect(() => {
    setSpeechSupported(Boolean(speechRecognitionConstructor()));
    return () => recognitionRef.current?.abort();
  }, []);

  const loadInterview = useCallback(async (showLoading = false) => {
    if (!Number.isSafeInteger(applicationId) || applicationId < 1) {
      setError("This application link is invalid.");
      setLoading(false);
      return;
    }
    if (showLoading) setLoading(true);
    try {
      const response = await api.get<CandidateAIInterview>(`/me/applications/${applicationId}/ai-interview`);
      setInterview(response);
      if (response.status !== "INTERVIEW_READY" && response.modality) setAnswerMode(response.modality);
      setError(null);
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.status === 404) {
        setError("An AI interview is not available for this application yet.");
      } else {
        setError(requestError instanceof ApiError ? requestError.detail : "Unable to load this interview.");
      }
    } finally {
      if (showLoading) setLoading(false);
    }
  }, [applicationId]);

  useEffect(() => {
    if (authLoading) return;
    if (!actor) {
      router.push(`/login?next=/ai-interview/${applicationId}`);
      return;
    }
    void loadInterview(true);
  }, [actor, authLoading, applicationId, loadInterview, router]);

  useEffect(() => {
    if (!interview || !ACTIVE_POLL_STATUSES.has(interview.status)) return;
    const timer = window.setTimeout(() => void loadInterview(), 1800);
    return () => window.clearTimeout(timer);
  }, [interview, loadInterview]);

  const currentQuestion = interview?.current_question ?? null;
  const draftKey = actor && currentQuestion ? answerDraftKey(actor.user_id, applicationId, currentQuestion.id) : null;
  const draftSaveMessage = (() => {
    switch (draftSaveState) {
      case "saving": return "Saving draft…";
      case "device-only": return "Draft saved on this device; server sync is pending.";
      default: return "Draft saved. You can return later.";
    }
  })();

  const persistDraft = useCallback((turnId: number, text: string) => {
    const save = draftSaveQueue.current.catch(() => undefined).then(async () => {
      await api.put<{ draft_answer_text: string; draft_updated_at: string }>(
        `/me/applications/${applicationId}/ai-interview/draft`,
        { turn_id: turnId, draft_answer_text: text },
      );
      setDraftSaveState("saved");
    });
    draftSaveQueue.current = save;
    return save;
  }, [applicationId]);

  useEffect(() => {
    if (!currentQuestion || !draftKey) {
      setAnswer("");
      setHydratedDraftKey(null);
      setDraftSaveState("saved");
      return;
    }
    const serverText = currentQuestion.draft_answer_text || "";
    const serverUpdatedAt = currentQuestion.draft_updated_at ? Date.parse(currentQuestion.draft_updated_at) : 0;
    const localDraft = readLocalAnswerDraft(draftKey);
    if (localDraft && localDraft.updatedAt > serverUpdatedAt) {
      setAnswer(localDraft.text);
      setDraftSaveState("device-only");
    } else {
      setAnswer(serverText);
      setDraftSaveState("saved");
    }
    setHydratedDraftKey(draftKey);
  }, [currentQuestion?.id, currentQuestion?.draft_answer_text, currentQuestion?.draft_updated_at, draftKey]);

  useEffect(() => {
    if (!currentQuestion || !draftKey || hydratedDraftKey !== draftKey || interview?.status !== "INTERVIEW_IN_PROGRESS" || submitting) return;

    const localUpdatedAt = Date.now();
    try {
      if (answer) window.localStorage.setItem(draftKey, JSON.stringify({ text: answer, updatedAt: localUpdatedAt }));
      else window.localStorage.removeItem(draftKey);
    } catch {
      // Server autosave remains available when the browser disables local storage.
    }

    setDraftSaveState("saving");
    draftTimerRef.current = window.setTimeout(() => {
      void persistDraft(currentQuestion.id, answer).catch(() => {
        setDraftSaveState("device-only");
      });
    }, 500);

    return () => {
      if (draftTimerRef.current !== null) window.clearTimeout(draftTimerRef.current);
      draftTimerRef.current = null;
    };
  }, [answer, currentQuestion?.id, draftKey, hydratedDraftKey, interview?.status, persistDraft, submitting]);

  const saveAndReturnLater = async () => {
    if (!currentQuestion || interview?.status !== "INTERVIEW_IN_PROGRESS" || submitting || leaving) return;
    if (draftTimerRef.current !== null) window.clearTimeout(draftTimerRef.current);
    draftTimerRef.current = null;
    setLeaving(true);
    setError(null);
    try {
      await persistDraft(currentQuestion.id, answer);
      router.push("/applications");
    } catch (requestError) {
      setDraftSaveState("device-only");
      setError(requestError instanceof ApiError ? requestError.detail : "The draft is saved on this device, but could not sync. Stay here and try again when you are online.");
      setLeaving(false);
    }
  };

  const startInterview = async () => {
    if (!interview || !acceptedNotice) return;
    setStarting(true);
    setError(null);
    try {
      const response = await api.post<CandidateAIInterview>(`/me/applications/${applicationId}/ai-interview/start`, {
        accepted: true,
        notice_version: interview.candidate_notice_version,
        modality: answerMode,
      });
      setInterview(response);
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.detail : "Could not start the interview.");
      await loadInterview();
    } finally {
      setStarting(false);
    }
  };

  const startListening = () => {
    const Recognition = speechRecognitionConstructor();
    if (!Recognition) {
      setError("Voice transcription is not available in this browser. Use the text accommodation or open this interview in a supported browser.");
      return;
    }
    try {
      const recognition = new Recognition();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = "en-US";
      finalTranscriptRef.current = answer.trim();
      recognition.onresult = (event) => {
        let interim = "";
        for (let index = event.resultIndex; index < event.results.length; index += 1) {
          const result = event.results[index];
          const transcript = result[0]?.transcript?.trim();
          if (!transcript) continue;
          if (result.isFinal) {
            finalTranscriptRef.current = `${finalTranscriptRef.current} ${transcript}`.trim();
          } else {
            interim = `${interim} ${transcript}`.trim();
          }
        }
        setAnswer(`${finalTranscriptRef.current} ${interim}`.trim());
      };
      recognition.onerror = (event) => {
        setListening(false);
        const messages: Record<string, string> = {
          "not-allowed": "Microphone permission was denied. Allow microphone access or use the text accommodation.",
          "audio-capture": "No microphone was found. Connect a microphone or use the text accommodation.",
          network: "The browser's speech-recognition service is unavailable. Try again or use the text accommodation.",
        };
        setError(messages[event.error] || "Voice transcription stopped. Your captured transcript is still available.");
      };
      recognition.onend = () => setListening(false);
      recognitionRef.current = recognition;
      recognition.start();
      setError(null);
      setListening(true);
    } catch {
      setError("The microphone could not be started. Check browser permissions and try again.");
      setListening(false);
    }
  };

  const stopListening = () => {
    recognitionRef.current?.stop();
    setListening(false);
  };

  const switchToTextAccommodation = async () => {
    if (interview?.status !== "INTERVIEW_IN_PROGRESS" || submitting || listening) return;
    setError(null);
    try {
      await api.post(`/me/applications/${applicationId}/ai-interview/text-accommodation`, {
        notice_version: interview.candidate_notice_version,
      });
      recognitionRef.current?.abort();
      setListening(false);
      setAnswerMode("TEXT");
      setInterview({ ...interview, modality: "TEXT" });
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.detail : "The text accommodation could not be selected. Your interview progress is still saved.");
    }
  };

  const submitAnswer = async (event: FormEvent) => {
    event.preventDefault();
    if (!interview?.current_question || !answer.trim() || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.post(`/me/applications/${applicationId}/ai-interview/answers`, {
        turn_id: interview.current_question.id,
        answer: answer.trim(),
        source: answerMode,
      });
      if (draftKey) window.localStorage.removeItem(draftKey);
      setDraftSaveState("saved");
      setAnswer("");
      finalTranscriptRef.current = "";
      setInterview({ ...interview, status: "ANSWER_PROCESSING", current_question: null, message: "Your answer is saved and being evaluated." });
      await loadInterview();
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.status === 409) {
        if (draftKey) window.localStorage.removeItem(draftKey);
        setError("The latest interview state has been restored. Review the current question before submitting again.");
        await loadInterview(true);
      } else {
        setError(requestError instanceof ApiError ? requestError.detail : "Your answer could not be submitted. Your draft is still here.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (authLoading || loading) {
    return <div className="min-h-screen"><Navbar /><PageShell className="!max-w-[760px] pt-[112px]"><SkeletonList count={3} /></PageShell></div>;
  }

  if (!interview) {
    return (
      <div className="min-h-screen">
        <Navbar />
        <PageShell className="!max-w-[760px] pt-[112px]">
          <PageHeader eyebrow="APPLICATION INTERVIEW" title="Interview unavailable" />
          <GlassCard className="mt-6 p-5"><p className="text-[13px] text-ink-muted">{error || "This interview is unavailable."}</p><Link href="/applications" className="mt-4 inline-block text-[13px] font-semibold text-brand hover:underline">Back to applications</Link></GlassCard>
        </PageShell>
      </div>
    );
  }

  const showHistory = interview.turns.filter((turn) => turn.answer_text !== null);
  const invitationExpired = interview.status === "INTERVIEW_READY"
    && Boolean(interview.invitation_expires_at)
    && Date.parse(interview.invitation_expires_at || "") <= Date.now();
  let interviewerState = "Questions appear as text";
  if (submitting) interviewerState = "Reviewing your response";
  else if (listening) interviewerState = "Listening to your answer";
  let microphoneState = "Text accommodation selected";
  if (answerMode === "VOICE") microphoneState = listening ? "Microphone active" : "Microphone off";

  return (
    <div className="min-h-screen">
      <Navbar />
      <PageShell className="!max-w-[820px] pt-[112px]">
        <Link href="/applications" className="mono text-[11px] tracking-[0.06em] text-ink-subtle hover:text-brand">← MY APPLICATIONS</Link>
        <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
          <PageHeader eyebrow="AI INTERVIEW" title="Your role-focused interview" />
          <StatusPill tone={interview.status === "REPORT_READY" ? "success" : "primary"}>{interview.status.replaceAll("_", " ")}</StatusPill>
        </div>
        <p className="mt-2 text-[13px] leading-relaxed text-ink-muted">{interview.message}</p>

        {error && <p role="alert" className="mt-4 text-[13px] text-[var(--color-error)]">{error}</p>}

        {interview.status === "INTERVIEW_READY" && (
          <GlassCard elevation="high" padding="lg" className="mt-6">
            <p className="eyebrow">BEFORE YOU START</p>
            <h2 className="mt-2 text-[17px] font-semibold text-ink-heading">Your AI interviewer is ready</h2>
            <p className="mt-3 text-[13px] leading-relaxed text-ink-muted">The interviewer presents questions as text. In the standard voice interview, speak your answers naturally; your recognized transcript and assessment are shared with the hiring team. The AI does not make the hiring decision. You can pause and return later; submitted progress is saved.</p>
            <p className="mt-3 text-[11px] leading-relaxed text-ink-subtle">Evalia stores your transcript, not a recording. Browser speech recognition may process audio according to your browser/provider settings. Camera is not requested. Notice version: {interview.candidate_notice_version}.</p>
            {interview.invitation_expires_at && <p className="mt-2 text-[11px] text-ink-muted">Please join before {new Date(interview.invitation_expires_at).toLocaleString()}.</p>}
            <div className="mt-5 flex flex-col gap-2 rounded-lg border border-subtle bg-[rgba(255,255,255,0.025)] p-4">
              <p className="text-[11px] font-semibold text-ink-heading">Interview format</p>
              <p className="text-[12px] text-ink-muted">Voice answers · text questions · about {interview.role_level.toLowerCase()}-level technical and behavioral topics</p>
              {!speechSupported && <p className="text-[11px] text-[var(--color-warning)]">This browser does not expose speech recognition. You can use the text accommodation or open the interview in a supported browser.</p>}
              <button type="button" className="mt-1 self-start text-[11px] text-brand underline" onClick={() => setAnswerMode((mode) => mode === "VOICE" ? "TEXT" : "VOICE")}>
                {answerMode === "VOICE" ? "Request the text-answer accommodation" : "Use voice answers instead"}
              </button>
              <p className="text-[10px] text-ink-subtle">Selected: {answerMode === "VOICE" ? "Voice answers" : "Text accommodation"}</p>
            </div>
            <label className="mt-5 flex cursor-pointer items-start gap-3 text-[12px] leading-relaxed text-ink-muted">
              <input type="checkbox" checked={acceptedNotice} onChange={(event) => setAcceptedNotice(event.target.checked)} className="mt-0.5 accent-[var(--color-primary)]" />
              <span>I understand this is an AI-led {answerMode === "VOICE" ? "voice" : "text accommodation"} interview and agree to submit my answers for evaluation for this application.</span>
            </label>
            <Button className="mt-5" loading={starting} disabled={!acceptedNotice || invitationExpired || (answerMode === "VOICE" && !speechSupported)} onClick={() => void startInterview()}>Join AI interview</Button>
            {invitationExpired && <p role="alert" className="mt-3 text-[11px] text-[var(--color-warning)]">This invitation expired. Contact the hiring team to request a new invitation.</p>}
          </GlassCard>
        )}

        {interview.status === "SCREENING_QUEUED" || interview.status === "SCREENING" ? (
          <GlassCard className="mt-6 p-5"><p className="text-[13px] text-ink-muted">Screening runs automatically after you apply. You can leave this page; your application tracker will update when it is ready.</p></GlassCard>
        ) : null}

        {interview.status === "ANSWER_PROCESSING" && (
          <GlassCard className="mt-6 p-5"><p className="text-[13px] text-ink-muted">Your answer is safely saved. The interviewer is reviewing it before asking the next question.</p></GlassCard>
        )}

        {currentQuestion && interview.status === "INTERVIEW_IN_PROGRESS" && (
          <GlassCard elevation="high" padding="lg" className="mt-6">
            <div className="grid gap-5 md:grid-cols-[200px_minmax(0,1fr)]">
              <div className="flex flex-col gap-3">
                <div className="flex min-h-[160px] flex-col items-center justify-center rounded-xl border border-subtle bg-[linear-gradient(145deg,rgba(249,115,22,0.13),rgba(20,24,40,0.8))] p-4 text-center">
                  <span className={`mb-3 flex h-14 w-14 items-center justify-center rounded-full border ${listening ? "border-[var(--color-success)] shadow-[0_0_26px_rgba(34,197,94,0.28)]" : "border-brand/40"} bg-[rgba(255,255,255,0.06)] text-[20px] font-bold text-brand`} aria-hidden="true">AI</span>
                  <p className="text-[12px] font-semibold text-ink-heading">Evalia AI interviewer</p>
                  <p className="mt-1 text-[10px] text-ink-subtle">{interviewerState}</p>
                </div>
                <div className="rounded-lg border border-subtle p-3">
                  <p className="eyebrow">YOUR MICROPHONE</p>
                  <p className="mt-2 text-[11px] text-ink-muted">{microphoneState}</p>
                </div>
              </div>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="eyebrow">{currentQuestion.phase} · {currentQuestion.competency_key.replaceAll("_", " ")}</p>
                  <span className="mono text-[10px] text-ink-subtle">LEVEL {currentQuestion.difficulty} · {currentQuestion.question_type.replaceAll("_", " ")}</span>
                </div>
                <div className="mt-3 rounded-xl border border-brand/20 bg-[rgba(249,115,22,0.05)] p-5">
                  <p className="mono text-[9px] tracking-[0.12em] text-brand">QUESTION {currentQuestion.sequence_no}</p>
                  <h2 className="mt-2 text-[18px] font-semibold leading-relaxed text-ink-heading">{currentQuestion.question_text}</h2>
                  <button type="button" className="mt-3 text-[11px] text-brand underline" onClick={() => setRepeatNotice(true)}>Repeat question</button>
                  {repeatNotice && <output aria-live="polite" className="mt-2 block text-[10px] text-ink-subtle">The question is shown above. Take your time before answering.</output>}
                </div>
                <form className="mt-5" onSubmit={submitAnswer}>
                  {answerMode === "VOICE" ? (
                    <>
                      <div className="min-h-[112px] rounded-xl border border-subtle bg-[rgba(255,255,255,0.025)] p-4" aria-live="polite" aria-label="Live transcript captions">
                        <p className="mono text-[9px] tracking-[0.1em] text-ink-subtle">LIVE CAPTIONS</p>
                        <p className="mt-3 whitespace-pre-wrap text-[13px] leading-relaxed text-ink-heading">{answer || (listening ? "Listening… speak naturally." : "Your recognized words will appear here. They are only submitted when you choose to submit.")}</p>
                      </div>
                      <Textarea label="REVIEW AND CORRECT TRANSCRIPT" rows={4} maxLength={12000} value={answer} onChange={(event) => { finalTranscriptRef.current = event.target.value; setAnswer(event.target.value); }} hint="Check the recognized words and correct any transcription mistakes before submitting." />
                      <div className="mt-4 flex flex-wrap items-center gap-2">
                        {listening ? (
                          <Button type="button" variant="secondary" onClick={stopListening}>Finish speaking</Button>
                        ) : (
                          <Button type="button" variant="secondary" disabled={!speechSupported || submitting} onClick={startListening}>{answer ? "Continue speaking" : "Start speaking"}</Button>
                        )}
                        {answer && !listening && <Button type="button" variant="ghost" onClick={() => { setAnswer(""); finalTranscriptRef.current = ""; }}>Clear transcript</Button>}
                        <Button type="button" variant="ghost" disabled={listening || submitting || leaving} onClick={() => void switchToTextAccommodation()}>Switch to text accommodation</Button>
                      </div>
                    </>
                  ) : (
                    <Textarea label="YOUR ANSWER (TEXT ACCOMMODATION)" rows={6} maxLength={12000} value={answer} onChange={(event) => setAnswer(event.target.value)} placeholder="Type your response…" required />
                  )}
                  <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                    <span role="status" aria-live="polite" className="text-[10px] text-ink-subtle">{draftSaveMessage}</span>
                    <div className="flex flex-wrap gap-2">
                      <Button type="button" variant="ghost" loading={leaving} disabled={submitting || listening || leaving} onClick={() => void saveAndReturnLater()}>Save and return later</Button>
                      <Button type="submit" loading={submitting} disabled={!answer.trim() || listening || leaving}>{answerMode === "VOICE" ? "Submit voice answer" : "Submit answer"}</Button>
                    </div>
                  </div>
                </form>
              </div>
            </div>
          </GlassCard>
        )}

        {showHistory.length > 0 && (
          <section className="mt-7">
            <p className="eyebrow">SAVED INTERVIEW PROGRESS</p>
            <div className="mt-3 flex flex-col gap-3">
              {showHistory.map((turn) => (
                <GlassCard key={turn.id} padding="sm">
                  <p className="mono text-[10px] text-ink-subtle">{turn.phase} · LEVEL {turn.difficulty}</p>
                  <p className="mt-2 text-[12px] font-semibold text-ink-heading">{turn.question_text}</p>
                  <p className="mt-2 whitespace-pre-wrap text-[12px] leading-relaxed text-ink-muted">{turn.answer_text}</p>
                </GlassCard>
              ))}
            </div>
          </section>
        )}

        {interview.status === "REPORT_PENDING" && <GlassCard className="mt-6 p-5"><p className="text-[13px] text-ink-muted">You completed the interview. The report is being prepared for recruiter review.</p></GlassCard>}
        {interview.status === "REPORT_READY" && <GlassCard className="mt-6 p-5"><p className="text-[13px] text-ink-muted">Your interview is complete and has been sent to the hiring team for human review. Check your application tracker for updates.</p></GlassCard>}
        {interview.status === "REVIEW_REQUIRED" && <GlassCard className="mt-6 p-5"><p className="text-[13px] text-ink-muted">This step needs additional review by the hiring team. A technical or AI service issue will not be treated as a failed interview.</p></GlassCard>}
      </PageShell>
    </div>
  );
}
