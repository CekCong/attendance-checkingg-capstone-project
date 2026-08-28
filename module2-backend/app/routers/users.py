"""User endpoints with RBAC stubs."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..security import get_current_user, require_roles, user_response
from ..store import get_by_id, list_users

router = APIRouter(prefix="/users", tags=["users"])


class UpdateMeBody(BaseModel):
    full_name: Optional[str] = None
    camera_consent: Optional[bool] = None
    geolocation_consent: Optional[bool] = None


@router.get("/me")
async def get_me(user=Depends(get_current_user)):
    return user_response(user)


@router.put("/me")
async def update_me(body: UpdateMeBody, user=Depends(get_current_user)):
    if body.full_name is not None:
        cleaned = body.full_name.replace("<script>", "").replace("</script>", "")
        user["full_name"] = cleaned
    if body.camera_consent is not None:
        user["camera_consent"] = body.camera_consent
    if body.geolocation_consent is not None:
        user["geolocation_consent"] = body.geolocation_consent
    return user_response(user)


@router.get("/")
async def list_all_users(_admin=Depends(require_roles("admin"))):
    items = list_users()
    return {"items": items, "total": len(items), "limit": 50, "offset": 0}


@router.get("/{user_id}")
async def get_user(user_id: str, current=Depends(get_current_user)):
    if current.get("role") not in {"admin", "instructor", "ta"} and current.get("id") != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    found = get_by_id(user_id)
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user_response(found)
