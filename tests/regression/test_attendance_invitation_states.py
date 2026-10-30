"""Run inside the backend: python - < tests/regression/test_attendance_invitation_states.py."""
import unittest
from unittest.mock import patch, Mock
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

try:
    from fastapi import HTTPException, Response
    from app.routers.attendance_codes import invitation, open_attendance, OpenAttendance
except ModuleNotFoundError as error:
    if error.name in {"fastapi", "app"}:
        raise unittest.SkipTest("Run these unit tests inside the backend container") from error
    raise


class InvitationStateTests(unittest.TestCase):
    @patch.dict("os.environ", {"ATTENDANCE_DEMO_MODE": "false"})
    def test_unavailable_codes_explain_why_without_exposing_a_secret(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        base = dict(id="test-lesson", status="scheduled", qr_code_secret=None, qr_code_expires_at=None,
                    scheduled_start=now + timedelta(minutes=5), scheduled_end=now + timedelta(hours=1),
                    checkin_opens_at=now, checkin_closes_at=now + timedelta(minutes=15))
        cases = [
            ("not_open", {}),
            ("upcoming", {"scheduled_start": now + timedelta(hours=1)}),
            ("ended", {"scheduled_end": now - timedelta(minutes=1)}),
            ("closed", {"status": "closed"}),
            ("cancelled", {"status": "cancelled"}),
            ("expired", {"status": "active", "qr_code_secret": "OLDCODE1", "qr_code_expires_at": now - timedelta(seconds=1)}),
        ]
        for reason, patch in cases:
            with self.subTest(reason=reason):
                result = invitation(SimpleNamespace(**{**base, **patch}), "https://students.example.edu")
                self.assertEqual(result, {"open": False, "session_id": "test-lesson", "reason": reason, "demo_mode": False})

    @patch.dict("os.environ", {"ATTENDANCE_DEMO_MODE": "false"})
    def test_normal_mode_still_rejects_outside_schedule_and_closed_lessons(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for state, start, end in [
            ("scheduled", now + timedelta(days=1), now + timedelta(days=1, hours=1)),
            ("active", now - timedelta(days=1), now - timedelta(hours=1)),
            ("closed", now - timedelta(minutes=1), now + timedelta(hours=1)),
        ]:
            with self.subTest(state=state):
                db = Mock()
                db.get.return_value = SimpleNamespace(instructor_id="tutor", status=state, scheduled_start=start, scheduled_end=end)
                with self.assertRaises(HTTPException) as raised:
                    open_attendance("lesson", OpenAttendance(student_url="https://students.example.edu"),
                                    None, Response(), {"role": "instructor", "id": "tutor"}, db)
                self.assertEqual(raised.exception.status_code, 400)
                db.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
