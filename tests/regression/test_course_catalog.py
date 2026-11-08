"""Only admins create courses; tutors add existing, unassigned catalog entries."""
import uuid
from datetime import datetime, timedelta

import pytest

from test_auth_migration import auth_app
from test_security_privacy_migration import headers
from app.models import UserModel, CourseModel, CourseInstructorModel, SessionModel, AuditLogModel
from app.routers import courses, sessions


@pytest.fixture
def catalog_app(auth_app):
    http, db, student, _, _ = auth_app
    for router in (courses.router, sessions.router):
        http.app.include_router(router, prefix='/api/v1')
    actors = {'student': student}
    for name, role in [('admin', 'admin'), ('teacher', 'instructor'), ('other', 'instructor'), ('ta', 'ta')]:
        actors[name] = UserModel(id=str(uuid.uuid4()), email=f'{name}@catalog.example', full_name=name,
                                role=role, hashed_password='unused', is_active=True)
        db.add(actors[name])
    db.commit()
    payload = {'code': 'CAT101', 'name': 'Catalog course', 'semester': '2026-S1'}
    response = http.post('/api/v1/courses/', headers=headers(actors['admin']), json=payload)
    assert response.status_code == 201, response.text
    return http, db, actors, response.json()


def test_only_admin_can_create_catalog_courses(catalog_app):
    http, db, actors, _ = catalog_app
    for name in ('teacher', 'other', 'student', 'ta'):
        response = http.post('/api/v1/courses/', headers=headers(actors[name]),
                             json={'code': name, 'name': 'Forbidden', 'semester': '2026-S1'})
        assert response.status_code == 403
    assert http.post('/api/v1/courses/', json={'code': 'anon', 'name': 'Forbidden', 'semester': '2026-S1'}).status_code in (401, 403)
    assert db.query(CourseModel).count() == 1


def test_add_existing_course_is_idempotent_and_allows_scheduling(catalog_app):
    http, db, actors, course = catalog_app
    teacher = headers(actors['teacher'])
    assert http.get('/api/v1/courses/', headers=teacher).json()['items'] == []
    available = http.get('/api/v1/courses/available', headers=teacher)
    assert available.status_code == 200, available.text
    assert available.json()['items'] == [{key: course[key] for key in ('id', 'code', 'name', 'semester')}]
    assert http.get(f"/api/v1/courses/{course['id']}", headers=teacher).status_code == 403
    for _ in range(2):
        response = http.post(f"/api/v1/courses/{course['id']}/assignment", headers=teacher,
                             json={'instructor_id': actors['other'].id})
        assert response.status_code == 200, response.text
        assert response.json()['id'] == course['id']
        assert response.json()['instructor_id'] == actors['teacher'].id
    assert db.query(CourseModel).count() == db.query(CourseInstructorModel).count() == 1
    assert db.query(SessionModel).count() == 0
    assert db.query(AuditLogModel).filter_by(resource_id=course['id']).count() == 1
    assert http.get('/api/v1/courses/available', headers=teacher).json()['items'] == []
    assert http.get('/api/v1/courses/', headers=teacher).json()['items'][0]['id'] == course['id']
    start = datetime.utcnow() + timedelta(days=1)
    lesson = http.post('/api/v1/sessions/', headers=teacher, json={
        'course_id': course['id'], 'name': 'Tutorial', 'scheduled_start': start.isoformat(),
        'scheduled_end': (start + timedelta(hours=1)).isoformat(),
    })
    assert lesson.status_code == 201, lesson.text


def test_catalog_does_not_offer_archived_or_assigned_courses(catalog_app):
    http, db, actors, course = catalog_app
    archived = CourseModel(id=str(uuid.uuid4()), code='OLD', name='Old', semester='2025', is_active=False)
    assigned = CourseModel(id=str(uuid.uuid4()), code='TAKEN', name='Assigned', semester='2026')
    legacy = CourseModel(id=str(uuid.uuid4()), code='LEGACY', name='Legacy assignment', semester='2026')
    db.add_all([archived, assigned, legacy]); db.flush()
    db.add(CourseInstructorModel(course_id=assigned.id, instructor_id=actors['other'].id))
    now = datetime.utcnow()
    db.add(SessionModel(id=str(uuid.uuid4()), course_id=legacy.id, instructor_id=actors['other'].id,
                        name='Legacy lesson', status='scheduled', scheduled_start=now, scheduled_end=now + timedelta(hours=1),
                        checkin_opens_at=now, checkin_closes_at=now + timedelta(hours=1)))
    db.commit()
    teacher = headers(actors['teacher'])
    listed = http.get('/api/v1/courses/available?limit=1', headers=teacher).json()
    assert listed['total'] == 1 and listed['items'][0]['id'] == course['id']
    assert http.get('/api/v1/courses/available?limit=1&offset=1', headers=teacher).json()['items'] == []
    for course_id, expected in [(archived.id, 400), (assigned.id, 409), (legacy.id, 409), (str(uuid.uuid4()), 404)]:
        assert http.post(f'/api/v1/courses/{course_id}/assignment', headers=teacher).status_code == expected
    assert db.query(CourseInstructorModel).one().instructor_id == actors['other'].id


def test_second_teacher_cannot_take_an_added_course(catalog_app):
    http, db, actors, course = catalog_app
    path = f"/api/v1/courses/{course['id']}/assignment"
    assert http.post(path, headers=headers(actors['teacher'])).status_code == 200
    assert http.post(path, headers=headers(actors['other'])).status_code == 409
    assert db.query(CourseInstructorModel).one().instructor_id == actors['teacher'].id


@pytest.mark.parametrize('name', ['student', 'ta', 'admin'])
def test_non_instructors_cannot_self_assign(catalog_app, name):
    http, db, actors, course = catalog_app
    assert http.get('/api/v1/courses/available', headers=headers(actors[name])).status_code == 403
    assert http.post(f"/api/v1/courses/{course['id']}/assignment", headers=headers(actors[name])).status_code == 403
    assert db.query(CourseInstructorModel).count() == 0
