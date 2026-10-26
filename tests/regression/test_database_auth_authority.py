import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

for parent in Path(__file__).resolve().parents:
    backend_path = parent / "module2-backend"
    if (backend_path / "app").is_dir():
        sys.path.insert(0, str(backend_path))
        break

from app.models import UserModel
from app.security import create_access_token, get_current_user


def test_access_authorization_uses_current_database_user():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    UserModel.__table__.create(engine)

    try:
        with Session(engine) as db:
            user = UserModel(
                id="user-1",
                email="user@example.com",
                full_name="Test User",
                hashed_password="not-used",
                role="student",
                is_active=True,
            )
            db.add(user)
            db.commit()

            token = create_access_token(
                {
                    "id": user.id,
                    "email": "stale@example.com",
                    "role": "admin",
                }
            )
            credentials = HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials=token,
            )

            authenticated_user = asyncio.run(get_current_user(credentials, db))
            assert authenticated_user["email"] == user.email
            assert authenticated_user["role"] == "student"

            user.role = "admin"
            db.commit()
            assert asyncio.run(get_current_user(credentials, db))["role"] == "admin"

            user.is_active = False
            db.commit()
            with pytest.raises(HTTPException) as disabled_error:
                asyncio.run(get_current_user(credentials, db))
            assert disabled_error.value.status_code == 403

            db.delete(user)
            db.commit()
            with pytest.raises(HTTPException) as deleted_error:
                asyncio.run(get_current_user(credentials, db))
            assert deleted_error.value.status_code == 401
    finally:
        engine.dispose()
