"""Conversation history, share links, and message feedback."""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.db import get_db
from backend.app.models_db import Conversation, Message, Share, User
from backend.app.services.auth import require_user

router = APIRouter(tags=["conversations"])


class ConversationCreate(BaseModel):
    title: str = Field(default="新对话", max_length=200)


class ConversationRename(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    payload: Optional[dict[str, Any]] = None
    feedback: Optional[str] = None
    created_at: datetime


class ConversationDetail(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: List[MessageOut]


class FeedbackBody(BaseModel):
    value: Optional[str] = None


class ShareOut(BaseModel):
    token: str
    url_path: str


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _owned_conversation(db: Session, conversation_id: str, user: User) -> Conversation:
    conv = db.get(Conversation, conversation_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conv


def _message_out(msg: Message) -> MessageOut:
    payload = None
    if msg.payload_json:
        try:
            payload = json.loads(msg.payload_json)
        except json.JSONDecodeError:
            payload = None
    return MessageOut(
        id=msg.id,
        role=msg.role,
        content=msg.content,
        payload=payload,
        feedback=msg.feedback,
        created_at=msg.created_at,
    )


@router.get("/api/conversations", response_model=List[ConversationSummary])
def list_conversations(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> List[ConversationSummary]:
    rows = db.scalars(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .options(selectinload(Conversation.messages))
        .order_by(Conversation.updated_at.desc())
    ).all()
    return [
        ConversationSummary(
            id=conv.id,
            title=conv.title,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            message_count=len(conv.messages),
        )
        for conv in rows
    ]


@router.post("/api/conversations", response_model=ConversationSummary)
def create_conversation(
    body: ConversationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> ConversationSummary:
    now = _utcnow()
    conv = Conversation(user_id=user.id, title=(body.title or "新对话")[:200], created_at=now, updated_at=now)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return ConversationSummary(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=0,
    )


@router.get("/api/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> ConversationDetail:
    conv = db.scalar(
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .options(selectinload(Conversation.messages))
    )
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return ConversationDetail(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[_message_out(m) for m in conv.messages],
    )


@router.patch("/api/conversations/{conversation_id}", response_model=ConversationSummary)
def rename_conversation(
    conversation_id: str,
    body: ConversationRename,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> ConversationSummary:
    conv = _owned_conversation(db, conversation_id, user)
    conv.title = body.title.strip()[:200]
    conv.updated_at = _utcnow()
    db.commit()
    db.refresh(conv)
    return ConversationSummary(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=len(conv.messages),
    )


@router.delete("/api/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    conv = _owned_conversation(db, conversation_id, user)
    db.delete(conv)
    db.commit()
    return {"ok": True}


@router.post("/api/conversations/{conversation_id}/share", response_model=ShareOut)
def share_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> ShareOut:
    conv = _owned_conversation(db, conversation_id, user)
    token = secrets.token_urlsafe(24)
    share = Share(token=token, conversation_id=conv.id)
    db.add(share)
    db.commit()
    return ShareOut(token=token, url_path=f"/share.html?token={token}")


@router.get("/api/shared/{token}", response_model=ConversationDetail)
def get_shared(token: str, db: Session = Depends(get_db)) -> ConversationDetail:
    share = db.scalar(select(Share).where(Share.token == token))
    if not share:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share not found")
    conv = db.scalar(
        select(Conversation)
        .where(Conversation.id == share.conversation_id)
        .options(selectinload(Conversation.messages))
    )
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return ConversationDetail(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[_message_out(m) for m in conv.messages],
    )


@router.post("/api/messages/{message_id}/feedback")
def set_feedback(
    message_id: str,
    body: FeedbackBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    msg = db.get(Message, message_id)
    if not msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    conv = db.get(Conversation, msg.conversation_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    if msg.role != "assistant":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only assistant messages accept feedback")
    if body.value is not None and body.value not in ("up", "down"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="feedback must be up, down, or null")
    msg.feedback = body.value
    db.commit()
    return {"ok": True, "feedback": msg.feedback}
