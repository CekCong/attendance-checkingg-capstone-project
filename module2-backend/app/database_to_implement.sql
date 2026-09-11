CREATE TABLE users (
    id VARCHAR(36) PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    role ENUM('student', 'instructor', 'ta', 'admin') NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    camera_consent BOOLEAN DEFAULT FALSE,
    geolocation_consent BOOLEAN DEFAULT FALSE,
    face_embedding_hash VARCHAR(64) NULL,
    face_enrolled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP NULL,
    scheduled_deletion_at TIMESTAMP NULL
);

CREATE TABLE courses (
    id VARCHAR(36) PRIMARY KEY,
    code VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT NULL,
    semester VARCHAR(20) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    venue_latitude FLOAT NULL,
    venue_longitude FLOAT NULL,
    venue_name VARCHAR(255) NULL,
    geofence_radius_meters FLOAT DEFAULT 100.0,
    require_face_recognition BOOLEAN DEFAULT FALSE,
    require_device_binding BOOLEAN DEFAULT TRUE,
    risk_threshold FLOAT DEFAULT 0.5,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- 1. Create custom ENUM type for status
CREATE TYPE session_status AS ENUM ('scheduled', 'active', 'closed', 'cancelled');

-- 2. Create the sessions table
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id UUID NOT NULL,
    instructor_id UUID NULL,
    name VARCHAR(255) NOT NULL,
    session_type VARCHAR(50) DEFAULT 'lecture',
    description TEXT NULL,
    scheduled_start TIMESTAMPTZ NOT NULL,
    scheduled_end TIMESTAMPTZ NOT NULL,
    checkin_opens_at TIMESTAMPTZ NOT NULL,
    checkin_closes_at TIMESTAMPTZ NOT NULL,
    status session_status NOT NULL DEFAULT 'scheduled',
    actual_start TIMESTAMPTZ NULL,
    actual_end TIMESTAMPTZ NULL,
    venue_latitude DOUBLE PRECISION NULL,
    venue_longitude DOUBLE PRECISION NULL,
    venue_name VARCHAR(255) NULL,
    geofence_radius_meters DOUBLE PRECISION NULL,
    require_liveness_check BOOLEAN DEFAULT TRUE,
    require_face_match BOOLEAN DEFAULT FALSE,
    risk_threshold DOUBLE PRECISION NULL,
    qr_code_secret VARCHAR(64) NULL,
    qr_code_expires_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_course FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    CONSTRAINT fk_instructor FOREIGN KEY (instructor_id) REFERENCES users(id) ON DELETE SET NULL
);

-- 3. Trigger to emulate "ON UPDATE CURRENT_TIMESTAMP"
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
   NEW.updated_at = CURRENT_TIMESTAMP;
   RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_sessions_updated_at
BEFORE UPDATE ON sessions
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE devices (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    device_fingerprint VARCHAR(64) UNIQUE NOT NULL,
    device_name VARCHAR(255) NULL,
    platform VARCHAR(50) NULL,
    browser VARCHAR(100) NULL,
    os_version VARCHAR(50) NULL,
    app_version VARCHAR(50) NULL,
    public_key TEXT NOT NULL,
    public_key_created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    public_key_expires_at TIMESTAMP NULL,
    attestation_passed BOOLEAN DEFAULT FALSE,
    last_attestation_at TIMESTAMP NULL,
    attestation_token TEXT NULL,
    is_trusted BOOLEAN DEFAULT FALSE,
    trust_score VARCHAR(20) DEFAULT 'low',
    is_emulator BOOLEAN DEFAULT FALSE,
    is_rooted_jailbroken BOOLEAN DEFAULT FALSE,
    first_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    total_checkins INTEGER DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    revoked_at TIMESTAMP NULL,
    revocation_reason TEXT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE checkins (
    id VARCHAR(36) PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL,
    student_id VARCHAR(36) NOT NULL,
    device_id VARCHAR(36) NULL,
    status ENUM('pending', 'approved', 'flagged', 'rejected', 'appealed') NOT NULL,
    checked_in_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    verified_at TIMESTAMP NULL,
    latitude FLOAT NULL,
    longitude FLOAT NULL,
    location_accuracy_meters FLOAT NULL,
    distance_from_venue_meters FLOAT NULL,
    liveness_passed BOOLEAN NULL,
    liveness_score FLOAT NULL,
    liveness_challenge_type VARCHAR(50) NULL,
    face_match_passed BOOLEAN NULL,
    face_match_score FLOAT NULL,
    face_embedding_hash VARCHAR(64) NULL,
    risk_score FLOAT NOT NULL DEFAULT 0.0,
    risk_factors TEXT NULL,
    qr_code_verified BOOLEAN DEFAULT FALSE,
    reviewed_by_id VARCHAR(36) NULL,
    reviewed_at TIMESTAMP NULL,
    review_notes TEXT NULL,
    appeal_reason TEXT NULL,
    appealed_at TIMESTAMP NULL,
    scheduled_deletion_at TIMESTAMP NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE SET NULL,
    FOREIGN KEY (reviewed_by_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE risk_signals (
    id VARCHAR(36) PRIMARY KEY,
    checkin_id VARCHAR(36) NOT NULL,
    signal_type ENUM(
        'geo_out_of_bounds', 'impossible_travel', 'geo_accuracy_low',
        'vpn_detected', 'proxy_detected', 'tor_detected', 'suspicious_ip',
        'device_unknown', 'device_emulator', 'device_rooted', 'attestation_failed',
        'rapid_succession', 'unusual_time', 'pattern_anomaly',
        'liveness_failed', 'liveness_low_confidence', 'deepfake_suspected', 'replay_suspected',
        'face_match_failed', 'face_match_low_confidence'
    ) NOT NULL,
    severity ENUM('low', 'medium', 'high', 'critical') NOT NULL,
    confidence FLOAT NOT NULL DEFAULT 1.0,
    details TEXT NULL,
    weight FLOAT NOT NULL DEFAULT 0.1,
    detected_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_risk_signals_checkin FOREIGN KEY (checkin_id) REFERENCES checkins(id) ON DELETE CASCADE
);

CREATE TABLE audit_logs (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NULL,
    action ENUM(
        'login_success',
        'login_failed',
        'logout',
        'user_created',
        'checkin_attempted',
        'checkin_approved',
        'checkin_rejected',
        'data_exported',
        'security_violation'
    ) NOT NULL,
    resource_type VARCHAR(50) NULL,
    resource_id VARCHAR(36) NULL,
    ip_address VARCHAR(45) NULL,
    user_agent VARCHAR(500) NULL,
    device_id VARCHAR(36) NULL,
    details TEXT NULL,
    success BOOLEAN DEFAULT TRUE,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_audit_logs_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_audit_logs_user_id (user_id),
    INDEX idx_audit_logs_action (action),
    INDEX idx_audit_logs_timestamp (timestamp),
    INDEX idx_audit_logs_resource (resource_type, resource_id),
    INDEX idx_audit_logs_ip_address (ip_address)
);