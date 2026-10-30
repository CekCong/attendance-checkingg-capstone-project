"""Live web auth checks: RUN_WEB_AUTH_TESTS=1 python3 -m unittest discover -s tests/regression -p test_web_registration.py -v"""
import json
import os
import unittest
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen


@unittest.skipUnless(os.getenv("RUN_WEB_AUTH_TESTS") == "1", "Requires running web portals and backend")
class WebRegistrationTests(unittest.TestCase):
    portals = ((3000, "student"), (8501, "instructor"))

    def post(self, port, path, body):
        request = Request(
            f"http://localhost:{port}/api/auth/{path}",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            response = urlopen(request, timeout=30)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response), response.headers

    def test_registration_login_and_duplicate_email(self):
        for port, role in self.portals:
            with self.subTest(role=role):
                body = {
                    "email": f"signup-test-{uuid.uuid4().hex}@example.com",
                    "full_name": "  Signup Test  ",
                    "password": "Local-test-password-123",
                    "role": "admin",  # Must not override the portal's role.
                }
                status, account, _ = self.post(port, "register", body)
                self.assertEqual(status, 201, account)
                self.assertEqual(account["role"], role)
                self.assertEqual(account["full_name"], "Signup Test")
                self.assertNotIn("hashed_password", account)
                status, duplicate, _ = self.post(port, "register", body)
                self.assertEqual(status, 400)
                self.assertEqual(duplicate["detail"], "Email already registered")
                status, session, headers = self.post(port, "login", body)
                self.assertEqual(status, 200, session)
                self.assertEqual(session["user"]["id"], account["id"])
                self.assertEqual(session["user"]["role"], role)
                self.assertTrue(session["access_token"])
                self.assertIn("HttpOnly", headers.get("Set-Cookie", ""))
                status, _, _ = self.post(port, "login", {**body, "password": "wrong-password"})
                self.assertEqual(status, 401)
                if role == "student":
                    status, _, _ = self.post(8501, "login", body)
                    self.assertEqual(status, 403)

    def test_invalid_registration_is_rejected_on_both_portals(self):
        valid = {"email": "invalid-signup-test@example.com", "full_name": "Signup Test", "password": "Password123"}
        for port, role in self.portals:
            for body in (None, {}, {**valid, "full_name": "   "},
                         {**valid, "password": "short"}, {**valid, "password": "x" * 73},
                         {**valid, "email": "not-an-email"}):
                with self.subTest(role=role, body=body):
                    status, data, _ = self.post(port, "register", body)
                    self.assertIn(status, (400, 422), data)
                    self.assertIsInstance(data["detail"], str)
