"use client";

import type { ConsentState } from "@/lib/types";
import { GlassCard } from "./GlassCard";

type ConsentStepProps = {
  consent: ConsentState;
  onChange: (partial: Partial<ConsentState>) => void;
  onConfirm: () => void;
  onCancel: () => void;
};

export function ConsentStep({
  consent,
  onChange,
  onConfirm,
  onCancel,
}: ConsentStepProps) {
  const canContinue = consent.camera;

  return (
    <GlassCard className="w-full max-w-md p-7 animate-fade-up">
      <h2 className="font-display text-2xl font-semibold text-white">
        Privacy consent
      </h2>
      <p className="mt-2 text-sm leading-relaxed text-white/80">
        Explicit consent is required before we access device sensors. Frames are
        transmitted to the verification service in-memory only and are not saved
        locally.
      </p>

      <div className="mt-6 space-y-3">
        <label className="flex cursor-pointer items-start gap-3 rounded-2xl border border-white/20 bg-white/10 p-4 transition hover:bg-white/15">
          <input
            type="checkbox"
            checked={consent.camera}
            onChange={(e) => onChange({ camera: e.target.checked })}
            className="mt-1 h-4 w-4 accent-emerald-400"
          />
          <span>
            <span className="block font-semibold text-white">Camera access</span>
            <span className="mt-1 block text-sm text-white/70">
              Capture a live selfie stream for a short liveness challenge. No
              photos are kept on this device.
            </span>
          </span>
        </label>

        <label className="flex cursor-pointer items-start gap-3 rounded-2xl border border-white/20 bg-white/10 p-4 transition hover:bg-white/15">
          <input
            type="checkbox"
            checked={consent.geolocation}
            onChange={(e) => onChange({ geolocation: e.target.checked })}
            className="mt-1 h-4 w-4 accent-emerald-400"
          />
          <span>
            <span className="block font-semibold text-white">
              Geolocation access
            </span>
            <span className="mt-1 block text-sm text-white/70">
              Location is skipped in this preview. You can leave this unchecked.
            </span>
          </span>
        </label>
      </div>

      <div className="mt-7 flex gap-3">
        <button
          type="button"
          onClick={onCancel}
          className="flex-1 rounded-2xl border border-white/30 bg-white/10 px-4 py-3 text-sm font-semibold text-white transition hover:bg-white/20"
        >
          Cancel
        </button>
        <button
          type="button"
          disabled={!canContinue}
          onClick={onConfirm}
          className="flex-[1.4] rounded-2xl bg-white/90 px-4 py-3 text-sm font-semibold text-sky-950 transition enabled:hover:bg-white disabled:cursor-not-allowed disabled:opacity-40"
        >
          I agree — continue
        </button>
      </div>
    </GlassCard>
  );
}
