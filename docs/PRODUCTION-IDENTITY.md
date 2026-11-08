# Stage 7, part 1: production identity controls

Implemented on 30 October 2026 (Singapore), while the Stage 6 MediaPipe download
was blocked (it is now resolved). This completes registration/bootstrap hardening;
it does not establish production deployment or real-device biometric acceptance.

## Registration and provisioning

Public registration now creates **student accounts only**, in both development
and production by default. Requests selecting `admin`, `instructor` or `ta` return
403, create no account, and append a `security_violation` audit event without the
submitted email/password. Existing accounts and roles are not changed. Review
pre-existing privileged accounts before exposing any database used with the old
teaching/demo registration policy.

An existing administrator can create staff through the authenticated
`POST /api/v1/admin/users/bulk` endpoint. Students cannot access that route.
The first administrator is created through a trusted operator command with
server/database access, never through an unauthenticated HTTP bootstrap endpoint.

From `module2-backend`, after applying the normal database migration, configure
`DATABASE_URL` for that deployment and run:

```bash
python -m app.bootstrap_admin --email operator@example.com --full-name "Initial Administrator"
```

The command prompts twice for a hidden password. Passwords must contain at least
12 characters and at most 72 UTF-8 bytes, avoiding bcrypt truncation. They are
stored as bcrypt hashes. For noninteractive secret-manager provisioning, pass
`--password-file /run/secrets/bootstrap-password`; the file must be a regular,
non-symlink file owned by the executing operator with mode 0600 or 0400. Passwords
are never accepted as command-line arguments or printed by the command. Protect
and remove temporary provisioning files under your normal secret-management policy.

Bootstrap refuses if **any administrator already exists**, including disabled or
deleted-account tombstones. It also refuses to promote an existing email address,
change passwords, or reactivate users. Recovery of an existing administrator is a
separate trusted operational procedure. The PostgreSQL transaction advisory lock
serializes concurrent bootstrap commands; the user and `initial_admin_bootstrap`
audit event commit together or roll back together. This concurrency guarantee is
validated on PostgreSQL; SQLite is used only for isolated unit tests.

## Explicit production configuration

Set `SAIV_ENV=production` on the backend. Startup then rejects:

- A missing/development signing key, or an actual signing key shorter than 32 bytes.
- `COOKIE_SECURE` not set to `true`.
- Any attempt to enable privileged self-registration.

Generate the signing key independently with a cryptographically secure generator
and supply it through deployment secrets. The length check cannot prove randomness.
The guard checks the key actually used to sign tokens, not merely an environment
value loaded later. Unknown `SAIV_ENV` values also fail startup.

These checks require HTTPS ingress; they do not install TLS or validate an ingress
configuration. Compose remains local development configuration, defaults to
`SAIV_ENV=development`, and explicitly disables privileged registration. It is
not a complete production deployment manifest.

## Isolated teaching/test compatibility

The supplied teaching API/tests create instructor/admin fixture accounts through
registration. That behavior now requires **both** of these explicit server settings:

```bash
SAIV_ENV=test ALLOW_PRIVILEGED_SELF_REGISTRATION=true \
REGISTRATION_RATE_LIMIT=100000 LOGIN_RATE_LIMIT=100000 \
API_RATE_LIMIT=100000 CHECKIN_RATE_LIMIT=1000 RATE_LIMIT_PREFIX=isolated-tests: \
uvicorn app.main:app --host 127.0.0.1 --port 8020 --no-proxy-headers
```

Use a separate disposable test backend/database and the usual database/Redis/face
configuration. Never enable this mode on a shared or externally exposed service.
The standard Compose service pins the override to false; use a separate native
fixture server as above. Normal local services retain normal quotas and student-only
registration. Existing valid staff accounts can still log in.

## Validation

- **198 public/regression tests passed** in the full run, with no failures/skips,
  using the isolated compatibility server plus the retained Stage 5 face service.
- **27 focused identity tests passed** after strengthening the bootstrap test to
  run two real CLI processes against an isolated PostgreSQL schema. Checks cover
  default role denial, test-only opt-in, unsafe production settings, actual signing
  key validation, student registration, hashed/audited bootstrap, refusal to reset
  or promote users, audit-failure rollback, private password files, and authenticated
  staff provisioning. These tests overlap the full suite; counts are not additive.
- The backend Docker image built successfully. It refused production startup with
  the development signing key. With an ephemeral test key and secure cookies, it
  denied all three privileged public roles while allowing student registration/login
  and returning Secure, HttpOnly cookies. This localhost check does not verify TLS.
- The normal backend was restarted with the new default registration policy;
  the real browser account/password/deletion flow passed afterwards.

For the PostgreSQL CLI race test, set `TEST_BOOTSTRAP_DATABASE_URL` to a disposable
schema-owner connection. The test creates a unique temporary schema, never uses
public application tables, and removes only its own schema afterwards. The other
identity tests use isolated SQLite and namespaced Redis database 2.

## Still outstanding

Stage 6's model-access blocker is resolved and the new MediaPipe pipeline/image
has passed automated acceptance. See [updated Stage 6 evidence](STAGE6-DEPENDENCIES-QR.md).

Stage 7 still needs real-phone biometric/attack testing, production HTTPS/secrets,
trusted ingress/IP configuration, backup/restore exercises, audit retention and
monitoring acceptance. Existing privileged accounts require an explicit deployment
review. No production deployment has been performed.
