# SAIV - Secure Attendance & Identity Verification

## NTU Computer Science Capstone Project

Welcome to our capstone project! The goal is to build a secure, privacy-preserving attendance system resistant to deepfakes, replay attacks, and remote sign-ins.

---

## Project Overview

### Learning Objectives
- Full-stack development (PWA frontend, REST API, database design)
- Security engineering (liveness detection, device binding, geofencing)
- Privacy-first architecture (PII minimization, encrypted storage)
- ML integration (pre-trained face recognition models)
- DevOps (Docker, observability)

---

## Architecture

4 modules:

### Module 1: Student Frontend PWA
**Recommended Tech Stack**: React/Next.js, TypeScript, WebRTC
- Student check-in interface
- Camera access for liveness challenges
- Geolocation with consent
- Device binding (public key rotation)
- Offline-capable PWA

### Module 2: Backend API
**Recommended Tech Stack**: Python FastAPI, PostgreSQL, Redis
- RESTful API with JWT authentication
- Session management (time-boxed check-ins)
- Check-in processing and validation
- Rate limiting and CORS
- Audit logging

### Module 3: Face Recognition & Risk Service
**Recommended Tech Stack**: Python, MediaPipe, OpenCV
- Liveness detection (blink, head pose)
- Face matching (with privacy controls)
- Risk scoring (signal fusion)
- Device attestation
- Anti-spoofing heuristics

### Module 4: Observability & Instructor Dashboard 
**Implemented stack**: Next.js instructor surface, Prometheus, Grafana
- Instructor web interface
- Real-time analytics
- Audit log explorer
- Metrics visualization
- CSV export for gradebook

---

## Migration status

Stages 1–6 are implemented on `hongyu`, including updated dependency locks,
session QR issuance/scanning and the verified MediaPipe Tasks runtime/image.
See [migration progress](docs/MIGRATION.md) and
[Stage 6 validation](docs/STAGE6-DEPENDENCIES-QR.md). Real-device biometric acceptance
remains open. Stage 7's student-only sign-up, initial-admin bootstrap and production
authentication configuration checks are implemented; see
[production identity controls](docs/PRODUCTION-IDENTITY.md). Production operations
remain open.

## Getting Started

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- Node.js 20.9+

### Quick Start

```bash
# Navigate to project directory
cd attendance-checkin-pwa

# Start infrastructure services (database, redis, prometheus)
docker-compose up -d postgres redis prometheus grafana

# Wait for services to be healthy
docker-compose ps

# Start developing your modules
# Each team member works on their assigned module
```

### Service URLs (when running)
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000/docs
- Face Recognition: http://localhost:8001/docs
- Dashboard: http://localhost:8501
- Grafana: http://localhost:3001 (admin/admin)
- Prometheus: http://localhost:9090

### Local web sign-up

Start Docker Desktop, then run from the project root:

```bash
docker compose up -d frontend dashboard face-recognition
```

Open http://localhost:3000 for students or http://localhost:8501 for tutors.
Students can choose **Create a student account** and enter a name, email, and
password of at least 8 characters. Staff accounts use Hongyu's existing
administrator provisioning flow; public signup cannot grant instructor or admin
roles. See [production identity](docs/PRODUCTION-IDENTITY.md).

The web containers use `BACKEND_INTERNAL_URL=http://backend:8000` for server-side
authentication and student API requests. Tutor API requests use `NEXT_PUBLIC_API_URL`.

### Tutor courses

Sign in to http://localhost:8501, then choose **New course** under **Your courses**.
Enter a unique course code and name, choose an academic year/semester from the
dropdown, and select **Create course**.
The course is saved, assigned to your tutor account, and automatically selected
for session creation. Use the course dropdown to switch between your courses.
In **Lesson calendar**, select **Add lesson**. Choose a lesson title, type, and
optional location. Select **Every week** to choose a weekday, inclusive start/end
dates, and start/end times, or **Does not repeat** for a single lesson. Check the
lesson-count/date preview, then save. All scheduling and calendar times use
Singapore time (SGT); semester options do not assume official term dates or holidays.

Use **Today**, the previous/next arrows, and **Day / Week / Month** to navigate the calendar.
On laptops the calendar sits on the left and attendance tools, flagged check-ins,
and analytics appear on the right. On smaller screens these sections stack.
Select a lesson block to show its attendance controls in the right panel.
Choose **Delete lesson or course…** in that panel to delete **this lesson only**
(the selected date and time) or **Delete all** (the entire course and every lesson).
For a course without lessons, use **Courses, students & semesters**, select the course,
and choose **Delete course…**. Both choices require confirmation and permanently
remove the associated attendance records; deleting a whole course also removes
its enrollments. Deleting one recurring lesson leaves other dates and other
lessons on the same day intact. Only the owning tutor or an administrator can delete.
The calendar scrolls through all 24 hours; on smaller screens use Day view or
scroll horizontally. Weekly schedules create separate attendance sessions for
each date (up to one year). A conflict rejects the whole schedule, and retrying
the same submission does not create duplicate lessons. Series editing and
automatic holiday exclusions are not included.

### Enrolling students with a CSV roster

In the tutor dashboard, open **Courses, students & semesters**, select a course,
then expand **Enroll students · Upload CSV**. Download the template or upload a
UTF-8 CSV with this column (numbers are text, so preserve leading zeroes in Excel):

```csv
matriculation_number
U2345678A
U2345679B
```

Preview the matches, then choose **Import roster into [course]**. Registered
students with matching numbers are enrolled immediately. Unknown numbers remain
pending until the student signs up or links their number in **Profile**. The
**Uploaded roster** list shows pending and enrolled statuses; **Refresh** updates it.
Imports add to the course and do not remove other students. Repeated rows/imports
do not create duplicate enrollments. Invalid files show row errors before any
rows are saved. Limit: 1,000 rows and 1 MB per upload.

New student signup asks for a matriculation number. Existing students can link it
once in Profile. Numbers are trimmed, uppercased, and unique across accounts;
after linking, students cannot change or remove the number themselves. Student
**My courses** shows their enrollments. Joining a lesson still uses the tutor's
QR/passcode followed by the existing verification flow.

For existing installations, apply the new schema before restarting the backend:

```bash
docker compose run --rm --no-deps db-migrate
docker compose restart backend
```

Regression check (isolated databases; Redis on port 6380):

```bash
PYTHONPATH=module2-backend:tests/regression DATABASE_URL=sqlite:////tmp/saiv-tests.db \
  python3 -m pytest tests/regression/test_course_rosters.py -v
```

### Attendance QR and passcode

**Demo mode is currently enabled in Docker Compose.** Tutors can generate QR codes
and passcodes for any lesson date or time, including reopening past, closed, or
cancelled lessons. Each generated code opens a fresh 15-minute check-in window.
The tutor panel displays a **Demo mode** notice. Enrollment and student verification
still apply, and closing a session stops check-ins until a tutor opens it again.
To restore scheduled attendance restrictions, run
`ATTENDANCE_DEMO_MODE=false docker compose up -d --no-build backend`.
Outside Compose, this flag defaults to `false`.

With demo mode disabled, the normal rules below apply.

Select a lesson and choose **Generate QR & passcode** in the right panel. This activates
the lesson and opens a 15-minute check-in window, capped at the lesson's end.
Codes can be opened from 15 minutes before the scheduled start. Switch between
**QR code** and **Passcode**; **Renew QR & passcode** invalidates the previous code and
**Close session** stops further check-ins.
The panel explains when a lesson is too early, ended, closed, or its code has
expired. After expiry, choose **Generate new QR & passcode** during the lesson's
attendance window. Selecting a calendar lesson alone does not open attendance.

Under **Student website URL**, enter the address where students can reach the
student portal. Use the shared HTTPS student URL for phones; `localhost:3000`
only works on the same computer. Camera and location access require HTTPS on
other devices. The student portal proxies attendance requests to `BACKEND_INTERNAL_URL`,
so phones do not need direct access to backend port 8000.

Students scan with their phone's Camera app or type the passcode in the student
portal, sign in, confirm sensor consent, enroll their face if needed, allow location
access, and complete the active liveness challenge. Device attestation and server
verification remain enabled. The backend records the check-in and reports approved, flagged for review,
or rejected. Students must already be enrolled in the course; a code does not
bypass enrollment or verification. Face-matching courses still require face enrollment.

QR images are generated locally by the backend. Student URLs can be changed
without rotating a currently active passcode. No external QR service is used.

```bash
PYTHONPATH=module2-backend:tests/regression DATABASE_URL=sqlite:////tmp/saiv-tests.db \
  python3 -m pytest tests/regression/test_calendar_attendance_merge.py -v
```
These tests use isolated databases, Redis on port 6380, and explicit biometric
test doubles. They cover the new controls together with Hongyu's verification flow.

Course assignments are stored in the `course_instructors` table, created by the
schema migration service. Existing assignments through sessions remain supported.
Recurring schedules and their occurrences are saved in `session_series` and
`session_occurrences`, also created by the schema migration service.

The legacy live course tests below require an isolated `SAIV_ENV=test` backend
with `ALLOW_PRIVILEGED_SELF_REGISTRATION=true` and increased fixture rate limits.
They must not be pointed at a production or shared deployment.

```bash
RUN_COURSE_TESTS=1 python3 -m unittest discover -s tests/regression -p test_tutor_courses.py -v
RUN_COURSE_TESTS=1 python3 -m unittest discover -s tests/regression -p test_recurring_lessons.py -v
docker compose exec -T dashboard node < tests/regression/calendar_helpers.cjs
```

To verify student registration and the staff-signup restriction on running portals
(creates student test accounts):

```bash
RUN_WEB_AUTH_TESTS=1 python3 -m unittest discover -s tests/regression -p test_web_registration.py -v
```

---

## Running Tests

You have access to the public test suite (75% of your grade).

**IMPORTANT:** Tests send HTTP requests to your running services. Your services MUST be running before you run tests.

### Step 1: Install Test Dependencies

```bash
cd attendance-checkin-pwa

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install test dependencies
pip install --upgrade pip
pip install -r requirements-test.txt
```

On Windows, run these commands in PowerShell instead (use Python 3.11):

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version
python -m pip install --upgrade pip
python -m pip install -r requirements-test.txt
```

If PowerShell reports that script execution is disabled when activating the
environment, use the environment's Python directly instead:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
```

The backend enforces 10 registrations/hour/IP, 60 logins/hour/IP,
1,000 authenticated API requests/hour/user, and 10 check-ins/minute/user.
See [authentication and development deployment](docs/AUTH-DEPLOYMENT.md) for
isolated test overrides and Docker configuration.

### Step 2: Start Your Services

```bash
# Build and start all your services
docker-compose up -d

# Wait for services to be healthy (about 30 seconds)
docker-compose ps

# Verify services are accessible
curl http://localhost:8000/health
curl http://localhost:8001/health
```

### Step 3: Run Tests

```bash
# Set test environment variables (optional - defaults to localhost)
export TEST_BACKEND_URL=http://localhost:8000
export TEST_FACE_URL=http://localhost:8001

# Run all public tests
python3 -m pytest tests/public/ -v

# Run specific test category
python3 -m pytest tests/public/test_api_functional.py -v
python3 -m pytest tests/public/test_security_basic.py -v
python3 -m pytest tests/public/test_privacy_basic.py -v
python3 -m pytest tests/public/test_face_recognition.py -v
python3 -m pytest tests/public/test_observability.py -v
python3 -m pytest tests/public/test_integration.py -v

# The scoring plugin shows a summary at the end:
# TOTAL SCORE: 90.0/90.0 (100.0%)
# LETTER GRADE: A
```

In PowerShell, set the optional test URLs this way:

```powershell
$env:TEST_BACKEND_URL = "http://localhost:8000"
$env:TEST_FACE_URL = "http://localhost:8001"

python -m pytest tests/public/ -v
```

### Step 4: Stop Services

```bash
# Stop all services
docker-compose down

# Stop and remove volumes (clean slate)
docker-compose down -v
```

### Troubleshooting

**Tests skipping with "Backend service not running":**
```bash
docker-compose up -d
docker-compose ps  # Verify all services are "Up"
```

**Connection refused errors:**
```bash
export TEST_BACKEND_URL=http://localhost:8000
curl $TEST_BACKEND_URL/health
```

In PowerShell:

```powershell
$env:TEST_BACKEND_URL = "http://localhost:8000"
curl.exe "$env:TEST_BACKEND_URL/health"
```

### Note on System Dependencies

Some packages require system-level dependencies:

- **face-recognition**: Requires `dlib` which needs `cmake` and C++ compiler
  - macOS: `brew install cmake`
  - Ubuntu: `sudo apt-get install cmake build-essential`

- **opencv-python**: Usually works out of the box, but may need:
  - Ubuntu: `sudo apt-get install libgl1-mesa-glx`

---

## Grading Breakdown

### Public Tests (90 points) 

| Test File | Points | Description |
|-----------|--------|-------------|
| test_api_functional.py | 26 | API endpoints, auth, CRUD operations |
| test_face_recognition.py | 15 | Face enrollment, matching, risk assessment |
| test_security_basic.py | 12 | JWT auth, input validation, rate limiting |
| test_privacy_basic.py | 8 | Consent, data minimization, retention |
| test_frontend_dashboard.py | 8 | Frontend/dashboard API contracts |
| test_observability.py | 12 | Stats, session management, export (bonus) |
| test_performance.py | 5 | Latency, concurrent users |
| test_integration.py | 4 | End-to-end check-in flow |

### Hidden Tests (40 points) 

| Category | Points | Description |
|----------|--------|-------------|
| Advanced Security | 12 | GPS spoofing, replay attacks, VPN detection |
| Privacy Auditing | 8 | Database audit, encryption validation |
| Face Recognition Advanced | 10 | Advanced liveness, anti-spoofing |
| Liveness Bonus | 3 | Advanced liveness features |
| Stress Testing | 7 | Concurrent users, edge cases |

---

## Documentation

Please review these specifications carefully:

- **[API Specification](docs/API-SPECIFICATION.md)** - Complete endpoint documentation
- **[Database Schema](docs/recommended_design/DATABASE-SCHEMA.md)** - All table definitions

---

## Project Structure

```
attendance-checkin-pwa/
├── module1-frontend/          # PWA (your implementation)
├── module2-backend/           # API (your implementation)
├── module3-face-recognition/  # ML service (your implementation)
├── module4-observability/     # Dashboard (your implementation)
├── tests/
│   ├── public/                # Public test suite (90 points)
│   └── scoring/               # Pytest scoring plugin
├── docs/
│   ├── API-SPECIFICATION.md
│   └── DATABASE-SCHEMA.md
└── docker-compose.yml
```

---

## Security Requirements

Your implementation must include:

1. **Authentication**
   - JWT tokens (HS256)
   - Bcrypt password hashing (cost >= 10)
   - Role-based access control

2. **Input Validation**
   - Sanitize all user input
   - Prevent SQL injection
   - Prevent XSS attacks

3. **Rate Limiting**
   - Protect against brute force
   - Use Redis for tracking

4. **Geofencing**
   - Validate GPS coordinates
   - Calculate distance to venue

---

## Required Admin Endpoints

Tests require these admin endpoints for test data setup. See [API Specification](docs/API-SPECIFICATION.md) for details.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/admin/users/{id}/deactivate` | PATCH | Deactivate user (for testing inactive login) |
| `/api/v1/admin/users/{id}/activate` | PATCH | Reactivate user |
| `/api/v1/admin/users/bulk` | POST | Bulk create users (for stress tests) |
| `/api/v1/admin/sessions/{id}/status` | PATCH | Update session status |
| `/api/v1/admin/enrollments/` | POST | Create enrollment (admin bypass) |

**Note:** These endpoints require admin authentication and are used by the test suite to set up test scenarios.

---

## Privacy Requirements

Your implementation must:

1. **Never store raw face images** - Process in memory, store only hashes
2. **Track consent** - Camera and geolocation permissions
3. **Implement retention** - 30-day auto-deletion of records
4. **Create audit logs** - Immutable event trail

---

## Tips for Success

1. **Read the specifications thoroughly** before coding
2. **Run tests frequently** to catch issues early
3. **Communicate with your team** - modules must integrate
4. **Don't over-engineer** - focus on requirements
5. **Think about security** from the start
6. **Document your decisions** for the final report

---

## Common Pitfalls

Avoid these mistakes:
- Storing raw face images (automatic privacy test failure)
- Ignoring rate limiting (vulnerable to attacks)
- Missing geofence validation (easy to bypass)
- Poor error handling (crashes under load)
- Incorrect CORS configuration (frontend can't communicate)

---
