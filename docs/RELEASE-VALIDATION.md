# Stage 5 validation — 30 October 2026 (Singapore)

Stage 5 completes the dashboard/reporting and offline implementation and validates
the application stack locally. This is **not production release approval**: the
Python dependency audit, real-device biometric acceptance and infrastructure
checks below remain release gates.

## Delivered behavior

- Dashboard course/session/attendance/audit collections load successive pages,
  with deterministic server ordering and duplicate-page detection. Student session
  and history lists also support later pages. Counts no longer silently stop at 100.
  Selecting a historical session retrieves that session's records independently
  of today's data. Daily dashboard reports use Singapore calendar boundaries.
- Exports come from the backend, apply authorization and filters to the complete
  query, and create a `data_exported` event before returning. JSON preserves values;
  CSV neutralizes spreadsheet formulas. Previously recorded course attendance is
  retained in reports when enrollment becomes inactive. Reports contain data still
  retained under the 30-day policy; they cannot recover already erased records.
- Student analytics are restricted to the requesting instructor's assigned courses.
  Session counts use active enrollment; page queries aggregate enrollment/check-in
  counts instead of issuing one count query per session.
- The service worker caches only the public offline page, manifest, icons and
  hashed Next static assets. Navigations use the network and fall back to a generic
  offline page. API requests, authenticated data and submissions are never cached
  or queued. Offline access does not constitute an attendance submission.
- Both services expose bounded-label Prometheus metrics and `/ready`; backend
  readiness checks PostgreSQL/Redis, face readiness checks Redis after model startup.
  Compose gates startup on readiness. Internal backend-to-face HTTP bypasses host
  proxy environment variables while retaining normal TLS verification.
- Routes reuse one database dependency per request. An ASGI admission limit holds
  at most ten API requests through dependency cleanup, reserving the 15-connection
  pool for maintenance and preventing blocking checkout under concurrent load.
  Additional API requests wait asynchronously. This is per process; deployment
  worker counts must still fit PostgreSQL's connection budget.
- Next.js is upgraded to 16.4.3, PostCSS to 8.5.32, and unused Axios/JOSE/localforage
  dependencies are removed. Cookie access uses the asynchronous Next API. The old,
  unconfigured `next lint` command is replaced by an explicit `npm run typecheck`.
  Production Docker runs the standalone artifact as the non-root `node` user.

## Evidence and its limits

- Public/regression tests now create consent, real enrollment, RSA device proof
  and fresh active challenges. Static sample frames must produce **rejected**
  attendance. Duplicate/history assertions check the persisted result; the frontend
  response test can no longer pass by skipping assertions on an error response.
- The previously skipped SQLite-specific concurrency test now uses HTTP against
  PostgreSQL with 20 distinct students. Enrollment happens before nonce issuance;
  no challenge lifetime is spent preparing the other accounts. Every submission
  must be recorded as rejected. Timing covers a known static-replay rejection
  path, not live-person inference. Identical frames are rejected before expensive
  per-frame model analysis; malformed image encoding still returns a validation error.
- Browser checks cover the real account/password/deletion flow and public offline
  behavior on production builds, plus workflow and instructor API doubles. Mobile
  instructor tests verify page 2, historical-session selection and downloaded JSON.
  Doubles test UI orchestration, not authorization or recognition accuracy; separate
  backend tests cover those boundaries, including 105-record reports and cross-course
  isolation. The real face-service tests cover repository same/different-person samples.
- Student and instructor production builds, TypeScript, Compose configuration,
  backend/face/frontend Docker builds, real container-to-container enrollment and
  replay rejection, and production-container account/offline browser flows are checked.
- Prometheus scrapes backend, face and its own metrics successfully. Grafana 13.3.0
  starts, provisions the seven-panel SAIV System Overview dashboard, and successfully
  queries its Prometheus datasource. Initial disk exhaustion was resolved by removing
  temporary application images/build caches. Grafana needs `NO_PROXY` for the internal
  Prometheus hostname in this cloud; Compose now supplies it. These checks verify
  provisioning and datasource connectivity, not every panel's visual layout.

Final checks: **154 public/regression tests passed**, **10 browser tests passed**
against the standalone production frontend (with a separate instructor build),
and **seven mobile camera-workflow tests passed**. No tests failed or skipped in
these final runs. The browser suite includes real account/offline tests and explicit
UI doubles as described above. The twenty-client static-replay workload passed; the slowest measured submission
was 1.419 seconds in that local run (not a live-inference benchmark).
Temporary application validation containers/images were removed after testing to
reclaim cloud storage. Native student/instructor apps and API services were restored
with normal rate limits. Local Prometheus and Grafana run on ports 9090 and 3001;
they use disposable development configuration. Source Dockerfiles and reproduction
commands remain available. A final metrics-label hardening change was followed by
two passing targeted readiness/metrics tests on both native services.

## Local reproduction

Node 20.9+ is required (Docker uses Node 22). Use a disposable PostgreSQL/Redis
stack and the restricted database role described in [SECURITY-PRIVACY.md](SECURITY-PRIVACY.md).
Fixture-heavy suites need a separate backend with explicit higher rate limits and
unique `RATE_LIMIT_PREFIX`; never deploy those test overrides.

```bash
# Start infrastructure, migration and applications; normal trusted network:
docker compose up --build postgres redis db-migrate face-recognition backend frontend dashboard

# In this cloud network, supply its trusted CA bundle only during builds:
PROXY_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
  docker compose -f docker-compose.yml -f docker-compose.proxy.yml \
  up --build postgres redis db-migrate face-recognition backend frontend dashboard
```

On restrictive-umask cloud checkouts, non-root monitoring images need readable
public configuration files. These paths contain service configuration, not secrets:

```bash
chmod a+r module4-observability/prometheus.yml
find module4-observability/grafana/provisioning -type d -exec chmod a+rx {} +
find module4-observability/grafana/provisioning -type f -exec chmod a+r {} +
```

Run the full suite with `TEST_BACKEND_URL`, `TEST_FACE_URL`,
`TEST_RUNTIME_DATABASE_URL` (restricted PostgreSQL role) and `TEST_FRONTEND_URL`.
The HTTPX proxy regression needs Next development over HTTP or production HTTPS;
HTTPX does not implement the browser's localhost exception for Secure cookies.
Browser production tests use Chromium and accept localhost as a secure context.
`TEST_DASHBOARD_URL` selects the separately built instructor surface.

```bash
python -m pytest tests/public tests/regression -q
python -m pytest tests/browser -q
# Mobile camera workflow contract tests:
TEST_MOBILE=1 python -m pytest tests/browser/test_student_workflow.py -q
```

## Remaining release gates

1. **Python dependency modernization.** The built backend and face images contain
   known-vulnerable legacy packages. [DEPENDENCY-AUDIT.json](DEPENDENCY-AUDIT.json)
   records installed versions, deduplicated advisory IDs and reported fix versions.
   The backend scan reported 11 affected packages; the face scan reported seven.
   Frontend production dependencies reported zero known vulnerabilities after the
   upgrade. These are scanner results, not a claim that every advisory is exploitable
   in this application. Several JOSE/ECDSA advisories have no listed fix; the legacy
   MediaPipe/protobuf compatibility constraints need deliberate migration and ML
   re-evaluation. Do not deploy these Python images as a security-approved release.
2. **Real-device biometric acceptance.** Verify positive live-person enrollment
   and blink/head-turn/smile on actual target phones, adverse lighting and camera
   quality; evaluate replay/deepfake samples and false accepts/rejects on an
   appropriate consented dataset. Current fixture timings and sample-image tests
   do not establish live-user p95 latency, accuracy or attack resistance.
3. **Deployment operations.** Verify monitoring and capacity in the target deployment;
   configure HTTPS, production secrets, trusted proxy/IP handling,
   IP lookup credentials, restricted service exposure, backup/audit retention and
   deletion-worker monitoring. Retained immutable audit metadata needs an explicit
   operational retention policy. Public-face-service endpoints should remain internal.
4. **Product acceptance.** Session-code entry works; camera QR decoding remains
   unimplemented. Validate the intended QR experience and accessibility on target
   devices. Large, changing datasets may require cursor/snapshot pagination and
   server-side dashboard summaries rather than collecting every page each poll.
