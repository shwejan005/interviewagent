"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Mic, MicOff, PhoneOff, Video, VideoOff } from "lucide-react";
import Navbar from "../../components/Navbar";
import { Button, GlassCard, PageShell, Select, SkeletonList, Textarea } from "../../components/ui";
import { useAuth } from "../../../lib/auth-context";
import { api, ApiError } from "../../../lib/api";

type Participant = { user_id: number; name: string; role: string; self?: boolean };
type JoinResponse = {
  interview_id: number;
  org_id: number;
  title: string;
  posting_title: string;
  org_name: string;
  scheduled_start: string;
  scheduled_end: string;
  timezone: string;
  ticket: string;
  ice_servers?: RTCIceServer[];
  participants: Participant[];
};
const SCORECARD_ITEMS = [
  { key: "role_skills", label: "Role-specific skills and job requirements" },
  { key: "problem_solving", label: "Problem-solving and reasoning" },
  { key: "experience_depth", label: "Depth of relevant experience" },
  { key: "communication", label: "Job-related communication" },
  { key: "collaboration", label: "Collaboration and ownership" },
];
type Signal = {
  type: "room_state" | "peer_joined" | "peer_left" | "offer" | "answer" | "ice_candidate" | "error";
  self_user_id?: number;
  participants?: Participant[];
  participant?: Participant;
  user_id?: number;
  from_user_id?: number;
  to_user_id?: number;
  sdp?: RTCSessionDescriptionInit;
  candidate?: RTCIceCandidateInit;
  message?: string;
};
type PeerState = { participant: Participant; stream: MediaStream | null };

const RTC_CONFIGURATION: RTCConfiguration = {
  iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
};

function backendWebSocketBase(): string {
  const configured = process.env.NEXT_PUBLIC_BACKEND_WS_URL?.trim();
  if (configured) return configured.replace(/\/$/, "");
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.hostname}:8000`;
}

function formatClock(value: string): string {
  return new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

export default function InAppInterviewRoomPage() {
  const params = useParams();
  const router = useRouter();
  const interviewId = Number(params.interviewId);
  const { actor, loading: authLoading } = useAuth();
  const [details, setDetails] = useState<JoinResponse | null>(null);
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [peers, setPeers] = useState<PeerState[]>([]);
  const [loading, setLoading] = useState(true);
  const [joining, setJoining] = useState(false);
  const [connected, setConnected] = useState(false);
  const [muted, setMuted] = useState(false);
  const [cameraOff, setCameraOff] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deviceReady, setDeviceReady] = useState(false);
  const [callEnded, setCallEnded] = useState(false);
  const [scorecardRatings, setScorecardRatings] = useState<Record<string, number | "">>({});
  const [scorecardEvidence, setScorecardEvidence] = useState<Record<string, string>>({});
  const [scorecardRecommendation, setScorecardRecommendation] = useState<"ADVANCE" | "HOLD">("ADVANCE");
  const [scorecardNotes, setScorecardNotes] = useState("");
  const [scorecardSubmitting, setScorecardSubmitting] = useState(false);
  const [scorecardResult, setScorecardResult] = useState<{ submitted: number; expected: number; complete: boolean } | null>(null);
  const localVideoRef = useRef<HTMLVideoElement>(null);
  const localStreamRef = useRef<MediaStream | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const peersRef = useRef(new Map<number, RTCPeerConnection>());
  const rtcConfigurationRef = useRef<RTCConfiguration>(RTC_CONFIGURATION);
  const selfUserIdRef = useRef<number | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      socketRef.current?.close();
      peersRef.current.forEach((peer) => peer.close());
      peersRef.current.clear();
      localStreamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  useEffect(() => {
    if (authLoading) return;
    if (!actor) {
      router.push(`/login?next=/meeting/${interviewId}`);
      return;
    }
    if (!Number.isSafeInteger(interviewId) || interviewId < 1) {
      setError("This interview room link is invalid.");
      setLoading(false);
      return;
    }
    api.post<JoinResponse>(`/me/interviews/${interviewId}/join`)
      .then((response) => {
        setDetails(response);
        setParticipants(response.participants);
        setLoading(false);
      })
      .catch((requestError) => {
        setError(requestError instanceof ApiError ? requestError.detail : "Unable to open this interview room.");
        setLoading(false);
      });
  }, [actor, authLoading, interviewId, router]);

  const updatePeerStream = useCallback((userId: number, stream: MediaStream | null) => {
    setPeers((current) => current.map((peer) => peer.participant.user_id === userId ? { ...peer, stream } : peer));
  }, []);

  const sendSignal = useCallback((message: Record<string, unknown>) => {
    if (socketRef.current?.readyState === WebSocket.OPEN) socketRef.current.send(JSON.stringify(message));
  }, []);

  const ensurePeer = useCallback((participant: Participant) => {
    const existing = peersRef.current.get(participant.user_id);
    if (existing) return existing;
    const connection = new RTCPeerConnection(rtcConfigurationRef.current);
    localStreamRef.current?.getTracks().forEach((track) => connection.addTrack(track, localStreamRef.current!));
    connection.onicecandidate = (event) => {
      if (event.candidate) sendSignal({ type: "ice_candidate", to_user_id: participant.user_id, candidate: event.candidate.toJSON() });
    };
    connection.ontrack = (event) => updatePeerStream(participant.user_id, event.streams[0] || null);
    connection.onconnectionstatechange = () => {
      if (connection.connectionState === "failed") setError("A direct media connection could not be established. Check the network/firewall and rejoin the room.");
    };
    peersRef.current.set(participant.user_id, connection);
    setPeers((current) => current.some((peer) => peer.participant.user_id === participant.user_id)
      ? current
      : [...current, { participant, stream: null }]);
    return connection;
  }, [sendSignal, updatePeerStream]);

  const offerToPeer = useCallback(async (participant: Participant) => {
    if (selfUserIdRef.current === null || selfUserIdRef.current >= participant.user_id) return;
    const connection = ensurePeer(participant);
    const offer = await connection.createOffer();
    await connection.setLocalDescription(offer);
    sendSignal({ type: "offer", to_user_id: participant.user_id, sdp: offer });
  }, [ensurePeer, sendSignal]);

  const handleRoomState = useCallback(async (message: Signal) => {
    selfUserIdRef.current = message.self_user_id ?? actor?.user_id ?? null;
    const others = message.participants || [];
    setParticipants((current) => [...current.filter((item) => item.self), ...others]);
    await Promise.all(others.map((participant) => offerToPeer(participant)));
  }, [actor?.user_id, offerToPeer]);

  const handlePeerJoined = useCallback(async (participant: Participant) => {
    setParticipants((current) => current.some((item) => item.user_id === participant.user_id) ? current : [...current, participant]);
    ensurePeer(participant);
    await offerToPeer(participant);
  }, [ensurePeer, offerToPeer]);

  const handlePeerLeft = useCallback((userId: number) => {
    peersRef.current.get(userId)?.close();
    peersRef.current.delete(userId);
    setPeers((current) => current.filter((peer) => peer.participant.user_id !== userId));
    setParticipants((current) => current.filter((item) => item.user_id !== userId));
  }, []);

  const handlePeerSignal = useCallback(async (message: Signal) => {
    if (!message.from_user_id) return;
    const participant = participants.find((item) => item.user_id === message.from_user_id)
      || { user_id: message.from_user_id, name: "Interview participant", role: "PARTICIPANT" };
    const connection = ensurePeer(participant);
    if (message.type === "offer" && message.sdp) {
      await connection.setRemoteDescription(message.sdp);
      const answer = await connection.createAnswer();
      await connection.setLocalDescription(answer);
      sendSignal({ type: "answer", to_user_id: message.from_user_id, sdp: answer });
    } else if (message.type === "answer" && message.sdp) {
      await connection.setRemoteDescription(message.sdp);
    } else if (message.type === "ice_candidate" && message.candidate) {
      await connection.addIceCandidate(message.candidate);
    }
  }, [ensurePeer, participants, sendSignal]);

  const handleSignal = useCallback(async (message: Signal) => {
    if (message.type === "room_state") {
      await handleRoomState(message);
      return;
    }
    if (message.type === "peer_joined" && message.participant) {
      await handlePeerJoined(message.participant);
      return;
    }
    if (message.type === "peer_left" && message.user_id) {
      handlePeerLeft(message.user_id);
      return;
    }
    if (message.type === "error") {
      setError(message.message || "The meeting signal could not be delivered.");
      return;
    }
    await handlePeerSignal(message);
  }, [handlePeerJoined, handlePeerLeft, handlePeerSignal, handleRoomState]);

  useEffect(() => {
    if (localVideoRef.current && localStreamRef.current) localVideoRef.current.srcObject = localStreamRef.current;
  }, [deviceReady, joining]);

  const joinRoom = async () => {
    if (!details || joining || connected) return;
    setJoining(true);
    setError(null);
    try {
      const freshTicket = await api.post<JoinResponse>(`/me/interviews/${interviewId}/join`);
      setDetails(freshTicket);
      rtcConfigurationRef.current = {
        iceServers: freshTicket.ice_servers?.length ? freshTicket.ice_servers : RTC_CONFIGURATION.iceServers,
      };
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: true });
      if (!mountedRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      localStreamRef.current = stream;
      if (localVideoRef.current) localVideoRef.current.srcObject = stream;
      setDeviceReady(true);
      const websocket = new WebSocket(
        `${backendWebSocketBase()}/ws/interviews/${interviewId}`,
        ["evalia-meeting-v1", freshTicket.ticket],
      );
      socketRef.current = websocket;
      websocket.onopen = () => {
        setConnected(true);
        setJoining(false);
      };
      websocket.onmessage = (event) => {
        try {
          void handleSignal(JSON.parse(event.data) as Signal).catch(() => setError("A peer connection could not be negotiated. Leave and try again."));
        } catch {
          setError("The meeting server sent an unreadable signal.");
        }
      };
      websocket.onerror = () => setError("Could not connect to the in-app meeting signal. Check the backend WebSocket URL and network.");
      websocket.onclose = (event) => {
        setConnected(false);
        if (event.code !== 1000 && mountedRef.current) setError(event.reason || "Meeting signal disconnected. You can leave and rejoin.");
      };
    } catch (mediaError) {
      const name = mediaError instanceof DOMException ? mediaError.name : "";
      if (name === "NotAllowedError") setError("Camera or microphone permission was denied. Allow access in your browser settings and try again.");
      else if (name === "NotFoundError") setError("A camera or microphone was not found. Connect a device and try again.");
      else setError("Could not start your camera and microphone. Check browser permissions and device settings.");
      setJoining(false);
    }
  };

  const disconnectMedia = () => {
    sendSignal({ type: "leave" });
    socketRef.current?.close(1000, "Participant left the room.");
    socketRef.current = null;
    peersRef.current.forEach((peer) => peer.close());
    peersRef.current.clear();
    localStreamRef.current?.getTracks().forEach((track) => track.stop());
    localStreamRef.current = null;
    setConnected(false);
    setDeviceReady(false);
  };

  const selfParticipant = details?.participants.find((participant) => participant.self);
  const isInterviewer = selfParticipant?.role === "INTERVIEWER";

  const leaveRoom = () => {
    disconnectMedia();
    if (isInterviewer) setCallEnded(true);
    else router.push("/interviews");
  };

  const submitScorecard = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!details || !isInterviewer || SCORECARD_ITEMS.some((item) => !scorecardRatings[item.key]) || scorecardSubmitting) return;
    setScorecardSubmitting(true);
    setError(null);
    try {
      const result = await api.post<{ submitted: number; expected: number; complete: boolean }>(
        `/orgs/${details.org_id}/interviews/${interviewId}/scorecard`,
        {
          ratings: SCORECARD_ITEMS.map((item) => ({ ...item, score: Number(scorecardRatings[item.key]), evidence: (scorecardEvidence[item.key] || "").trim() })),
          recommendation: scorecardRecommendation,
          notes: scorecardNotes.trim(),
        },
        { orgId: details.org_id },
      );
      setScorecardResult(result);
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.detail : "Unable to submit this scorecard.");
    } finally {
      setScorecardSubmitting(false);
    }
  };

  const toggleMute = () => {
    const nextMuted = !muted;
    localStreamRef.current?.getAudioTracks().forEach((track) => { track.enabled = !nextMuted; });
    setMuted(nextMuted);
  };

  const toggleCamera = () => {
    const nextOff = !cameraOff;
    localStreamRef.current?.getVideoTracks().forEach((track) => { track.enabled = !nextOff; });
    setCameraOff(nextOff);
  };
  let connectionLabel = "LOBBY";
  if (joining) connectionLabel = "JOINING";
  if (connected) connectionLabel = "CONNECTED";

  if (authLoading || loading) return <><Navbar /><PageShell className="!max-w-[940px] pt-[112px]"><SkeletonList count={3} /></PageShell></>;

  if (!details) return <><Navbar /><PageShell className="!max-w-[760px] pt-[112px]"><GlassCard className="mt-24 p-6"><p className="text-[14px] font-semibold text-ink-heading">Meeting room unavailable</p><p className="mt-2 text-[12px] text-ink-muted">{error || "This interview room is unavailable."}</p><Button className="mt-4" variant="secondary" onClick={() => router.push("/interviews")}>Back to agenda</Button></GlassCard></PageShell></>;

  return (
    <div className="min-h-screen">
      <Navbar />
      <PageShell className="!max-w-[1180px] pt-[104px]">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div><p className="eyebrow">IN-APP HUMAN INTERVIEW</p><h1 className="mt-2 text-[24px] font-bold text-ink-heading">{details.title}</h1><p className="mt-1 text-[12px] text-ink-muted">{details.posting_title} · {details.org_name}</p><p className="mt-1 text-[10px] text-ink-subtle">{formatClock(details.scheduled_start)} ({details.timezone})</p></div>
          <span className={`rounded-full border px-3 py-1 text-[10px] ${connected ? "border-[var(--color-success)]/30 text-[var(--color-success)]" : "border-subtle text-ink-subtle"}`}>{connectionLabel}</span>
        </div>
        {error && <p role="alert" className="mt-4 rounded-lg border border-[var(--color-warning)]/30 bg-[rgba(245,158,11,0.08)] p-3 text-[12px] text-[var(--color-warning)]">{error}</p>}
        <div className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
          <div className="grid min-h-[420px] gap-3 sm:grid-cols-2">
            <GlassCard padding="sm" className="relative min-h-[220px] overflow-hidden bg-black/30">
              <video ref={localVideoRef} autoPlay muted playsInline className="h-full min-h-[200px] w-full rounded-lg object-cover">
                <track kind="captions" srcLang="en" label="Captions unavailable for this human call" src="/empty.vtt" />
              </video>
              <span className="absolute bottom-4 left-4 rounded-md bg-black/60 px-2 py-1 text-[10px] text-white">You{muted ? " · muted" : ""}</span>
            </GlassCard>
            {peers.map((peer) => <RemoteParticipantTile key={peer.participant.user_id} peer={peer} />)}
            {!connected && <GlassCard padding="lg" className="flex min-h-[220px] flex-col items-center justify-center text-center"><span className="flex h-16 w-16 items-center justify-center rounded-full bg-brand/10 text-xl font-bold text-brand">E</span><p className="mt-3 text-[13px] font-semibold text-ink-heading">Secure in-app meeting room</p><p className="mt-1 max-w-[300px] text-[11px] text-ink-subtle">Camera and microphone are not connected until you join. Media is peer-to-peer; the server relays signaling only.</p></GlassCard>}
          </div>
          <aside className="flex flex-col gap-4">
            <GlassCard padding="sm"><p className="eyebrow">PARTICIPANTS</p><div className="mt-3 flex flex-col gap-2">{participants.map((person) => <div key={person.user_id} className="flex items-center justify-between gap-2 text-[11px]"><span className="truncate text-ink-heading">{person.name}{person.self ? " (you)" : ""}</span><span className="text-ink-subtle">{person.role.replaceAll("_", " ")}</span></div>)}</div></GlassCard>
            <GlassCard padding="sm"><p className="eyebrow">CONNECTION</p><p className="mt-2 text-[10px] leading-relaxed text-ink-muted">Media uses a direct peer connection when possible. If TURN is configured, temporary relay credentials are used when direct paths fail. Network and multi-worker validation are still required for production.</p></GlassCard>
            {connected ? (
              <div className="flex flex-wrap gap-2">
                <Button variant="secondary" onClick={toggleMute}>{muted ? <MicOff size={15} /> : <Mic size={15} />}{muted ? "Unmute" : "Mute"}</Button>
                <Button variant="secondary" onClick={toggleCamera}>{cameraOff ? <VideoOff size={15} /> : <Video size={15} />}{cameraOff ? "Camera on" : "Camera off"}</Button>
                <Button variant="ghost" onClick={leaveRoom}><PhoneOff size={15} />{isInterviewer ? "End call & score" : "Leave"}</Button>
              </div>
            ) : (
              <Button loading={joining} onClick={() => void joinRoom()}>Join call</Button>
            )}
          </aside>
        </div>
        {callEnded && isInterviewer && (
          <GlassCard elevation="high" padding="lg" className="mt-6">
            <p className="eyebrow">INDEPENDENT INTERVIEW SCORECARD</p>
            <h2 className="mt-2 text-[17px] font-semibold text-ink-heading">Rate the evidence from this round</h2>
            <p className="mt-1 text-[11px] text-ink-subtle">Other interviewers' ratings stay hidden until every assigned scorecard is submitted. A recruiter makes the next-stage decision.</p>
            {scorecardResult ? (
              <output className="mt-4 block text-[12px] text-[var(--color-success)]">Scorecard saved ({scorecardResult.submitted}/{scorecardResult.expected}). {scorecardResult.complete ? "All panel scorecards are in; recruiter review is required." : "Waiting for the other interviewer(s)."}</output>
            ) : (
              <form className="mt-5 flex flex-col gap-4" onSubmit={(event) => void submitScorecard(event)}>
                {SCORECARD_ITEMS.map((item) => <div key={item.key} className="flex flex-col gap-2">
                  <Select label={`${item.label} · 1 NEEDS DEVELOPMENT — 5 STRONG`} value={scorecardRatings[item.key] ?? ""} onChange={(event) => setScorecardRatings((current) => ({ ...current, [item.key]: event.target.value ? Number(event.target.value) : "" }))}>
                    <option value="">Choose a rating</option><option value="1">1 · Needs significant development</option><option value="2">2 · Below expectations</option><option value="3">3 · Meets expectations</option><option value="4">4 · Strong evidence</option><option value="5">5 · Exceptional evidence</option>
                  </Select>
                  <Textarea label={`${item.label} · EVIDENCE`} rows={2} maxLength={1000} value={scorecardEvidence[item.key] || ""} onChange={(event) => setScorecardEvidence((current) => ({ ...current, [item.key]: event.target.value }))} placeholder="Specific job-related example or observation…" hint="Required: add at least 10 characters of job-related evidence." />
                </div>)}
                <Select label="YOUR RECOMMENDATION" value={scorecardRecommendation} onChange={(event) => setScorecardRecommendation(event.target.value as "ADVANCE" | "HOLD")}><option value="ADVANCE">Advance to the next round</option><option value="HOLD">Hold for further review</option></Select>
                <Textarea label="EVIDENCE-BASED NOTES" rows={4} maxLength={4000} value={scorecardNotes} onChange={(event) => setScorecardNotes(event.target.value)} placeholder="Job-related evidence, strengths, and areas to probe…" />
                <Button type="submit" loading={scorecardSubmitting} disabled={SCORECARD_ITEMS.some((item) => !scorecardRatings[item.key] || (scorecardEvidence[item.key] || "").trim().length < 10)}>Submit scorecard</Button>
              </form>
            )}
          </GlassCard>
        )}
      </PageShell>
    </div>
  );
}

function RemoteParticipantTile({ peer }: Readonly<{ peer: PeerState }>) {
  const ref = useCallback((element: HTMLVideoElement | null) => {
    if (element && peer.stream) element.srcObject = peer.stream;
  }, [peer.stream]);
  return (
    <GlassCard padding="sm" className="relative min-h-[220px] overflow-hidden bg-black/30">
      {peer.stream ? <video ref={ref} autoPlay playsInline className="h-full min-h-[200px] w-full rounded-lg object-cover"><track kind="captions" srcLang="en" label="Captions unavailable for this human call" src="/empty.vtt" /></video> : <div className="flex h-full min-h-[200px] items-center justify-center text-3xl font-bold text-brand">{peer.participant.name.slice(0, 1).toUpperCase()}</div>}
      <span className="absolute bottom-4 left-4 rounded-md bg-black/60 px-2 py-1 text-[10px] text-white">{peer.participant.name}</span>
    </GlassCard>
  );
}
