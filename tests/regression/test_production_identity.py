"""Production registration boundaries and atomic operator-only admin bootstrap."""
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from test_auth_migration import auth_app
from app.bootstrap_admin import create_initial_admin, password_from_file
from app.models import Base, UserModel, AuditLogModel
from app.routers.auth import verify_password
from app.runtime_security import validate_runtime_security


@pytest.mark.parametrize('role', ['admin', 'instructor', 'ta'])
@pytest.mark.parametrize('mode', ['development', 'production', 'test'])
def test_privileged_public_registration_denied_by_default(auth_app, monkeypatch, role, mode):
    http, db, _, _, _ = auth_app
    monkeypatch.setenv('SAIV_ENV', mode)
    monkeypatch.delenv('ALLOW_PRIVILEGED_SELF_REGISTRATION', raising=False)
    response = http.post('/api/v1/auth/register', json={'email':'escalate@example.com',
        'password':'valid-password','full_name':'Escalate','role':role})
    assert response.status_code == 403
    assert db.query(UserModel).filter_by(email='escalate@example.com').count() == 0
    assert db.query(AuditLogModel).filter_by(details='privileged_registration_denied',success=False).count() == 1


def test_test_fixture_opt_in_cannot_enable_production_privilege(auth_app, monkeypatch):
    http, db, _, _, _ = auth_app
    monkeypatch.setenv('ALLOW_PRIVILEGED_SELF_REGISTRATION','true')
    monkeypatch.setenv('SAIV_ENV','production')
    body = {'email':'teacher@example.com','password':'valid-password','full_name':'Teacher','role':'instructor'}
    assert http.post('/api/v1/auth/register',json=body).status_code == 403
    monkeypatch.setenv('SAIV_ENV','test')
    assert http.post('/api/v1/auth/register',json=body).status_code == 201
    assert db.query(UserModel).filter_by(email=body['email']).one().role == 'instructor'


def test_student_signup_still_works_in_production_mode(auth_app, monkeypatch):
    http, db, _, _, _ = auth_app
    monkeypatch.setenv('SAIV_ENV','production')
    monkeypatch.delenv('ALLOW_PRIVILEGED_SELF_REGISTRATION',raising=False)
    response = http.post('/api/v1/auth/register',json={'email':'student@example.com','password':'valid-password','full_name':'Student'})
    assert response.status_code == 201 and response.json()['role'] == 'student'
    assert verify_password('valid-password',db.query(UserModel).filter_by(email='student@example.com').one().hashed_password)


@pytest.mark.parametrize('settings', [
    {'SAIV_ENV':'typo'},
    {'SAIV_ENV':'development','ALLOW_PRIVILEGED_SELF_REGISTRATION':'true'},
    {'SAIV_ENV':'production'},
    {'SAIV_ENV':'production','SECRET_KEY':'saiv-dev-secret-change-me','COOKIE_SECURE':'true'},
    {'SAIV_ENV':'production','SECRET_KEY':'x'*48},
    {'SAIV_ENV':'production','SECRET_KEY':'x'*48,'COOKIE_SECURE':'true','ALLOW_PRIVILEGED_SELF_REGISTRATION':'true'},
])
def test_unsafe_runtime_configuration_fails_closed(monkeypatch, settings):
    for name in ('SAIV_ENV','SECRET_KEY','COOKIE_SECURE','ALLOW_PRIVILEGED_SELF_REGISTRATION'):
        monkeypatch.delenv(name,raising=False)
    for name,value in settings.items(): monkeypatch.setenv(name,value)
    with pytest.raises(RuntimeError): validate_runtime_security()


def test_production_checks_the_key_actually_used_to_sign(monkeypatch):
    monkeypatch.setenv('SAIV_ENV','production'); monkeypatch.setenv('SECRET_KEY','x'*48)
    monkeypatch.setenv('COOKIE_SECURE','true'); monkeypatch.delenv('ALLOW_PRIVILEGED_SELF_REGISTRATION',raising=False)
    validate_runtime_security()
    with pytest.raises(RuntimeError): validate_runtime_security(signing_key='saiv-dev-secret-change-me')


def test_bootstrap_creates_hashed_audited_admin_once(auth_app):
    _, db, _, _, _ = auth_app
    password = 'bootstrap-test-password'
    user_id = create_initial_admin(db, 'Bootstrap@Example.com', '<Admin>', password)
    admin = db.get(UserModel,user_id)
    assert admin.role == 'admin' and admin.is_active
    assert admin.email == 'bootstrap@example.com' and admin.full_name == '&lt;Admin&gt;'
    assert admin.hashed_password != password and verify_password(password,admin.hashed_password)
    audit = db.query(AuditLogModel).filter_by(details='initial_admin_bootstrap').one()
    assert audit.user_id == user_id and audit.resource_id == user_id
    assert password not in str(audit.details)
    original_hash = admin.hashed_password
    admin.is_active = False; db.commit()
    with pytest.raises(ValueError,match='already exists'):
        create_initial_admin(db,'another@example.com','Another','another-password')
    assert db.query(UserModel).filter_by(role='admin').count() == 1
    assert not db.get(UserModel,user_id).is_active and db.get(UserModel,user_id).hashed_password == original_hash


def test_bootstrap_never_promotes_existing_student(auth_app):
    _,db,student,_,_ = auth_app
    original_hash = student.hashed_password
    with pytest.raises(ValueError,match='will not promote'):
        create_initial_admin(db,student.email,'Changed','new-valid-password')
    db.refresh(student)
    assert student.role == 'student' and student.hashed_password == original_hash


def test_bootstrap_rolls_back_if_audit_write_fails(auth_app):
    _,db,_,_,_ = auth_app
    db.execute(text("CREATE TRIGGER fail_audit BEFORE INSERT ON audit_logs BEGIN SELECT RAISE(ABORT, 'test failure'); END"))
    db.commit()
    with pytest.raises(SQLAlchemyError):
        create_initial_admin(db,'rollback@example.com','Rollback','valid-bootstrap-password')
    assert db.query(UserModel).filter_by(email='rollback@example.com').count() == 0


@pytest.mark.parametrize('password',['short','a'*73,'\U0001f600'*19])
def test_bootstrap_rejects_short_or_bcrypt_truncating_passwords(auth_app,password):
    _,db,_,_,_ = auth_app
    with pytest.raises(ValueError): create_initial_admin(db,'bad@example.com','Bad',password)
    assert db.query(UserModel).filter_by(role='admin').count() == 0


def test_private_password_file_and_noninteractive_cli(tmp_path):
    file = tmp_path/'secret'; file.write_text('private-test-password\n');file.chmod(0o600)
    assert password_from_file(str(file)) == 'private-test-password'
    file.chmod(0o644)
    with pytest.raises(ValueError): password_from_file(str(file))
    link=tmp_path/'link';link.symlink_to(file)
    with pytest.raises(OSError): password_from_file(str(link))
    root=Path(__file__).resolve().parents[2]/'module2-backend'
    result=subprocess.run([sys.executable,'-m','app.bootstrap_admin','--email','admin@example.com','--full-name','Admin'],
        cwd=root,input='',text=True,capture_output=True)
    assert result.returncode == 1 and '--password-file' in result.stderr


def test_postgres_concurrent_bootstrap_creates_only_one_admin(tmp_path):
    url=os.getenv('TEST_BOOTSTRAP_DATABASE_URL')
    if not url: pytest.skip('Set TEST_BOOTSTRAP_DATABASE_URL to a disposable PostgreSQL schema-owner connection')
    schema='test_bootstrap_'+uuid.uuid4().hex
    owner=create_engine(url)
    with owner.begin() as connection: connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    isolated=create_engine(url,connect_args={'options':f'-csearch_path={schema}'})
    try:
        Base.metadata.create_all(isolated)
        password_file = tmp_path / 'bootstrap-password'
        password_file.write_text('concurrent-bootstrap-password\n'); password_file.chmod(0o600)
        connection_url = make_url(url).update_query_dict({'options':f'-csearch_path={schema}'}).render_as_string(hide_password=False)
        def create(index):
            result = subprocess.run([sys.executable,'-m','app.bootstrap_admin',
                '--email',f'admin{index}@example.com','--full-name','Admin','--password-file',str(password_file)],
                cwd=Path(__file__).resolve().parents[2]/'module2-backend',
                env={**os.environ,'DATABASE_URL':connection_url},text=True,capture_output=True,timeout=30)
            assert 'concurrent-bootstrap-password' not in result.stdout + result.stderr
            assert result.returncode in (0,1), result.stderr
            if result.returncode == 1: assert 'already exists' in result.stderr
            else: assert 'Created initial administrator' in result.stdout
            return result.returncode
        with ThreadPoolExecutor(max_workers=2) as executor: results=list(executor.map(create,[1,2]))
        assert sorted(results) == [0,1]
        with Session(isolated) as db:
            assert db.query(UserModel).filter_by(role='admin').count() == 1
            assert db.query(AuditLogModel).filter_by(details='initial_admin_bootstrap').count() == 1
    finally:
        isolated.dispose()
        with owner.begin() as connection: connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        owner.dispose()


def test_bootstrapped_admin_can_provision_staff_but_student_cannot(auth_app, monkeypatch):
    from app.routers import admin
    http,db,student,_,_ = auth_app
    http.app.include_router(admin.router,prefix='/api/v1')
    monkeypatch.setenv('SAIV_ENV','production')
    monkeypatch.delenv('ALLOW_PRIVILEGED_SELF_REGISTRATION',raising=False)
    create_initial_admin(db,'operator@example.com','Operator','operator-test-password')
    def token(email,password):
        result=http.post('/api/v1/auth/login',json={'email':email,'password':password})
        assert result.status_code == 200
        return {'Authorization':'Bearer '+result.json()['access_token']}
    body={'users':[{'email':'staff@example.com','full_name':'Staff','password':'staff-test-password','role':'instructor'}]}
    assert http.post('/api/v1/admin/users/bulk',json=body,headers=token(student.email,'valid-password')).status_code == 403
    result=http.post('/api/v1/admin/users/bulk',json=body,headers=token('operator@example.com','operator-test-password'))
    assert result.status_code == 201 and result.json()['created'] == 1, result.text
    staff=token('staff@example.com','staff-test-password')
    assert http.get('/api/v1/auth/me',headers=staff).json()['role'] == 'instructor'
