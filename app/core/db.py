# app/core/db.py - Database engine and session management
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """Declarative base for ORM models."""


def get_engine() -> AsyncEngine:
    db_url = settings.DB_URL
    # Normalize in-memory SQLite for async usage.
    if db_url.startswith("sqlite+pysqlite://"):
        db_url = db_url.replace("sqlite+pysqlite://", "sqlite+aiosqlite://", 1)
    return create_async_engine(db_url, future=True, echo=False)


engine = get_engine()
AsyncSessionLocal = async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield an async database session."""
    async with AsyncSessionLocal() as session:
        yield session


async def init_models() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
