import type { WorkflowStep } from "@/lib/types";

const STEPS: { id: WorkflowStep; label: string }[] = [
  { id: "CONSENT", label: "Consent" },
  { id: "ENROLLMENT", label: "Enrollment" },
  { id: "GEOLOCATION", label: "Location" },
  { id: "LIVENESS_CHALLENGE", label: "Liveness" },
  { id: "SUBMITTING", label: "Verify" },
];
function stepIndex(step: WorkflowStep) {
  if (step === "SUCCESS" || step === "ERROR") return STEPS.length;
  if (step === "PREPARING") return 0;
  return Math.max(
    0,
    STEPS.findIndex((s) => s.id === step),
  );
}

type StepIndicatorProps = {
  step: WorkflowStep;
};

export function StepIndicator({ step }: StepIndicatorProps) {
  if (step === "IDLE") return null;

  const current = stepIndex(step);

  return (
    <ol className="mb-6 flex w-full max-w-md items-center justify-between gap-1 px-1">
      {STEPS.map((s, i) => {
        const done = i < current || step === "SUCCESS";
        const active = i === current && step !== "SUCCESS" && step !== "ERROR";

        return (
          <li key={s.id} className="flex flex-1 flex-col items-center gap-2">
            <span
              className={[
                "flex h-8 w-8 items-center justify-center rounded-full text-xs font-semibold transition-all duration-500",
                done
                  ? "bg-emerald-300/90 text-emerald-950 shadow-[0_0_20px_rgba(110,231,183,0.45)]"
                  : active
                    ? "bg-white/90 text-sky-950 ring-2 ring-white/70"
                    : "bg-white/20 text-white/70",
              ].join(" ")}
              aria-current={active ? "step" : undefined}
            >
              {done ? "✓" : i + 1}
            </span>
            <span
              className={[
                "text-[11px] font-medium tracking-wide",
                active || done ? "text-white" : "text-white/55",
              ].join(" ")}
            >
              {s.label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
