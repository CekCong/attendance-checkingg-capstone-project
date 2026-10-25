import uuid
from datetime import datetime
from typing import Optional, Any, List
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.orm import declarative_base, sessionmaker
import os
from dotenv import load_dotenv
from ..database import get_db as shared_get_db
from ..models import DeviceModel
from ..security import get_current_user, require_roles
from ..audit import add_audit_log
from ..device_challenge import (
    DEVICE_CHALLENGE_TTL_SECONDS,
    DeviceChallengeStoreError,
    create_device_challenge,
)

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://postgres:your_password@localhost:5432/your_database"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    yield from shared_get_db()

router = APIRouter(prefix="/devices", tags=["Devices"])

# --- Pydantic Schemas ---
class DeviceRegisterRequest(BaseModel):
    device_fingerprint: str = Field(..., max_length=64, description="Unique device hash")
    device_name: Optional[str] = Field(None, max_length=255, description="Friendly name")
    platform: Optional[str] = Field(None, description="Platform type (ios|android|web|desktop)")
    browser: Optional[str] = Field(None, max_length=100)
    public_key: Optional[str] = Field(None, description="PEM encoded public key")

class DeviceUpdateRequest(BaseModel):
    device_name: Optional[str] = Field(None, max_length=255)
    is_trusted: Optional[bool] = Field(None, description="Admin only")
    is_active: Optional[bool] = Field(None, description="Deactivate device")

class DeviceChallengeRequest(BaseModel):
    device_fingerprint: str = Field(..., max_length=64)
    session_id: uuid.UUID

class DeviceChallengeResponse(BaseModel):
    challenge: str
    expires_in: int

class DeviceResponse(BaseModel):
    id: str
    device_fingerprint: Optional[str] = None
    device_name: Optional[str] = None
    platform: Optional[str] = None
    is_trusted: bool
    trust_score: str
    is_active: bool
    first_seen_at: datetime
    last_seen_at: Optional[datetime] = None
    total_checkins: Optional[int] = 0

    class Config:
        orm_mode = True


# --- Helper to extract user info ---
def get_user_id_and_role(current_user: Any):
    user_id = current_user.get("id") if isinstance(current_user, dict) else getattr(current_user, "id", None)
    user_role = current_user.get("role") if isinstance(current_user, dict) else getattr(current_user, "role", "user")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate user credentials."
        )
    return str(user_id), user_role


# --- Endpoints ---

@router.get("/", status_code=status.HTTP_200_OK)
def list_all_devices(
    _current_user: Any = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    """List all registered devices. Requires admin role."""
    devices = db.query(DeviceModel).all()
    return {"items": devices, "total": len(devices)}

@router.post("/", status_code=status.HTTP_201_CREATED, response_model=DeviceResponse)
@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=DeviceResponse)
def register_device(
    payload: DeviceRegisterRequest,
    request: Request,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Register a new device. Requires auth."""
    user_id, _ = get_user_id_and_role(current_user)

    existing_device = db.query(DeviceModel).filter(DeviceModel.device_fingerprint == payload.device_fingerprint).first()
    if existing_device:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A device with this fingerprint is already registered."
        )

    new_device = DeviceModel(
        id=str(uuid.uuid4()),
        user_id=user_id,
        device_fingerprint=payload.device_fingerprint,
        device_name=payload.device_name,
        platform=payload.platform,
        browser=payload.browser,
        public_key=payload.public_key or "",
        is_trusted=False,
        trust_score="low",
        is_active=True,
        total_checkins=0
    )

    db.add(new_device)
    add_audit_log(
        db,
        request,
        "device_registered",
        user_id=user_id,
        resource_type="device",
        resource_id=new_device.id,
        details=f"platform={payload.platform or 'unknown'}",
    )
    db.commit()
    db.refresh(new_device)
    return new_device


@router.get("/my-devices", status_code=status.HTTP_200_OK, response_model=List[DeviceResponse])
def list_my_devices(
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List current user's registered devices. Requires auth."""
    user_id, _ = get_user_id_and_role(current_user)
    devices = db.query(DeviceModel).filter(DeviceModel.user_id == user_id).all()
    return devices


@router.post("/challenge", response_model=DeviceChallengeResponse)
def issue_device_challenge(
    payload: DeviceChallengeRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Issue a one-time challenge for a registered device to sign."""
    user_id, _ = get_user_id_and_role(current_user)
    device = db.query(DeviceModel).filter(
        DeviceModel.device_fingerprint == payload.device_fingerprint,
        DeviceModel.user_id == user_id,
        DeviceModel.is_active.is_(True),
    ).first()
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active registered device not found.",
        )
    if not device.public_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The registered device does not have a public key.",
        )

    try:
        challenge = create_device_challenge(
            user_id,
            device.id,
            str(payload.session_id),
        )
    except DeviceChallengeStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return {
        "challenge": challenge,
        "expires_in": DEVICE_CHALLENGE_TTL_SECONDS,
    }


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_device(
    device_id: str,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove a device. Requires auth (owner or admin)."""
    user_id, user_role = get_user_id_and_role(current_user)

    device = db.query(DeviceModel).filter(DeviceModel.id == device_id).first()
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")

    # Check authorization: must be owner or admin
    if device.user_id != user_id and user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You are neither the owner nor an admin."
        )

    db.delete(device)
    db.commit()
    return None


@router.patch("/{device_id}", status_code=status.HTTP_200_OK, response_model=DeviceResponse)
def update_device(
    device_id: str,
    payload: DeviceUpdateRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update device properties. Requires auth (owner for name/status, admin for trust)."""
    user_id, user_role = get_user_id_and_role(current_user)

    device = db.query(DeviceModel).filter(DeviceModel.id == device_id).first()
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")

    is_owner = (device.user_id == user_id)
    is_admin = (user_role == "admin")

    if not is_owner and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied."
        )

    # Handle update fields respecting permissions
    if payload.device_name is not None:
        if not is_owner and not is_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owner can update device name.")
        device.device_name = payload.device_name

    if payload.is_active is not None:
        if not is_owner and not is_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owner can deactivate device.")
        device.is_active = payload.is_active

    if payload.is_trusted is not None:
        if not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin permission required to update 'is_trusted' status."
            )
        device.is_trusted = payload.is_trusted

    db.commit()
    db.refresh(device)
    return device
