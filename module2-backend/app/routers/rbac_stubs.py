"""RBAC-gated stub endpoints used by role dashboards and security tests."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditLogModel, CheckinModel, DeviceModel, SessionModel, UserModel
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

    checkins = (
        db.query(CheckinModel, UserModel, DeviceModel)
        .join(UserModel, CheckinModel.student_id == UserModel.id)
        .outerjoin(DeviceModel, CheckinModel.device_id == DeviceModel.id)
        .filter(CheckinModel.session_id == session_id)
        .order_by(CheckinModel.checked_in_at.asc())
        .all()
    )
    return [
        {
            "id": checkin.id,
            "student_id": checkin.student_id,
            "student_name": student.full_name,
            "student_email": student.email,
            "status": checkin.status,
            "checked_in_at": checkin.checked_in_at,
            "distance_from_venue_meters": checkin.distance_from_venue_meters,
            "risk_score": checkin.risk_score,
            "risk_factors": json.loads(checkin.risk_factors) if checkin.risk_factors else [],
            "liveness_passed": checkin.liveness_passed,
            "device_trusted": bool(device and device.is_trusted),
        }
        for checkin, student, device in checkins
    ]


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
