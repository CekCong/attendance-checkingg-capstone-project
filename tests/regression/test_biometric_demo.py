"""Explicit local biometric simulation; other attendance controls remain enforced."""
import pytest

from test_auth_migration import auth_app
from test_security_privacy_migration import attendance, headers
from app.models import CheckinModel, EnrollmentModel
from app.routers import checkins
from app.runtime_security import biometric_demo_enabled, validate_runtime_security


@pytest.mark.parametrize('mode', ['development', 'test'])
def test_demo_skips_biometrics_and_marks_records_without_fake_enrollment(attendance, monkeypatch, mode):
    http, db, student, lesson, _, body = attendance
    monkeypatch.setenv('SAIV_ENV', mode)
    monkeypatch.setenv('BIOMETRIC_DEMO_MODE', 'true')
    student.face_enrolled = False
    student.face_embedding_hash = None
    lesson.require_face_match = True
    db.commit()
    async def never_called(*args, **kwargs):
        raise AssertionError('Biometric model must not be invoked in demo mode')
    async def issue(*args):
        return {'challenge_id': 'demo-ticket', 'challenge_type': 'blink', 'expires_in': 60}
    monkeypatch.setattr(checkins, 'create_liveness_challenge', issue)
    monkeypatch.setattr(checkins, 'check_liveness', never_called)
    monkeypatch.setattr(checkins, 'verify_face', never_called)
    challenge = http.post('/api/v1/checkins/liveness-challenge', headers=headers(student), json={'session_id': lesson.id})
    assert challenge.status_code == 200, challenge.text
    response = http.post('/api/v1/checkins/', headers=headers(student), json=body)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data['status'] == 'approved'
    assert data['liveness_passed'] and data['face_match_passed'] and data['biometric_demo_mode']
    assert any(factor['type'] == 'biometric_demo_bypass' for factor in data['risk_factors'])
    db.refresh(student)
    assert not student.face_enrolled and student.face_embedding_hash is None
    # Historical labels reflect the saved attempt even after demo mode is disabled.
    monkeypatch.setenv('BIOMETRIC_DEMO_MODE', 'false')
    history = http.get('/api/v1/checkins/my-checkins', headers=headers(student)).json()
    assert history[0]['biometric_demo_mode'] is True


@pytest.mark.parametrize('mode', ['development', 'production'])
def test_bypass_is_opt_in_and_client_cannot_enable_it(attendance, monkeypatch, mode):
    http, _, student, _, _, body = attendance
    monkeypatch.setenv('SAIV_ENV', mode)
    if mode == 'production':
        monkeypatch.setenv('BIOMETRIC_DEMO_MODE', 'true')
    else:
        monkeypatch.delenv('BIOMETRIC_DEMO_MODE', raising=False)
    async def failed(*args, **kwargs):
        return {'liveness_passed': False, 'liveness_score': 0}
    monkeypatch.setattr(checkins, 'check_liveness', failed)
    assert not biometric_demo_enabled()
    response = http.post('/api/v1/checkins/', headers=headers(student), json={**body, 'biometric_demo_mode': True})
    assert response.status_code == 201, response.text
    assert response.json()['status'] == 'rejected'
    assert response.json()['biometric_demo_mode'] is False


def test_production_startup_refuses_biometric_demo(monkeypatch):
    monkeypatch.setenv('SAIV_ENV', 'production')
    monkeypatch.setenv('BIOMETRIC_DEMO_MODE', 'true')
    with pytest.raises(RuntimeError, match='prohibited in production'):
        validate_runtime_security()


@pytest.mark.parametrize('restriction,expected', [('device', 400), ('qr', 400), ('closed', 400), ('enrollment', 403), ('outside_sg', 403)])
def test_demo_keeps_other_attendance_rules(attendance, monkeypatch, restriction, expected):
    http, db, student, lesson, _, body = attendance
    monkeypatch.setenv('SAIV_ENV', 'development')
    monkeypatch.setenv('BIOMETRIC_DEMO_MODE', 'true')
    if restriction == 'device':
        body = {**body, 'device_signature': None, 'device_challenge': None}
    elif restriction == 'qr':
        lesson.qr_code_secret = 'EXPECTED'
    elif restriction == 'closed':
        lesson.status = 'closed'
    elif restriction == 'enrollment':
        db.query(EnrollmentModel).one().is_active = False
    else:
        body = {**body, 'latitude': 0, 'longitude': 0}
    db.commit()
    response = http.post('/api/v1/checkins/', headers=headers(student), json=body)
    assert response.status_code == expected, response.text
    assert db.query(CheckinModel).count() == 0
