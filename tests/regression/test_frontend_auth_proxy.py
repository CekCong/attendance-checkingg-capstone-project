"""Run with TEST_FRONTEND_URL and TEST_BACKEND_URL pointing at the same stack."""
import os
import uuid

import httpx
import pytest

FRONTEND = os.getenv('TEST_FRONTEND_URL')
pytestmark = pytest.mark.skipif(not FRONTEND, reason='Set TEST_FRONTEND_URL for frontend auth integration')


def test_frontend_auth_uses_backend_authority():
    backend = os.getenv('TEST_BACKEND_URL', 'http://localhost:8000')
    with httpx.Client(base_url=backend, timeout=30) as api, httpx.Client(base_url=FRONTEND, timeout=30) as web:
        suffix = uuid.uuid4().hex
        credentials = {'email': f'proxy-{suffix}@example.com', 'password': 'proxy-test-password'}
        created = api.post('/api/v1/auth/register', json={**credentials, 'full_name': 'Proxy Test', 'role': 'student'})
        assert created.status_code == 201
        user_id = created.json()['id']
        admin_credentials = {'email': f'proxy-admin-{suffix}@example.com', 'password': 'proxy-test-password'}
        assert api.post('/api/v1/auth/register', json={**admin_credentials, 'full_name': 'Admin', 'role': 'admin'}).status_code == 201
        admin_login = api.post('/api/v1/auth/login', json=admin_credentials)
        assert admin_login.status_code == 200
        admin_headers = {'Authorization': f"Bearer {admin_login.json()['access_token']}"}

        login = web.post('/api/auth/login', json=credentials, headers={'Origin': FRONTEND})
        assert login.status_code == 200
        assert 'refresh_token' not in login.json()
        assert 'HttpOnly' in login.headers['set-cookie']
        assert login.headers['cache-control'] == 'no-store'
        refreshed = web.post('/api/auth/refresh')
        assert refreshed.status_code == 200
        assert refreshed.json()['user']['id'] == user_id
        assert 'refresh_token' not in refreshed.json()
        headers = {'Authorization': f"Bearer {refreshed.json()['access_token']}"}
        me = api.get('/api/v1/auth/me', headers=headers)
        assert me.status_code == 200
        assert me.json()['id'] == user_id
        logged_out = web.post('/api/auth/logout', headers=headers)
        assert logged_out.status_code == 200
        assert 'Max-Age=0' in logged_out.headers['set-cookie']
        assert web.post('/api/auth/refresh').status_code == 401
        logs = api.get('/api/v1/audit/', params={'user_id': user_id}, headers=admin_headers)
        assert logs.status_code == 200
        assert any(row['action'] == 'logout' for row in logs.json()['items'])

        assert web.post('/api/auth/login', json=credentials).status_code == 200
        assert api.patch(f'/api/v1/admin/users/{user_id}/deactivate', headers=admin_headers).status_code == 200
        disabled = web.post('/api/auth/refresh')
        assert disabled.status_code == 403
        assert 'Max-Age=0' in disabled.headers['set-cookie']
        assert web.post('/api/auth/refresh').status_code == 401
        assert web.post('/api/auth/login', json={'email': 123, 'password': 'x'}).status_code == 400
        assert web.post('/api/auth/login', json=credentials, headers={'Origin': 'https://unrelated.example'}).status_code == 403
