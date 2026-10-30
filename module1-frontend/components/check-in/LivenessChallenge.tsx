"use client";

import { useEffect, useRef, useState } from "react";
import { GlassCard } from "./GlassCard";

type Props = { onComplete: (frameBase64: string) => void; onError: (message: string) => void };

export function LivenessChallenge({ onComplete, onError }: Props) {
  const video = useRef<HTMLVideoElement>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let active = true;
    let stream: MediaStream | null = null;
    if (!navigator.mediaDevices?.getUserMedia) {
      onError("Camera access requires HTTPS on phones (or localhost on this computer).");
      return;
    }
    void navigator.mediaDevices.getUserMedia({ video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } }, audio: false })
      .then((capture) => {
        if (!active) { capture.getTracks().forEach((track) => track.stop()); return; }
        stream = capture;
        if (video.current) video.current.srcObject = capture;
      }).catch(() => { if (active) onError("Unable to open your camera. Allow camera access and try again."); });
    return () => { active = false; stream?.getTracks().forEach((track) => track.stop()); };
  }, [onError]);

  function capture() {
    if (!video.current?.videoWidth) return;
    const canvas = document.createElement("canvas");
    canvas.width = Math.min(640, video.current.videoWidth);
    canvas.height = Math.round(canvas.width * video.current.videoHeight / video.current.videoWidth);
    const context = canvas.getContext("2d");
    if (!context) { onError("Unable to capture a frame. Please try again."); return; }
    context.drawImage(video.current, 0, 0, canvas.width, canvas.height);
    onComplete(canvas.toDataURL("image/jpeg", 0.85));
  }
  return <GlassCard className="w-full max-w-md p-5">
    <h2 className="font-display text-xl font-semibold text-white">Camera verification</h2>
    <p className="mt-2 text-sm text-white/75">Face the camera in good light. Your live capture will be checked by the verification service.</p>
    <video ref={video} autoPlay muted playsInline onCanPlay={() => setReady(true)} className="mt-4 aspect-[4/3] w-full rounded-2xl bg-slate-950 object-cover" />
    <button type="button" disabled={!ready} onClick={capture} className="mt-4 w-full rounded-xl bg-white/90 px-5 py-3 font-semibold text-sky-950 disabled:opacity-50">{ready ? "Capture and continue" : "Opening camera…"}</button>
  </GlassCard>;
}
