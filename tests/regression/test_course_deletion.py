"""RUN_COURSE_TESTS=1 python3 -m unittest discover -s tests/regression -p test_course_deletion.py -v"""
import json
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen


@unittest.skipUnless(os.getenv("RUN_COURSE_TESTS") == "1", "Requires local backend")
class CourseDeletionTests(unittest.TestCase):
    @staticmethod
    def request(method, path, body=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = Request("http://localhost:8000/api/v1" + path, method=method, headers=headers,
                      data=json.dumps(body).encode() if body is not None else None)
        try:
            response = urlopen(req, timeout=30)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None

    @classmethod
    def setUpClass(cls):
        cls.people = {}
        for label, role in (("admin", "admin"), ("owner", "instructor"), ("other", "instructor"), ("student", "student")):
            body = {"email": f"delete-test-{uuid.uuid4().hex}@example.com", "password": "Local-delete-test-123",
                    "full_name": "Deletion Test", "role": role}
            status, user = cls.request("POST", "/auth/register", body)
            assert status == 201, user
            status, auth = cls.request("POST", "/auth/login", body)
            assert status == 200, auth
            cls.people[label] = (user["id"], auth["access_token"])

    def setUp(self):
        self.token = self.people["owner"][1]
        self.courses = []
        for _ in range(2):
            status, course = self.request("POST", "/courses/", {
                "instructor_id": self.people["owner"][0], "code": "DEL-" + uuid.uuid4().hex[:10], "name": "Deletion Test", "semester": "2026/27 Semester 1",
            }, self.people["admin"][1])
            self.assertEqual(status, 201, course)
            self.courses.append(course)
        self.course, self.other_course = self.courses
        day = (datetime.now(timezone.utc) + timedelta(days=14)).date()
        self.schedule = {"request_id": str(uuid.uuid4()), "course_id": self.course["id"], "name": "Weekly lab",
                         "start_date": str(day), "end_date": str(day + timedelta(days=7)), "weekday": day.weekday(),
                         "start_time": "10:00", "end_time": "11:00", "timezone": "Asia/Singapore"}
        status, series = self.request("POST", "/sessions/recurring", self.schedule, self.token)
        self.assertEqual(status, 201, series)
        self.series = series
        self.same_day = self.create_lesson(self.course, f"{day}T12:00:00+08:00", f"{day}T13:00:00+08:00")
        self.unrelated = self.create_lesson(self.other_course, f"{day}T14:00:00+08:00", f"{day}T15:00:00+08:00")

    def tearDown(self):
        for course in self.courses:
            self.request("DELETE", f"/courses/{course['id']}?permanent=true", token=self.token)

    def create_lesson(self, course, start, end):
        status, lesson = self.request("POST", "/sessions/", {"course_id": course["id"], "name": "Single lesson",
            "scheduled_start": start, "scheduled_end": end, "require_liveness_check": False}, self.token)
        self.assertEqual(status, 201, lesson)
        return lesson

    def lesson_ids(self, course):
        status, result = self.request("GET", f"/sessions/?course_id={course['id']}", token=self.token)
        self.assertEqual(status, 200, result)
        return {item["id"] for item in result["items"]}

    def test_one_occurrence_keeps_other_dates_and_same_day_lessons(self):
        deleted, kept = self.series["sessions"]
        status, result = self.request("DELETE", f"/sessions/{deleted['id']}?permanent=true", token=self.token)
        self.assertEqual(status, 204, result)
        self.assertEqual(self.lesson_ids(self.course), {kept["id"], self.same_day["id"]})
        self.assertEqual(self.lesson_ids(self.other_course), {self.unrelated["id"]})
        # Retrying the original recurrence request must not resurrect deleted dates.
        status, series = self.request("POST", "/sessions/recurring", self.schedule, self.token)
        self.assertEqual(status, 201, series)
        self.assertEqual([item["id"] for item in series["sessions"]], [kept["id"]])
        status, _ = self.request("GET", f"/courses/{self.course['id']}", token=self.token)
        self.assertEqual(status, 200)

    def test_delete_all_removes_only_selected_course(self):
        status, result = self.request("DELETE", f"/courses/{self.course['id']}?permanent=true", token=self.token)
        self.assertEqual(status, 204, result)
        status, _ = self.request("GET", f"/courses/{self.course['id']}", token=self.token)
        self.assertEqual(status, 404)
        status, listed = self.request("GET", "/sessions/", token=self.token)
        self.assertEqual(status, 200, listed)
        self.assertFalse(any(item["course_id"] == self.course["id"] for item in listed["items"]))
        self.assertEqual(self.lesson_ids(self.other_course), {self.unrelated["id"]})
        status, _ = self.request("POST", "/sessions/recurring", self.schedule, self.token)
        self.assertEqual(status, 404)

    def test_other_tutor_student_anonymous_cannot_delete(self):
        for token in (self.people["other"][1], self.people["student"][1], None):
            for path in (f"/courses/{self.course['id']}", f"/sessions/{self.same_day['id']}"):
                status, result = self.request("DELETE", path + "?permanent=true", token=token)
                self.assertIn(status, (401, 403), result)
        self.assertEqual(len(self.lesson_ids(self.course)), 3)

    def test_delete_with_attendance_revokes_codes_and_removes_records(self):
        for scope in ("sessions", "courses"):
            with self.subTest(scope=scope):
                now = datetime.now(timezone.utc)
                lesson = self.create_lesson(self.course, (now + timedelta(minutes=1)).isoformat(), (now + timedelta(hours=1)).isoformat())
                if scope == "sessions":
                    status, data = self.request("POST", "/enrollments/", {
                        "course_id": self.course["id"], "student_id": self.people["student"][0]}, self.token)
                    self.assertEqual(status, 201, data)
                status, invite = self.request("POST", f"/sessions/{lesson['id']}/attendance-code", {"student_url": "https://students.example.edu"}, self.token)
                self.assertEqual(status, 200, invite)
                status, checkin = self.request("POST", "/checkins/", {
                    "session_id": lesson["id"], "latitude": 1.3483, "longitude": 103.6831,
                    "device_fingerprint": "delete-test-" + uuid.uuid4().hex, "qr_code": invite["passcode"],
                }, self.people["student"][1])
                self.assertEqual(status, 201, checkin)
                # The default API still requires explicit consent to delete an active lesson.
                status, _ = self.request("DELETE", f"/sessions/{lesson['id']}", token=self.token)
                self.assertEqual(status, 400)
                target = lesson["id"] if scope == "sessions" else self.course["id"]
                status, result = self.request("DELETE", f"/{scope}/{target}?permanent=true", token=self.token)
                self.assertEqual(status, 204, result)
                status, _ = self.request("POST", "/attendance/resolve", {"code": invite["passcode"]}, self.people["student"][1])
                self.assertEqual(status, 400)
                status, _ = self.request("GET", f"/checkins/{checkin['id']}", token=self.people["student"][1])
                self.assertEqual(status, 404)
