"""Auth behavior with an isolated database and real, namespaced Redis limits."""
import sys
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
import redis
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'module2-backend'))
from app import rate_limit
from app.database import get_db
from app.models import Base, UserModel, AuditLogModel
from app.routers import auth, checkins
from app.security import create_access_token, create_refresh_token, create_token


@pytest.fixture
def auth_app(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    user = UserModel(id=str(uuid.uuid4()), email='auth@example.com', full_name='Auth Test',
                     role='student', is_active=True, failed_login_attempts=0,
                     hashed_password=auth.get_password_hash('valid-password'))
    db.add(user)
    db.commit()
    client = redis.Redis(host='localhost', port=6380, db=2, decode_responses=True)
    client.ping()
    prefix = f'test-auth:{uuid.uuid4()}:'
    monkeypatch.setenv('RATE_LIMIT_PREFIX', prefix)
    monkeypatch.setattr(rate_limit, '_get_redis', lambda: client)
    monkeypatch.setattr(auth, 'LOGIN_RATE_LIMIT', 60)
    monkeypatch.setattr(auth, 'REGISTRATION_RATE_LIMIT', 10)
    monkeypatch.setenv('API_RATE_LIMIT', '1000')
    monkeypatch.setenv('CHECKIN_RATE_LIMIT', '10')
    app = FastAPI()
    app.include_router(auth.router, prefix='/api/v1')
    app.include_router(checkins.router, prefix='/api/v1')
    def database():
        yield db
    app.dependency_overrides[get_db] = database
    # checkins wraps the shared dependency with its own generator.
    app.dependency_overrides[checkins.get_db] = database
    with TestClient(app) as http:
        yield http, db, user, client, prefix
    keys = list(client.scan_iter(match=prefix + '*'))
    if keys:
        client.delete(*keys)
    db.close()
    engine.dispose()


def subject(user):
    return {'id': user.id, 'email': user.email, 'role': user.role}


def test_refresh_uses_database_role_and_rejects_disabled_deleted_and_expired(auth_app):
    http, db, user, _, _ = auth_app
    token = create_refresh_token(subject(user))
    user.role = 'instructor'
    db.commit()
    refreshed = http.post('/api/v1/auth/refresh', json={'refresh_token': token})
    assert refreshed.status_code == 200
    assert refreshed.json()['user']['role'] == 'instructor'
    access = refreshed.json()['access_token']
    assert http.get('/api/v1/auth/me', headers={'Authorization': f'Bearer {access}'}).status_code == 200
    expired = create_token(subject(user), 'refresh', timedelta(seconds=-1))
    assert http.post('/api/v1/auth/refresh', json={'refresh_token': expired}).status_code == 401
    assert http.post('/api/v1/auth/refresh', json={'refresh_token': access}).status_code == 401
    user.is_active = False
    db.commit()
    assert http.post('/api/v1/auth/refresh', json={'refresh_token': token}).status_code == 403
    db.delete(user)
    db.commit()
    assert http.post('/api/v1/auth/refresh', json={'refresh_token': token}).status_code == 401


def test_logout_is_audited_and_clears_cookie(auth_app):
    http, db, user, _, _ = auth_app
    login = http.post('/api/v1/auth/login', json={'email': user.email, 'password': 'valid-password'})
    assert login.status_code == 200
    assert 'HttpOnly' in login.headers['set-cookie']
    response = http.post('/api/v1/auth/logout', headers={'Authorization': f"Bearer {login.json()['access_token']}"})
    assert response.status_code == 200
    assert 'Max-Age=0' in response.headers['set-cookie']
    assert db.query(AuditLogModel).filter_by(user_id=user.id, action='logout').count() == 1


def test_login_and_registration_default_limits(auth_app):
    http, _, user, client, prefix = auth_app
    for _ in range(60):
        response = http.post('/api/v1/auth/login', json={'email': 'missing@example.com', 'password': 'wrong'})
        assert response.status_code == 401
    assert http.post('/api/v1/auth/login', json={'email': 'missing@example.com', 'password': 'wrong'}).status_code == 429
    for _ in range(10):
        assert http.post('/api/v1/auth/register', json={
            'email': user.email, 'password': 'valid-password', 'full_name': 'Duplicate',
        }).status_code == 400
    assert http.post('/api/v1/auth/register', json={
        'email': user.email, 'password': 'valid-password', 'full_name': 'Duplicate',
    }).status_code == 429
    assert all(0 < client.ttl(key) <= 3600 for key in client.scan_iter(match=prefix + '*'))


def test_api_limit_is_per_user_and_expired_tokens_cannot_use_it(auth_app, monkeypatch):
    http, db, user, _, _ = auth_app
    monkeypatch.setenv('API_RATE_LIMIT', '2')
    access = create_access_token(subject(user))
    headers = {'Authorization': f'Bearer {access}'}
    assert http.get('/api/v1/auth/me', headers=headers).status_code == 200
    assert http.get('/api/v1/auth/me', headers=headers).status_code == 200
    blocked = http.get('/api/v1/auth/me', headers=headers)
    assert blocked.status_code == 429
    assert blocked.headers['retry-after'] == '3600'
    other = UserModel(id=str(uuid.uuid4()), email='other@example.com', full_name='Other', role='student', is_active=True, hashed_password='unused')
    db.add(other)
    db.commit()
    assert http.get('/api/v1/auth/me', headers={'Authorization': f'Bearer {create_access_token(subject(other))}'}).status_code == 200
    expired = create_token(subject(other), 'access', timedelta(seconds=-1))
    assert http.get('/api/v1/auth/me', headers={'Authorization': f'Bearer {expired}'}).status_code == 401


def test_checkin_limit_counts_failed_attempts(auth_app):
    http, _, user, _, _ = auth_app
    headers = {'Authorization': f'Bearer {create_access_token(subject(user))}'}
    body = {'session_id': str(uuid.uuid4()), 'latitude': 1.3, 'longitude': 103.7, 'device_fingerprint': 'test'}
    for _ in range(10):
        assert http.post('/api/v1/checkins/', json=body, headers=headers).status_code == 404
    assert http.post('/api/v1/checkins/', json=body, headers=headers).status_code == 429


def test_redis_failure_does_not_disable_limits(auth_app, monkeypatch):
    http, _, user, _, _ = auth_app
    monkeypatch.setattr(rate_limit, '_get_redis', lambda: None)
    monkeypatch.delenv('RATE_LIMIT_ALLOW_MEMORY', raising=False)
    assert http.post('/api/v1/auth/login', json={'email': user.email, 'password': 'valid-password'}).status_code == 503
