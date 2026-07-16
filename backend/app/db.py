"""SQLAlchemy engine / session helpers for app persistence."""
from __future__ import annotations

from collections.abc import Generator
from typing import Optional

from sqlalchemy import create_engine, event
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


def init_db() -> None:
    """Create tables if missing. Import models so metadata is registered."""
    from backend.app import models_db  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)


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
