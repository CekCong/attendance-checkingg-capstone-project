"""RUN_COURSE_TESTS=1 python3 -m unittest discover -s tests/regression -p test_recurring_lessons.py -v"""
import json
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen


@unittest.skipUnless(os.getenv("RUN_COURSE_TESTS") == "1", "Requires running backend")
class RecurringLessonTests(unittest.TestCase):
    def request(self, method, path, body=None, token=None):
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
            return response.status, json.load(response)

    def account(self, role):
        body = {"email": f"calendar-{uuid.uuid4().hex}@example.com", "password": "Local-calendar-test-123",
                "full_name": "Calendar Test", "role": role}
        status, result = self.request("POST", "/auth/register", body)
        self.assertEqual(status, 201, result)
        status, result = self.request("POST", "/auth/login", body)
        self.assertEqual(status, 200, result)
        return result["access_token"]

    def setUp(self):
        self.token = self.account("instructor")
        admin_token = self.account("admin")
        status, self.course = self.request("POST", "/courses/", {
            "code": f"CAL-{uuid.uuid4().hex[:10]}", "name": "Calendar tests", "semester": "2026/27 Semester 1",
        }, admin_token)
        self.assertEqual(status, 201, self.course)
        status, assigned = self.request("POST", f"/courses/{self.course['id']}/assignment", token=self.token)
        self.assertEqual(status, 200, assigned)
        self.start = (datetime.now(timezone.utc) + timedelta(days=14)).date()
        self.start += timedelta(days=(0 - self.start.weekday()) % 7)
        self.payload = {"request_id": str(uuid.uuid4()), "course_id": self.course["id"], "name": "Weekly tutorial",
                        "session_type": "tutorial", "start_date": str(self.start), "end_date": str(self.start + timedelta(days=21)),
                        "weekday": 0, "start_time": "07:30", "end_time": "09:00", "timezone": "Asia/Singapore", "venue_name": "TR4"}

    def lessons(self):
        status, data = self.request("GET", f"/sessions/?course_id={self.course['id']}&limit=100", token=self.token)
        self.assertEqual(status, 200, data)
        return data["items"]

    def test_weekly_dates_timezone_metadata_and_retry(self):
        status, result = self.request("POST", "/sessions/recurring", self.payload, self.token)
        self.assertEqual(status, 201, result)
        self.assertEqual(result["count"], 4)  # both date bounds inclusive
        lessons = self.lessons()
        self.assertEqual(len(lessons), 4)
        expected = datetime.combine(self.start, datetime.min.time()) - timedelta(minutes=30)
        for index, lesson in enumerate(lessons):
            self.assertEqual(datetime.fromisoformat(lesson["scheduled_start"]).replace(tzinfo=None), expected + timedelta(weeks=index))
            self.assertEqual(lesson["series_id"], result["series_id"])
            self.assertEqual(lesson["venue_name"], "TR4")
            self.assertEqual(lesson["session_type"], "tutorial")
        status, again = self.request("POST", "/sessions/recurring", self.payload, self.token)
        self.assertEqual(status, 201, again)
        self.assertEqual(again, result)
        self.assertEqual(len(self.lessons()), 4)
        status, _ = self.request("POST", "/sessions/recurring", {**self.payload, "name": "Changed"}, self.token)
        self.assertEqual(status, 409)

    def test_invalid_schedules_create_nothing(self):
        variants = [
            {"end_date": str(self.start - timedelta(days=1))},
            {"end_date": str(self.start + timedelta(days=367))},
            {"end_time": "07:30"}, {"end_time": "06:00"}, {"weekday": 7},
            {"timezone": "America/New_York"}, {"name": "  "},
            {"weekday": 1, "end_date": str(self.start)},
            {"start_date": "2020-01-01", "end_date": "2020-02-01"},
        ]
        for patch in variants:
            with self.subTest(patch=patch):
                status, data = self.request("POST", "/sessions/recurring", {**self.payload, **patch}, self.token)
                self.assertEqual(status, 422, data)
        self.assertEqual(self.lessons(), [])

    def test_conflict_in_middle_rolls_back_whole_series(self):
        conflict_day = self.start + timedelta(days=7)
        status, data = self.request("POST", "/sessions/", {
            "course_id": self.course["id"], "name": "Existing lecture",
            "scheduled_start": f"{conflict_day}T08:00:00+08:00", "scheduled_end": f"{conflict_day}T09:00:00+08:00",
        }, self.token)
        self.assertEqual(status, 201, data)
        status, data = self.request("POST", "/sessions/recurring", self.payload, self.token)
        self.assertEqual(status, 409, data)
        self.assertIn("No lessons were added", data["detail"])
        self.assertEqual(len(self.lessons()), 1)

    def test_student_other_tutor_and_anonymous_cannot_schedule(self):
        for token in (self.account("student"), self.account("instructor"), None):
            status, data = self.request("POST", "/sessions/recurring", self.payload, token)
            self.assertIn(status, (401, 403), data)
        self.assertEqual(self.lessons(), [])

    def test_adjacent_lessons_allowed_and_calendar_date_filter(self):
        status, data = self.request("POST", "/sessions/recurring", self.payload, self.token)
        self.assertEqual(status, 201, data)
        status, data = self.request("POST", "/sessions/recurring", {
            **self.payload, "request_id": str(uuid.uuid4()), "start_time": "09:00", "end_time": "10:00",
        }, self.token)
        self.assertEqual(status, 201, data)
        start = str(self.start) + "T00:00:00%2B08:00"
        end = str(self.start + timedelta(days=1)) + "T00:00:00%2B08:00"
        status, data = self.request("GET", f"/sessions/?overlap_start={start}&end_date={end}", token=self.token)
        self.assertEqual(status, 200, data)
        self.assertEqual(data["total"], 2)
