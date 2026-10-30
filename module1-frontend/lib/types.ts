export type WorkflowStep =
  | "IDLE"
  | "CONSENT"
  | "LIVENESS_CHALLENGE"
  | "GEOLOCATION"
  | "SUBMITTING"
  | "SUCCESS"
  | "ERROR";

export type ConsentState = {
  camera: boolean;
  geolocation: boolean;
};

export type GeoCoordinates = {
  latitude: number;
  longitude: number;
  accuracy: number;
};

export type CheckInPayload = {
  /** In-memory Base64 frame only — never persisted to disk or shown as a static image. */
  frameBase64: string;
  coordinates: GeoCoordinates | null;
  consentedAt: string;
  classCode: string;
};

export type CheckInResult = {
  ok: boolean;
  status?: string;
  verificationId?: string;
  message: string;
  classCode?: string;
  classTitle?: string;
};

export type LessonHistoryItem = {
  status?: string;
  id: string;
  classCode: string;
  classTitle: string;
  verifiedAt: string;
};

export type WorkflowState = {
  step: WorkflowStep;
  classCode: string | null;
  classTitle: string | null;
  consent: ConsentState;
  consentedAt: string | null;
  /** Ephemeral Base64 frame held only until submission completes. */
  frameBase64: string | null;
  coordinates: GeoCoordinates | null;
  result: CheckInResult | null;
  errorMessage: string | null;
};

export type WorkflowAction =
  | { type: "START"; payload: { classCode: string; classTitle: string } }
  | { type: "SET_CONSENT"; payload: Partial<ConsentState> }
  | { type: "CONFIRM_CONSENT" }
  | { type: "LIVENESS_COMPLETE"; payload: { frameBase64: string } }
  | { type: "GEOLOCATION_COMPLETE"; payload: GeoCoordinates }
  | { type: "GEOLOCATION_FAILED"; payload: string }
  | { type: "SUBMIT_START" }
  | { type: "SUBMIT_SUCCESS"; payload: CheckInResult }
  | { type: "SUBMIT_ERROR"; payload: string }
  | { type: "RESET" };
