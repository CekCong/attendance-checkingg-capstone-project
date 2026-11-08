"""Create the first administrator through trusted operator/database access only.

From module2-backend: python -m app.bootstrap_admin --email ... --full-name ...
The password is read through a hidden terminal prompt or a private password file.
This command never promotes, reactivates or resets an existing account.
"""
import argparse
import getpass
import os
import stat
import sys
import uuid

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .database import SessionLocal
from .models import AuditLogModel, UserModel
from .routers.auth import RegisterBody, get_password_hash

# All bootstrap processes targeting one PostgreSQL database share this transaction lock.
BOOTSTRAP_LOCK = 0x5341495641444D


def create_initial_admin(db, email: str, full_name: str, password: str) -> str:
    if len(password) < 12 or len(password.encode("utf-8")) > 72:
        raise ValueError("Administrator password must have at least 12 characters and at most 72 UTF-8 bytes")
    try:
        body = RegisterBody(email=email, full_name=full_name, password=password, role="admin")
    except ValidationError:
        raise ValueError("Invalid administrator email, name or password") from None
    try:
        if db.get_bind().dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": BOOTSTRAP_LOCK})
        if db.query(UserModel.id).filter_by(role="admin").first():
            raise ValueError("An administrator already exists; bootstrap cannot create or reset another")
        email = str(body.email).lower().strip()
        if db.query(UserModel.id).filter_by(email=email).first():
            raise ValueError("This email already belongs to an account; bootstrap will not promote it")
        user = UserModel(id=str(uuid.uuid4()), email=email, full_name=body.full_name,
                         hashed_password=get_password_hash(password), role="admin", is_active=True,
                         failed_login_attempts=0)
        db.add(user)
        db.flush()
        user_id = user.id
        db.add(AuditLogModel(id=str(uuid.uuid4()), user_id=user_id, action="user_created",
                            resource_type="user", resource_id=user_id, success=True,
                            user_agent="saiv-bootstrap-admin", details="initial_admin_bootstrap"))
        db.commit()
        return user_id
    except Exception:
        db.rollback()
        raise


def password_from_file(path: str) -> str:
    # Open once and validate the opened file, avoiding path/stat replacement races.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "r", encoding="utf-8") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.geteuid():
            raise ValueError("Password file must be a regular file owned by this operator with mode 0600 or 0400")
        value = source.read(1024)
        if len(value) == 1024:
            raise ValueError("Password file is too long")
        return value.rstrip("\r\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--full-name", required=True)
    parser.add_argument("--password-file", help="Private operator-owned password file; otherwise prompt securely")
    args = parser.parse_args()
    try:
        if args.password_file:
            password = password_from_file(args.password_file)
        elif sys.stdin.isatty():
            password = getpass.getpass("New administrator password: ")
            if password != getpass.getpass("Confirm administrator password: "):
                raise ValueError("Passwords do not match")
        else:
            raise ValueError("Use an interactive terminal or --password-file; passwords are never command-line arguments")
        with SessionLocal() as db:
            user_id = create_initial_admin(db, args.email, args.full_name, password)
        print(f"Created initial administrator {user_id}")
        return 0
    except (ValueError, OSError) as error:
        # These messages contain no supplied password or connection URL.
        print(str(error), file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print("Administrator creation failed; no partial account was committed. Check database configuration.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
