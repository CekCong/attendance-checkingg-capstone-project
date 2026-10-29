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

Implemented:
- Load all report pages, retrieve historical sessions, and export complete scoped
  attendance from the backend with audit events and CSV formula protection.
- Apply Singapore calendar boundaries and preserve recorded attendance after
  enrollment changes; fix instructor analytics scope and session query counts.
- Add a public offline fallback without caching private data or queuing submissions.
- Add readiness checks and bounded metrics for both services, Compose health gates,
  trusted build-CA support, and internal face-service proxy bypass.
- Share database sessions and bound API concurrency to prevent pool exhaustion.
- Upgrade Next.js to 16.4.3 and ship a non-root standalone production image.
- Migrate legacy tests to full consent/device/liveness proofs; require persisted
  rejection of static replay. Replace the concurrency skip with 20 real HTTP clients.

Validation on 30 October 2026 (Singapore): **154 public/regression tests passed,
zero failed, zero skipped**, against Docker backend/face services and PostgreSQL.
The 20-client workload verifies the static-replay rejection path; it does not
establish live-inference latency or biometric accuracy. Student/instructor production
builds and TypeScript passed, along with 10 browser tests and seven mobile camera
workflow tests. Browser and monitoring evidence, dependency audit,
reproduction commands and remaining release gates are documented in
[release validation](RELEASE-VALIDATION.md).

## 6. Dependency modernization and session QR — completed

Implemented: audited Python dependency locks, PyJWT migration, test/runtime dependency
separation, lean backend Docker image, expiring instructor-issued QR codes and local
student camera decoding with manual fallback. Validation: 172 public/regression tests,
17 Docker API/student tests, seven QR browser tests and seven mobile workflow tests
passed. Student/instructor production builds, TypeScript and the new ArcFace stack
also passed compatibility checks. New application dependency audits report zero
known vulnerabilities.

The model-access blocker is resolved. Official MediaPipe assets now have pinned
SHA-256 checks at installation and startup, and the face image includes EGL/GLES
libraries. **Five real-model/integrity acceptance tests and 199 public/regression
tests passed**, with zero failures or skips, against the new face Docker runtime
and updated backend. The image passed dependency consistency and advisory checks,
and both model runtimes loaded with networking disabled. The normal face service
now uses the new image. See [Stage 6 evidence and commands](STAGE6-DEPENDENCIES-QR.md).

Real-device biometric acceptance and production deployment/provisioning are still
release gates. Completing this migration does not establish production release approval.

## 7. Production readiness — identity controls implemented

Public registration now creates students only by default. A trusted operator can
bootstrap the first administrator atomically, with protected password input and
an audit event; existing admins provision staff through the protected API.
Production startup validates the actual signing key, secure cookies and disabled
privileged registration. Teaching fixture compatibility requires an explicitly
isolated test mode.

Validation: 198 full-suite tests and 27 focused identity tests passed (overlapping
coverage), including concurrent PostgreSQL CLI bootstrap. Docker startup/configuration
and registration/cookie behavior passed. See [production identity controls](PRODUCTION-IDENTITY.md).

Stage 6's automated model/container acceptance is now complete.
Real-device biometric testing and production operations remain open; no production
release is claimed.
