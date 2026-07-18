"""ORM models for auth, conversations, messages, and share links."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    sessions: Mapped[List["AuthSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    conversations: Mapped[List["Conversation"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="sessions")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="新对话", nullable=False)
    # Active root message for the conversation tree (null until first message / after migration).
    active_root_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[List["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )
    shares: Mapped[List["Share"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    # Tree parent (no DB FK — subtree delete handled in Python). Null = root user message.
    parent_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    # Active child along the current branch (sibling selection for n/m).
    active_child_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feedback: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # up | down | null
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class Share(Base):
    __tablename__ = "shares"
    __table_args__ = (UniqueConstraint("token", name="uq_shares_token"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    token: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    conversation: Mapped["Conversation"] = relationship(back_populates="shares")
