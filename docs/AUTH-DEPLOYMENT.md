# Authentication and development deployment

The backend signs tokens and checks the current database user for login, refresh,
and authenticated requests. Next.js forwards authentication requests and keeps
refresh tokens in an HttpOnly, SameSite=Lax cookie. Access tokens live in browser
session storage and memory; page restoration consults the backend. Refresh runs
before access-token expiry and when the window regains focus near expiry.
Logout, password changes, account deactivation and deletion increment the user's
database authentication version, invalidating all previously issued access and
refresh tokens. Logout accepts the server-held refresh token even after access
expiry. Password changes sign the browser out immediately. Tokens issued before
Stage 4 require a new login. Refresh tokens remain reusable until expiry or account
session revocation; this is account-wide revocation, not per-device refresh rotation.

## Addresses

- `BACKEND_INTERNAL_URL`: server-only backend address. Compose uses
  `http://backend:8000`; local Next development defaults to `http://localhost:8000`.
- `NEXT_PUBLIC_API_URL`: browser-reachable backend origin. Compose defaults to
  `http://localhost:8000`. Production images embed this at build time.
- `FRONTEND_ORIGIN` / `DASHBOARD_ORIGIN`: optional browser origins passed as
  `APP_ORIGIN` to the corresponding Next server. Set these for HTTPS ingress,
  e.g. `https://attendance.example.edu`. Authentication checks Origin against this
  value, or against the incoming Host and request scheme during local development.
- `CORS_ALLOWED_ORIGINS`: comma-separated browser frontend origins accepted by the
  backend. Defaults to the two local frontend ports.
- `SECRET_KEY`: backend-only signing secret. Set a strong secret for deployment;
  the fallback is for disposable development only. The frontend needs no signing key.
- `COOKIE_SECURE=true`: enable Secure on cookies issued directly by the backend
  when served over HTTPS. Production Next cookies are always Secure.

Ingress must preserve Host and validate any client-IP forwarding. The application
reads the peer address supplied by ASGI; it does not trust arbitrary
X-Forwarded-For headers. Authentication forwarded by Next is conservatively counted
against the Next server's peer IP, so users share that limit until a trusted ingress
client-IP arrangement is configured. Do not broadly trust forwarded headers.

## Docker

Compose runs `db-migrate` with the schema-owner credentials before starting the
backend. The backend uses `saiv_app`, which cannot change schema or mutate audit
history. The API deliberately refuses to start with the old superuser connection.
See [security/privacy deployment](SECURITY-PRIVACY.md) for native setup and migration
instructions. Compose passwords are disposable local defaults; set separate,
strong deployment credentials. `IPINFO_TOKEN` is now supplied through the environment.

`docker compose up --build` uses the frontend `development` image target and live
reload. This target does not require a production font download. For a production
frontend image, build with `--target production` and supply the appropriate build
arguments for app surface and browser API origin. Production build validation still
requires access to `fonts.googleapis.com` and `fonts.gstatic.com`.

On machines whose network uses a private HTTPS inspection CA, the frontend, backend
and face-service Dockerfiles accept an optional BuildKit secret named `proxy_ca`:

```bash
docker build --secret id=proxy_ca,src=/path/to/trusted-ca-bundle.pem \
  --target development -t saiv-frontend module1-frontend
docker build --secret id=proxy_ca,src=/path/to/trusted-ca-bundle.pem \
  -t saiv-backend module2-backend
```

Use a trust bundle supplied by the environment. The secret is mounted only for
installation/build commands; it is not copied into the image. TLS and package
integrity verification remain enabled. Stage 5 builds and validates the real
face-service image, including its bundled model and backend integration. The
optional `docker-compose.proxy.yml` overlay supplies the same build secret to all
application images; see [release validation](RELEASE-VALIDATION.md).

Production frontend images use Next.js 16 standalone output and run as the
non-root `node` user. Node 20.9+ is required for native builds (Docker uses Node 22).
The browser API origin and student/instructor surface must be supplied at build
time. Both API services expose `/ready`; Compose waits for these dependency checks
before starting dependent services. `/health` remains a basic process check.

## Rate limits and isolated tests

Defaults: `REGISTRATION_RATE_LIMIT=10`, `LOGIN_RATE_LIMIT=60`,
`API_RATE_LIMIT=1000`, `CHECKIN_RATE_LIMIT=10`. Redis counters have atomic TTLs.
An unavailable Redis limiter returns 503. `RATE_LIMIT_ALLOW_MEMORY=true` is an
explicit single-process development fallback, not a deployment setting.

HTTP fixture suites create many accounts from one IP. Start a separate backend
for those suites with a separate `RATE_LIMIT_PREFIX` and explicit higher limits:

```bash
REGISTRATION_RATE_LIMIT=100000 LOGIN_RATE_LIMIT=100000 \
API_RATE_LIMIT=100000 CHECKIN_RATE_LIMIT=100000 RATE_LIMIT_PREFIX=test-suite: \
uvicorn app.main:app --port 8020 --no-proxy-headers
```

Run from `module2-backend` with the normal database/Redis environment configured.
Never apply those test overrides to deployment. Tests in
`tests/regression/test_auth_migration.py` exercise the actual default login,
registration and check-in boundaries using isolated SQLite and namespaced Redis
on localhost:6380, database 2. They also test a smaller configurable API quota.

For the live frontend/backend integration test, use:

```bash
TEST_FRONTEND_URL=http://localhost:3000 TEST_BACKEND_URL=http://localhost:8000 \
PYTHONPATH=tests python -m pytest tests/regression/test_frontend_auth_proxy.py -q
```

It creates test users and audit events. Run against a disposable development stack.
For this HTTPX test use Next development on HTTP, or a production server over HTTPS:
HTTPX does not implement browsers' Secure-cookie exception for HTTP localhost.
The Chromium account test also runs against the production build on localhost.

## Stage 6 dependency checkpoint

The backend now uses PyJWT with HS256 and mandatory subject/issued-at/expiry/type/
authentication-version claims. Existing valid signed tokens remain compatible;
roles and revocation still come from the database. Runtime/test dependencies are
separated and hash-locked for Python 3.11. Use a clean environment so removed
legacy packages do not remain installed.

Session QR issuance is available to assigned instructors/admins at
`POST /api/v1/sessions/{session_id}/qr-code`; successful responses include the
opaque manual code, versioned JSON payload and UTC expiry. They inherit the API's
`Cache-Control: no-store`. A new code enables required-code verification and rotates
any earlier one; it does not bypass enrollment, consent, device or liveness checks.

The new MediaPipe runtime requires versioned official model downloads, which the
current cloud proxy blocks. The environment draft adds `storage.googleapis.com`;
model and Docker acceptance remain pending. See [Stage 6 status and commands](STAGE6-DEPENDENCIES-QR.md)
before restarting the retained Stage 5 face process or building the new face image.
