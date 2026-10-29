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
Google Fonts network access is now available and the production frontend build
has passed. Browser interaction coverage is recorded in Stage 3.

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
The Google Fonts blocker was resolved before Stage 3; full face-service container
deployment remains release-validation work.
See [authentication/deployment notes](AUTH-DEPLOYMENT.md) for commands and limits.

## 3. Real student attendance workflow

Implemented:
- Student registration, backend session selection, and server attendance history.
- Persisted consent and face enrollment, real camera frames and geolocation.
- Browser device key registration, signed server challenges, and active liveness.
- Backend submission with distinct approved, flagged, rejected and pending results.
- Persisted display-name/password changes and permission/network error handling.

Validation: production build, TypeScript, public/regression suite (112 passed;
one pre-existing concurrent performance test marked skipped), eight Chromium
workflow/account tests, mobile viewport, production account persistence, and real face-service
static replay rejection. See [student workflow notes](STUDENT-WORKFLOW.md).
Manual real-device positive liveness and camera QR decoding remain outstanding.

## 4. Security and privacy

Implemented:
- Require both consents, active liveness and signed fresh device challenges
  according to session/course policy; verification outages fail closed.
- Revoke copied access/refresh tokens on logout, password changes, deactivation
  and deletion. Password changes sign the browser out.
- Flag impossible travel, unknown devices and unavailable country lookups;
  distinguish unavailable IP data from a confirmed foreign country.
- Schedule password-confirmed account deletion and erase due personal data;
  retain disabled tombstones and immutable audit events.
- Coarsen persisted coordinates and remove coordinates from new audit events.
- Install database audit guards, provision a restricted runtime role, move schema
  changes into a separate migration job, and scope instructor audit reads.

Validation: 30 focused security/privacy tests (including real PostgreSQL
permissions and Redis one-use challenge races), eight Chromium browser tests,
TypeScript and production build. Combined public/regression run: **136 passed,
six failed, one pre-existing performance skip**. The six unchanged supplied tests
expect check-ins without mandatory consent/proofs; they are documented explicitly
in [security/privacy notes](SECURITY-PRIVACY.md), along with deployment commands,
audit-retention limits and the distinction between ML doubles and real samples.
The repeatable migration and owner-level audit trigger were also verified locally.

## 5. Dashboard completeness and release validation

- Migrate the six legacy check-in fixtures to the full consent/proof workflow
  without relaxing the enforced policy; rerun the complete suite.
- Verify pagination, report completeness, scope, and audited exports.
- Add offline app-shell caching without caching authentication or submissions.
- Verify mobile behavior, monitoring, Docker deployment, and the full public suite.
- Evaluate real face/attack samples and concurrent workloads separately from
  endpoint contract tests; record any remaining limitations.
