"""Auth API: register / login / logout / me."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.models_db import User
from backend.app.services.auth import (
    check_rate_limit,
    client_ip,
    create_auth_session,
    get_optional_user,
    get_web_config,
    hash_password,
    revoke_session,
    verify_password,
)
from backend.app.web_config import WebConfig

router = APIRouter(prefix="/api/auth", tags=["auth"])


class AuthBody(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class ResetPasswordBody(BaseModel):
    email: EmailStr
    new_password: str = Field(..., min_length=8, max_length=128)


class UserOut(BaseModel):
    id: str
    email: str


def _set_session_cookie(response: Response, raw_token: str, cfg: WebConfig) -> None:
    response.set_cookie(
        key=cfg.cookie_name,
        value=raw_token,
        max_age=cfg.cookie_max_age,
        httponly=True,
        secure=cfg.cookie_secure,
        samesite=cfg.cookie_samesite,  # type: ignore[arg-type]
        path="/",
    )


def _clear_session_cookie(response: Response, cfg: WebConfig) -> None:
    response.delete_cookie(key=cfg.cookie_name, path="/")


@router.post("/register", response_model=UserOut)
def register(
    body: AuthBody,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    cfg: WebConfig = Depends(get_web_config),
) -> UserOut:
    check_rate_limit(f"register:{client_ip(request)}", cfg.auth_rate_limit_per_minute)
    email = body.email.lower().strip()
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        # Generic message — do not reveal whether email exists in other flows;
        # here register may say "already registered" which is acceptable.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(email=email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    raw, _ = create_auth_session(db, user, cfg)
    _set_session_cookie(response, raw, cfg)
    return UserOut(id=user.id, email=user.email)


@router.post("/login", response_model=UserOut)
def login(
    body: AuthBody,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    cfg: WebConfig = Depends(get_web_config),
) -> UserOut:
    check_rate_limit(f"login:{client_ip(request)}", cfg.auth_rate_limit_per_minute)
    email = body.email.lower().strip()
    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    raw, _ = create_auth_session(db, user, cfg)
    _set_session_cookie(response, raw, cfg)
    return UserOut(id=user.id, email=user.email)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    cfg: WebConfig = Depends(get_web_config),
) -> dict:
    raw = request.cookies.get(cfg.cookie_name)
    revoke_session(db, raw, cfg)
    _clear_session_cookie(response, cfg)
    return {"ok": True}


@router.get("/me", response_model=Optional[UserOut])
def me(user: Optional[User] = Depends(get_optional_user)) -> Optional[UserOut]:
    if user is None:
        return None
    return UserOut(id=user.id, email=user.email)


@router.post("/reset-password")
def reset_password(
    body: ResetPasswordBody,
    request: Request,
    db: Session = Depends(get_db),
    cfg: WebConfig = Depends(get_web_config),
) -> dict:
    """Reset password by email (local/demo). Disable with AUTH_ALLOW_PASSWORD_RESET=0."""
    if not cfg.allow_password_reset:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password reset is disabled. Contact an administrator.",
        )
    check_rate_limit(f"reset:{client_ip(request)}", cfg.auth_rate_limit_per_minute)
    email = body.email.lower().strip()
    user = db.scalar(select(User).where(User.email == email))
    # Same message whether or not the email exists (avoid enumeration).
    if user:
        user.password_hash = hash_password(body.new_password)
        db.commit()
    return {"ok": True, "message": "若该邮箱已注册，密码已更新，请使用新密码登录。"}
