"""Live course checks: RUN_COURSE_TESTS=1 python3 -m unittest discover -s tests/regression -p test_tutor_courses.py -v"""
import json
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen


@unittest.skipUnless(os.getenv("RUN_COURSE_TESTS") == "1", "Requires running backend")
class TutorCourseTests(unittest.TestCase):
    @staticmethod
    def request(method, path, body=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(os.getenv("TEST_BACKEND_URL", "http://localhost:8000") + "/api/v1" + path, method=method,
                          data=json.dumps(body).encode() if body is not None else None,
                          headers=headers)
        try:
            response = urlopen(request, timeout=20)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    @classmethod
    def setUpClass(cls):
        cls.users = {}
        for label, role in (("owner", "instructor"), ("other", "instructor"), ("student", "student"), ("admin", "admin")):
            body = {"email": f"course-test-{uuid.uuid4().hex}@example.com",
                    "password": "Local-course-test-123", "full_name": "Course Test", "role": role}
            status, user = cls.request("POST", "/auth/register", body)
            assert status == 201, user
            status, session = cls.request("POST", "/auth/login", body)
            assert status == 200, session
            cls.users[label] = (user["id"], session["access_token"])

    def payload(self):
        return {"code": "TEST-" + uuid.uuid4().hex[:10], "name": "Test Course", "semester": "2026-S1"}

    def test_owner_can_add_existing_course_list_select_and_schedule(self):
        owner_id, token = self.users["owner"]
        status, course = self.request("POST", "/courses/", self.payload(), self.users["admin"][1])
        self.assertEqual(status, 201, course)
        status, course = self.request("POST", f"/courses/{course['id']}/assignment", token=token)
        self.assertEqual(status, 200, course)
        self.assertEqual(course["instructor_id"], owner_id)
        status, courses = self.request("GET", "/courses/", token=token)
        self.assertEqual(status, 200, courses)
        self.assertIn(course["id"], [item["id"] for item in courses["items"]])
        status, details = self.request("GET", f"/courses/{course['id']}", token=token)
        self.assertEqual(status, 200, details)
        self.assertEqual(details["instructor_id"], owner_id)
        status, sessions = self.request("GET", f"/sessions/?course_id={course['id']}", token=token)
        self.assertEqual(status, 200, sessions)
        self.assertEqual(sessions["items"], [], "Creation must not add a placeholder session")
        start = datetime.now(timezone.utc) + timedelta(days=1)
        payload = {"course_id": course["id"], "name": "First tutorial", "scheduled_start": start.isoformat(),
                   "scheduled_end": (start + timedelta(hours=1)).isoformat()}
        status, session = self.request("POST", "/sessions/", payload, token)
        self.assertEqual(status, 201, session)
        self.assertEqual(session["course_id"], course["id"])
        other_token = self.users["other"][1]
        status, other_courses = self.request("GET", "/courses/", token=other_token)
        self.assertEqual(status, 200)
        self.assertNotIn(course["id"], [item["id"] for item in other_courses["items"]])
        for method, path, body in (("GET", f"/courses/{course['id']}", None),
                                   ("POST", "/sessions/", payload),
                                   ("PUT", f"/courses/{course['id']}", {"name": "Unauthorized"})):
            status, _ = self.request(method, path, body, other_token)
            self.assertEqual(status, 403)
        status, updated = self.request("PUT", f"/courses/{course['id']}", {"name": "Updated course"}, token)
        self.assertEqual(status, 200, updated)

    def test_tutor_cannot_assign_another_tutor(self):
        status, _ = self.request("POST", "/courses/", {**self.payload(), "instructor_id": self.users["other"][0]}, self.users["owner"][1])
        self.assertEqual(status, 403)

    def test_instructor_student_and_anonymous_cannot_create(self):
        for token in (self.users["owner"][1], self.users["student"][1], None):
            status, _ = self.request("POST", "/courses/", self.payload(), token)
            self.assertIn(status, (401, 403))

    def test_duplicate_and_blank_fields(self):
        token = self.users["admin"][1]
        payload = self.payload()
        status, data = self.request("POST", "/courses/", payload, token)
        self.assertEqual(status, 201, data)
        status, _ = self.request("POST", "/courses/", payload, token)
        self.assertEqual(status, 400)
        for field in ("code", "name", "semester"):
            status, _ = self.request("POST", "/courses/", {**self.payload(), field: "  "}, token)
            self.assertEqual(status, 422)

    def test_admin_can_assign_course_before_any_sessions(self):
        owner_id, owner_token = self.users["owner"]
        status, course = self.request("POST", "/courses/", {**self.payload(), "instructor_id": owner_id}, self.users["admin"][1])
        self.assertEqual(status, 201, course)
        status, data = self.request("GET", f"/courses/?instructor_id={owner_id}", token=self.users["admin"][1])
        self.assertEqual(status, 200, data)
        self.assertIn(course["id"], [item["id"] for item in data["items"]])
        status, data = self.request("GET", f"/courses/{course['id']}", token=owner_token)
        self.assertEqual(status, 200, data)
