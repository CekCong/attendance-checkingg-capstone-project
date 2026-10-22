import uuid
from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

from .models import AuditLogModel


def add_audit_log(
    db: Session,
    request: Request,
    action: str,
    *,
    user_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[str] = None,
    success: bool = True,
) -> None:
    db.add(
        AuditLogModel(
            id=str(uuid.uuid4()),
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            details=details,
            success=success,
        )
    )
