"""Database engine, session factory and declarative base.

SQLite is the supported target: a fresh clone runs with no database server, no
credentials and no setup step. PostgreSQL is left as an optional, untested path.

The only behavioural difference the application cares about is that SQLite has no
server-side NUMERIC rounding, which is why all money rounding is done in Python
(``app.services.money``) rather than in SQL. Foreign keys are enabled explicitly
on every SQLite connection because the schema relies on them and SQLite disables
them by default.
"""
from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _build_engine() -> Engine:
    settings = get_settings()
    url = settings.database_url
    kwargs: dict = {"pool_pre_ping": True, "future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = _build_engine()
        if _engine.dialect.name == "sqlite":
            # Foreign keys are off by default in SQLite; the schema relies on them.
            @event.listens_for(_engine, "connect")
            def _fk_on(dbapi_conn, _record):  # pragma: no cover - driver hook
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                cur.close()
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _SessionLocal


def reset_engine() -> None:
    """Drop cached engine/session state. Used by tests after changing DATABASE_URL."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Standalone transactional scope for scripts and tests."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_all() -> None:
    """Create the schema directly. Alembic is the supported path; this exists for
    tests and for the SQLite fallback where running Alembic adds no value."""
    from app import models  # noqa: F401  (registers the mappers)

    Base.metadata.create_all(bind=get_engine())
