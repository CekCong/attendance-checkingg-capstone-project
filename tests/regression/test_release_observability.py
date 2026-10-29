"""Readiness checks and bounded, payload-free Prometheus labels."""
import uuid
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_auth_migration import auth_app


def test_readiness_reports_dependency_failure(auth_app, monkeypatch):
    from app import main
    monkeypatch.setattr(main, 'engine', auth_app[1].get_bind())
    monkeypatch.setattr(main, 'get_redis_client', lambda: None)
    app = FastAPI()
    app.add_api_route('/ready', main.readiness)
    with TestClient(app) as client:
        response = client.get('/ready')
        assert response.status_code == 503 and response.json()['status'] == 'unavailable'
        monkeypatch.setattr(main, 'get_redis_client', lambda: auth_app[3])
        assert client.get('/ready').json() == {'status':'ready'}


def test_both_services_expose_ready_and_bounded_metrics(client, face_client):
    for service, metric in ((client, 'saiv_http_requests_total'), (face_client, 'saiv_face_http_requests_total')):
        assert service.get('/ready').status_code == 200
        marker = f'private-marker-{uuid.uuid4().hex}'
        assert service.get('/' + marker).status_code == 404
        # PROPFIND is accepted by the HTTP parser but is not an API method.
        custom_method = 'PROPFIND'
        assert service.request(custom_method, '/health').status_code == 405
        metrics = service.get('/metrics')
        assert metrics.status_code == 200
        assert metric in metrics.text
        assert 'path="unmatched"' in metrics.text
        assert marker not in metrics.text
        assert custom_method not in metrics.text
        assert 'method="OTHER"' in metrics.text
