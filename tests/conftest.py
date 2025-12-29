# tests/conftest.py - Test configuration and path setup
import sys
from pathlib import Path

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.db import Base  # noqa: E402
import app.core.db as core_db  # noqa: E402
import app.collectors.frames_loader as frames_loader  # noqa: E402
import app.core.signals as signals_mod  # noqa: E402
import app.collectors.eightk_parser as eightk_parser  # noqa: E402
import app.collectors.submissions_watcher as submissions_watcher  # noqa: E402


@pytest_asyncio.fixture
async def db_session(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    TestSessionLocal = async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    monkeypatch.setattr(core_db, "engine", engine)
    monkeypatch.setattr(core_db, "AsyncSessionLocal", TestSessionLocal)
    monkeypatch.setattr(frames_loader, "AsyncSessionLocal", TestSessionLocal)
    monkeypatch.setattr(signals_mod, "AsyncSessionLocal", TestSessionLocal)
    monkeypatch.setattr(eightk_parser, "AsyncSessionLocal", TestSessionLocal)
    monkeypatch.setattr(submissions_watcher, "AsyncSessionLocal", TestSessionLocal)

    yield TestSessionLocal

    await engine.dispose()
