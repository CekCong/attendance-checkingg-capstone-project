"use client";
import { useEffect, useRef, useState } from "react";
import { captureFrameAsBase64 } from "@/lib/captureFrame";
import { studentRequest, type LivenessTicket } from "@/lib/studentApi";
import { GlassCard } from "./GlassCard";

type Props = {
  token: string;
  sessionId: string;
  enrollment?: boolean;
  onEnroll: (frame: string) => Promise<void>;
  onComplete: (frames: string[], ticket: LivenessTicket) => Promise<void>;
  onError: (message: string) => void;
};
const ACTION = {
  blink: "Close your eyes, then open them",
  head_turn: "Turn your head slowly to one side",
  smile: "Smile naturally",
};

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
  const [ready, setReady] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [instruction, setInstruction] = useState(
    "Look straight at the camera in good lighting.",
  );
  useEffect(() => {
    const current = generation.current;
    if (!navigator.mediaDevices?.getUserMedia) {
      onError(
        "Camera access requires HTTPS or localhost and a supported browser.",
      );
      return;
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
      generation.current += 1;
      stream.current?.getTracks().forEach((track) => track.stop());
      stream.current = null;
    };
  }, [onError]);

  async function capture() {
    if (!ready || busy.current || !video.current) return;
    busy.current = true;
    setCapturing(true);
    const current = generation.current;
    const frames: string[] = [];
    const canvas = document.createElement("canvas");
    try {
      if (enrollment) {
        setInstruction("Enrolling your face…");
        await onEnroll(captureFrameAsBase64(video.current, canvas, 0.85));
        return;
      }
      const ticket = await studentRequest<LivenessTicket>(
        "/checkins/liveness-challenge",
        token,
        { method: "POST", body: JSON.stringify({ session_id: sessionId }) },
      );
      const expiresAt = Date.now() + ticket.expires_in * 1000;
      // Module 3 requires 15 frames: neutral, requested action, neutral.
      for (let index = 0; index < 15; index++) {
        if (generation.current !== current) return;
        setInstruction(
          index < 5
            ? "Look straight ahead with eyes open"
            : index < 10
              ? ACTION[ticket.challenge_type]
              : "Return to a neutral face with eyes open",
        );
        await new Promise((resolve) => window.setTimeout(resolve, 300));
        if (generation.current !== current || !video.current) return;
        frames.push(captureFrameAsBase64(video.current, canvas, 0.85));
      }
      if (Date.now() >= expiresAt)
        throw new Error("The challenge expired. Please start again.");
      stream.current?.getTracks().forEach((track) => track.stop());
      await onComplete(frames, ticket);
    } catch (error) {
      if (generation.current === current)
        onError(
          error instanceof Error
            ? error.message
            : "Unable to complete camera verification.",
        );
    } finally {
      frames.length = 0;
      canvas.width = 0;
      canvas.height = 0;
      busy.current = false;
      if (generation.current === current) setCapturing(false);
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
          : "Keep your face in view and follow the changing instructions."}
      </p>
      <video
        ref={video}
        muted
        playsInline
        autoPlay
        onLoadedData={() => setReady(true)}
        className="mt-4 aspect-[4/3] w-full -scale-x-100 rounded-xl bg-black"
      />
      <p aria-live="polite" className="my-4 text-lg font-semibold">
        {instruction}
      </p>
      <button
        disabled={!ready || capturing}
        onClick={() => void capture()}
        className="w-full rounded-xl bg-white p-3 font-semibold text-sky-950 disabled:opacity-40"
      >
        {capturing
          ? "Please wait…"
          : enrollment
            ? "Capture enrollment photo"
            : "Start liveness challenge"}
      </button>
    </GlassCard>
  );
}
