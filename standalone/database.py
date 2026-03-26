"""
Optional standalone database for file metadata and retention tracking.

Leave DATABASE_URL empty to run fully stateless. Routers handle a None session.
"""
from __future__ import annotations

from typing import Generator, Optional

from sqlalchemy import Column, DateTime, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from standalone.config import get_settings

settings = get_settings()

_engine = None
_SessionLocal = None


class Base(DeclarativeBase):
    pass


class StoredFile(Base):
    """Tracks cloud-stored files for retention/cleanup."""

    __tablename__ = "stored_files"

    id = Column(Integer, primary_key=True, index=True)
    cloud_key = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    storage_backend = Column(String, nullable=False)  # s3 | azure | gcs
    expires_at = Column(DateTime(timezone=True), nullable=False)
    statement_id = Column(Integer, nullable=True)


def _init_engine():
    global _engine, _SessionLocal
    if not settings.database_url:
        return
    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    _engine = create_engine(settings.database_url, connect_args=connect_args)
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def create_tables():
    _init_engine()
    if _engine:
        Base.metadata.create_all(bind=_engine)


def get_db() -> Generator[Optional[Session], None, None]:
    if _SessionLocal is None:
        yield None
        return
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()
