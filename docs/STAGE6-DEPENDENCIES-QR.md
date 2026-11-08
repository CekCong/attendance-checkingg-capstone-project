# Stage 6: dependency modernization and QR — 30 October 2026 (Singapore)

The backend dependency migration, session QR workflow and MediaPipe Tasks migration
are implemented. Official model access now works. The two model artifacts are
SHA-256 pinned and checked both before atomic installation and before native model
loading. The new face Docker image contains the models and required EGL/GLES
libraries. Real-device biometric and production acceptance remain separate gates.

## Implemented and verified

- Replace python-jose/ECDSA with PyJWT, restrict decoding to HS256, and require
  subject, issued-at, expiry, token type and authentication version. Existing valid
  HS256 tokens remain compatible; database roles and account revocation remain
  authoritative. Unsigned, wrong-algorithm, expired and incomplete tokens are rejected.
- Update FastAPI/Starlette, Pydantic, cryptography and supporting packages. Remove
  unused geopy, multipart parsing and OpenTelemetry exporters/instrumentation.
  Keep the required OpenTelemetry API and Prometheus metrics. Move pytest and
  fixture tools out of production requirements.
- Commit input manifests plus complete, hash-verified Python dependency locks
  targeting Python 3.11. Test requirements reuse the runtime locks. Backend Docker
  installs binary wheels with hash verification and no longer installs compiler
  tooling. TLS verification remains enabled.
- Assigned instructors/admins can issue or rotate a session QR code during its
  active check-in window. The code has 192 bits of randomness, expires within
  90 seconds (or at session close), and rotation invalidates the previous code.
  Issuing the first code enables required-code validation for that session.
  Issuance is audited as `session_updated` with `qr_code_rotated` details;
  secrets never appear in audit entries or student session responses.
- Instructor UI displays a real QR image, manual code and expiry; expired images
  disappear. Student scanning uses the rear camera where available and decodes
  pixels locally. It accepts a plain code or the versioned session-bound JSON
  payload, rejects unrelated URLs/wrong-session payloads, and never navigates to
  scanned content. Camera streams stop after capture, cancellation, hiding the
  page, unmounting, and late permission resolution. Manual entry remains available.
  Scanning does not grant biometric consent or submit attendance.
- The full backend verification policy still applies to QR submissions. Missing,
  incorrect, rotated and expired codes cannot create attendance records. No schema
  migration is needed for these changes; existing session QR columns/audit actions
  are reused.

## Evidence and boundaries

- **172 public/regression tests passed**, with zero failures or skips in the final
  full run. This used the new Python 3.11 backend and the previously running Stage 5
  face service. It validates backend migration/interoperability, not the new Tasks
  liveness pipeline. Twenty concurrent static-replay submissions are included.
- **17 API/student-flow tests passed against the new backend Docker image**;
  `pip check` also passed inside it. This container used the same Stage 5 face service.
- Ten existing browser scenarios passed; all **seven new QR browser tests passed**
  on rerun after correcting the permission-denial test stub. QR tests use actual
  QR pixels and independent encoders/decoders, with explicit camera/API doubles.
  They cover decoding, session binding, URL rejection, cancellation, camera denial,
  instructor generation/rotation/expiry and mobile layout. Seven existing mobile
  camera workflow tests also passed. Actual phone-camera acceptance remains manual.
- Student and instructor production builds and frontend TypeScript passed. After
  restoring the normal local ports/quotas, the real account flow and seven QR
  browser checks passed again (eight tests).
- The new ArcFace/NumPy/ONNX stack passed a real three-image compatibility test:
  normalized 512-dimensional embeddings, same-person cosine about 0.778 and
  different-person cosine about -0.043. These three images establish compatibility
  only, not population accuracy or live-user performance.
- Audits report **zero known vulnerabilities** for the new backend runtime lock,
  built backend installed dependencies, new face runtime lock and frontend production
  dependencies. See [audit evidence](DEPENDENCY-AUDIT-STAGE6.json). Scans cover
  application package advisories, not OS images, deployment configuration or unknown
  vulnerabilities. Those checkpoint scans predated face-container acceptance;
  the completed migration evidence below includes the installed face-image packages.

## Completed face-service migration

MediaPipe 1.2 removes `mediapipe.solutions`. The adapter now targets Tasks
`FaceDetector` and `FaceLandmarker`, with normalized detection boxes, the existing
landmark indices and unchanged liveness thresholds. Models preload at startup;
missing assets fail startup instead of downloading during requests. Shared Tasks
instances are serialized and closed at shutdown.

The installer uses versioned official HTTPS URLs and atomically writes each verified
model file. A checksum failure preserves the existing file and removes the temporary
download. Startup rejects missing or corrupt models before creating native Tasks.
The pins in `app/model_assets.py`, recorded from the official HTTPS downloads, are:

| Model | SHA-256 |
| --- | --- |
| `blaze_face_short_range.tflite` | `b4578f35940bf5a1a655214a1cce5cab13eba73c1297cd78e1a04c2380b0152f` |
| `face_landmarker.task` | `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff` |

The first native Tasks run identified a missing `libGLESv2.so.2`; the Dockerfile
now installs `libgles2` and `libegl1`. No liveness thresholds were relaxed.

From `module3-face-recognition`, for native development:

```bash
export MEDIAPIPE_MODEL_DIR=/workspace/saiv-runtime/mediapipe
export INSIGHTFACE_HOME=/workspace/saiv-runtime/insightface
export MPLCONFIGDIR=/workspace/.cache/matplotlib
# On this cloud host, libgles2 was extracted from a signed Debian package here.
# A normal system installation of libgles2/libegl1 does not need this override.
export LD_LIBRARY_PATH=/workspace/saiv-native-libs/usr/lib/x86_64-linux-gnu
/workspace/saiv-stage6-venv/bin/python -m app.prepare_models

# Start a separate native test face service:
REDIS_URL=redis://localhost:6380 \
  /workspace/saiv-stage6-venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8022
```

From the repository root with the same model environment:

```bash
/workspace/saiv-stage6-venv/bin/python -m pytest tests/acceptance/test_model_migration.py -q
# Run HTTP tests with the isolated backend pointing at the same face service.
```

All five native model acceptance tests pass: real ArcFace embeddings, real Tasks
face detection/landmarks and blank-image rejection, missing/corrupt startup assets,
and atomic download failure. The new Docker image passes `pip check`; its installed
Python packages have zero known vulnerabilities in the advisory scan. Both model
runtimes load with Docker networking disabled, using only bundled assets.

The final full suite passed **199 public/regression tests, zero failures/skips**
in 160.23 seconds against the new face Docker image, current native Python 3.11
backend, PostgreSQL and Redis. The backend ran with isolated teaching-fixture flags
and elevated test quotas; normal services retain student-only registration and
default quotas. This run includes enrollment/verification, liveness contracts,
20 concurrent static-replay rejections, QR proofs and production identity controls.
It replaces the checkpoint's reliance on the old Stage 5 face runtime.

Image: `saiv-stage6-face`, ID
`sha256:85e70440cb0d31f71f23d672c2f8530f6956ba74975de8a203df422af4ca9840`.
Build with `docker build -t saiv-stage6-face module3-face-recognition` from the root,
adding the documented optional `proxy_ca` secret if the network requires it.
The cloud's normal port 8001 now runs this image with Redis on localhost:6380.
After restoring normal ports and quotas, the real account flow and seven QR
browser checks passed again (**eight browser tests**). The QR scenarios retain
their explicit camera/API doubles; this is not real-phone camera acceptance.

Reproduce the full suite against a disposable fixture backend and Next development
server configured as described in [authentication/deployment](AUTH-DEPLOYMENT.md):

```bash
TEST_BACKEND_URL=http://localhost:8020 TEST_FACE_URL=http://localhost:8022 \
TEST_FRONTEND_URL=http://localhost:3012 \
TEST_RUNTIME_DATABASE_URL="$RUNTIME_TEST_DATABASE_URL" \
TEST_BOOTSTRAP_DATABASE_URL="$OWNER_TEST_DATABASE_URL" \
  /workspace/saiv-stage6-venv/bin/python -m pytest tests/public tests/regression -q
```

The two database variables above must contain the disposable restricted-runtime
and schema-owner connections respectively. The backend's `FACE_SERVICE_URL` must
point to that same face service. Tests create disposable fixture accounts and
audit records; do not run them against production data.

Real target phone liveness, attack/accuracy evaluation and production deployment remain release
gates. Stage 7 now restricts public registration and provides operator-only administrator
bootstrap; see [production identity controls](PRODUCTION-IDENTITY.md). Review existing
privileged accounts before external exposure. Production secrets, HTTPS, trusted proxy/IP handling and audit/
backup retention still require deployment acceptance.

## Dependency reproduction

```bash
uv pip compile module2-backend/requirements.in --python-version 3.11 --generate-hashes -o module2-backend/requirements.txt
uv pip compile module3-face-recognition/requirements.in --python-version 3.11 --generate-hashes -o module3-face-recognition/requirements.txt
uv pip compile requirements-test.in --python-version 3.11 --generate-hashes -o requirements-test.txt
# Install in a clean Python 3.11 environment, not on top of the Stage 5 environment:
python -m pip install --require-hashes -r requirements-test.txt
python -m pip check
```

Use the isolated fixture-rate overrides in [AUTH-DEPLOYMENT.md](AUTH-DEPLOYMENT.md)
for HTTP suites. The normal local student/instructor apps and updated backend are
restored on their usual ports with normal quotas. Use the new face image or the
Python 3.11 environment above; the old Stage 5 environment is no longer required.
