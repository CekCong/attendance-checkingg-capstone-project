"use client";

import { GlassCard } from "./GlassCard";

/** Minimal 1×1 PNG — placeholder only; no camera capture in this stub. */
const STUB_FRAME =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";

type LivenessChallengeProps = {
  onComplete: (frameBase64: string) => void;
  onError: (message: string) => void;
};

export function LivenessChallenge({ onComplete }: LivenessChallengeProps) {
  return (
    <GlassCard className="w-full max-w-md overflow-hidden p-4 animate-fade-up sm:p-5">
      <h2 className="px-1 font-display text-xl font-semibold text-white">
        Liveness challenge
      </h2>
      <p className="mt-1 px-1 text-sm text-white/75">
        Face capture is stubbed for now. Continue to skip the camera and move to
        location verification.
      </p>

      <div className="relative mt-4 flex aspect-[3/4] items-center justify-center overflow-hidden rounded-2xl bg-sky-950/40 ring-1 ring-white/25">
        <div className="h-[52%] w-[62%] rounded-[50%] border-2 border-dashed border-white/40" />
        <div className="pointer-events-none absolute inset-x-0 bottom-4 mx-auto max-w-[90%] rounded-2xl border border-white/25 bg-white/20 px-4 py-3 text-center backdrop-blur-xl">
          <p className="text-base font-semibold text-white drop-shadow">
            Camera skipped
          </p>
        </div>
      </div>

      <button
        type="button"
        onClick={() => onComplete(STUB_FRAME)}
        className="mt-4 w-full rounded-2xl bg-white/90 px-6 py-3.5 text-base font-semibold text-sky-950 shadow-lg transition hover:bg-white active:scale-[0.98]"
      >
        Continue
      </button>
    </GlassCard>
  );
}
