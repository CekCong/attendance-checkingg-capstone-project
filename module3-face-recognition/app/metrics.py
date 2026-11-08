"""Bounded-label service metrics; no user identifiers or biometric payloads."""
import time
from prometheus_client import Counter, Histogram, CONTENT_TYPE_LATEST, generate_latest
from fastapi import Request, Response

REQUESTS = Counter('saiv_face_http_requests_total', 'Face-service requests', ['method', 'path', 'status'])
DURATION = Histogram('saiv_face_http_request_duration_seconds', 'Face-service latency', ['method', 'path'])

async def observe(request: Request, call_next):
    if request.url.path == '/metrics':
        return await call_next(request)
    method = request.method if request.method in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE", "CONNECT"} else "OTHER"
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers['Cache-Control'] = 'no-store'
        return response
    finally:
        route = getattr(request.scope.get('route'), 'path', 'unmatched')
        REQUESTS.labels(method, route, str(status)).inc()
        DURATION.labels(method, route).observe(time.perf_counter()-started)

def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
