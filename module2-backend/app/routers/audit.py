import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditLogModel
from ..security import require_roles


class AuditAction(str, Enum):
    login_success = "login_success"
    login_failed = "login_failed"
    logout = "logout"
    user_created = "user_created"
    user_updated = "user_updated"
    checkin_attempted = "checkin_attempted"
    checkin_approved = "checkin_approved"
    checkin_flagged = "checkin_flagged"
    checkin_rejected = "checkin_rejected"
    checkin_appealed = "checkin_appealed"
    checkin_reviewed = "checkin_reviewed"
    session_created = "session_created"
    session_updated = "session_updated"
    session_deleted = "session_deleted"
    enrollment_added = "enrollment_added"
    enrollment_removed = "enrollment_removed"
    device_registered = "device_registered"
    face_enrolled = "face_enrolled"
    data_exported = "data_exported"
    security_violation = "security_violation"

# --- SQLAlchemy Model ---
from ..models import AuditLogModel as AuditLog

class AuditLogCreate(BaseModel):
    action: AuditAction
    resource_type: Optional[str] = Field(None, max_length=50)
    resource_id: Optional[str] = Field(None, max_length=36)
    device_id: Optional[str] = Field(None, max_length=36)
    details: Optional[str] = None
    success: bool = True


class AuditLogResponse(BaseModel):
    id: str
    user_id: Optional[str] = None
    action: AuditAction
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    device_id: Optional[str] = None
    details: Optional[str] = None
    success: bool
    timestamp: datetime

    class Config:
        from_attributes = True


class AuditLogListResponse(BaseModel):
    items: List[AuditLogResponse]
    total: int
    limit: int
    offset: int


router = APIRouter(prefix="/audit", tags=["Audit Logs"])


@router.get("/logs", response_model=AuditLogListResponse)
@router.get("", response_model=AuditLogListResponse)
@router.get("/", response_model=AuditLogListResponse)
def get_audit_logs(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user_id: Optional[str] = Query(None),
    action: Optional[AuditAction] = Query(None),
    resource_type: Optional[str] = Query(None),
    success: Optional[bool] = Query(None),
    _user: Dict[str, Any] = Depends(require_roles("instructor", "admin")),
    db: Session = Depends(get_db),
):
    query = db.query(AuditLogModel)
    if user_id:
        query = query.filter(AuditLogModel.user_id == user_id)
    if action:
        query = query.filter(AuditLogModel.action == action.value)
    if resource_type:
        query = query.filter(AuditLogModel.resource_type == resource_type)
    if success is not None:
        query = query.filter(AuditLogModel.success == success)

    total = query.count()
    items = (
        query.order_by(AuditLogModel.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("/logs", response_model=AuditLogResponse, status_code=status.HTTP_201_CREATED)
def create_audit_log(
    payload: AuditLogCreate,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    audit_entry = AuditLogModel(
        id=str(uuid.uuid4()),
        user_id=current_user.get("id"),
        action=payload.action.value,
        resource_type=payload.resource_type,
        resource_id=payload.resource_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        device_id=payload.device_id,
        details=payload.details,
        success=payload.success,
    )
    db.add(audit_entry)
    db.commit()
    db.refresh(audit_entry)
    return audit_entry

@router.get("/summary")
async def get_audit_summary(
    days: int = 7,
    _admin: Dict[str, Any] = Depends(require_roles("admin")),
):
    return {
        "period_days": days,
        "total_logs": 0,
        "by_action": {},
    }
