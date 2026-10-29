"""Report completeness and instructor isolation beyond a single page."""
import csv
import io
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import event
from test_auth_migration import auth_app, subject
from app.models import UserModel, CourseModel, SessionModel, EnrollmentModel, CheckinModel, AuditLogModel
from app.routers import sessions, courses, stats, export, audit
from app.security import create_access_token


def headers(user):
    return {'Authorization': 'Bearer ' + create_access_token(subject(user))}


@pytest.fixture
def reports(auth_app):
    http, db, student, _, _ = auth_app
    for router in (sessions, courses, stats, export, audit):
        http.app.include_router(router.router, prefix='/api/v1')
        if router in (sessions, courses):
            http.app.dependency_overrides[router.get_db] = lambda: db
    teacher = UserModel(id=str(uuid.uuid4()), email='teacher@example.com', full_name='Teacher', role='instructor', hashed_password='unused')
    admin = UserModel(id=str(uuid.uuid4()), email='admin@example.com', full_name='Admin', role='admin', hashed_password='unused')
    student.full_name = '=2+3'
    owned = CourseModel(id=str(uuid.uuid4()), code='OWNED', name='Owned', semester='2026')
    hidden = CourseModel(id=str(uuid.uuid4()), code='HIDDEN', name='Hidden', semester='2026')
    db.add_all([teacher, admin, owned, hidden]); db.flush()
    now = datetime.utcnow()
    rows = []
    for index in range(106):
        session = SessionModel(id=str(uuid.uuid4()), course_id=owned.id if index < 105 else hidden.id,
            instructor_id=teacher.id if index < 105 else admin.id, name=f'Lecture {index}', status='active',
            scheduled_start=now, scheduled_end=now+timedelta(hours=1), checkin_opens_at=now, checkin_closes_at=now+timedelta(hours=1))
        db.add(session); db.flush()
        checkin = CheckinModel(id=str(uuid.uuid4()), session_id=session.id, student_id=student.id,
            status='flagged', checked_in_at=now, risk_score=0.6)
        db.add(checkin); rows.append((session, checkin))
    for course in (owned, hidden):
        db.add(EnrollmentModel(id=str(uuid.uuid4()), student_id=student.id, course_id=course.id, is_active=True))
    db.commit()
    return http, db, student, teacher, admin, owned, hidden, rows


@pytest.mark.parametrize('path', ['/checkins/', '/checkins/flagged', '/sessions/'])
def test_complete_stable_pagination_and_scope(reports, path):
    http, _, _, teacher, _, _, _, _ = reports
    first = http.get('/api/v1'+path, headers=headers(teacher), params={'limit':100,'offset':0})
    second = http.get('/api/v1'+path, headers=headers(teacher), params={'limit':100,'offset':100})
    assert first.status_code == second.status_code == 200
    assert first.json()['total'] == second.json()['total'] == 105
    ids = [item['id'] for page in (first, second) for item in page.json()['items']]
    assert len(ids) == len(set(ids)) == 105
    repeated = http.get('/api/v1'+path, headers=headers(teacher), params={'limit':100,'offset':0})
    assert [item['id'] for item in repeated.json()['items']] == ids[:100]


def test_student_lists_support_later_pages(reports):
    http, _, student, _, _, _, _, _ = reports
    for path in ('/sessions/my-sessions', '/checkins/my-checkins'):
        first = http.get('/api/v1'+path, headers=headers(student), params={'limit':100})
        second = http.get('/api/v1'+path, headers=headers(student), params={'limit':100,'offset':100})
        assert first.status_code == second.status_code == 200
        assert len(first.json()) == 100 and len(second.json()) == 6
        assert len({row['id'] for page in (first, second) for row in page.json()}) == 106


def test_student_report_does_not_disclose_other_courses(reports):
    http, _, student, teacher, admin, owned, hidden, _ = reports
    result = http.get(f'/api/v1/stats/students/{student.id}', headers=headers(teacher))
    assert result.status_code == 200
    assert result.json()['total_enrolled_courses'] == 1
    assert result.json()['total_sessions'] == 105
    assert [row['course_id'] for row in result.json()['courses']] == [owned.id]
    assert all(row['course_code'] == 'OWNED' for row in result.json()['recent_checkins'])
    full = http.get(f'/api/v1/stats/students/{student.id}', headers=headers(admin))
    assert full.json()['total_enrolled_courses'] == 2


def test_exports_are_complete_scoped_audited_and_formula_safe(reports):
    http, db, student, teacher, admin, _, _, rows = reports
    result = http.get('/api/v1/export/checkins?format=json', headers=headers(teacher))
    assert result.status_code == 200
    assert result.json()['total'] == len(result.json()['records']) == 105
    assert result.json()['records'][0]['student_name'] == '=2+3'
    assert db.query(AuditLogModel).filter_by(action='data_exported', user_id=teacher.id).count() == 1
    csv_response = http.get('/api/v1/export/checkins', headers=headers(teacher))
    csv_rows = list(csv.DictReader(io.StringIO(csv_response.text)))
    assert len(csv_rows) == 105 and all(row['student_name'] == "'=2+3" for row in csv_rows)
    assert http.get('/api/v1/export/checkins?format=json', headers=headers(student)).status_code == 403
    denied = http.get('/api/v1/export/checkins', params={'session_id':rows[-1][0].id}, headers=headers(teacher))
    assert denied.status_code == 403
    assert db.query(AuditLogModel).filter_by(action='data_exported', user_id=teacher.id).count() == 2
    assert http.get('/api/v1/export/checkins?format=json', headers=headers(admin)).json()['total'] == 106
    filtered = http.get('/api/v1/export/checkins', params={'format':'json','session_id':rows[0][0].id}, headers=headers(teacher))
    assert filtered.json()['total'] == 1


def test_session_page_query_count_is_bounded(reports):
    http, db, _, teacher, _, _, _, _ = reports
    queries = []
    def count(*args):
        queries.append(1)
    event.listen(db.get_bind(), 'before_cursor_execute', count)
    try:
        response = http.get('/api/v1/sessions/?limit=100', headers=headers(teacher))
        assert response.status_code == 200
        assert len(response.json()['items']) == 100
        assert len(queries) <= 8, len(queries)
    finally:
        event.remove(db.get_bind(), 'before_cursor_execute', count)


def test_course_export_retains_recorded_results_after_enrollment_dropped(reports):
    http, db, student, teacher, _, owned, _, _ = reports
    enrollment = db.query(EnrollmentModel).filter_by(student_id=student.id, course_id=owned.id).one()
    enrollment.is_active = False
    db.commit()
    result = http.get(f'/api/v1/export/attendance/{owned.id}?format=json', headers=headers(teacher))
    assert result.status_code == 200
    assert len(result.json()) == 105
    assert all(row['status'] == 'flagged' for row in result.json())


def test_overview_uses_singapore_calendar_day(reports, monkeypatch):
    from datetime import timezone
    http, db, _, teacher, _, _, _, rows = reports
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            value = datetime(2026, 10, 29, 18, tzinfo=timezone.utc)
            return value.astimezone(tz) if tz else value.replace(tzinfo=None)
    monkeypatch.setattr(stats, 'datetime', Clock)
    for _, checkin in rows:
        checkin.checked_in_at = datetime(2026, 10, 29, 15, 59)
    rows[0][1].checked_in_at = datetime(2026, 10, 29, 16, 30)
    db.commit()
    result = http.get('/api/v1/stats/overview?days=2', headers=headers(teacher))
    assert result.status_code == 200, result.text
    assert result.json()['today_checkins'] == 1
    assert result.json()['trends']['checkins_by_day'][-1] == {'date':'2026-10-30','count':1}
    assert export._as_date(datetime(2026, 10, 29, 16, 30)) == '2026-10-30'
