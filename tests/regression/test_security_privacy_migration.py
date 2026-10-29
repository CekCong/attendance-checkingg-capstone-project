"""Stage 4 security invariants; ML responses are explicit doubles in these tests."""
import base64
import importlib.util
import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from sqlalchemy import text, create_engine
from sqlalchemy.exc import DBAPIError

from test_auth_migration import auth_app, subject
from app.models import (AuditLogModel, CheckinModel, CourseModel, DeviceModel,
                        EnrollmentModel, SessionModel, UserModel, RiskSignalModel)
from app.routers import checkins, users, audit, auth
from app.security import create_access_token, create_refresh_token
from app.device_challenge import create_device_challenge, _challenge_key
from app.retention import cleanup_expired_users
from app.migrate import install_audit_guards, check_runtime_database
from app.services.face_client import FaceServiceError

spec = importlib.util.spec_from_file_location('stage4_risk', Path(__file__).resolve().parents[2] / 'module3-face-recognition/app/services/risk.py')
risk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(risk)


def headers(user):
    return {'Authorization': f'Bearer {create_access_token({**subject(user), "auth_version": user.auth_version})}'}


def test_copied_tokens_revoked_on_logout_and_password_change(auth_app):
    http, db, user, _, _ = auth_app
    def login(password='valid-password'):
        response = http.post('/api/v1/auth/login', json={'email': user.email, 'password': password})
        assert response.status_code == 200
        return response.json()
    first, second = login(), login()
    assert http.post('/api/v1/auth/logout', json={'refresh_token': first['refresh_token']}).status_code == 200
    for pair in (first, second):
        assert http.get('/api/v1/auth/me', headers={'Authorization': 'Bearer ' + pair['access_token']}).status_code == 401
        assert http.post('/api/v1/auth/refresh', json={'refresh_token': pair['refresh_token']}).status_code == 401
    current = login()
    response = http.post('/api/v1/auth/password', headers={'Authorization': 'Bearer ' + current['access_token']}, json={
        'current_password': 'valid-password', 'new_password': 'new-valid-password'})
    assert response.status_code == 200
    assert http.post('/api/v1/auth/refresh', json={'refresh_token': current['refresh_token']}).status_code == 401
    assert http.get('/api/v1/auth/me', headers={'Authorization': 'Bearer ' + current['access_token']}).status_code == 401
    fresh = login('new-valid-password')
    assert http.get('/api/v1/auth/me', headers={'Authorization': 'Bearer ' + fresh['access_token']}).status_code == 200


@pytest.fixture
def attendance(auth_app, monkeypatch):
    http, db, user, redis, _ = auth_app
    http.app.include_router(users.router, prefix='/api/v1')
    http.app.include_router(audit.router, prefix='/api/v1')
    user.camera_consent = user.geolocation_consent = user.face_enrolled = True
    user.face_embedding_hash = 'a' * 64
    course = CourseModel(id=str(uuid.uuid4()), code=uuid.uuid4().hex[:12], name='Security', semester='2026', require_device_binding=True)
    now = datetime.utcnow()
    session = SessionModel(id=str(uuid.uuid4()), course=course, name='Security', status='active',
        scheduled_start=now, scheduled_end=now+timedelta(hours=1), checkin_opens_at=now-timedelta(minutes=5),
        checkin_closes_at=now+timedelta(hours=1), require_liveness_check=True, risk_threshold=0.99)
    db.add_all([course, session, EnrollmentModel(id=str(uuid.uuid4()), student_id=user.id, course_id=course.id, is_active=True)])
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    device = DeviceModel(id=str(uuid.uuid4()), user_id=user.id, device_fingerprint=uuid.uuid4().hex, public_key=public_key, is_active=True)
    db.add(device)
    db.commit()
    challenge = create_device_challenge(user.id, device.id, session.id)
    signature = key.sign(challenge.encode(), padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256())
    body = {'session_id': session.id, 'latitude': 1.3483456, 'longitude': 103.6831234,
        'location_accuracy_meters': 20, 'device_fingerprint': device.device_fingerprint,
        'device_challenge': challenge, 'device_signature': base64.b64encode(signature).decode(),
        'liveness_challenge_id': str(uuid.uuid4()), 'liveness_challenge_type': 'blink',
        'liveness_challenge_response': ['explicit-test-frame']*15}
    async def live(*args, **kwargs):
        return {'liveness_passed': True, 'liveness_score': 0.99}
    async def assess(**kwargs):
        device_risk = risk.device_risk(kwargs['device_signature'], kwargs['device_public_key'], kwargs['device_challenge'])
        return {'risk_score': 0.01, 'signal_breakdown': {'device': device_risk, 'ip_country': 0}}
    monkeypatch.setattr(checkins, 'check_liveness', live)
    monkeypatch.setattr(checkins, 'assess_risk', assess)
    yield http, db, user, session, device, body
    redis.delete(_challenge_key(challenge))


@pytest.mark.parametrize('consent', ['camera_consent', 'geolocation_consent'])
def test_checkin_requires_each_consent(attendance, consent):
    http, db, user, _, _, body = attendance
    setattr(user, consent, False)
    db.commit()
    result = http.post('/api/v1/checkins/', json=body, headers=headers(user))
    assert result.status_code == 403
    assert db.query(CheckinModel).count() == 0


@pytest.mark.parametrize('patch', [
    {'liveness_challenge_id': None}, {'liveness_challenge_type': 'passive'},
    {'liveness_challenge_response': None}, {'liveness_challenge_response': ['one-frame']},
    {'device_challenge': None, 'device_signature': None},
])
def test_required_proofs_cannot_be_omitted(attendance, patch):
    http, db, user, _, _, body = attendance
    result = http.post('/api/v1/checkins/', json={**body, **patch}, headers=headers(user))
    assert result.status_code == 400, result.text
    assert db.query(CheckinModel).count() == 0


@pytest.mark.parametrize('service', ['check_liveness', 'verify_face', 'assess_risk'])
def test_outage_never_approves_even_with_high_threshold_and_nonce_is_consumed(attendance, monkeypatch, service):
    http, db, user, session, _, body = attendance
    if service == 'verify_face':
        session.require_face_match = True
        db.commit()
    async def unavailable(*args, **kwargs):
        raise FaceServiceError(503, 'Unavailable')
    monkeypatch.setattr(checkins, service, unavailable)
    assert http.post('/api/v1/checkins/', json=body, headers=headers(user)).status_code == 503
    assert db.query(CheckinModel).count() == 0
    assert http.post('/api/v1/checkins/', json=body, headers=headers(user)).status_code == 409


@pytest.mark.parametrize('result', [
    {'liveness_passed': 'false', 'liveness_score': 1},
    {'liveness_passed': True, 'liveness_score': float('nan')},
    {'liveness_passed': True, 'liveness_score': 2},
])
def test_malformed_verification_response_fails_closed(attendance, monkeypatch, result):
    http, db, user, _, _, body = attendance
    async def malformed(*args, **kwargs):
        return result
    monkeypatch.setattr(checkins, 'check_liveness', malformed)
    assert http.post('/api/v1/checkins/', json=body, headers=headers(user)).status_code == 503
    assert db.query(CheckinModel).count() == 0


@pytest.mark.parametrize('mode', ['invalid', 'expired', 'wrong_session'])
def test_device_proof_is_bound_and_verified(attendance, auth_app, mode):
    http, db, user, _, device, body = attendance
    if mode == 'invalid':
        body['device_signature'] = base64.b64encode(b'bad-signature').decode()
    elif mode == 'expired':
        auth_app[3].delete(_challenge_key(body['device_challenge']))
    else:
        body['device_challenge'] = create_device_challenge(user.id, device.id, str(uuid.uuid4()))
    response = http.post('/api/v1/checkins/', json=body, headers=headers(user))
    assert response.status_code == (403 if mode == 'invalid' else 409), response.text
    assert db.query(CheckinModel).count() == 0


def test_location_is_coarse_and_absent_from_audit(attendance):
    http, db, user, _, _, body = attendance
    response = http.post('/api/v1/checkins/', json=body, headers=headers(user))
    assert response.status_code == 201, response.text
    assert response.json()['status'] == 'approved'
    record = db.query(CheckinModel).one()
    assert record.latitude == 1.348 and record.longitude == 103.683
    assert http.post('/api/v1/checkins/', json=body, headers=headers(user)).status_code == 400
    history = http.get('/api/v1/checkins/my-checkins', headers=headers(user))
    assert history.status_code == 200 and history.json()[0]['id'] == record.id
    for event in db.query(AuditLogModel).all():
        assert 'latitude' not in (event.details or '')
        assert '1.3483456' not in (event.details or '')


def test_impossible_travel_is_flagged_even_with_permissive_threshold(attendance):
    http, db, user, session, _, body = attendance
    previous = CheckinModel(id=str(uuid.uuid4()), session_id=session.id, student_id=user.id,
        status='approved', checked_in_at=datetime.utcnow()-timedelta(seconds=10), latitude=1.4, longitude=104.0)
    # Prior observation belongs to a different session.
    other = SessionModel(id=str(uuid.uuid4()), course_id=session.course_id, name='Previous', status='closed',
        scheduled_start=session.scheduled_start, scheduled_end=session.scheduled_end,
        checkin_opens_at=session.checkin_opens_at, checkin_closes_at=session.checkin_closes_at)
    previous.session_id = other.id
    db.add_all([other, previous])
    db.commit()
    response = http.post('/api/v1/checkins/', json=body, headers=headers(user))
    assert response.status_code == 201, response.text
    assert response.json()['status'] == 'flagged'
    assert any(item['type'] == 'impossible_travel' for item in response.json()['risk_factors'])


def test_unknown_device_is_flagged_when_binding_is_optional(attendance):
    http, db, user, session, _, body = attendance
    session.course.require_device_binding = False
    db.commit()
    body.update(device_fingerprint='unregistered', device_challenge=None, device_signature=None)
    response = http.post('/api/v1/checkins/', json=body, headers=headers(user))
    assert response.status_code == 201 and response.json()['status'] == 'flagged'


def test_unknown_country_is_reviewed_not_rejected(attendance, monkeypatch):
    http, _, user, _, _, body = attendance
    async def unknown(**kwargs):
        return {'risk_score': 0.1, 'signal_breakdown': {'device': 0, 'ip_country': 0.5, 'ip_country_unknown': 1}}
    monkeypatch.setattr(checkins, 'assess_risk', unknown)
    response = http.post('/api/v1/checkins/', json=body, headers=headers(user))
    assert response.status_code == 201 and response.json()['status'] == 'flagged'


def test_country_lookup_failure_is_not_foreign_and_can_recover(monkeypatch):
    monkeypatch.setattr(risk, 'IPINFO_TOKEN', 'test-token')
    calls = []
    def lookup(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise risk.httpx.ConnectError('test outage')
        return risk.httpx.Response(200, json={'country':'SG'}, request=risk.httpx.Request('GET', 'https://example.com'))
    monkeypatch.setattr(risk.httpx, 'get', lookup)
    assert risk.ip_country_risk('8.8.8.8') == 0.5
    assert risk.ip_country_risk('8.8.8.8') == 0
    assert len(calls) == 2
    monkeypatch.setattr(risk, 'get_ip_info', lambda _: {'country': 'US'})
    assert risk.ip_country_risk('8.8.8.8') == 1
    assert risk.ip_country_risk('127.0.0.1') == 0


def test_deletion_revokes_access_erases_due_data_and_keeps_audit(attendance):
    http, db, user, session, device, _ = attendance
    original_email = user.email
    access = headers(user)
    refresh = create_refresh_token(subject(user))
    record = CheckinModel(id=str(uuid.uuid4()), session_id=session.id, student_id=user.id, device_id=device.id, status='approved')
    db.add(record)
    db.flush()
    db.add(RiskSignalModel(id=str(uuid.uuid4()), checkin_id=record.id, signal_type='device_unknown', severity='low'))
    db.commit()
    with db.get_bind().begin() as connection:
        install_audit_guards(connection)
    bad = http.request('DELETE', '/api/v1/users/me', headers=access, json={'current_password': 'wrong'})
    assert bad.status_code == 400
    response = http.request('DELETE', '/api/v1/users/me', headers=access, json={'current_password': 'valid-password'})
    assert response.status_code == 202, response.text
    db.refresh(user)
    assert 29 <= (user.scheduled_deletion_at - datetime.utcnow()).days <= 30
    assert http.get('/api/v1/auth/me', headers=access).status_code == 403
    assert http.post('/api/v1/auth/refresh', json={'refresh_token': refresh}).status_code == 403
    assert cleanup_expired_users(db) == 0
    event = db.query(AuditLogModel).one()
    original_event = (event.id, event.details, event.user_id)
    user.scheduled_deletion_at = datetime.utcnow()-timedelta(seconds=1)
    db.commit()
    assert cleanup_expired_users(db) == 1
    assert cleanup_expired_users(db) == 0
    db.refresh(user)
    assert user.email != original_email and user.hashed_password == '!deleted'
    assert user.face_embedding_hash is None and not user.is_active
    assert all(db.query(model).count() == 0 for model in [DeviceModel, CheckinModel, RiskSignalModel, EnrollmentModel])
    db.refresh(event)
    assert (event.id, event.details, event.user_id) == original_event
    for statement in ['UPDATE audit_logs SET details = NULL', 'DELETE FROM audit_logs']:
        with pytest.raises(DBAPIError):
            db.execute(text(statement))
        db.rollback()


def test_instructor_audit_scope_excludes_unrelated_events(attendance):
    http, db, user, session, _, _ = attendance
    instructor = UserModel(id=str(uuid.uuid4()), email='teacher@example.com', full_name='Teacher', role='instructor', hashed_password='unused')
    db.add(instructor)
    session.instructor_id = instructor.id
    own = AuditLogModel(id=str(uuid.uuid4()), user_id=user.id, action='session_updated', resource_type='session', resource_id=session.id)
    unrelated = AuditLogModel(id=str(uuid.uuid4()), user_id=user.id, action='login_success', resource_type='user', resource_id=user.id)
    db.add_all([own, unrelated]); db.commit()
    response = http.get('/api/v1/audit/', headers=headers(instructor))
    assert response.status_code == 200
    assert [item['id'] for item in response.json()['items']] == [own.id]
    response = http.get('/api/v1/audit/?resource_type=user', headers=headers(instructor))
    assert response.json()['total'] == 0


def test_postgres_runtime_cannot_mutate_or_disable_audit():
    url = os.getenv('TEST_RUNTIME_DATABASE_URL')
    if not url:
        pytest.skip('Set TEST_RUNTIME_DATABASE_URL for PostgreSQL permission verification')
    engine = create_engine(url)
    try:
        check_runtime_database(engine)
        for statement in [
            "UPDATE audit_logs SET details = 'tampered' WHERE false", 'DELETE FROM audit_logs WHERE false',
            'TRUNCATE audit_logs', 'ALTER TABLE audit_logs DISABLE TRIGGER audit_no_mutation',
            'DROP TABLE audit_logs',
        ]:
            with engine.connect() as connection:
                transaction = connection.begin()
                try:
                    with pytest.raises(DBAPIError):
                        connection.execute(text(statement))
                finally:
                    transaction.rollback()
    finally:
        engine.dispose()

@pytest.mark.parametrize('mismatch', ['user', 'session', 'action', 'expired', 'race'])
def test_liveness_nonce_binding_expiry_and_atomic_use(auth_app, monkeypatch, mismatch):
    from concurrent.futures import ThreadPoolExecutor
    challenge_spec = importlib.util.spec_from_file_location('stage4_challenge', Path(__file__).resolve().parents[2] / 'module3-face-recognition/app/services/liveness_challenge.py')
    challenge = importlib.util.module_from_spec(challenge_spec)
    challenge_spec.loader.exec_module(challenge)
    redis = auth_app[3]
    monkeypatch.setattr(challenge, 'redis_client', lambda: redis)
    user_id, session_id = str(uuid.uuid4()), str(uuid.uuid4())
    nonce, action = challenge.create_liveness_challenge(user_id, session_id)
    key = f'liveness:challenge:{nonce}'
    assert 0 < redis.ttl(key) <= 60
    try:
        if mismatch == 'race':
            with ThreadPoolExecutor(max_workers=2) as executor:
                outcomes = list(executor.map(lambda _: challenge.consume_liveness_challenge(nonce, user_id, session_id, action)[0], range(2)))
            assert sorted(outcomes) == [False, True]
        else:
            if mismatch == 'expired':
                redis.expire(key, 0)
            valid, _ = challenge.consume_liveness_challenge(
                nonce, 'different' if mismatch == 'user' else user_id,
                'different' if mismatch == 'session' else session_id,
                'passive' if mismatch == 'action' else action)
            assert not valid
        assert not challenge.consume_liveness_challenge(nonce, user_id, session_id, action)[0]
    finally:
        redis.delete(key)
