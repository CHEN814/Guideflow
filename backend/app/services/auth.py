"""Password hashing, session cookies, and auth helpers."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Deque, Dict, Optional, Tuple

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.models_db import AuthSession, User
from backend.app.web_config import WebConfig, load_web_config

_rate_buckets: Dict[str, Deque[float]] = defaultdict(deque)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def hash_session_token(raw_token: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), raw_token.encode("utf-8"), hashlib.sha256).hexdigest()


def create_session_token() -> str:
    return secrets.token_urlsafe(32)


def check_rate_limit(key: str, limit: int, window_seconds: int = 60) -> None:
    now = time.monotonic()
    bucket = _rate_buckets[key]
    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()
    if len(bucket) >= limit:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many attempts, try later")
    bucket.append(now)


def create_auth_session(db: Session, user: User, cfg: WebConfig) -> Tuple[str, AuthSession]:
    raw = create_session_token()
    token_hash = hash_session_token(raw, cfg.auth_secret)
    expires = datetime.now(timezone.utc) + timedelta(seconds=cfg.session_ttl_seconds)
    row = AuthSession(user_id=user.id, token_hash=token_hash, expires_at=expires)
    db.add(row)
    db.commit()
    db.refresh(row)
    return raw, row


def revoke_session(db: Session, raw_token: Optional[str], cfg: WebConfig) -> None:
    if not raw_token:
        return
    token_hash = hash_session_token(raw_token, cfg.auth_secret)
    row = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash))
    if row:
        db.delete(row)
        db.commit()


def get_user_by_session_token(db: Session, raw_token: Optional[str], cfg: WebConfig) -> Optional[User]:
    if not raw_token:
        return None
    token_hash = hash_session_token(raw_token, cfg.auth_secret)
    row = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash))
    if not row:
        return None
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        db.delete(row)
        db.commit()
        return None
    return db.get(User, row.user_id)


def get_web_config() -> WebConfig:
    return load_web_config()


def get_optional_user(
    request: Request,
    db: Session = Depends(get_db),
    cfg: WebConfig = Depends(get_web_config),
) -> Optional[User]:
    raw = request.cookies.get(cfg.cookie_name)
    return get_user_by_session_token(db, raw, cfg)


def require_user(user: Optional[User] = Depends(get_optional_user)) -> User:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return user


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client:
        return request.client.host
    return "unknown"
