"""RBAC-gated stub endpoints used by role dashboards and security tests."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..security import require_roles

router = APIRouter(tags=["rbac"])


@router.get("/checkins/session/{session_id}")
async def session_checkins(session_id: str, _user=Depends(require_roles("ta", "instructor", "admin"))):
    return {"session_id": session_id, "items": [], "total": 0}


@router.get("/audit/")
@router.get("/audit")
@router.get("/audit/logs")
async def audit_logs(_user=Depends(require_roles("admin"))):
    return {"items": [], "total": 0}
