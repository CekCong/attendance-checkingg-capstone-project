import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException, Request, Response
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

for parent in Path(__file__).resolve().parents:
    backend_path = parent / "module2-backend"
    if (backend_path / "app").is_dir():
        sys.path.insert(0, str(backend_path))
        break

from app.models import UserModel
from app.routers import admin, auth


def make_request() -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
    )


def test_bulk_created_user_can_log_in_with_normalized_email(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    UserModel.__table__.create(engine)
    monkeypatch.setattr(admin, "add_audit_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(auth, "add_audit_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(auth, "check_rate_limit", lambda *args, **kwargs: True)

    try:
        with Session(engine) as db:
            created = admin.bulk_create_users(
                users_data=[
                    admin.UserCreate(
                        email="Bulk.User@Example.com",
                        password="test-password-123",
                        full_name="Bulk User",
                        role=admin.UserRole.student,
                    )
                ],
                request=make_request(),
                _={"role": "admin"},
                db=db,
            )

            assert created[0].email == "bulk.user@example.com"

            login_result = asyncio.run(
                auth.login(
                    body=auth.LoginBody(
                        email="BULK.USER@example.com",
                        password="test-password-123",
                    ),
                    request=make_request(),
                    response=Response(),
                    db=db,
                )
            )

            assert login_result["user"]["id"] == created[0].id
            assert login_result["access_token"]

            with pytest.raises(HTTPException) as error:
                admin.bulk_create_users(
                    users_data=[
                        admin.UserCreate(
                            email="BULK.USER@example.com",
                            password="another-password-123",
                            full_name="Duplicate User",
                            role=admin.UserRole.student,
                        )
                    ],
                    request=make_request(),
                    _={"role": "admin"},
                    db=db,
                )

            assert error.value.status_code == 400
    finally:
        engine.dispose()
