# Migration on hongyu

The implementation is being migrated in independently verified stages. Passing
HTTP contract tests alone does not establish end-to-end attendance or spoof resistance.

## 1. Database-backed reporting and route ownership

Implemented:
- Remove legacy routers that shadow statistics and attendance exports.
- Aggregate audit summaries from persisted events.
- Remove the mock instructor dashboard endpoint and sample-data dependency.
- Remove duplicate device-list registration while retaining the active handler.
- Cover empty reports, unknown sessions, course authorization, and audit counts.

Validation: reporting regressions, API functional tests, observability tests,
frontend/dashboard HTTP contracts, and frontend TypeScript checking.
Production builds currently require Google Fonts network access that the cloud
runtime denies. Browser interaction testing remains outstanding.

## 2. Authentication and deployment

Implemented:
- Login, refresh, and logout now use the backend authority; remove frontend signing.
- Restore sessions from the backend and renew access tokens before expiry.
- Separate internal Docker addresses, browser API addresses, and browser origins.
- Restore specified rate limits with atomic Redis counters and explicit isolated
  test overrides. Redis failure returns 503 unless memory fallback is opted into.
- Build development frontend and backend images with optional proxy CA trust.

Validation: 49 API/security/dashboard/reporting tests, 8 auth/limiter regressions,
TypeScript checks, Compose validation, and frontend/backend authentication over
Docker networking (including different backend signing key, refresh, disabled
accounts, logout audit, cookie clearing, and browser Origin checks).
Production frontend builds remain blocked by Google Fonts network access; full
face-service container deployment and browser UI validation remain outstanding.
See [authentication/deployment notes](AUTH-DEPLOYMENT.md) for commands and limits.

## 3. Real student attendance workflow

- Replace local mock success and seeded history with backend records.
- Persist profile/password changes instead of local-only placeholder behavior.
- Integrate registration, consent persistence, face enrollment, camera capture,
  geolocation, session selection, and device registration.
- Submit fresh server-issued liveness/device challenges and display actual
  approved, flagged, or rejected outcomes.
- Verify the complete workflow in a browser, including permission denial.

## 4. Security and privacy

- Enforce challenge freshness and service-failure behavior consistently.
- Add server-side session revocation for copied tokens after logout.
- Implement impossible-travel checks and test network lookup failures.
- Add account deletion scheduling and personal-data cleanup.
- Limit stored location precision and remove precise coordinates from logs.
- Enforce audit immutability with appropriate database permissions; review
  instructor access to audit records.

## 5. Dashboard completeness and release validation

- Verify pagination, report completeness, scope, and audited exports.
- Add offline app-shell caching without caching authentication or submissions.
- Verify mobile behavior, monitoring, Docker deployment, and the full public suite.
- Evaluate real face/attack samples and concurrent workloads separately from
  endpoint contract tests; record any remaining limitations.
