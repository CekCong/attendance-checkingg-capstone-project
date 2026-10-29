"use client";
import { useEffect, useRef, useState } from "react";
import { readSessionQr } from "@/lib/sessionQr";

type Props = { sessionId: string; onCode: (code: string) => void; onClose: () => void };

export function SessionQrScanner({ sessionId, onCode, onClose }: Props) {
  const video = useRef<HTMLVideoElement>(null);
  const callbacks = useRef({ onCode, onClose });
  callbacks.current = { onCode, onClose };
  const [message, setMessage] = useState("Starting camera…");
  useEffect(() => {
    let cancelled = false;
    let media: MediaStream | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const stop = () => {
      cancelled = true;
      clearTimeout(timer);
      media?.getTracks().forEach((track) => track.stop());
      if (video.current) video.current.srcObject = null;
    };
    const hidden = () => { if (document.hidden) { stop(); callbacks.current.onClose(); } };
    document.addEventListener("visibilitychange", hidden);
    async function start() {
      try {
        // Load decoder before asking permission; no images leave this component.
        const { default: jsQR } = await import("jsqr");
        if (cancelled) return;
        if (!navigator.mediaDevices?.getUserMedia) throw new Error("unsupported");
        media = await navigator.mediaDevices.getUserMedia({ audio: false,
          video: { facingMode: { ideal: "environment" }, width: { ideal: 640 }, height: { ideal: 480 } } });
        if (cancelled) { media.getTracks().forEach((track) => track.stop()); return; }
        const preview = video.current;
        if (!preview) { stop(); return; }
        preview.srcObject = media;
        await preview.play();
        if (cancelled) return;
        setMessage("Point the camera at your instructor’s session QR code.");
        const canvas = document.createElement("canvas");
        const context = canvas.getContext("2d", { willReadFrequently: true });
        if (!context) throw new Error("canvas unavailable");
        const scan = () => {
          if (cancelled) return;
          try {
            if (preview!.videoWidth && preview!.videoHeight) {
              const scale = Math.min(1, 640 / preview!.videoWidth);
              canvas.width = Math.round(preview!.videoWidth * scale);
              canvas.height = Math.round(preview!.videoHeight * scale);
              context!.drawImage(preview!, 0, 0, canvas.width, canvas.height);
              const frame = context!.getImageData(0, 0, canvas.width, canvas.height);
              const found = jsQR(frame.data, frame.width, frame.height, { inversionAttempts: "attemptBoth" });
              if (found) {
                try {
                  const code = readSessionQr(found.data, sessionId);
                  stop(); callbacks.current.onCode(code); return;
                } catch (error) { setMessage((error as Error).message); }
              }
            }
            timer = setTimeout(scan, 200);
          } catch { stop(); setMessage("Camera preview failed. Close the scanner and enter the code manually."); }
        };
        scan();
      } catch {
        if (!cancelled) {
          stop();
          setMessage("Camera unavailable or permission denied. Close the scanner and enter the code manually.");
        }
      }
    }
    void start();
    return () => { stop(); document.removeEventListener("visibilitychange", hidden); };
  }, [sessionId]);
  return <section aria-label="Session QR scanner" className="mt-4 rounded-xl border border-white/30 p-3">
    <video ref={video} muted playsInline aria-label="QR camera preview" className="w-full rounded-lg" />
    <p role="status" className="mt-2">{message}</p>
    <button type="button" onClick={onClose} className="mt-3 underline">Close scanner</button>
  </section>;
}
