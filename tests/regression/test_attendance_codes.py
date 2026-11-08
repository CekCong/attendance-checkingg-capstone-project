"""RUN_COURSE_TESTS=1 python3 -m unittest discover -s tests/regression -p test_attendance_codes.py -v"""
import json
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
from xml.etree import ElementTree


@unittest.skipUnless(os.getenv("RUN_COURSE_TESTS") == "1", "Requires local backend and student portal")
class AttendanceCodeTests(unittest.TestCase):
    @staticmethod
    def request(method, path, body=None, token=None, web=False):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        base = "http://localhost:3000/api/attendance" if web else "http://localhost:8000/api/v1"
        req = Request(base + path, method=method, headers=headers,
                      data=json.dumps(body).encode() if body is not None else None)
        try:
            response = urlopen(req, timeout=90)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None

    @classmethod
    def setUpClass(cls):
        cls.people = {}
        for label, role in (("admin", "admin"), ("owner", "instructor"), ("other", "instructor"), ("student", "student"), ("outsider", "student")):
            body = {"email": f"qr-test-{uuid.uuid4().hex}@example.com", "password": "Local-qr-test-123", "full_name": "QR Test", "role": role}
            status, user = cls.request("POST", "/auth/register", body)
            assert status == 201, user
            status, session = cls.request("POST", "/auth/login", body)
            assert status == 200, session
            cls.people[label] = (user["id"], session["access_token"])

    def setUp(self):
        self.token = self.people["owner"][1]
        status, self.course = self.request("POST", "/courses/", {"instructor_id": self.people["owner"][0], "code": "QR-" + uuid.uuid4().hex[:10], "name": "QR Test", "semester": "2026/27 Semester 1"}, self.people["admin"][1])
        self.assertEqual(status, 201, self.course)
        now = datetime.now(timezone.utc)
        status, self.lesson = self.request("POST", "/sessions/", {"course_id": self.course["id"], "name": "Attendance test", "scheduled_start": (now + timedelta(minutes=1)).isoformat(), "scheduled_end": (now + timedelta(hours=1)).isoformat(), "require_liveness_check": False}, self.token)
        self.assertEqual(status, 201, self.lesson)
        status, result = self.request("POST", "/enrollments/", {"course_id": self.course["id"], "student_id": self.people["student"][0]}, self.token)
        self.assertEqual(status, 201, result)
        self.path = f"/sessions/{self.lesson['id']}/attendance-code"

    def tearDown(self):
        self.request("DELETE", f"/courses/{self.course['id']}?permanent=true", token=self.token)

    def issue(self):
        status, data = self.request("POST", self.path, {"student_url": "https://students.example.edu"}, self.token)
        self.assertEqual(status, 200, data)
        self.assertTrue(data["open"])
        return data

    def test_qr_and_passcode_resolve_through_student_portal(self):
        data = self.issue()
        self.assertEqual(data["join_url"], "https://students.example.edu/#attendance=" + data["passcode"])
        self.assertEqual(len(data["passcode"]), 8)
        self.assertEqual(ElementTree.fromstring(data["qr_svg"]).tag, "{http://www.w3.org/2000/svg}svg")
        expiry = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        self.assertGreater(expiry, datetime.now(timezone.utc))
        self.assertLessEqual(expiry, datetime.now(timezone.utc) + timedelta(minutes=15))
        code = data["passcode"].lower()
        status, resolved = self.request("POST", "/resolve", {"code": code[:4] + " " + code[4:]}, self.people["student"][1], web=True)
        self.assertEqual(status, 200, resolved)
        self.assertEqual(resolved["session_id"], self.lesson["id"])
        self.assertEqual(resolved["qr_code"], data["passcode"])
        status, alternate = self.request("GET", self.path + "?student_url=" + quote("https://class.example.edu"), token=self.token)
        self.assertEqual(status, 200, alternate)
        self.assertEqual(alternate["passcode"], data["passcode"])
        self.assertTrue(alternate["join_url"].startswith("https://class.example.edu/"))

    def test_renewal_invalidates_old_code_and_close_revokes(self):
        old = self.issue()
        new = self.issue()
        self.assertNotEqual(old["passcode"], new["passcode"])
        status, _ = self.request("POST", "/attendance/resolve", {"code": old["passcode"]}, self.people["student"][1])
        self.assertEqual(status, 400)
        status, result = self.request("PATCH", f"/sessions/{self.lesson['id']}", {"status": "closed"}, self.token)
        self.assertEqual(status, 200, result)
        status, _ = self.request("POST", "/attendance/resolve", {"code": new["passcode"]}, self.people["student"][1])
        self.assertEqual(status, 400)
        status, data = self.request("GET", self.path, token=self.token)
        self.assertEqual(status, 200)
        self.assertFalse(data["open"])

    def test_permissions_and_enrollment(self):
        data = self.issue()
        for token in (self.people["other"][1], self.people["student"][1], None):
            for method, body in (("GET", None), ("POST", {"student_url": "https://students.example.edu"})):
                status, result = self.request(method, self.path, body, token)
                self.assertIn(status, (401, 403), result)
        status, _ = self.request("POST", "/attendance/resolve", {"code": data["passcode"]}, self.people["outsider"][1])
        self.assertEqual(status, 403)

    def test_closed_window_and_future_lesson_respects_demo_mode(self):
        data = self.issue()
        now = datetime.now(timezone.utc)
        status, result = self.request("PATCH", f"/sessions/{self.lesson['id']}", {"checkin_closes_at": (now - timedelta(seconds=1)).isoformat()}, self.token)
        self.assertEqual(status, 200, result)
        status, _ = self.request("POST", "/attendance/resolve", {"code": data["passcode"]}, self.people["student"][1])
        self.assertEqual(status, 400)
        status, result = self.request("PATCH", f"/sessions/{self.lesson['id']}", {"scheduled_start": (now + timedelta(days=1)).isoformat(), "scheduled_end": (now + timedelta(days=1, hours=1)).isoformat()}, self.token)
        self.assertEqual(status, 200, result)
        status, _ = self.request("POST", self.path, {"student_url": "https://students.example.edu"}, self.token)
        self.assertEqual(status, 200 if data.get("demo_mode") else 400)

    def test_code_is_required_by_real_checkin_and_duplicates_rejected(self):
        data = self.issue()
        payload = {"session_id": self.lesson["id"], "latitude": 1.3483, "longitude": 103.6831, "device_fingerprint": "qr-test-device", "qr_code": "WRONG"}
        student = self.people["student"][1]
        status, result = self.request("POST", "/checkin", payload, student, web=True)
        self.assertEqual(status, 400, result)
        payload["qr_code"] = data["passcode"]
        status, result = self.request("POST", "/checkin", payload, student, web=True)
        self.assertEqual(status, 201, result)
        self.assertEqual(result["session_id"], self.lesson["id"])
        self.assertIn(result["status"], ("approved", "flagged", "rejected"))
        self.assertTrue(result["id"])
        status, result = self.request("POST", "/checkin", payload, student, web=True)
        self.assertEqual(status, 400, result)
        self.assertIn("Already checked in", result["detail"])
