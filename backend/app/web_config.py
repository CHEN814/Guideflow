"""Web/auth runtime configuration (env-driven, cloud-safe defaults)."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from backend.app.settings import ROOT_DIR

# Process-level cache so Depends(get_web_config) does not mint a new HMAC secret
# on every request when AUTH_SECRET is unset (that would invalidate all sessions).
_cached_config: Optional["WebConfig"] = None


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _parse_origins(raw: str | None) -> List[str]:
    if not raw or not str(raw).strip():
        return [
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:8001",
            "http://localhost:8001",
        ]
    return [item.strip() for item in str(raw).split(",") if item.strip()]


def _dev_auth_secret(data_dir: Path) -> str:
    """Stable dev secret across reload; production must set AUTH_SECRET."""
    path = data_dir / ".auth_secret"
    if path.is_file():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    secret = secrets.token_hex(32)
    path.write_text(secret, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return secret


@dataclass(frozen=True)
class WebConfig:
    database_url: str
    auth_secret: str
    session_ttl_seconds: int
    cors_origins: List[str]
    cookie_name: str
    cookie_secure: bool
    cookie_samesite: str
    cookie_max_age: int
    auth_rate_limit_per_minute: int
    allow_password_reset: bool


def load_web_config(*, force_reload: bool = False) -> WebConfig:
    global _cached_config
    if _cached_config is not None and not force_reload:
        return _cached_config

    # Ensure .env is loaded even if this runs before load_settings().
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT_DIR / ".env", encoding="utf-8-sig")
    except Exception:
        pass

    data_dir = ensure_data_dir()
    default_db = f"sqlite:///{(ROOT_DIR / 'data' / 'app.db').as_posix()}"
    database_url = os.getenv("DATABASE_URL", default_db).strip() or default_db
    auth_secret = os.getenv("AUTH_SECRET", "").strip().strip("'\"")
    if not auth_secret:
        # Dev fallback only; production MUST set AUTH_SECRET.
        auth_secret = _dev_auth_secret(data_dir)

    session_ttl = int(os.getenv("AUTH_SESSION_TTL", str(60 * 60 * 24 * 14)))
    cookie_samesite = (os.getenv("COOKIE_SAMESITE", "lax") or "lax").strip().lower()
    if cookie_samesite not in ("lax", "strict", "none"):
        cookie_samesite = "lax"

    _cached_config = WebConfig(
        database_url=database_url,
        auth_secret=auth_secret,
        session_ttl_seconds=session_ttl,
        cors_origins=_parse_origins(os.getenv("CORS_ORIGINS")),
        cookie_name=os.getenv("AUTH_COOKIE_NAME", "guideflow_session").strip() or "guideflow_session",
        cookie_secure=_as_bool(os.getenv("COOKIE_SECURE"), default=False),
        cookie_samesite=cookie_samesite,
        cookie_max_age=session_ttl,
        auth_rate_limit_per_minute=int(os.getenv("AUTH_RATE_LIMIT_PER_MINUTE", "20")),
        # Local/demo reset without email. Disable in production (set AUTH_ALLOW_PASSWORD_RESET=0).
        allow_password_reset=_as_bool(os.getenv("AUTH_ALLOW_PASSWORD_RESET"), default=True),
    )
    return _cached_config


def reset_web_config_cache() -> None:
    """Tests only: clear cached config so env changes take effect."""
    global _cached_config
    _cached_config = None


def ensure_data_dir() -> Path:
    data_dir = ROOT_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir
