"""Rejected attendance retries use fresh proofs and retain a single attendance row."""
import base64
import json
import uuid
from datetime import datetime, timedelta

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from test_auth_migration import auth_app
from test_security_privacy_migration import attendance, headers
from app.checkin_feedback import liveness_failure_code, rejection_reasons
from app.device_challenge import create_device_challenge
from app.models import AuditLogModel, CheckinModel, EnrollmentModel
from app.routers import checkins
from app.services.face_client import FaceServiceError


@pytest.fixture
def retry_app(attendance, monkeypatch):
    http, db, student, lesson, device, template = attendance
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    device.public_key = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    db.commit()
    result = {"liveness_passed": False, "liveness_score": 0,
              "details": {"action_detected": False}}
    issued, used = set(), set()

    async def issue(*args):
        challenge_id = str(uuid.uuid4())
        issued.add(challenge_id)
        return {"challenge_id": challenge_id, "challenge_type": "smile", "expires_in": 60}

    async def verify(*args, **kwargs):
        challenge_id = kwargs["challenge_id"]
        if challenge_id not in issued or challenge_id in used:
            raise FaceServiceError(409, "Liveness challenge already used or invalid")
        used.add(challenge_id)
        return result.copy()

    monkeypatch.setattr(checkins, "create_liveness_challenge", issue)
    monkeypatch.setattr(checkins, "check_liveness", verify)

    def fresh_body():
        response = http.post('/api/v1/checkins/liveness-challenge', headers=headers(student),
                             json={"session_id": lesson.id})
        assert response.status_code == 200, response.text
        challenge = create_device_challenge(student.id, device.id, lesson.id)
        signature = key.sign(challenge.encode(), padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256())
        return {**template, "device_challenge": challenge,
                "device_signature": base64.b64encode(signature).decode(),
                "liveness_challenge_id": response.json()["challenge_id"], "liveness_challenge_type": "smile"}

    def submit(body=None):
        return http.post('/api/v1/checkins/', headers=headers(student), json=body or fresh_body())

    return http, db, student, lesson, result, fresh_body, submit


def test_rejected_retry_updates_attendance_and_retains_audit(retry_app):
    http, db, student, _, result, _, submit = retry_app
    rejected = submit()
    assert rejected.status_code == 201, rejected.text
    initial = rejected.json()
    assert initial['status'] == 'rejected'
    assert 'smile sequence' in initial['rejection_reasons'][0]
    history = http.get('/api/v1/checkins/my-checkins', headers=headers(student)).json()
    detail = http.get('/api/v1/checkins/' + initial['id'], headers=headers(student)).json()
    assert history[0]['rejection_reasons'] == detail['rejection_reasons'] == initial['rejection_reasons']
    result.update(liveness_passed=True, liveness_score=0.99)
    retried = submit()
    assert retried.status_code == 201, retried.text
    assert retried.json()['id'] == initial['id']
    assert retried.json()['status'] == 'approved'
    assert retried.json()['rejection_reasons'] == []
    assert db.query(CheckinModel).count() == 1
    assert db.query(AuditLogModel).filter_by(action='checkin_rejected').count() == 1
    snapshots = [json.loads(row.details) for row in db.query(AuditLogModel).all()
                 if row.details and row.details.startswith('{"retry_previous_attempt"')]
    assert len(snapshots) == 1
    assert snapshots[0]['status'] == 'rejected'
    assert any(f['type'] == 'liveness_action_failed' for f in snapshots[0]['risk_factors'])
    history = http.get('/api/v1/checkins/my-checkins', headers=headers(student)).json()
    assert len(history) == 1 and history[0]['status'] == 'approved'


def test_repeated_rejections_keep_one_row_and_new_reasons(retry_app):
    _, db, _, _, result, _, submit = retry_app
    first = submit().json()
    result['details'] = {'error': 'Every frame must contain exactly one face.'}
    second = submit()
    assert second.status_code == 201, second.text
    assert second.json()['id'] == first['id']
    assert second.json()['status'] == 'rejected'
    assert 'face could not be read clearly' in second.json()['rejection_reasons'][0]
    assert db.query(CheckinModel).count() == 1


def test_manual_rejection_notes_are_shown_and_retry_clears_old_review(retry_app):
    http, db, student, _, result, _, submit = retry_app
    submit()
    record = db.query(CheckinModel).one()
    record.reviewed_at = datetime.utcnow()
    record.reviewed_by_id = student.id  # Fixture identity; simulates an existing reviewed record.
    record.review_notes = 'Please repeat verification in the classroom.'
    record.appeal_reason = 'Previous appeal'
    record.appealed_at = datetime.utcnow()
    db.commit()
    history = http.get('/api/v1/checkins/my-checkins', headers=headers(student)).json()
    assert 'Please repeat verification in the classroom.' in history[0]['rejection_reasons'][0]
    result.update(liveness_passed=True, liveness_score=0.99)
    response = submit()
    assert response.status_code == 201, response.text
    db.refresh(record)
    assert record.status == 'approved'
    assert record.reviewed_at is None and record.reviewed_by_id is None and record.review_notes is None
    assert record.appeal_reason is None and record.appealed_at is None
    assert any('Please repeat verification in the classroom.' in (row.details or '') for row in db.query(AuditLogModel).all())


@pytest.mark.parametrize('state', ['approved', 'flagged', 'pending', 'appealed'])
def test_non_rejected_attendance_cannot_retry(retry_app, state):
    http, db, student, lesson, _, fresh, submit = retry_app
    body = fresh()
    submit(body)
    record = db.query(CheckinModel).one()
    record.status = state
    db.commit()
    ticket = http.post('/api/v1/checkins/liveness-challenge', headers=headers(student), json={'session_id': lesson.id})
    assert ticket.status_code == 400
    assert submit(body).status_code == 400
    assert db.query(CheckinModel).one().status == state


@pytest.mark.parametrize('restriction,expected', [('closed', 400), ('expired', 400), ('unenrolled', 403), ('qr', 400)])
def test_retry_preserves_session_and_enrollment_rules(retry_app, restriction, expected):
    http, db, student, lesson, _, fresh, submit = retry_app
    original = submit().json()
    body = fresh()
    if restriction == 'closed':
        lesson.status = 'closed'
    elif restriction == 'expired':
        lesson.checkin_closes_at = datetime.utcnow() - timedelta(seconds=1)
    elif restriction == 'unenrolled':
        db.query(EnrollmentModel).one().is_active = False
    else:
        lesson.qr_code_secret = 'new-code'
    db.commit()
    assert submit(body).status_code == expected
    if restriction != 'qr':
        assert http.post('/api/v1/checkins/liveness-challenge', headers=headers(student), json={'session_id': lesson.id}).status_code == expected
    record = db.query(CheckinModel).one()
    assert record.id == original['id'] and record.status == 'rejected'


def test_retry_requires_fresh_device_and_liveness_proofs(retry_app):
    _, db, _, _, result, fresh, submit = retry_app
    body = fresh()
    assert submit(body).status_code == 201
    result.update(liveness_passed=True, liveness_score=0.99)
    assert submit(body).status_code == 409  # consumed device nonce
    new_body = fresh()
    new_body['liveness_challenge_id'] = body['liveness_challenge_id']
    assert submit(new_body).status_code == 409
    assert db.query(CheckinModel).one().status == 'rejected'
    assert submit().json()['status'] == 'approved'


def test_service_failure_does_not_erase_previous_rejection(retry_app, monkeypatch):
    _, db, _, _, _, fresh, submit = retry_app
    original = submit().json()
    body = fresh()
    async def unavailable(*args, **kwargs):
        raise FaceServiceError(503, 'Unavailable')
    monkeypatch.setattr(checkins, 'check_liveness', unavailable)
    assert submit(body).status_code == 503
    record = db.query(CheckinModel).one()
    assert record.status == 'rejected' and record.id == original['id']
    assert record.checked_in_at.isoformat() == original['checked_in_at']


def test_retry_does_not_overwrite_a_concurrent_completed_attempt(retry_app, monkeypatch):
    _, db, _, _, _, fresh, submit = retry_app
    submit()
    body = fresh()
    async def completed_elsewhere(*args, **kwargs):
        record = db.query(CheckinModel).one()
        record.status = 'approved'
        db.commit()
        return {'liveness_passed': False, 'liveness_score': 0}
    monkeypatch.setattr(checkins, 'check_liveness', completed_elsewhere)
    response = submit(body)
    assert response.status_code == 409, response.text
    assert db.query(CheckinModel).one().status == 'approved'


@pytest.mark.parametrize('error,code', [
    ('Identical frames cannot satisfy an active challenge.', 'liveness_no_motion'),
    ('Every frame must contain exactly one face.', 'liveness_face_unclear'),
    ('Faces do not match across all frames.', 'liveness_face_inconsistent'),
    ('Not every frame matches the enrolled face.', 'liveness_reference_mismatch'),
])
def test_safe_liveness_reasons(error, code):
    assert liveness_failure_code({'error': error}) == code
    assert liveness_failure_code({'error': 'Unexpected internal diagnostic'}) is None
    reasons = rejection_reasons('rejected', [{'type': 'liveness_failed'}, {'type': code}])
    assert len(reasons) == 1


def test_legacy_and_multiple_rejection_reasons_are_honest():
    assert 'more detailed reason was not recorded' in rejection_reasons('rejected', '[{"type":"liveness_failed"}]')[0]
    factors = [{'type': 'critical_geofence_exceeded'}, {'type': 'face_match_failed'}, {'type': 'ip_country_risk', 'weight': 1}]
    assert len(rejection_reasons('rejected', factors)) == 3
    assert rejection_reasons('approved', factors) == []
    assert 'instructor rejected' in rejection_reasons('rejected', factors, reviewed_at=datetime.utcnow())[0]
