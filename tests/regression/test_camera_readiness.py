"""Camera preparation is authenticated, consented, bounded and non-mutating."""
import pytest

from test_auth_migration import auth_app
from test_security_privacy_migration import headers
from app.models import CheckinModel, AuditLogModel
from app.routers import users
from app.services.face_client import FaceServiceError


@pytest.fixture
def camera_app(auth_app, monkeypatch):
    http, db, user, _, _ = auth_app
    http.app.include_router(users.router, prefix='/api/v1')
    user.camera_consent = True
    db.commit()
    calls = []
    result = {'ready': True, 'message': 'Ready', 'warnings': []}

    async def check(image):
        calls.append(image)
        return result.copy()

    monkeypatch.setattr(users, 'check_camera_readiness', check)
    return http, db, user, calls, result


def test_readiness_does_not_enroll_or_mark_attendance(camera_app):
    http, db, user, calls, _ = camera_app
    before = (user.face_enrolled, user.face_embedding_hash)
    response = http.post('/api/v1/users/me/face/readiness', headers=headers(user), json={'image': 'frame'})
    assert response.status_code == 200
    assert response.json()['ready'] is True
    assert calls == ['frame']
    db.refresh(user)
    assert (user.face_enrolled, user.face_embedding_hash) == before
    assert db.query(CheckinModel).count() == db.query(AuditLogModel).count() == 0


def test_readiness_requires_auth_and_camera_consent(camera_app):
    http, db, user, calls, _ = camera_app
    endpoint = '/api/v1/users/me/face/readiness'
    assert http.post(endpoint, json={'image': 'frame'}).status_code in (401, 403)
    user.camera_consent = False
    db.commit()
    assert http.post(endpoint, headers=headers(user), json={'image': 'frame'}).status_code == 400
    assert calls == []


def test_readiness_rate_and_payload_limits(camera_app):
    http, _, user, calls, _ = camera_app
    endpoint = '/api/v1/users/me/face/readiness'
    for image in ('', 'a' * 2_000_001):
        assert http.post(endpoint, headers=headers(user), json={'image': image}).status_code == 422
    for _ in range(20):
        assert http.post(endpoint, headers=headers(user), json={'image': 'frame'}).status_code == 200
    assert http.post(endpoint, headers=headers(user), json={'image': 'frame'}).status_code == 429
    assert len(calls) == 20


def test_readiness_propagates_feedback_and_rejects_invalid_service_results(camera_app):
    http, _, user, _, result = camera_app
    result.update(ready=False, message='Move closer')
    response = http.post('/api/v1/users/me/face/readiness', headers=headers(user), json={'image': 'frame'})
    assert response.json() == result
    result['ready'] = 'yes'
    assert http.post('/api/v1/users/me/face/readiness', headers=headers(user), json={'image': 'frame'}).status_code == 503


def test_readiness_service_failure_is_not_a_pass(camera_app, monkeypatch):
    http, _, user, _, _ = camera_app

    async def unavailable(image):
        raise FaceServiceError(503, 'Face recognition service unavailable')

    monkeypatch.setattr(users, 'check_camera_readiness', unavailable)
    assert http.post('/api/v1/users/me/face/readiness', headers=headers(user), json={'image': 'frame'}).status_code == 503
