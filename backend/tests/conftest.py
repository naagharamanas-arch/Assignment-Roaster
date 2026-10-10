"""Shared test fixtures: in-memory SQLite DB and a TestClient app."""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.exceptions import register_exception_handlers
from app.models import Base
from app.routers import auth as auth_router


@pytest.fixture
def db_session() -> Iterator[Session]:
    """Fresh in-memory SQLite database per test."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def app(db_session: Session) -> FastAPI:
    """FastAPI app with the auth router and get_db overridden."""
    application = FastAPI()
    auth_router.limiter.reset()
    application.state.limiter = auth_router.limiter
    application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
    register_exception_handlers(application)
    application.include_router(auth_router.router, prefix="/api/v1")

    def _get_db() -> Iterator[Session]:
        yield db_session

    application.dependency_overrides[get_db] = _get_db
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """TestClient bound to the test app."""
    with TestClient(app) as test_client:
        yield test_client
