"""Database engine and session management."""

import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_DEFAULT_URL = "postgresql://user:password@localhost:5432/assignment_roaster"


def _resolve_database_url() -> str:
    """Return DATABASE_URL from app settings if available, else the environment."""
    try:
        from app.config import settings

        url = getattr(settings, "DATABASE_URL", None)
        if isinstance(url, str) and url:
            return url
    except ImportError:
        pass
    return os.getenv("DATABASE_URL", _DEFAULT_URL)


DATABASE_URL: str = _resolve_database_url()

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
