"use client";

import { GlassCard } from "./GlassCard";

type IdleStepProps = {
  onStart: () => void;
};

export function IdleStep({ onStart }: IdleStepProps) {
  return (
    <GlassCard className="w-full max-w-md p-8 text-center animate-fade-up">
      <p className="mb-2 text-sm font-medium uppercase tracking-[0.2em] text-white/70">
        Student check-in
      </p>
      <h1 className="font-display text-4xl font-semibold tracking-tight text-white drop-shadow-sm">
        SAIV
      </h1>
      <p className="mt-4 text-pretty text-base leading-relaxed text-white/85">
        Secure attendance with camera liveness and location verification. Your
        biometric frames are sent only for this session and never stored on
        this device.
      </p>
      <button
        type="button"
        onClick={onStart}
        className="mt-8 w-full rounded-2xl bg-white/90 px-6 py-3.5 text-base font-semibold text-sky-950 shadow-lg transition hover:bg-white active:scale-[0.98]"
      >
        Start check-in
      </button>
    </GlassCard>
  );
}
