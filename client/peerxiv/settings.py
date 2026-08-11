from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BASE_DIR.parent
DEVELOPMENT_SECRET = "peerxiv-development-only"


def _csv_env(name: str, default: str = "") -> tuple[str, ...] | None:
    values = tuple(value.strip() for value in os.getenv(name, default).split(",") if value.strip())
    return values or None


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _trusted_hosts() -> tuple[str, ...] | None:
    values = list(_csv_env("PEERXIV_TRUSTED_HOSTS") or ())
    render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
    if render_hostname and render_hostname not in values:
        values.append(render_hostname)
    return tuple(values) or None


def _database_url() -> str:
    value = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'peerxiv.sqlite3'}")
    # Select psycopg 3 explicitly. This also accepts the legacy postgres:// form
    # still emitted by a few deployment providers.
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg://", 1)
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


class BaseConfig:
    ENVIRONMENT = "base"
    APP_NAME = "PeerXiv"
    API_VERSION = "v1"
    REGISTRATION_MODE = os.getenv("PEERXIV_REGISTRATION_MODE", "open").strip().casefold()
    ALPHA_INVITE_CODE = os.getenv("PEERXIV_ALPHA_INVITE_CODE", "")
    SECRET_KEY = os.getenv("PEERXIV_SECRET_KEY", DEVELOPMENT_SECRET)
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    SESSION_COOKIE_NAME = "peerxiv_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    SESSION_REFRESH_EACH_REQUEST = False
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 30
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024
    MAX_JSON_CONTENT_LENGTH = 2 * 1024 * 1024
    MAX_FORM_MEMORY_SIZE = 512 * 1024
    MAX_FORM_PARTS = 100
    MANUSCRIPT_STORAGE_ROOT = os.getenv(
        "PEERXIV_MANUSCRIPT_STORAGE_ROOT",
        str(BASE_DIR / "uploads" / "manuscripts"),
    )
    MANUSCRIPT_REDIRECT_HOSTS = _csv_env("PEERXIV_MANUSCRIPT_REDIRECT_HOSTS")
    MAX_MANUSCRIPT_BYTES = int(os.getenv("PEERXIV_MAX_MANUSCRIPT_BYTES", str(45 * 1024 * 1024)))
    MAX_MANUSCRIPT_PAGES = int(os.getenv("PEERXIV_MAX_MANUSCRIPT_PAGES", "5000"))
    CLAMAV_HOST = os.getenv("PEERXIV_CLAMAV_HOST") or None
    CLAMAV_PORT = int(os.getenv("PEERXIV_CLAMAV_PORT", "3310"))
    CLAMAV_TIMEOUT = float(os.getenv("PEERXIV_CLAMAV_TIMEOUT", "30"))
    MALWARE_SCAN_REQUIRED = _bool_env("PEERXIV_MALWARE_SCAN_REQUIRED")
    DEFAULT_LICENSE = "CC BY 4.0"
    REDIS_URL = os.getenv("REDIS_URL") or None
    SOCKETIO_MESSAGE_QUEUE = REDIS_URL
    SOCKETIO_CHANNEL = os.getenv("SOCKETIO_CHANNEL", "peerxiv")
    SOCKETIO_ASYNC_MODE = os.getenv("SOCKETIO_ASYNC_MODE", "threading")
    FRONTEND_ORIGINS = _csv_env("PEERXIV_FRONTEND_ORIGINS")
    TRUSTED_HOSTS = _trusted_hosts()
    PROXY_FIX_ENABLED = _bool_env("PEERXIV_PROXY_FIX")
    PROXY_FIX_X_FOR = int(os.getenv("PEERXIV_PROXY_X_FOR", "1"))
    PROXY_FIX_X_PROTO = int(os.getenv("PEERXIV_PROXY_X_PROTO", "1"))
    PROXY_FIX_X_HOST = int(os.getenv("PEERXIV_PROXY_X_HOST", "1"))
    PROXY_FIX_X_PORT = int(os.getenv("PEERXIV_PROXY_X_PORT", "1"))
    PROXY_FIX_X_PREFIX = int(os.getenv("PEERXIV_PROXY_X_PREFIX", "0"))
    SECURITY_HEADERS_ENABLED = True
    HSTS_ENABLED = False
    CONTENT_SECURITY_POLICY = (
        "default-src 'self'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'; "
        "form-action 'self'; "
        "object-src 'none'; "
        "script-src 'self'; "
        "style-src 'self' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
        "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
        "img-src 'self' data:; "
        "connect-src 'self'"
    )
    RATELIMIT_ENABLED = True
    RATELIMIT_HEADERS_ENABLED = True
    RATELIMIT_STORAGE_URI = os.getenv("PEERXIV_RATELIMIT_STORAGE_URI") or REDIS_URL or "memory://"
    RATELIMIT_KEY_PREFIX = os.getenv("PEERXIV_RATELIMIT_KEY_PREFIX", "peerxiv")
    RATELIMIT_IN_MEMORY_FALLBACK_ENABLED = True
    ALLOW_SQLITE_PRODUCTION = _bool_env("PEERXIV_ALLOW_SQLITE_PRODUCTION")
    HOST = os.getenv("PEERXIV_HOST", "127.0.0.1")
    PORT = int(os.getenv("PEERXIV_PORT", "8000"))


class DevelopmentConfig(BaseConfig):
    ENVIRONMENT = "development"
    DEBUG = True
    FRONTEND_ORIGINS = _csv_env(
        "PEERXIV_FRONTEND_ORIGINS",
        "http://127.0.0.1:8000,http://localhost:8000",
    )


class TestingConfig(BaseConfig):
    ENVIRONMENT = "testing"
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SOCKETIO_MESSAGE_QUEUE = None
    FRONTEND_ORIGINS = None
    RATELIMIT_ENABLED = False


class ProductionConfig(BaseConfig):
    ENVIRONMENT = "production"
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"
    HSTS_ENABLED = True
    REGISTRATION_MODE = os.getenv("PEERXIV_REGISTRATION_MODE", "invite").strip().casefold()
    MALWARE_SCAN_REQUIRED = _bool_env("PEERXIV_MALWARE_SCAN_REQUIRED", True)


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def resolve_config(name: str | None = None):
    selected = name or os.getenv("PEERXIV_ENV", "development")
    try:
        return CONFIGS[selected]
    except KeyError as error:
        raise ValueError(f"Unknown PeerXiv configuration: {selected}") from error


def validate_config(config: dict) -> None:
    """Fail fast on production defaults that would silently weaken a deployment."""

    if config.get("ENVIRONMENT") != "production":
        return

    failures: list[str] = []
    secret = str(config.get("SECRET_KEY") or "")
    if secret == DEVELOPMENT_SECRET or len(secret) < 32:
        failures.append("PEERXIV_SECRET_KEY must be a random value of at least 32 characters")

    database_url = str(config.get("SQLALCHEMY_DATABASE_URI") or "")
    if database_url.startswith("sqlite:") and not config.get("ALLOW_SQLITE_PRODUCTION"):
        failures.append(
            "DATABASE_URL must use PostgreSQL (or explicitly set "
            "PEERXIV_ALLOW_SQLITE_PRODUCTION=1 for a single-instance deployment)"
        )

    trusted_hosts = config.get("TRUSTED_HOSTS")
    if not trusted_hosts:
        failures.append("PEERXIV_TRUSTED_HOSTS must list the public deployment host names")

    origins = config.get("FRONTEND_ORIGINS") or ()
    if "*" in origins:
        failures.append("PEERXIV_FRONTEND_ORIGINS cannot contain '*' in production")

    registration_mode = str(config.get("REGISTRATION_MODE") or "")
    if registration_mode not in {"open", "invite", "disabled"}:
        failures.append("PEERXIV_REGISTRATION_MODE must be open, invite, or disabled")
    if registration_mode == "invite" and len(str(config.get("ALPHA_INVITE_CODE") or "")) < 12:
        failures.append("PEERXIV_ALPHA_INVITE_CODE must contain at least 12 characters")

    if config.get("MALWARE_SCAN_REQUIRED") and not config.get("CLAMAV_HOST"):
        failures.append("PEERXIV_CLAMAV_HOST is required when malware scanning is enforced")

    if failures:
        formatted = "\n- ".join(failures)
        raise RuntimeError(f"Unsafe PeerXiv production configuration:\n- {formatted}")
