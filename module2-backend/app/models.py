from sqlalchemy import Column, String, Boolean, Integer, Float, Text, DateTime, Enum, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

AUDIT_ACTION_VALUES = (
    'login_success', 'login_failed', 'logout', 'user_created', 'user_updated',
    'checkin_attempted', 'checkin_approved', 'checkin_flagged',
    'checkin_rejected', 'checkin_appealed', 'checkin_reviewed',
    'session_created', 'session_updated', 'session_deleted',
    'enrollment_added', 'enrollment_removed', 'device_registered',
    'face_enrolled', 'data_exported', 'security_violation',
)

class UserModel(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    
    # Converted ENUM type for roles matching the SQL schema
    role = Column(Enum('student', 'instructor', 'ta', 'admin', name="user_role_enum"), nullable=False)
    
    is_active = Column(Boolean, nullable=False, default=True)
    camera_consent = Column(Boolean, default=False)
    geolocation_consent = Column(Boolean, default=False)
    face_embedding_hash = Column(String(64), nullable=True)
    face_enrolled = Column(Boolean, default=False)
    failed_login_attempts = Column(Integer, nullable=False, default=0)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    last_login_at = Column(DateTime, nullable=True)
    scheduled_deletion_at = Column(DateTime, nullable=True)


class CourseModel(Base):
    __tablename__ = "courses"

    id = Column(String(36), primary_key=True)
    code = Column(String(20), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    semester = Column(String(20), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    
    venue_latitude = Column(Float, nullable=True)
    venue_longitude = Column(Float, nullable=True)
    venue_name = Column(String(255), nullable=True)
    geofence_radius_meters = Column(Float, default=100.0)
    
    require_face_recognition = Column(Boolean, default=False)
    require_device_binding = Column(Boolean, default=True)
    risk_threshold = Column(Float, default=0.5)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

class CourseInstructorModel(Base):
    __tablename__ = "course_instructors"

    course_id = Column(String(36), ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True)
    instructor_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)


class EnrollmentModel(Base):
    __tablename__ = "enrollments"

    id = Column(String(36), primary_key=True)
    student_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = Column(String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    
    is_active = Column(Boolean, nullable=False, default=True)
    enrolled_at = Column(DateTime, nullable=False, server_default=func.now())
    dropped_at = Column(DateTime, nullable=True)

    __table_args__ = (
        # Ensures a student cannot duplicate an active/existing enrollment record for the same course
        UniqueConstraint('student_id', 'course_id', name='uq_student_course_enrollment'),
    )


class SessionModel(Base):
    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True)
    course_id = Column(String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    instructor_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False)
    session_type = Column(String(50), default='lecture')
    description = Column(Text, nullable=True)
    
    scheduled_start = Column(DateTime, nullable=False)
    scheduled_end = Column(DateTime, nullable=False)
    checkin_opens_at = Column(DateTime, nullable=False)
    checkin_closes_at = Column(DateTime, nullable=False)
    
    status = Column(Enum('scheduled', 'active', 'closed', 'cancelled', name="session_status_enum"), nullable=False)
    actual_start = Column(DateTime, nullable=True)
    actual_end = Column(DateTime, nullable=True)
    
    venue_latitude = Column(Float, nullable=True)
    venue_longitude = Column(Float, nullable=True)
    venue_name = Column(String(255), nullable=True)
    geofence_radius_meters = Column(Float, nullable=True)
    
    require_liveness_check = Column(Boolean, default=True)
    require_face_match = Column(Boolean, default=False)
    risk_threshold = Column(Float, nullable=True)
    
    qr_code_secret = Column(String(64), nullable=True)
    qr_code_expires_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    course = relationship("CourseModel")

class SessionSeriesModel(Base):
    __tablename__ = "session_series"

    id = Column(String(36), primary_key=True)
    instructor_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    course_id = Column(String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    schedule = Column(Text, nullable=False)


class SessionOccurrenceModel(Base):
    __tablename__ = "session_occurrences"

    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True)
    series_id = Column(String(36), ForeignKey("session_series.id", ondelete="CASCADE"), nullable=False, index=True)


class DeviceModel(Base):
    __tablename__ = "devices"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    device_fingerprint = Column(String(64), unique=True, nullable=False)
    device_name = Column(String(255), nullable=True)
    platform = Column(String(50), nullable=True)
    browser = Column(String(100), nullable=True)
    os_version = Column(String(50), nullable=True)
    app_version = Column(String(50), nullable=True)
    
    public_key = Column(Text, nullable=False)
    public_key_created_at = Column(DateTime, nullable=False, server_default=func.now())
    public_key_expires_at = Column(DateTime, nullable=True)
    
    attestation_passed = Column(Boolean, default=False)
    last_attestation_at = Column(DateTime, nullable=True)
    attestation_token = Column(Text, nullable=True)
    
    is_trusted = Column(Boolean, default=False)
    trust_score = Column(String(20), default='low')
    is_emulator = Column(Boolean, default=False)
    is_rooted_jailbroken = Column(Boolean, default=False)
    
    first_seen_at = Column(DateTime, nullable=False, server_default=func.now())
    last_seen_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    total_checkins = Column(Integer, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    revoked_at = Column(DateTime, nullable=True)
    revocation_reason = Column(Text, nullable=True)


class CheckinModel(Base):
    __tablename__ = "checkins"

    id = Column(String(36), primary_key=True)
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    device_id = Column(String(36), ForeignKey("devices.id", ondelete="SET NULL"), nullable=True)
    
    status = Column(Enum('pending', 'approved', 'flagged', 'rejected', 'appealed', name="checkin_status_enum"), nullable=False)
    checked_in_at = Column(DateTime, nullable=False, server_default=func.now())
    verified_at = Column(DateTime, nullable=True)
    
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    location_accuracy_meters = Column(Float, nullable=True)
    distance_from_venue_meters = Column(Float, nullable=True)
    
    liveness_passed = Column(Boolean, nullable=True)
    liveness_score = Column(Float, nullable=True)
    liveness_challenge_type = Column(String(50), nullable=True)
    
    face_match_passed = Column(Boolean, nullable=True)
    face_match_score = Column(Float, nullable=True)
    face_embedding_hash = Column(String(64), nullable=True)
    
    risk_score = Column(Float, nullable=False, default=0.0)
    risk_factors = Column(Text, nullable=True)
    qr_code_verified = Column(Boolean, default=False)
    
    reviewed_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_notes = Column(Text, nullable=True)
    appeal_reason = Column(Text, nullable=True)
    appealed_at = Column(DateTime, nullable=True)
    scheduled_deletion_at = Column(DateTime, nullable=True)

    session = relationship("SessionModel")
    student = relationship("UserModel", foreign_keys=[student_id])
    reviewer = relationship("UserModel", foreign_keys=[reviewed_by_id])


class RiskSignalModel(Base):
    __tablename__ = "risk_signals"

    id = Column(String(36), primary_key=True)
    checkin_id = Column(String(36), ForeignKey("checkins.id", ondelete="CASCADE"), nullable=False)
    
    signal_type = Column(Enum(
        'geo_out_of_bounds', 'impossible_travel', 'geo_accuracy_low',
        'vpn_detected', 'proxy_detected', 'tor_detected', 'suspicious_ip',
        'device_unknown', 'device_emulator', 'device_rooted', 'attestation_failed',
        'rapid_succession', 'unusual_time', 'pattern_anomaly',
        'liveness_failed', 'liveness_low_confidence', 'deepfake_suspected', 'replay_suspected',
        'face_match_failed', 'face_match_low_confidence',
        name="signal_type_enum"
    ), nullable=False)
    
    severity = Column(Enum('low', 'medium', 'high', 'critical', name="risk_severity_enum"), nullable=False)
    confidence = Column(Float, nullable=False, default=1.0)
    details = Column(Text, nullable=True)
    weight = Column(Float, nullable=False, default=0.1)
    detected_at = Column(DateTime, nullable=False, server_default=func.now())


class AuditLogModel(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    action = Column(Enum(*AUDIT_ACTION_VALUES, name="audit_action_enum"), nullable=False)
    
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(String(36), nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    device_id = Column(String(36), nullable=True)
    details = Column(Text, nullable=True)
    success = Column(Boolean, default=True)
    timestamp = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index('idx_audit_logs_user_id', 'user_id'),
        Index('idx_audit_logs_action', 'action'),
        Index('idx_audit_logs_timestamp', 'timestamp'),
        Index('idx_audit_logs_resource', 'resource_type', 'resource_id'),
        Index('idx_audit_logs_ip_address', 'ip_address'),
    )
