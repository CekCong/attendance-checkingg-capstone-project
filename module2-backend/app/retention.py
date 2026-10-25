from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .models import CheckinModel


CHECKIN_RETENTION_DAYS = 30


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
