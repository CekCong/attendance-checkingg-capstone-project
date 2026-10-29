"use client";
import { useCallback, useRef, useState } from "react";
import { useAuth } from "@/components/auth/AuthProvider";
import { StudentDashboard } from "@/components/dashboards/StudentDashboard";
import {
  studentRequest,
  type StudentSession,
  type StudentProfile,
  type LivenessTicket,
} from "@/lib/studentApi";
import { prepareDevice, signDevice } from "@/lib/deviceIdentity";
import type {
  CheckInResult,
  ConsentState,
  GeoCoordinates,
  WorkflowStep,
} from "@/lib/types";
import { ConsentStep } from "./ConsentStep";
import { GeolocationStep } from "./GeolocationStep";
import { LivenessChallenge } from "./LivenessChallenge";
import { ResultStep, SubmittingStep } from "./ResultStep";
import { StepIndicator } from "./StepIndicator";

export function CheckInWorkflow() {
  const { user, accessToken } = useAuth();
  const [step, setStep] = useState<WorkflowStep>("IDLE");
  const [session, setSession] = useState<StudentSession | null>(null);
  const [qrCode, setQrCode] = useState("");
  const [consent, setConsent] = useState<ConsentState>({
    camera: false,
    geolocation: false,
  });
  const [coordinates, setCoordinates] = useState<GeoCoordinates | null>(null);
  const [result, setResult] = useState<CheckInResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const device = useRef<Awaited<ReturnType<typeof prepareDevice>> | null>(null);
  const busy = useRef(false);
  const operation = useRef(0);
  const fail = useCallback((message: string) => {
    setCoordinates(null);
    setError(message);
    setStep("ERROR");
  }, []);
  const located = useCallback((value: GeoCoordinates) => {
    setCoordinates(value);
    setStep("LIVENESS_CHALLENGE");
  }, []);

  function reset() {
    operation.current += 1;
    setStep("IDLE");
    setSession(null);
    setCoordinates(null);
    setResult(null);
    setError(null);
    setConsent({ camera: false, geolocation: false });
    device.current = null;
  }
  async function begin() {
    if (
      !accessToken ||
      !user ||
      !consent.camera ||
      !consent.geolocation ||
      busy.current
    )
      return;
    busy.current = true;
    const current = operation.current;
    setStep("PREPARING");
    try {
      const profile = await studentRequest<StudentProfile>(
        "/users/me",
        accessToken,
        {
          method: "PUT",
          body: JSON.stringify({
            camera_consent: true,
            geolocation_consent: true,
          }),
        },
      );
      device.current = await prepareDevice(user.id, accessToken);
      if (current === operation.current)
        setStep(profile.face_enrolled ? "GEOLOCATION" : "ENROLLMENT");
    } catch (e) {
      if (current === operation.current)
        fail(
          e instanceof Error ? e.message : "Unable to prepare verification.",
        );
    } finally {
      busy.current = false;
    }
  }
  async function enroll(frame: string) {
    const current = operation.current;
    await studentRequest("/users/me/face/enroll", accessToken, {
      method: "POST",
      body: JSON.stringify({ image: frame.split(",")[1] }),
    });
    if (current === operation.current) setStep("GEOLOCATION");
  }
  async function submit(frames: string[], ticket: LivenessTicket) {
    if (
      !session ||
      !coordinates ||
      !device.current ||
      !accessToken ||
      busy.current
    )
      return;
    busy.current = true;
    setStep("SUBMITTING");
    try {
      const attestation = await signDevice(
        device.current,
        session.id,
        accessToken,
      );
      const saved = await studentRequest<CheckInResult>(
        "/checkins/",
        accessToken,
        {
          method: "POST",
          body: JSON.stringify({
            session_id: session.id,
            ...attestation,
            latitude: coordinates.latitude,
            longitude: coordinates.longitude,
            location_accuracy_meters: coordinates.accuracy,
            liveness_challenge_response: frames,
            liveness_challenge_id: ticket.challenge_id,
            liveness_challenge_type: ticket.challenge_type,
            ...(qrCode ? { qr_code: qrCode } : {}),
          }),
        },
      );
      setCoordinates(null);
      setResult(saved);
      setStep("SUCCESS");
    } catch (e) {
      fail(
        e instanceof Error
          ? e.message
          : "Submission failed. Refresh history before retrying if your connection was interrupted.",
      );
    } finally {
      busy.current = false;
    }
  }
  if (!user || !accessToken) return null;
  if (user.role !== "student")
    return (
      <p className="p-6">
        Sign in with a student account to submit attendance.
      </p>
    );
  return (
    <div className="flex w-full max-w-lg flex-col items-center gap-4 px-4 py-6">
      <StepIndicator step={step} />
      {step === "IDLE" && (
        <StudentDashboard
          token={accessToken}
          onStartCheckIn={(selected, code) => {
            setSession(selected);
            setQrCode(code);
            setStep("CONSENT");
          }}
        />
      )}
      {step === "CONSENT" && (
        <ConsentStep
          consent={consent}
          onChange={(partial) =>
            setConsent((previous) => ({ ...previous, ...partial }))
          }
          onConfirm={() => void begin()}
          onCancel={reset}
        />
      )}
      {step === "PREPARING" && (
        <p>Saving consent and registering this device…</p>
      )}
      {(step === "ENROLLMENT" || step === "LIVENESS_CHALLENGE") && session && (
        <LivenessChallenge
          key={step}
          token={accessToken}
          sessionId={session.id}
          enrollment={step === "ENROLLMENT"}
          onEnroll={enroll}
          onComplete={submit}
          onError={fail}
        />
      )}
      {step === "GEOLOCATION" && (
        <GeolocationStep onComplete={located} onError={fail} />
      )}
      {step === "SUBMITTING" && <SubmittingStep />}
      {(step === "SUCCESS" || step === "ERROR") && (
        <ResultStep
          variant={step}
          result={result}
          errorMessage={error}
          onReset={reset}
        />
      )}
      {["ENROLLMENT", "GEOLOCATION", "LIVENESS_CHALLENGE"].includes(step) && (
        <button onClick={reset} className="underline">
          Cancel verification
        </button>
      )}
    </div>
  );
}
