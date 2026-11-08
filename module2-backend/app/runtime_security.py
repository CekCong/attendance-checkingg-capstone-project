"""Safe registration defaults and deployment authentication prerequisites."""
import os

DEVELOPMENT_SECRET = "saiv-dev-secret-change-me"


def biometric_demo_enabled() -> bool:
    return (os.getenv("SAIV_ENV", "development") in {"development", "test"}
            and os.getenv("BIOMETRIC_DEMO_MODE", "false").lower() == "true")


def privileged_registration_enabled() -> bool:
    # Compatibility for isolated teaching/test fixtures, never a deployment mode.
    return (os.getenv("SAIV_ENV", "development") == "test" and
            os.getenv("ALLOW_PRIVILEGED_SELF_REGISTRATION", "false").lower() == "true")


def validate_runtime_security(signing_key: str | None = None) -> None:
    mode = os.getenv("SAIV_ENV", "development")
    if mode not in {"development", "test", "production"}:
        raise RuntimeError("SAIV_ENV must be development, test or production")
    opted_in = os.getenv("ALLOW_PRIVILEGED_SELF_REGISTRATION", "false").lower() == "true"
    if opted_in and mode != "test":
        raise RuntimeError("Privileged self-registration is allowed only in isolated SAIV_ENV=test instances")
    if mode == "production":
        if os.getenv("BIOMETRIC_DEMO_MODE", "false").lower() == "true":
            raise RuntimeError("BIOMETRIC_DEMO_MODE is prohibited in production")
        secret = signing_key if signing_key is not None else os.getenv("SECRET_KEY", "")
        if secret == DEVELOPMENT_SECRET or len(secret.encode()) < 32:
            raise RuntimeError("Production requires an independently generated SECRET_KEY of at least 32 bytes")
        if os.getenv("COOKIE_SECURE", "false").lower() != "true":
            raise RuntimeError("Production requires COOKIE_SECURE=true and HTTPS ingress")
