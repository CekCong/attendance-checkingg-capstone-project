# Student attendance workflow

1. Create a student account or sign in. An instructor/admin must enroll the student
   in a course. The student dashboard lists active enrolled sessions whose check-in
   windows are open, plus the latest 100 backend attendance records.
2. Select a session. If session-code verification is enabled, enter the current
   code provided by the instructor. The previous simulated QR scanner is removed;
   camera-based QR decoding is not implemented.
3. Agree to both camera and geolocation use. These choices are saved to the backend.
   The browser creates a non-exportable RSA-PSS private key in IndexedDB and
   registers its public key. Keys are separate for each account on this browser;
   clearing site data requires registering a new key.
4. If no face is enrolled, capture a front-facing enrollment image. The backend
   sends it to the face service and stores the resulting template, not the image.
5. Grant geolocation permission. Then start the liveness challenge. The server
   chooses blink, head turn, or smile; follow the neutral/action/neutral prompts.
   The client captures exactly 15 frames in memory, obtains and signs a fresh
   device challenge, and submits through the backend.
6. The result displays the backend status: approved, flagged, rejected, or pending.
   Returning to the dashboard reloads server history. A network error does not
   imply failure to persist: refresh history before retrying an interrupted request.

Camera access requires HTTPS or localhost. Capture uses at most 640x480 video;
streams stop on cancellation, navigation, or completion. Location errors stop
submission. Frames are not saved to browser storage. Device keys do not provide
hardware attestation or protection against arbitrary same-origin script execution.

Profile display-name edits and password changes are saved to the backend. Email
and username are read-only; language/appearance remain local preferences. Existing
copied tokens are not yet revoked after password changes or logout; this belongs
to the next security stage.

## Verification

Install the standard test dependencies and optional `requirements-browser.txt`.
Start the backend, face service, database, Redis, and Next frontend. Use separate
rate-limit configuration for fixture-heavy test runs as described in
[AUTH-DEPLOYMENT.md](AUTH-DEPLOYMENT.md).

```bash
TEST_BACKEND_URL=http://localhost:8020 TEST_FRONTEND_URL=http://localhost:3000 \
PYTHONPATH=tests python -m pytest tests/public tests/regression -q

TEST_FRONTEND_URL=http://localhost:3000 PYTHONPATH=tests \
python -m pytest tests/browser/test_student_workflow.py -q

TEST_BACKEND_URL=http://localhost:8020 TEST_FRONTEND_URL=http://localhost:3000 \
PYTHONPATH=tests python -m pytest tests/browser/test_account_integration.py -q
```

The workflow browser tests explicitly use API doubles and Chromium's fake camera.
They verify consent, capture, signatures, status handling, permission denial,
cancellation, and network failure. `TEST_MOBILE=1` enables a mobile viewport.
They do not validate face recognition accuracy or real phone camera behavior.

The account browser test uses real services. The student migration regression also
uses real services and a repository sample image: it verifies enrollment, signed
device submission, rejection of a static replay through active liveness, and
persisted rejected history. Positive live-person acceptance, cross-device camera
quality, and broader attack-image evaluation remain release-validation work.
