# Stage 6 checkpoint — 30 October 2026 (Singapore)

The backend dependency migration and session QR workflow are implemented and
verified. **The MediaPipe migration is prepared but not accepted yet:** the cloud
proxy returns `403 Forbidden` for its official model host, `storage.googleapis.com`.
The environment draft adds that host and preserves both Google Fonts hosts.
Review/save the draft in environment settings and publish, then retry the model
preparation and acceptance commands below. Saving the draft alone does not change
runtime access. Stage 6 remains open until the new face pipeline is tested.

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
  vulnerabilities. The still-running Stage 5 face process retains its old dependencies;
  do not mistake the candidate face lock's audit for a completed runtime migration.

## Prepared face-service changes — still blocked

MediaPipe 1.2 removes `mediapipe.solutions`. The adapter now targets Tasks
`FaceDetector` and `FaceLandmarker`, with normalized detection boxes, the existing
landmark indices and unchanged liveness thresholds. Models preload at startup;
missing assets fail startup instead of downloading during requests. Shared Tasks
instances are serialized and closed at shutdown.

The installer uses versioned official HTTPS URLs and atomically writes the two
model files. It prints their SHA-256 digests for recording once access works.
The download has not succeeded here, so model digests and real Tasks output are
not yet verified. Do not substitute an untrusted mirror or weaken thresholds to
make acceptance pass. Docker preparation now requires this model-download access.

After the network update, from `module3-face-recognition`:

```bash
export MEDIAPIPE_MODEL_DIR=/workspace/saiv-runtime/mediapipe
export INSIGHTFACE_HOME=/workspace/saiv-runtime/insightface
export MPLCONFIGDIR=/workspace/.cache/matplotlib
/workspace/saiv-stage6-venv/bin/python -m app.prepare_models

# After model preparation succeeds, start a separate test face service:
REDIS_URL=redis://localhost:6380 \
  /workspace/saiv-stage6-venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8022
```

From the repository root with the same model environment:

```bash
/workspace/saiv-stage6-venv/bin/python -m pytest tests/acceptance/test_model_migration.py -q
# Then run face/public/liveness tests against port 8022 and rerun full backend
# verification with FACE_SERVICE_URL pointing to that new service. Rebuild and
# validate the new face Docker image before replacing the retained Stage 5 process.
```

The standalone ArcFace acceptance test passed. The Tasks test and new face Docker
image remain unrun because their required model files are unavailable. Real target
phone liveness, attack/accuracy evaluation and production deployment remain release
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
restored on their usual ports with normal quotas. The old face service is retained
only for development continuity until the new one passes acceptance.
