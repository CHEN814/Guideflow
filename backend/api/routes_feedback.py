"""Doctor feedback API with simple rule-based categorization."""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.models_db import DoctorFeedback, Message, User
from backend.app.services.auth import get_optional_user
from backend.app.services.feedback_classifier import CATEGORY_LABELS, classify_feedback, label_for

router = APIRouter(prefix="/api/feedback", tags=["feedback"])

CATEGORY_LABELS_LIST = [label_for(k) for k in CATEGORY_LABELS]


class FeedbackIn(BaseModel):
    conversation_id: Optional[str] = None
    message_id: Optional[str] = None
    question: str = ""
    answer: str = ""
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    helpful: Optional[str] = Field(default=None, pattern="^(yes|no)$")
    category: Optional[str] = None
    comment: str = ""

    @model_validator(mode="after")
    def _clean(self):
        self.question = (self.question or "").strip()
        self.answer = (self.answer or "").strip()
        self.comment = (self.comment or "").strip()
        return self


class FeedbackOut(BaseModel):
    id: str
    primary_category: str
    auto_primary: str
    auto_tags: list[str]


class FeedbackSummaryOut(BaseModel):
    total: int
    categories: dict[str, int]


class FeedbackItemOut(BaseModel):
    id: str
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None
    answer_message_id: Optional[str] = None
    question: str
    answer: str
    rating: Optional[int] = None
    helpful: Optional[str] = None
    primary_category: str
    auto_primary: str
    auto_tags: list[str]
    comment: str
    created_at: str


class FeedbackListOut(BaseModel):
    total: int
    items: list[FeedbackItemOut]


def _json_list(raw: str) -> list[str]:
    try:
        parsed = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


@router.post("", response_model=FeedbackOut)
def submit_feedback(
    body: FeedbackIn,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
) -> FeedbackOut:
    msg = db.get(Message, body.message_id) if body.message_id else None

    clf = classify_feedback(body.comment or body.answer or body.question, doctor_category=body.category, rating=body.rating, helpful=body.helpful)
    fb = DoctorFeedback(
        user_id=user.id if user else None,
        conversation_id=body.conversation_id or (msg.conversation_id if msg else None),
        answer_message_id=msg.id if msg else None,
        question_text=body.question,
        answer_excerpt=body.answer,
        rating=body.rating,
        helpful=body.helpful,
        primary_category=body.category or label_for(clf.primary),
        categories_json=json.dumps(clf.tags, ensure_ascii=False),
        comment=body.comment,
        auto_primary=label_for(clf.primary),
        auto_tags_json=json.dumps(clf.tags, ensure_ascii=False),
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return FeedbackOut(id=fb.id, primary_category=fb.primary_category, auto_primary=fb.auto_primary, auto_tags=clf.tags)


@router.get("/summary", response_model=FeedbackSummaryOut)
def feedback_summary(db: Session = Depends(get_db)) -> FeedbackSummaryOut:
    rows = db.execute(select(DoctorFeedback.primary_category, func.count(DoctorFeedback.id)).group_by(DoctorFeedback.primary_category)).all()
    categories = {label: int(count) for label, count in rows}
    for label in CATEGORY_LABELS_LIST:
        categories.setdefault(label, 0)
    return FeedbackSummaryOut(total=sum(categories.values()), categories=categories)


@router.get("/list", response_model=FeedbackListOut)
def feedback_list(
    limit: int = 50,
    offset: int = 0,
    category: Optional[str] = None,
    rating: Optional[int] = None,
    q: str = "",
    db: Session = Depends(get_db),
) -> FeedbackListOut:
    safe_limit = max(1, min(int(limit), 200))
    safe_offset = max(0, int(offset))
    filters = []
    category = (category or "").strip()
    q = (q or "").strip()
    if category:
        filters.append(DoctorFeedback.primary_category == category)
    if rating is not None and 1 <= int(rating) <= 5:
        filters.append(DoctorFeedback.rating == int(rating))
    if q:
        like = f"%{q}%"
        filters.append(
            or_(
                DoctorFeedback.question_text.like(like),
                DoctorFeedback.answer_excerpt.like(like),
                DoctorFeedback.comment.like(like),
            )
        )

    base_query = select(DoctorFeedback)
    count_query = select(func.count(DoctorFeedback.id))
    for condition in filters:
        base_query = base_query.where(condition)
        count_query = count_query.where(condition)

    total = int(db.execute(count_query).scalar_one() or 0)
    rows = db.execute(
        base_query
        .order_by(DoctorFeedback.created_at.desc())
        .offset(safe_offset)
        .limit(safe_limit)
    ).scalars().all()
    items = [
        FeedbackItemOut(
            id=fb.id,
            user_id=fb.user_id,
            conversation_id=fb.conversation_id,
            answer_message_id=fb.answer_message_id,
            question=fb.question_text,
            answer=fb.answer_excerpt,
            rating=fb.rating,
            helpful=fb.helpful,
            primary_category=fb.primary_category,
            auto_primary=fb.auto_primary,
            auto_tags=_json_list(fb.auto_tags_json),
            comment=fb.comment,
            created_at=fb.created_at.isoformat(),
        )
        for fb in rows
    ]
    return FeedbackListOut(total=total, items=items)
