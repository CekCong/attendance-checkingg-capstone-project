"""
PUBLIC TESTS: Performance (5 points)

These tests verify performance requirements:
- Response latency (p95 < 2s) - 3 pts
- Concurrent user handling - 1 pt
- Database query optimization - 1 pt

Students can run these tests to ensure their implementation meets performance targets.
"""
import pytest
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed


class TestResponseLatency:
    """Test API response latency (3 points)"""

    @pytest.mark.points(1, category="latency")
    def test_auth_endpoint_latency(self, client, test_student):
        """Test that authentication completes within 2 seconds."""
        start = time.time()
        response = client.post("/api/v1/auth/login", json={
            "email": test_student["email"],
            "password": test_student["password"]
        })
        duration = time.time() - start

        assert response.status_code == 200
        assert duration < 2.0, f"Login took {duration:.2f}s, should be < 2s"

    @pytest.mark.points(1, category="latency")
    def test_checkin_endpoint_latency(self, client, prepared_checkin, auth_headers_student):
        """Measure full verification of a static replay, excluding enrollment/capture."""
        start = time.time()
        response = client.post("/api/v1/checkins/", headers=auth_headers_student, json=prepared_checkin)
        duration = time.time() - start

        assert response.status_code == 201, response.text
        assert response.json()["status"] == "rejected"
        assert duration < 2.0, f"Check-in took {duration:.2f}s, should be < 2s"

    @pytest.mark.points(0.5, category="latency")
    def test_list_endpoint_latency(self, client):
        """Test that list endpoints respond quickly."""
        start = time.time()
        response = client.get("/api/v1/courses/")
        duration = time.time() - start

        assert response.status_code == 200
        assert duration < 1.0, f"List courses took {duration:.2f}s, should be < 1s"

    @pytest.mark.points(0.5, category="latency")
    def test_health_check_latency(self, client):
        """Test that health check is very fast."""
        start = time.time()
        response = client.get("/health")
        duration = time.time() - start

        assert response.status_code in [200, 503]
        assert duration < 0.5, f"Health check took {duration:.2f}s, should be < 0.5s"


class TestConcurrentUsers:
    """Test concurrent user handling (1 point)"""

    @pytest.mark.points(1, category="concurrency")
    def test_concurrent_logins(self, client, test_student):
        """Test handling 10 concurrent login requests with same user."""
        email = test_student["email"]
        password = test_student["password"]

        def login():
            response = client.post("/api/v1/auth/login", json={
                "email": email,
                "password": password
            })
            return response.status_code == 200

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(login) for _ in range(10)]
            results = [f.result() for f in as_completed(futures)]

        # At least 80% should succeed
        success_rate = sum(results) / len(results)
        assert success_rate >= 0.8, f"Only {success_rate*100:.1f}% of concurrent logins succeeded"

    def test_concurrent_checkins(self, client, test_course, test_session, auth_headers_admin, record_property):
        """Twenty distinct students submit complete proofs and static replays concurrently."""
        import uuid
        from verification import prepare_static_replay
        students = []
        # Issue challenges only after all enrollment work is complete, to avoid
        # spending the 60-second challenge lifetime preparing other accounts.
        for index in range(20):
            email = f"concurrent-{uuid.uuid4().hex}@example.com"
            created = client.post("/api/v1/auth/register", json={"email": email,
                "password": "concurrent-password", "full_name": f"Concurrent {index}", "role": "student"})
            assert created.status_code == 201
            login = client.post("/api/v1/auth/login", json={"email": email, "password": "concurrent-password"})
            assert login.status_code == 200
            headers = {"Authorization": "Bearer " + login.json()["access_token"]}
            enrolled = client.post("/api/v1/admin/enrollments/", headers=auth_headers_admin,
                json={"student_id": created.json()["id"], "course_id": test_course["id"]})
            assert enrolled.status_code in (200, 201)
            body = prepare_static_replay(client, headers, test_session["id"], issue_challenges=False)
            students.append((headers, body))
        from verification import issue_proofs
        bodies = [(headers, issue_proofs(client, headers, body)) for headers, body in students]
        def submit(entry):
            headers, body = entry
            started = time.perf_counter()
            response = client.post("/api/v1/checkins/", headers=headers, json=body, timeout=120)
            return response, time.perf_counter()-started
        with ThreadPoolExecutor(max_workers=20) as executor:
            outcomes = list(executor.map(submit, bodies))
        for response, _ in outcomes:
            assert response.status_code == 201, response.text
            assert response.json()["status"] == "rejected"
            assert response.json()["liveness_passed"] is False
        durations = sorted(duration for _, duration in outcomes)
        record_property("static_replay_concurrency", 20)
        record_property("static_replay_max_seconds", round(durations[-1], 3))
        assert len({response.json()["id"] for response, _ in outcomes}) == 20


class TestDatabaseOptimization:
    """Test database query optimization (1 point)"""

    @pytest.mark.points(0.5, category="db_optimization")
    def test_no_n_plus_one_queries(self, client, test_session, auth_headers_instructor):
        """Test that listing check-ins doesn't cause N+1 query problem."""
        # This is a basic test - in production, would use query profiling
        start = time.time()
        response = client.get(f"/api/v1/checkins/session/{test_session['id']}", headers=auth_headers_instructor)
        duration = time.time() - start

        assert response.status_code == 200
        # Should be fast even with many check-ins
        assert duration < 1.0, f"Listing check-ins took {duration:.2f}s, may indicate N+1 queries"

    @pytest.mark.points(0.5, category="db_optimization")
    def test_pagination_support(self, client):
        """Test that large result sets support pagination."""
        # Basic test for pagination existence
        response = client.get("/api/v1/courses/", params={"limit": 10, "offset": 0})
        # Should either work with pagination or return all results quickly
        assert response.status_code == 200