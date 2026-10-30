"""Run with RUN_COURSE_TESTS=1 and local Docker demo mode enabled."""
import os
import unittest
from datetime import datetime, timedelta, timezone

import test_attendance_codes as fixtures


@unittest.skipUnless(os.getenv("RUN_COURSE_TESTS") == "1", "Requires local demo backend and student portal")
class AttendanceDemoTests(unittest.TestCase):
    request = staticmethod(fixtures.AttendanceCodeTests.request)
    setUpClass = classmethod(fixtures.AttendanceCodeTests.setUpClass.__func__)
    setUp = fixtures.AttendanceCodeTests.setUp
    tearDown = fixtures.AttendanceCodeTests.tearDown
    issue = fixtures.AttendanceCodeTests.issue

    def check_in(self, invite):
        self.assertTrue(invite["demo_mode"])
        student = self.people["student"][1]
        status, result = self.request("POST", "/resolve", {"code": invite["passcode"]}, student, web=True)
        self.assertEqual(status, 200, result)
        status, result = self.request("POST", "/checkin", {
            "session_id": self.lesson["id"], "latitude": 1.3483, "longitude": 103.6831,
            "device_fingerprint": "demo-test-device", "qr_code": invite["passcode"],
        }, student, web=True)
        self.assertEqual(status, 201, result)
        self.assertEqual(result["session_id"], self.lesson["id"])

    def change_dates(self, start, end):
        status, data = self.request("PATCH", f"/sessions/{self.lesson['id']}", {
            "scheduled_start": start.isoformat(), "scheduled_end": end.isoformat(),
        }, self.token)
        self.assertEqual(status, 200, data)
        status, data = self.request("GET", self.path, token=self.token)
        self.assertEqual(status, 200, data)
        self.assertTrue(data["demo_mode"])
        self.assertEqual(data["reason"], "not_open")

    def test_future_lesson_accepts_real_checkin_now(self):
        start = datetime.now(timezone.utc) + timedelta(days=7)
        self.change_dates(start, start + timedelta(hours=1))
        self.check_in(self.issue())

    def test_past_lesson_has_fresh_expiry_and_accepts_checkin(self):
        start = datetime.now(timezone.utc) - timedelta(days=7)
        self.change_dates(start, start + timedelta(hours=1))
        invite = self.issue()
        expiry = datetime.fromisoformat(invite["expires_at"].replace("Z", "+00:00"))
        self.assertGreater(expiry, datetime.now(timezone.utc) + timedelta(minutes=14))
        self.check_in(invite)

    def test_closed_lesson_can_reopen_but_close_still_revokes_code(self):
        old = self.issue()
        status, result = self.request("PATCH", f"/sessions/{self.lesson['id']}", {"status": "closed"}, self.token)
        self.assertEqual(status, 200, result)
        status, _ = self.request("POST", "/attendance/resolve", {"code": old["passcode"]}, self.people["student"][1])
        self.assertEqual(status, 400)
        renewed = self.issue()
        self.assertNotEqual(old["passcode"], renewed["passcode"])
        self.check_in(renewed)

    def test_cancelled_lesson_can_reopen_for_demonstration(self):
        status, result = self.request("PATCH", f"/sessions/{self.lesson['id']}", {"status": "cancelled"}, self.token)
        self.assertEqual(status, 200, result)
        self.check_in(self.issue())
