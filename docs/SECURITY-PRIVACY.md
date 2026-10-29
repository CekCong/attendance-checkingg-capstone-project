# Stage 4: security and privacy

## Enforced behavior

- Check-in requires both stored consents. Sessions requiring liveness accept only
  a server-issued active challenge and 15 frames, backed by an enrolled template.
  Module 3 consumes challenges atomically, checks user/session/action binding,
  and expires them after 60 seconds. Device-bound courses require signed one-use
  challenges (120 seconds). A failed attempt consumes its supplied challenges;
  retries obtain fresh ones.
- Missing proofs cannot create attendance. Invalid signatures fail; required
  liveness/face failures produce rejected attendance. Any verification-service
  outage or malformed result returns 503 without inserting a check-in, even when
  the instructor configured a permissive risk threshold.
- Unknown devices and unavailable public-IP country data force review. Only a
  confirmed non-Singapore country signal triggers the geographic rejection rule.
  Lookup failures are not cached indefinitely. Set `IPINFO_TOKEN` for public-IP
  lookups; missing configuration means review, not a false foreign-country result.
- Impossible travel forces review, using the most recent approved observation,
  a 300 km/h threshold, and GPS/rounding uncertainty of at least 100 m per point.
  Rejected locations cannot poison this history. This is a review heuristic;
  browser GPS and accuracy remain client-supplied signals.
- Exact GPS is used in memory for the geofence decision. Stored coordinates use
  three decimal places (roughly 111 m); stored venue distance is rounded to 100 m.
  New audit events contain no coordinates. The migration rounds existing check-in
  locations without rewriting immutable audit history.
- Access and refresh tokens carry a database authentication version. Logout,
  password changes, deactivation and deletion invalidate all previous versions.
  Re-enabling an account does not restore revoked tokens. Existing pre-migration
  tokens require a new login. Refresh rotation and per-device session management
  are not implemented.
- `DELETE /api/v1/users/me` requires the current password, disables access now,
  and sets `scheduled_deletion_at` to 30 days later. The hourly retention worker
  removes due account profile fields, password hash, face template, device keys,
  enrollments, attendance and associated risk signals. A disabled tombstone ID
  remains to preserve audit foreign keys. Pending/erased accounts cannot be
  reactivated. Cleanup is idempotent; completion follows the deadline at the next
  worker run. Existing check-ins also retain their independent 30-day expiry.
- PostgreSQL audit triggers reject UPDATE, DELETE and TRUNCATE. The API role has
  only SELECT/INSERT privileges on audit logs and cannot disable triggers or drop
  their table. Instructors see their own events and events for assigned courses,
  sessions and attendance; administrators retain global audit access.

Audit records, including security IP/user-agent metadata and any legacy free-text
content, are retained by the briefing's immutable-audit requirement. Account
cleanup is not a claim that audit metadata becomes anonymous. Historical audit
rows may contain precise coordinates from earlier code; they are not rewritten.
A production retention policy for audit metadata/backups remains release work.
Database owners/superusers remain trusted administrators: they can change schema
and disable protection. Stronger protection from database administrators requires
external write-once storage, which is outside this implementation.

## Database migration and runtime permissions

Back up a non-disposable database before schema migrations. The migration adds
`users.auth_version`, rounds existing attendance locations, installs audit guards,
and optionally provisions a separate API role. It is repeatable. It does not drop
tables or rewrite audit records. The API no longer creates schema at startup.

For local Compose, `docker compose up --build` runs `db-migrate` first. For native
local development, from `module2-backend` with dependencies installed:

```bash
DATABASE_URL=postgresql://saiv:saiv_password@localhost:5434/saiv \
APP_DATABASE_ROLE=saiv_app APP_DATABASE_PASSWORD=saiv_app_dev_password \
python -m app.migrate

DATABASE_URL=postgresql://saiv_app:saiv_app_dev_password@localhost:5434/saiv \
REDIS_URL=redis://localhost:6380 FACE_SERVICE_URL=http://localhost:8001 \
uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-proxy-headers
```

These are disposable development credentials. Deployment should supply a schema
owner only to its migration job and use a separate restricted runtime secret.
The Compose password substitution expects URL-safe password characters; supply
properly encoded connection URLs when configuring services outside Compose.
The startup guard rejects a superuser, audit owner, mutable audit permissions,
or missing/disabled audit trigger. New tables require grants through migration.

## Validation and compatibility

`tests/regression/test_security_privacy_migration.py` exercises copied-token
revocation, consent/proof omission, invalid/expired/wrong-session device proofs,
one-use active challenge binding and races, service outages, malformed replies,
coarse location persistence, travel/unknown-network review, deletion/idempotence,
audit preservation/scope, and restricted PostgreSQL privileges. ML success paths
in these tests use explicit doubles; the separate student migration test verifies
static replay rejection against the real face service.

Run the PostgreSQL permission check by setting `TEST_RUNTIME_DATABASE_URL` to the
restricted test database connection. SQLite/Redis regression tests use an isolated
in-memory database and Redis database 2; live HTTP tests require the separate
backend with fixture-rate overrides described in `AUTH-DEPLOYMENT.md`.

The supplied public suite contains six incompatible legacy expectations:

- `test_api_functional.py`: successful check-in, duplicate check-in, and history
  tests submit no consent, device proof, or active-liveness proof.
- `test_frontend_dashboard.py::test_checkin_request_format` omits consent/proofs.
- `test_integration.py::test_complete_student_checkin_flow` grants consent but
  omits required active-liveness/device proofs.
- `test_performance.py::test_checkin_endpoint_latency` expects 201 without consent
  or required proofs; its latency result is not a valid complete-verification benchmark.

These supplied assertions are preserved and fail under the stricter requirements.
Do not restore permissive check-in behavior to make them green. Stage 5 must migrate
those fixtures to complete verification flows and distinguish contract, ML and
performance evidence. Positive real-person liveness and device-camera acceptance
still require real-device evaluation.
