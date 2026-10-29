export type WorkflowStep =
  | "IDLE"
  | "CONSENT"
  | "PREPARING"
  | "ENROLLMENT"
  | "GEOLOCATION"
  | "LIVENESS_CHALLENGE"
  | "SUBMITTING"
  | "SUCCESS"
  | "ERROR";
export type ConsentState = { camera: boolean; geolocation: boolean };
export type GeoCoordinates = {
  latitude: number;
  longitude: number;
  accuracy: number;
};
export type CheckInResult = {
  id: string;
  status: "approved" | "flagged" | "rejected" | "pending" | "appealed";
};
