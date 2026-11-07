"use client";
import { useEffect, useRef, useState } from "react";
import { captureFrameAsBase64 } from "@/lib/captureFrame";
import { studentRequest, type LivenessTicket } from "@/lib/studentApi";
import { captureLivenessSequence } from "@/lib/livenessCapture";
import { GlassCard } from "./GlassCard";

type Props = {
  token: string;
  sessionId: string;
  enrollment?: boolean;
  onEnroll: (frame: string) => Promise<void>;
  onComplete: (frames: string[], ticket: LivenessTicket) => Promise<void>;
  onError: (message: string) => void;
};
type CameraReadiness = { ready: boolean; message: string; warnings: string[] };

export function LivenessChallenge({
  token,
  sessionId,
  enrollment = false,
  onEnroll,
  onComplete,
  onError,
}: Props) {
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const generation = useRef(0);
  const busy = useRef(false);
  const interrupted = useRef(false);
  const [ready, setReady] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [captureError, setCaptureError] = useState<string | null>(null);
  const [detail, setDetail] = useState("Keep your whole face in view, with a light in front of you.");
  const [warnings, setWarnings] = useState<string[]>([]);
  const [countdown, setCountdown] = useState<number | null>(null);
  const [stage, setStage] = useState(0);
  const [instruction, setInstruction] = useState(
    "Look straight at the camera in good lighting.",
  );
  useEffect(() => {
    const current = generation.current;
    const interrupt = () => { if (document.hidden && busy.current) interrupted.current = true; };
    document.addEventListener("visibilitychange", interrupt);
    if (!navigator.mediaDevices?.getUserMedia) {
      onError(
        "Camera access requires HTTPS or localhost and a supported browser.",
      );
      return () => document.removeEventListener("visibilitychange", interrupt);
    }
    void navigator.mediaDevices
      .getUserMedia({
        audio: false,
        video: {
          facingMode: "user",
          width: { ideal: 640, max: 640 },
          height: { ideal: 480, max: 480 },
        },
      })
      .then(async (media) => {
        if (generation.current !== current) {
          media.getTracks().forEach((track) => track.stop());
          return;
        }
        stream.current = media;
        if (video.current) {
          video.current.srcObject = media;
          await video.current.play();
        }
      })
      .catch(() => {
        if (generation.current === current)
          onError(
            "Camera unavailable or permission denied. Enable camera access and try again.",
          );
      });
    return () => {
      document.removeEventListener("visibilitychange", interrupt);
      generation.current += 1;
      stream.current?.getTracks().forEach((track) => track.stop());
      stream.current = null;
    };
  }, [onError]);

  async function capture() {
    if (!ready || busy.current || !video.current) return;
    busy.current = true;
    interrupted.current = false;
    setCapturing(true);
    setCaptureError(null);
    setWarnings([]);
    setStage(0);
    const current = generation.current;
    let frames: string[] = [];
    const canvas = document.createElement("canvas");
    const assertActive = () => {
      if (generation.current !== current) throw new Error("Capture cancelled.");
      if (interrupted.current || document.hidden)
        throw new Error("Recording was interrupted. Keep this page open and try again.");
      const track = stream.current?.getVideoTracks()[0];
      if (!video.current || video.current.readyState < 2 || video.current.paused || !track || track.readyState !== "live" || track.muted)
        throw new Error("The camera stopped sending pictures. Check the camera connection and try again.");
    };
    const wait = (milliseconds: number) => new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds));
    try {
      assertActive();
      setInstruction("Checking your camera picture…");
      setDetail("Checking face visibility and lighting before recording.");
      const readiness = await studentRequest<CameraReadiness>("/users/me/face/readiness", token, {
        method: "POST",
        body: JSON.stringify({ image: captureFrameAsBase64(video.current!, canvas, 0.85) }),
      });
      assertActive();
      if (!readiness.ready) throw new Error(readiness.message);
      setWarnings(readiness.warnings);
      if (enrollment) {
        for (let seconds = 3; seconds > 0; seconds--) {
          setInstruction("Camera ready · Look straight ahead");
          setDetail("Keep your eyes open and your mouth relaxed for your enrollment photo.");
          setCountdown(seconds);
          await wait(1000);
          assertActive();
        }
        setCountdown(null);
        setInstruction("Enrolling your face…");
        await onEnroll(captureFrameAsBase64(video.current!, canvas, 0.85));
        return;
      }
      setInstruction("Camera ready · Preparing your challenge…");
      // Count network time against the ticket lifetime conservatively.
      const requestedAt = Date.now();
      const ticket = await studentRequest<LivenessTicket>(
        "/checkins/liveness-challenge",
        token,
        { method: "POST", body: JSON.stringify({ session_id: sessionId }) },
      );
      const expiresAt = requestedAt + ticket.expires_in * 1000;
      const assertChallenge = () => {
        assertActive();
        if (Date.now() >= expiresAt) throw new Error("The challenge expired. Please start again.");
      };
      assertChallenge();
      frames = await captureLivenessSequence(ticket.challenge_type, {
        assertActive: assertChallenge,
        wait,
        capture: () => captureFrameAsBase64(video.current!, canvas, 0.85),
        prompt: (title, help, seconds, nextStage) => {
          setInstruction(title); setDetail(help); setCountdown(seconds); setStage(nextStage);
        },
      });
      assertChallenge();
      setCountdown(null);
      setInstruction("Recording complete · Verifying…");
      await onComplete(frames, ticket);
    } catch (error) {
      if (generation.current === current) {
        setInstruction("Verification paused");
        setDetail("Follow the guidance below, then try again when you are ready.");
        setCaptureError(
          error instanceof Error
            ? error.message
            : "Unable to complete camera verification.",
        );
      }
    } finally {
      frames.length = 0;
      canvas.width = 0;
      canvas.height = 0;
      busy.current = false;
      if (generation.current === current) { setCapturing(false); setCountdown(null); }
    }
  }
  return (
    <GlassCard className="w-full p-5">
      <h2 className="text-2xl font-semibold">
        {enrollment ? "Enroll your face" : "Liveness challenge"}
      </h2>
      <p className="mt-2">
        {enrollment
          ? "Take a clear, front-facing image to create your face template. Raw images are not retained."
          : "We will check your camera, then guide you through a short gesture. Wait for each instruction before moving."}
      </p>
      <p className="mt-2 text-sm text-slate-300">The camera check sends one image for processing without saving it. It does not mark attendance or change your face template.</p>
      <div className="relative mt-4">
      <video
        ref={video}
        muted
        playsInline
        autoPlay
        onLoadedData={() => setReady(true)}
        className="aspect-[4/3] w-full -scale-x-100 rounded-xl bg-black"
      />
      <div aria-hidden="true" className="pointer-events-none absolute inset-x-[22%] inset-y-[10%] rounded-[50%] border-2 border-white/50" />
      {countdown !== null && <span aria-hidden="true" className="absolute bottom-3 right-3 rounded-full bg-slate-950/80 px-4 py-2 text-2xl font-bold tabular-nums">{countdown}</span>}
      </div>
      <div role="status" aria-live="polite" aria-atomic="true" className="my-4">
        <p className="text-lg font-semibold">{instruction}</p>
        <p className="mt-1 text-sm">{detail}</p>
      </div>
      {capturing && !enrollment && <progress aria-label="Challenge progress" className="mb-3 w-full" max={3} value={stage} />}
      {warnings.map((warning) => <p key={warning} className="mb-3 text-sm text-amber-200">{warning}</p>)}
      {captureError && <p role="alert" className="mb-4 rounded-lg border border-amber-300/50 bg-amber-300/10 p-3">{captureError}</p>}
      <button
        disabled={!ready || capturing}
        onClick={() => void capture()}
        className="w-full rounded-xl bg-white p-3 font-semibold text-sky-950 disabled:opacity-40"
      >
        {capturing
          ? "Please wait…"
          : enrollment
            ? "Check camera & capture photo"
            : "Check camera & start challenge"}
      </button>
    </GlassCard>
  );
}
