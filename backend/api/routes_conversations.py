"""Conversation history, share links, message feedback, and tree branch ops."""
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
    parent_id: Optional[str] = None
    active_child_id: Optional[str] = None
    created_at: datetime


class ConversationDetail(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    active_root_id: Optional[str] = None
    messages: List[MessageOut]


class FeedbackBody(BaseModel):
    value: Optional[str] = None


class ShareOut(BaseModel):
    token: str
    url_path: str


class ActiveBranchBody(BaseModel):
    message_id: str = Field(..., min_length=1, max_length=36)


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
        parent_id=msg.parent_id,
        active_child_id=msg.active_child_id,
        created_at=msg.created_at,
    )


def _children_map(messages: list[Message]) -> dict[Optional[str], list[Message]]:
    by_parent: dict[Optional[str], list[Message]] = {}
    for m in messages:
        by_parent.setdefault(m.parent_id, []).append(m)
    for kids in by_parent.values():
        kids.sort(key=lambda x: (x.created_at, x.id))
    return by_parent


def _linearize_active_path(
    messages: list[Message],
    active_root_id: Optional[str],
) -> list[Message]:
    """Walk active_child_id from root; fall back to last child when unset."""
    if not messages:
        return []
    by_id = {m.id: m for m in messages}
    by_parent = _children_map(messages)
    roots = by_parent.get(None, [])
    if not roots:
        # Orphaned / legacy: fall back to chronological order
        return sorted(messages, key=lambda m: (m.created_at, m.id))

    start: Optional[Message] = None
    if active_root_id and active_root_id in by_id and by_id[active_root_id].parent_id is None:
        start = by_id[active_root_id]
    if start is None:
        start = roots[-1]

    path: list[Message] = []
    cur: Optional[Message] = start
    seen: set[str] = set()
    while cur is not None and cur.id not in seen:
        seen.add(cur.id)
        path.append(cur)
        kids = by_parent.get(cur.id, [])
        nxt: Optional[Message] = None
        if cur.active_child_id and cur.active_child_id in by_id:
            cand = by_id[cur.active_child_id]
            if cand.parent_id == cur.id:
                nxt = cand
        if nxt is None and kids:
            nxt = kids[-1]
        cur = nxt
    return path


def _collect_subtree_ids(root_id: str, by_parent: dict[Optional[str], list[Message]]) -> list[str]:
    """DFS collect root + all descendants (post-order for safe delete)."""
    out: list[str] = []

    def walk(mid: str) -> None:
        for child in by_parent.get(mid, []):
            walk(child.id)
        out.append(mid)

    walk(root_id)
    return out


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
        active_root_id=conv.active_root_id,
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


@router.post("/api/conversations/{conversation_id}/active-branch")
def set_active_branch(
    conversation_id: str,
    body: ActiveBranchBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    """Point the parent's active_child_id (or conversation active_root_id) at message_id."""
    conv = db.scalar(
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .options(selectinload(Conversation.messages))
    )
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    msg = db.get(Message, body.message_id)
    if not msg or msg.conversation_id != conv.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    if msg.parent_id is None:
        conv.active_root_id = msg.id
    else:
        parent = db.get(Message, msg.parent_id)
        if not parent or parent.conversation_id != conv.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid parent")
        parent.active_child_id = msg.id
    conv.updated_at = _utcnow()
    db.commit()
    return {"ok": True, "active_root_id": conv.active_root_id, "message_id": msg.id}


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
    # Share page expects a linear active path only.
    path = _linearize_active_path(list(conv.messages), conv.active_root_id)
    return ConversationDetail(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        active_root_id=conv.active_root_id,
        messages=[_message_out(m) for m in path],
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


@router.delete("/api/messages/{message_id}")
def delete_message_branch(
    message_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    """Delete a message and its entire subtree; retarget sibling activation."""
    msg = db.get(Message, message_id)
    if not msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    conv = db.scalar(
        select(Conversation)
        .where(Conversation.id == msg.conversation_id)
        .options(selectinload(Conversation.messages))
    )
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    all_msgs = list(conv.messages)
    by_parent = _children_map(all_msgs)
    siblings = by_parent.get(msg.parent_id, [])
    sib_ids = [s.id for s in siblings]
    if msg.id not in sib_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inconsistent tree")

    idx = sib_ids.index(msg.id)
    # Prefer previous sibling, else next.
    if idx > 0:
        fallback = sib_ids[idx - 1]
    elif idx + 1 < len(sib_ids):
        fallback = sib_ids[idx + 1]
    else:
        fallback = None

    to_delete = _collect_subtree_ids(msg.id, by_parent)
    delete_set = set(to_delete)

    if msg.parent_id is None:
        if conv.active_root_id == msg.id or conv.active_root_id in delete_set:
            conv.active_root_id = fallback
    else:
        parent = db.get(Message, msg.parent_id)
        if parent and (parent.active_child_id == msg.id or parent.active_child_id in delete_set):
            parent.active_child_id = fallback

    # Clear active_child_id pointers into the deleted set from survivors.
    for m in all_msgs:
        if m.id in delete_set:
            continue
        if m.active_child_id in delete_set:
            m.active_child_id = None

    for mid in to_delete:
        row = db.get(Message, mid)
        if row:
            db.delete(row)

    conv.updated_at = _utcnow()
    db.commit()
    return {"ok": True, "deleted": to_delete, "fallback_id": fallback}
