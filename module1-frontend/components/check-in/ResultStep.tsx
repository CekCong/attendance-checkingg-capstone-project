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
    "Your attendance has not been approved. Review the reason below before trying again.",
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
  onRetry,
}: {
  variant: "SUCCESS" | "ERROR";
  result: CheckInResult | null;
  errorMessage: string | null;
  onReset: () => void;
  onRetry?: () => void;
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
      {result?.biometric_demo_mode && <p className="mt-3 text-sm">Demo record: face and liveness checks were bypassed.</p>}
      {variant === "SUCCESS" && result?.status === "rejected" && (
        <div className="mt-4 text-left">
          <h3 className="font-semibold">Why it was rejected</h3>
          <ul className="mt-2 list-disc space-y-2 pl-5 text-sm">
            {(result.rejection_reasons?.length ? result.rejection_reasons : ["A detailed reason is unavailable. Contact your instructor for help."])
              .map((reason) => <li key={reason}>{reason}</li>)}
          </ul>
          {onRetry && <>
            <p className="mt-3 text-sm">You can retry while attendance is open. We will request a fresh location and a new verification challenge.</p>
            <button type="button" onClick={onRetry} className="mt-4 w-full rounded-xl bg-white p-3 font-semibold text-sky-950">
              Retry attendance
            </button>
          </>}
        </div>
      )}
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
