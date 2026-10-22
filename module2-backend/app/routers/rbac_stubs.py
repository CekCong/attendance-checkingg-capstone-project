"""RBAC-gated stub endpoints used by role dashboards and security tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditLogModel, SessionModel
from ..security import require_roles
from ..course_access import require_course_staff_access

router = APIRouter(tags=["rbac"])


@router.get("/checkins/session/{session_id}")
async def session_checkins(
    session_id: str,
    _user=Depends(require_roles("ta", "instructor", "admin")),
    db: Session = Depends(get_db),
):
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID '{session_id}' not found.",
        )
    if _user.get("role") in {"instructor", "ta"}:
        require_course_staff_access(db, _user, session.course_id)
    return []


@router.get("/audit/summary")
async def audit_summary(
    days: int = Query(7, ge=1, le=365),
    _user=Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    period_start = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    action_counts = (
        db.query(AuditLogModel.action, func.count(AuditLogModel.id))
        .filter(AuditLogModel.timestamp >= period_start)
        .group_by(AuditLogModel.action)
        .all()
    )
    by_action = {
        action.value if hasattr(action, "value") else str(action): count
        for action, count in action_counts
    }

    return {
        "period_days": days,
        "total_logs": sum(by_action.values()),
        "by_action": by_action,
    }
