"use client";

import type { CheckInResult, GeoCoordinates } from "@/lib/types";
import { GlassCard } from "./GlassCard";

type SubmittingStepProps = {
  hasFrame: boolean;
  coordinates: GeoCoordinates | null;
};

export function SubmittingStep({ hasFrame, coordinates }: SubmittingStepProps) {
  return (
    <GlassCard className="w-full max-w-md p-8 text-center animate-fade-up">
      <div className="mx-auto mb-5 h-12 w-12 animate-spin rounded-full border-2 border-white/25 border-t-white" />
      <h2 className="font-display text-2xl font-semibold text-white">
        Verifying attendance
      </h2>
      <p className="mt-3 text-sm text-white/80">
        Submitting your check-in to the attendance service.
      </p>
      <ul className="mt-5 space-y-2 text-left text-sm text-white/75">
        <li className="rounded-xl border border-white/15 bg-white/10 px-3 py-2">
          Liveness: {hasFrame ? "live capture ready" : "missing"}
        </li>
        <li className="rounded-xl border border-white/15 bg-white/10 px-3 py-2">
          Location:
          {coordinates
            ? ` (${coordinates.latitude.toFixed(5)}, ${coordinates.longitude.toFixed(5)})`
            : ""}
        </li>
      </ul>
    </GlassCard>
  );
}

type ResultStepProps = {
  variant: "SUCCESS" | "ERROR";
  result: CheckInResult | null;
  errorMessage: string | null;
  onReset: () => void;
};

export function ResultStep({
  variant,
  result,
  errorMessage,
  onReset,
}: ResultStepProps) {
  const success = variant === "SUCCESS";

  return (
    <GlassCard className="w-full max-w-md p-8 text-center animate-fade-up">
      <div
        className={[
          "mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-full text-2xl",
          success
            ? "bg-emerald-300/90 text-emerald-950 shadow-[0_0_28px_rgba(110,231,183,0.5)]"
            : "bg-rose-300/90 text-rose-950 shadow-[0_0_28px_rgba(253,164,175,0.45)]",
        ].join(" ")}
      >
        {success ? "✓" : "!"}
      </div>
      <h2 className="font-display text-2xl font-semibold text-white">
        {success ? (result?.status === "flagged" ? "Awaiting tutor review" : "Check-in complete") : "Check-in failed"}
      </h2>
      <p className="mt-3 text-sm leading-relaxed text-white/85">
        {success
          ? (result?.message ?? "Attendance verified successfully.")
          : (errorMessage ?? "Something went wrong. Please try again.")}
      </p>
      {success && result?.verificationId ? (
        <p className="mt-4 rounded-xl border border-white/20 bg-white/10 px-3 py-2 font-mono text-xs tracking-wide text-white/90">
          ID: {result.verificationId}
        </p>
      ) : null}
      <button
        type="button"
        onClick={onReset}
        className="mt-7 w-full rounded-2xl bg-white/90 px-6 py-3.5 text-sm font-semibold text-sky-950 transition hover:bg-white"
      >
        {success ? "Back to dashboard" : "Try again"}
      </button>
    </GlassCard>
  );
}
