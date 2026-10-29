from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .models import CheckinModel, UserModel, DeviceModel, EnrollmentModel, RiskSignalModel, AuditLogModel
import uuid


CHECKIN_RETENTION_DAYS = 30
ACCOUNT_RETENTION_DAYS = 30


def cleanup_expired_users(db: Session) -> int:
    """Erase account data while retaining a non-login tombstone for audit FKs."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    users = db.query(UserModel).filter(UserModel.scheduled_deletion_at <= now).with_for_update().all()
    for user in users:
        records = db.query(CheckinModel.id).filter(CheckinModel.student_id == user.id)
        db.query(RiskSignalModel).filter(RiskSignalModel.checkin_id.in_(records)).delete(synchronize_session=False)
        db.query(CheckinModel).filter(CheckinModel.student_id == user.id).delete(synchronize_session=False)
        db.query(DeviceModel).filter(DeviceModel.user_id == user.id).delete(synchronize_session=False)
        db.query(EnrollmentModel).filter(EnrollmentModel.student_id == user.id).delete(synchronize_session=False)
        user.email = f"deleted-{user.id}@deleted.example.com"
        user.full_name = "Deleted account"
        user.hashed_password = "!deleted"
        user.face_embedding_hash = None
        user.face_enrolled = False
        user.camera_consent = False
        user.geolocation_consent = False
        user.last_login_at = None
        user.failed_login_attempts = 0
        user.is_active = False
        user.auth_version += 1
        user.scheduled_deletion_at = None
        db.add(AuditLogModel(id=str(uuid.uuid4()), user_id=user.id, action="user_updated",
                            resource_type="user", resource_id=user.id,
                            details="Personal account data erased", success=True))
    db.commit()
    return len(users)


def cleanup_expired_checkins(db: Session) -> int:
    """Schedule legacy check-ins and delete records whose retention has expired."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    unscheduled = (
        db.query(CheckinModel)
        .filter(CheckinModel.scheduled_deletion_at.is_(None))
        .all()
    )
    for checkin in unscheduled:
        checkin.scheduled_deletion_at = (
            checkin.checked_in_at + timedelta(days=CHECKIN_RETENTION_DAYS)
        )

    db.flush()
    deleted = (
        db.query(CheckinModel)
        .filter(CheckinModel.scheduled_deletion_at <= now)
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted
