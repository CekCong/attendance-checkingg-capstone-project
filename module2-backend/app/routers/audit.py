import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import Column, String, Text, Boolean, DateTime, Enum as SQLEnum, ForeignKey, create_engine, func
from sqlalchemy.orm import declarative_base, sessionmaker, Session
import enum
import os
from dotenv import load_dotenv

from app.security import get_current_user, require_roles

# --- Database Setup ---
load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://postgres:your_password@localhost:5432/your_database"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Enum Definition matching PostgreSQL CREATE TABLE ---
class AuditAction(str, enum.Enum):
    login_success = "login_success"
    login_failed = "login_failed"
    logout = "logout"
    user_created = "user_created"
    checkin_attempted = "checkin_attempted"
    checkin_approved = "checkin_approved"
    checkin_rejected = "checkin_rejected"
    data_exported = "data_exported"
    security_violation = "security_violation"

# --- SQLAlchemy Model ---
from models import AuditLogModel as AuditLog

# --- Pydantic Schemas ---
class AuditLogCreate(BaseModel):
    user_id: Optional[str] = None
    action: AuditAction
    resource_type: Optional[str] = Field(None, max_length=50)
    resource_id: Optional[str] = Field(None, max_length=36)
    ip_address: Optional[str] = Field(None, max_length=45)
    user_agent: Optional[str] = Field(None, max_length=500)
    device_id: Optional[str] = Field(None, max_length=36)
    details: Optional[str] = None
    success: Optional[bool] = True

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

# --- Router Implementation (app/routers/audit.py) ---
router = APIRouter(prefix="/audit", tags=["Audit Logs"])

# GET /audit/logs - Retrieve audit logs
@router.get("/logs", response_model=AuditLogListResponse)
def get_audit_logs(
    skip: int = Query(0, ge=0, alias="offset"),
    limit: int = Query(50, ge=1, le=100),
    user_id: Optional[str] = Query(None, description="Filter logs by User ID"),
    action: Optional[AuditAction] = Query(None, description="Filter logs by Action type"),
    resource_type: Optional[str] = Query(None, description="Filter logs by Resource Type"),
    success: Optional[bool] = Query(None, description="Filter logs by success/failure status"),
    _admin: Dict[str, Any] = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    query = db.query(AuditLog)

    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if action:
        query = query.filter(AuditLog.action == action)
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)
    if success is not None:
        query = query.filter(AuditLog.success == success)

    total = query.count()
    items = query.order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit).all()

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": skip
    }


# POST /audit/logs - Create audit entry
@router.post("/logs", response_model=AuditLogResponse, status_code=status.HTTP_201_CREATED)
def create_audit_log(
    payload: AuditLogCreate,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Auto-populate user_id, ip_address, and user_agent if omitted in payload
    log_data = payload.model_dump()
    if not log_data.get("user_id"):
        log_data["user_id"] = current_user.get("id")
    if not log_data.get("ip_address"):
        log_data["ip_address"] = request.client.host if request.client else None
    if not log_data.get("user_agent"):
        log_data["user_agent"] = request.headers.get("user-agent")

    audit_entry = AuditLog(
        id=str(uuid.uuid4()),
        **log_data
    )

    db.add(audit_entry)
    db.commit()
    db.refresh(audit_entry)
    return audit_entry