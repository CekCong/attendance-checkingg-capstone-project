"""JWT migration and session QR authorization/lifetime; biometric results use explicit doubles."""
import json
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from test_auth_migration import auth_app, subject
from test_security_privacy_migration import attendance, headers
from app import security
from app.models import AuditLogModel, CheckinModel, UserModel
from app.routers import sessions


@pytest.mark.parametrize('change', ['none', 'wrong_algorithm', 'missing_exp', 'missing_sub', 'future_iat', 'expired', 'refresh'])
def test_jwt_rejects_invalid_claims_and_algorithms(auth_app, change):
    http, _, user, _, _ = auth_app
    now = int(datetime.now(timezone.utc).timestamp())
    payload = {'sub': user.id, 'iat': now, 'exp': now+60, 'type': 'access', 'av': 0}
    algorithm = 'HS256'
    if change == 'none': algorithm = 'none'
    elif change == 'wrong_algorithm': algorithm = 'HS384'
    elif change == 'missing_exp': del payload['exp']
    elif change == 'missing_sub': del payload['sub']
    elif change == 'future_iat': payload['iat'] = now+120
    elif change == 'expired': payload['exp'] = now-1
    elif change == 'refresh': payload['type'] = 'refresh'
    token = jwt.encode(payload, '' if algorithm == 'none' else security.SECRET_KEY, algorithm=algorithm)
    assert http.get('/api/v1/auth/me', headers={'Authorization': 'Bearer '+token}).status_code == 401


def test_hs256_tokens_from_previous_library_remain_compatible(auth_app):
    # Independent standard-library signing replicates the old HS256 wire format.
    import base64, hashlib, hmac
    http, _, user, _, _ = auth_app
    def encode(value): return base64.urlsafe_b64encode(json.dumps(value, separators=(',', ':')).encode()).rstrip(b'=')
    now = int(datetime.now(timezone.utc).timestamp())
    parts = [encode({'alg':'HS256','typ':'JWT'}), encode({'sub':user.id, 'iat':now, 'exp':now+60, 'type':'access','av':0})]
    signing_input = b'.'.join(parts)
    signature = base64.urlsafe_b64encode(hmac.new(security.SECRET_KEY.encode(), signing_input, hashlib.sha256).digest()).rstrip(b'=')
    assert http.get('/api/v1/auth/me', headers={'Authorization':'Bearer '+(signing_input+b'.'+signature).decode()}).status_code == 200


@pytest.fixture
def qr_session(attendance):
    http, db, student, session, device, body = attendance
    http.app.include_router(sessions.router, prefix='/api/v1')
    teacher = UserModel(id=str(uuid.uuid4()), email='qr-teacher@example.com', full_name='QR Teacher', role='instructor', hashed_password='unused', is_active=True)
    outsider = UserModel(id=str(uuid.uuid4()), email='other-teacher@example.com', full_name='Other Teacher', role='instructor', hashed_password='unused', is_active=True)
    session.instructor_id = teacher.id
    db.add_all([teacher, outsider]); db.commit()
    return http, db, student, session, body, teacher, outsider


def test_qr_issue_is_scoped_private_and_audited(qr_session):
    http, db, student, session, _, teacher, outsider = qr_session
    path = f'/api/v1/sessions/{session.id}/qr-code'
    for user in (student, outsider):
        assert http.post(path, headers=headers(user)).status_code == 403
    response = http.post(path, headers=headers(teacher))
    assert response.status_code == 200
    issued = response.json()
    assert json.loads(issued['payload']) == {'v':1,'session_id':session.id,'code':issued['code']}
    expiry = datetime.fromisoformat(issued['expires_at'])
    assert 0 < (expiry-datetime.now(timezone.utc)).total_seconds() <= 90
    assert expiry.replace(tzinfo=None) <= session.checkin_closes_at
    event = db.query(AuditLogModel).filter_by(action='session_updated', details='qr_code_rotated').one()
    assert issued['code'] not in str(event.details)
    for path in (f'/api/v1/sessions/{session.id}', '/api/v1/sessions/my-sessions'):
        visible = http.get(path, headers=headers(student))
        assert visible.status_code == 200
        assert issued['code'] not in visible.text
        assert 'qr_code_secret' not in visible.text


@pytest.mark.parametrize('bad_code', [None, 'wrong-code', '\u2603', 'rotated', 'expired'])
def test_missing_invalid_rotated_or_expired_qr_cannot_create_attendance(qr_session, bad_code):
    http, db, student, session, body, teacher, _ = qr_session
    path = f'/api/v1/sessions/{session.id}/qr-code'
    first = http.post(path, headers=headers(teacher)).json()
    if bad_code == 'rotated':
        second = http.post(path, headers=headers(teacher)).json()
        assert first['code'] != second['code']
        code = first['code']
    elif bad_code == 'expired':
        session.qr_code_expires_at = datetime.utcnow()-timedelta(seconds=1); db.commit()
        code = first['code']
    else: code = bad_code
    response = http.post('/api/v1/checkins/', headers=headers(student), json={**body, 'qr_code':code})
    assert response.status_code == 400, response.text
    assert db.query(CheckinModel).count() == 0


def test_current_qr_still_requires_and_accepts_complete_verification(qr_session):
    http, db, student, session, body, teacher, _ = qr_session
    issued = http.post(f'/api/v1/sessions/{session.id}/qr-code', headers=headers(teacher)).json()
    response = http.post('/api/v1/checkins/', headers=headers(student), json={**body, 'qr_code':issued['code']})
    assert response.status_code == 201, response.text
    assert db.query(CheckinModel).count() == 1


@pytest.mark.parametrize('mode', ['closed', 'future', 'ended'])
def test_qr_cannot_be_issued_outside_open_window(qr_session, mode):
    http, db, _, session, _, teacher, _ = qr_session
    if mode == 'closed': session.status = 'closed'
    elif mode == 'future': session.checkin_opens_at = datetime.utcnow()+timedelta(minutes=5)
    else: session.checkin_closes_at = datetime.utcnow()-timedelta(seconds=1)
    db.commit()
    assert http.post(f'/api/v1/sessions/{session.id}/qr-code', headers=headers(teacher)).status_code == 400
