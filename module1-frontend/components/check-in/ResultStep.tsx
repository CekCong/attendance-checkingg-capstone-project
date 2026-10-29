"use client";
import type { CheckInResult } from "@/lib/types";
import { GlassCard } from "./GlassCard";
export function SubmittingStep() {
  return (
    <GlassCard className="w-full p-8 text-center">
      <h2 className="text-2xl font-semibold">Verifying attendance</h2>
      <p className="mt-4">
        Checking your face, liveness, location, and device. Please keep this
        page open.
      </p>
    </GlassCard>
  );
}
const MESSAGES = {
  approved: ["Attendance approved", "Your attendance has been recorded."],
  flagged: [
    "Check-in needs review",
    "Your check-in was recorded and flagged for instructor review. It is not approved yet.",
  ],
  rejected: [
    "Check-in rejected",
    "Your check-in did not pass verification. Contact your instructor to review the record.",
  ],
  pending: [
    "Check-in pending",
    "Your check-in was recorded and is awaiting a decision.",
  ],
  appealed: ["Appeal pending", "Your instructor is reviewing your appeal."],
};
export function ResultStep({
  variant,
  result,
  errorMessage,
  onReset,
}: {
  variant: "SUCCESS" | "ERROR";
  result: CheckInResult | null;
  errorMessage: string | null;
  onReset: () => void;
}) {
  const message =
    variant === "SUCCESS" && result
      ? MESSAGES[result.status]
      : [
          "Check-in could not be completed",
          errorMessage ?? "Please try again.",
        ];
  return (
    <GlassCard className="w-full p-8 text-center">
      <h2 className="text-2xl font-semibold">{message[0]}</h2>
      <p role="status" className="mt-4">
        {message[1]}
      </p>
      {result && <p className="mt-4 text-xs">Record: {result.id}</p>}
      <button
        onClick={onReset}
        className="mt-6 w-full rounded-xl bg-white p-3 text-sky-950"
      >
        Back to dashboard
      </button>
    </GlassCard>
  );
}
