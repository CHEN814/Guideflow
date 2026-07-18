"""FastAPI service: QA, auth, conversations, images."""
from __future__ import annotations

import json
import queue
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Iterator, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.routes_auth import router as auth_router
from backend.api.routes_conversations import router as conversations_router
from backend.app.db import get_db, get_session_factory, init_db
from backend.app.models_db import Conversation, Message, User
from backend.app.services.auth import get_optional_user
from backend.app.services.qa import QAService
from backend.app.settings import ROOT_DIR, load_settings
from backend.app.web_config import load_web_config

UTF8_JSON_HEADERS = {"Content-Type": "application/json; charset=utf-8"}


def _is_safe_image_filename(filename: str) -> bool:
    """Reject path traversal; allow Unicode filenames (e.g. full-width colon)."""
    if not filename or filename != Path(filename).name:
        return False
    if not filename.lower().endswith(".png"):
        return False
    if ".." in filename or "/" in filename or "\\" in filename:
        return False
    if any(ord(ch) < 32 for ch in filename):
        return False
    return True


def _fallback_payload(question: str, reason: str) -> dict[str, Any]:
    return {
        "question": question,
        "answer_markdown": (
            "## 结论\n"
            "当前本地知识库索引未就绪，后端暂时切换到降级模式。\n\n"
            "## 建议\n"
            "请先补齐 `data/indexes/bm25_index.pkl` 和相关知识库文件，或者继续使用前端内置示例内容。"
        ),
        "answer_paragraphs": [],
        "sources": [],
        "graph_triples": [],
        "attached_references": [],
        "reference_links": {},
        "verification": {"status": "degraded", "reason": reason},
        "degraded": [reason],
        "run_id": "fallback",
        "trace_path": "fallback",
        "figures": [],
        "trace": {
            "retrieval_stages": [],
            "rerank_comparison": [],
            "graph_steps": [],
            "verification": {"status": "degraded", "reason": reason},
            "evidence_hits": [],
            "panel_hint": {"mode": "fallback", "evidence_count": 0, "graph_count": 0},
        },
    }


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_parent_message(
    db: Session,
    *,
    conv: Conversation,
    parent_message_id: Optional[str],
) -> Optional[Message]:
    """Return parent message if it belongs to this conversation; else None (treat as new root)."""
    if not parent_message_id:
        return None
    parent = db.get(Message, parent_message_id)
    if parent is None or parent.conversation_id != conv.id:
        return None
    return parent


def _persist_qa_turn(
    *,
    user: Optional[User],
    conversation_id: Optional[str],
    question: str,
    payload: dict[str, Any],
    parent_message_id: Optional[str] = None,
    regenerate: bool = False,
) -> Optional[dict[str, str]]:
    """Persist messages on the conversation tree when logged in. Returns message ids."""
    if user is None:
        return None
    factory = get_session_factory()
    db = factory()
    try:
        conv: Optional[Conversation] = None
        if conversation_id:
            conv = db.get(Conversation, conversation_id)
            if conv is None or conv.user_id != user.id:
                conv = None
        if conv is None:
            title = question.strip()[:40] + ("…" if len(question.strip()) > 40 else "")
            conv = Conversation(
                user_id=user.id,
                title=title or "新对话",
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
            db.add(conv)
            db.flush()

        parent = _resolve_parent_message(db, conv=conv, parent_message_id=parent_message_id)
        now = _utcnow()
        user_msg_id: Optional[str] = None
        assistant_msg: Message

        if regenerate:
            # New assistant sibling under an existing user node.
            if parent is None or parent.role != "user":
                regenerate = False
            else:
                assistant_msg = Message(
                    conversation_id=conv.id,
                    parent_id=parent.id,
                    role="assistant",
                    content=payload.get("answer_markdown") or "",
                    payload_json=json.dumps(payload, ensure_ascii=False),
                    created_at=now,
                )
                db.add(assistant_msg)
                db.flush()
                parent.active_child_id = assistant_msg.id
                user_msg_id = parent.id

        if not regenerate:
            # New user (+ assistant) under parent (assistant leaf, or root if None).
            user_parent_id = parent.id if parent is not None else None
            user_msg = Message(
                conversation_id=conv.id,
                parent_id=user_parent_id,
                role="user",
                content=question,
                created_at=now,
            )
            db.add(user_msg)
            db.flush()
            assistant_msg = Message(
                conversation_id=conv.id,
                parent_id=user_msg.id,
                role="assistant",
                content=payload.get("answer_markdown") or "",
                payload_json=json.dumps(payload, ensure_ascii=False),
                created_at=now,
            )
            db.add(assistant_msg)
            db.flush()
            user_msg.active_child_id = assistant_msg.id
            if parent is None:
                conv.active_root_id = user_msg.id
            else:
                parent.active_child_id = user_msg.id
            user_msg_id = user_msg.id

        conv.updated_at = now
        if conv.title in ("新对话", "") and question.strip():
            conv.title = question.strip()[:40] + ("…" if len(question.strip()) > 40 else "")
        db.commit()
        return {
            "conversation_id": conv.id,
            "user_message_id": user_msg_id or "",
            "assistant_message_id": assistant_msg.id,
        }
    except Exception:
        db.rollback()
        return None
    finally:
        db.close()


def _iter_sse_from_sync_generator(sync_gen: Iterator[dict]) -> Iterator[bytes]:
    for event in sync_gen:
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")


def _sse_queue_bridge(sync_gen: Iterator[dict]) -> AsyncGenerator[bytes, None]:
    """Run a blocking generator in a thread and yield SSE bytes asynchronously."""
    q: queue.Queue[Optional[bytes]] = queue.Queue(maxsize=32)

    def worker() -> None:
        try:
            for chunk in _iter_sse_from_sync_generator(sync_gen):
                q.put(chunk)
        except Exception as exc:  # pragma: no cover
            err = {"type": "error", "detail": str(exc)}
            q.put(f"data: {json.dumps(err, ensure_ascii=False)}\n\n".encode("utf-8"))
        finally:
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    async def agen() -> AsyncGenerator[bytes, None]:
        while True:
            item = await __import__("asyncio").to_thread(q.get)
            if item is None:
                break
            yield item

    return agen()


class HistoryTurn(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=0, max_length=8000)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    trace: bool = True
    stream: bool = True
    conversation_id: Optional[str] = None
    history: Optional[list[HistoryTurn]] = None
    # Tree attachment: parent node id (assistant leaf for follow-up, user for regen, etc.)
    parent_message_id: Optional[str] = None
    # When True, only create a new assistant sibling under parent_message_id (must be user).
    regenerate: bool = False


def create_app() -> FastAPI:
    settings = load_settings()
    web_cfg = load_web_config()
    init_db()
    qa_service = QAService(settings)

    app = FastAPI(title="Guideflow QA API", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=web_cfg.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    app.include_router(auth_router)
    app.include_router(conversations_router)

    frontend_dir = ROOT_DIR / "frontend"
    if frontend_dir.is_dir():
        app.mount("/app", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

    @app.get("/health")
    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/ask")
    async def ask(
        body: AskRequest,
        request: Request,
        db: Session = Depends(get_db),
        user: Optional[User] = Depends(get_optional_user),
    ) -> Any:
        nonlocal qa_service
        service = qa_service

        history_payload = [
            {"role": turn.role, "content": turn.content}
            for turn in (body.history or [])
            if turn.content.strip()
        ][-8:]

        if not body.stream:
            try:
                result = service.ask(
                    body.question,
                    trace_enabled=body.trace,
                    history=history_payload,
                )
                payload_obj = result.to_web_payload()
            except Exception as exc:  # pragma: no cover
                payload_obj = _fallback_payload(body.question, str(exc))
            ids = _persist_qa_turn(
                user=user,
                conversation_id=body.conversation_id,
                question=body.question,
                payload=payload_obj,
                parent_message_id=body.parent_message_id,
                regenerate=body.regenerate,
            )
            if ids:
                payload_obj["conversation_id"] = ids["conversation_id"]
                payload_obj["user_message_id"] = ids["user_message_id"]
                payload_obj["assistant_message_id"] = ids["assistant_message_id"]
            return JSONResponse(content=payload_obj, headers=UTF8_JSON_HEADERS)

        def event_gen() -> Iterator[dict]:
            try:
                final_payload: Optional[dict] = None
                for event in service.ask_stream(
                    body.question,
                    trace_enabled=body.trace,
                    history=history_payload,
                ):
                    if event.get("type") == "final":
                        final_payload = event.get("payload") or {}
                        ids = _persist_qa_turn(
                            user=user,
                            conversation_id=body.conversation_id,
                            question=body.question,
                            payload=final_payload,
                            parent_message_id=body.parent_message_id,
                            regenerate=body.regenerate,
                        )
                        if ids and isinstance(final_payload, dict):
                            final_payload["conversation_id"] = ids["conversation_id"]
                            final_payload["user_message_id"] = ids["user_message_id"]
                            final_payload["assistant_message_id"] = ids["assistant_message_id"]
                            event = {"type": "final", "payload": final_payload}
                    yield event
                if final_payload is None:
                    fallback = _fallback_payload(body.question, "empty_stream")
                    yield {"type": "final", "payload": fallback}
            except Exception as exc:  # pragma: no cover
                fallback = _fallback_payload(body.question, str(exc))
                yield {"type": "token", "text": fallback.get("answer_markdown", "")}
                yield {"type": "final", "payload": fallback}

        return StreamingResponse(
            _sse_queue_bridge(event_gen()),
            media_type="text/event-stream; charset=utf-8",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/images/{filename}")
    def get_image(filename: str) -> FileResponse:
        if not _is_safe_image_filename(filename):
            raise HTTPException(status_code=400, detail="Invalid filename")
        current_settings = qa_service.settings
        path = current_settings.page_image_dir / filename
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="Image not found")
        resolved = path.resolve()
        cache_root = current_settings.page_image_dir.resolve()
        try:
            resolved.relative_to(cache_root)
        except ValueError:
            raise HTTPException(status_code=403, detail="Access denied") from None
        return FileResponse(resolved, media_type="image/png")

    app.state.qa_service = qa_service
    app.state.settings = settings
    app.state.web_config = web_cfg
    return app


app = create_app()
