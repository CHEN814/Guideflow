"""SQLAlchemy engine / session helpers for app persistence."""
from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.app.web_config import ensure_data_dir, load_web_config

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker[Session]] = None


class Base(DeclarativeBase):
    pass


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is not None:
        return _engine

    ensure_data_dir()
    cfg = load_web_config()
    connect_args = {}
    if cfg.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    _engine = create_engine(
        cfg.database_url,
        connect_args=connect_args,
        future=True,
    )

    if cfg.database_url.startswith("sqlite"):

        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def _migrate_message_tree_columns(engine: Engine) -> None:
    """Idempotent ADD COLUMN for conversation tree fields (SQLite)."""
    cfg = load_web_config()
    if not cfg.database_url.startswith("sqlite"):
        # Non-SQLite: create_all handles new DBs; ALTER for existing left to ops.
        return

    with engine.begin() as conn:
        conv_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(conversations)")).fetchall()}
        msg_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(messages)")).fetchall()}
        if "active_root_id" not in conv_cols:
            conn.execute(text("ALTER TABLE conversations ADD COLUMN active_root_id VARCHAR(36)"))
        if "parent_id" not in msg_cols:
            conn.execute(text("ALTER TABLE messages ADD COLUMN parent_id VARCHAR(36)"))
        if "active_child_id" not in msg_cols:
            conn.execute(text("ALTER TABLE messages ADD COLUMN active_child_id VARCHAR(36)"))


def _backfill_linear_message_trees() -> None:
    """One-time: chain legacy linear messages into a tree (active_root_id IS NULL)."""
    from backend.app.models_db import Conversation, Message

    factory = get_session_factory()
    db = factory()
    try:
        convs = db.scalars(select(Conversation).where(Conversation.active_root_id.is_(None))).all()
        for conv in convs:
            epoch = datetime.min.replace(tzinfo=timezone.utc)
            msgs = sorted(
                [m for m in conv.messages],
                key=lambda m: (m.created_at or epoch, m.id),
            )
            if not msgs:
                continue
            # Already partially tree-shaped (e.g. parent_id set) — only set root if missing.
            if any(m.parent_id for m in msgs):
                roots = [m for m in msgs if not m.parent_id]
                if roots and not conv.active_root_id:
                    conv.active_root_id = roots[0].id
                continue
            for i, msg in enumerate(msgs):
                msg.parent_id = msgs[i - 1].id if i > 0 else None
                msg.active_child_id = msgs[i + 1].id if i + 1 < len(msgs) else None
            conv.active_root_id = msgs[0].id
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Create tables if missing, migrate columns, backfill linear trees."""
    from backend.app import models_db  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _migrate_message_tree_columns(engine)
    _backfill_linear_message_trees()


def get_db() -> Generator[Session, None, None]:
    factory = get_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()


def reset_db_for_tests() -> None:
    """Drop and recreate tables (tests only)."""
    global _engine, _SessionLocal
    from backend.app import models_db  # noqa: F401

    if _engine is not None:
        Base.metadata.drop_all(bind=_engine)
        _engine.dispose()
    _engine = None
    _SessionLocal = None
    init_db()
