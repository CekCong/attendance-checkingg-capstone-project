"""RBAC-gated stub endpoints used by role dashboards and security tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditLogModel
from ..security import require_roles

router = APIRouter(tags=["rbac"])


@router.get("/checkins/session/{session_id}")
async def session_checkins(session_id: str, _user=Depends(require_roles("ta", "instructor", "admin"))):
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


@router.get("/audit/")
@router.get("/audit")
@router.get("/audit/logs")
async def audit_logs(_user=Depends(require_roles("admin"))):
    return {"items": [], "total": 0}
