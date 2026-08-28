"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { useAuth } from "@/components/auth/AuthProvider";
import { StudentDashboard } from "@/components/dashboards/StudentDashboard";
import { submitCheckIn } from "@/lib/mockApi";
import { appendLessonHistory } from "@/lib/attendanceHistory";
import type { ConsentState } from "@/lib/types";
import {
  initialWorkflowState,
  workflowReducer,
} from "@/lib/workflowReducer";
import { ConsentStep } from "./ConsentStep";
import { IdleStep } from "./IdleStep";
import { LivenessChallenge } from "./LivenessChallenge";
import { ResultStep, SubmittingStep } from "./ResultStep";
import { StepIndicator } from "./StepIndicator";

export function CheckInWorkflow() {
  const { user } = useAuth();
  const [state, dispatch] = useReducer(workflowReducer, initialWorkflowState);
  const submittingRef = useRef(false);
  const [historyVersion, setHistoryVersion] = useState(0);

  const handleConsentChange = useCallback((partial: Partial<ConsentState>) => {
    dispatch({ type: "SET_CONSENT", payload: partial });
  }, []);

  const handleLivenessComplete = useCallback((frameBase64: string) => {
    dispatch({ type: "LIVENESS_COMPLETE", payload: { frameBase64 } });
  }, []);

  const handleLivenessError = useCallback((message: string) => {
    dispatch({ type: "SUBMIT_ERROR", payload: message });
  }, []);

  useEffect(() => {
    if (state.step !== "SUBMITTING") {
      submittingRef.current = false;
      return;
    }

    if (submittingRef.current) return;
    submittingRef.current = true;

    const { frameBase64, coordinates, consentedAt, classCode, classTitle } = state;

    if (!frameBase64 || !consentedAt || !classCode) {
      dispatch({
        type: "SUBMIT_ERROR",
        payload: "Missing check-in data. Please restart from the dashboard.",
      });
      return;
    }

    let cancelled = false;

    void (async () => {
      try {
        const result = await submitCheckIn({
          frameBase64,
          coordinates,
          consentedAt,
          classCode,
        });

        if (cancelled) return;

        if (result.ok) {
          if (user) {
            appendLessonHistory(user.email, {
              id: result.verificationId ?? `CHK-${Date.now()}`,
              classCode: result.classCode ?? classCode,
              classTitle: result.classTitle ?? classTitle ?? classCode,
              verifiedAt: new Date().toISOString(),
            });
            setHistoryVersion((n) => n + 1);
          }
          dispatch({ type: "SUBMIT_SUCCESS", payload: result });
        } else {
          dispatch({ type: "SUBMIT_ERROR", payload: result.message });
        }
      } catch {
        if (!cancelled) {
          dispatch({
            type: "SUBMIT_ERROR",
            payload: "Network error while submitting check-in. Please retry.",
          });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.step]);

  return (
    <div className="flex w-full max-w-lg flex-col items-center px-4 py-4 sm:py-8">
      <StepIndicator step={state.step} />

      {state.step === "IDLE" && user && (
        <StudentDashboard
          email={user.email}
          historyVersion={historyVersion}
          onStartCheckIn={(classCode, classTitle) =>
            dispatch({ type: "START", payload: { classCode, classTitle } })
          }
        />
      )}

      {state.step === "IDLE" && !user && (
        <IdleStep onStart={() => dispatch({ type: "START", payload: { classCode: "DEMO", classTitle: "Demo" } })} />
      )}

      {state.step === "CONSENT" && (
        <ConsentStep
          consent={state.consent}
          onChange={handleConsentChange}
          onConfirm={() => dispatch({ type: "CONFIRM_CONSENT" })}
          onCancel={() => dispatch({ type: "RESET" })}
        />
      )}

      {state.step === "LIVENESS_CHALLENGE" && (
        <LivenessChallenge
          onComplete={handleLivenessComplete}
          onError={handleLivenessError}
        />
      )}

      {state.step === "SUBMITTING" && (
        <SubmittingStep
          hasFrame={Boolean(state.frameBase64)}
          coordinates={state.coordinates}
        />
      )}

      {(state.step === "SUCCESS" || state.step === "ERROR") && (
        <ResultStep
          variant={state.step}
          result={state.result}
          errorMessage={state.errorMessage}
          onReset={() => dispatch({ type: "RESET" })}
        />
      )}
    </div>
  );
}
