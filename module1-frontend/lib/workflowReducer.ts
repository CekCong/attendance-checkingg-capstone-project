import type { WorkflowAction, WorkflowState } from "@/lib/types";

export const initialWorkflowState: WorkflowState = {
  step: "IDLE",
  classCode: null,
  classTitle: null,
  consent: { camera: false, geolocation: false },
  consentedAt: null,
  frameBase64: null,
  coordinates: null,
  result: null,
  errorMessage: null,
};

export function workflowReducer(
  state: WorkflowState,
  action: WorkflowAction,
): WorkflowState {
  switch (action.type) {
    case "START":
      return {
        ...initialWorkflowState,
        step: "CONSENT",
        classCode: action.payload.classCode,
        classTitle: action.payload.classTitle,
      };

    case "SET_CONSENT":
      return {
        ...state,
        consent: { ...state.consent, ...action.payload },
      };

    case "CONFIRM_CONSENT":
      if (!state.consent.camera || !state.consent.geolocation) {
        return state;
      }
      return {
        ...state,
        step: "LIVENESS_CHALLENGE",
        consentedAt: new Date().toISOString(),
      };

    case "LIVENESS_COMPLETE":
      // Read location only after camera capture and explicit consent.
      return {
        ...state,
        step: "GEOLOCATION",
        frameBase64: action.payload.frameBase64,
        coordinates: null,
        errorMessage: null,
      };

    case "GEOLOCATION_COMPLETE":
      return {
        ...state,
        step: "SUBMITTING",
        coordinates: action.payload,
        errorMessage: null,
      };

    case "GEOLOCATION_FAILED":
      return {
        ...state,
        step: "ERROR",
        errorMessage: action.payload,
        frameBase64: null,
      };

    case "SUBMIT_START":
      return {
        ...state,
        step: "SUBMITTING",
      };

    case "SUBMIT_SUCCESS":
      return {
        ...state,
        step: "SUCCESS",
        result: action.payload,
        frameBase64: null,
        errorMessage: null,
      };

    case "SUBMIT_ERROR":
      return {
        ...state,
        step: "ERROR",
        errorMessage: action.payload,
        result: null,
        frameBase64: null,
      };

    case "RESET":
      return initialWorkflowState;

    default:
      return state;
  }
}
