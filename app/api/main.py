# app/api/main.py - FastAPI entrypoint exposing jobs and signals API
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Iterable, Optional

from fastapi import FastAPI, Query
from sqlalchemy import desc, select

from app.collectors.eightk_parser import parse_and_signal
from app.collectors.frames_loader import FramesLoader
from app.collectors.prelim_turnaround import find_prelim_turnarounds
from app.collectors.submissions_watcher import refresh_submissions
from app.core.config import configure_logging, settings
from app.core.db import AsyncSessionLocal, init_models
from app.core.models import Company, Signal
from app.core.signals import detect_turnarounds
from app.api.routers import router


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    settings
    await init_models()
    yield


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan, title="SEC Collector API", version="0.1.0")
    app.include_router(router, prefix="/api")

    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/signals")
    async def get_signals(
        signal_type: Optional[str] = Query(None, alias="type"), limit: int = 50
    ) -> list[dict[str, object]]:
        async with AsyncSessionLocal() as session:
            stmt = select(Signal).order_by(desc(Signal.created_at)).limit(limit)
            if signal_type:
                stmt = stmt.where(Signal.signal_type == signal_type)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [
                {
                    "company_id": row.company_id,
                    "period_end": row.period_end,
                    "type": row.signal_type,
                    "score": row.score,
                    "evidence": row.evidence_link,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in rows
            ]

    @app.post("/jobs/backfill_frames")
    async def job_backfill_frames() -> dict[str, object]:
        frames: Iterable[str] = [f"CY{y}Q{q}" for y in (2024, 2025) for q in (1, 2, 3, 4)]
        loader = FramesLoader(client=None)  # client None -> internal getter
        await loader.load_frames(frames)
        return {"ok": True, "frames": list(frames)}

    @app.post("/jobs/refresh_submissions")
    async def job_refresh_submissions() -> dict[str, object]:
        updated = await refresh_submissions()
        return {"ok": True, "updated": updated}

    @app.post("/jobs/parse_8k")
    async def job_parse_8k() -> dict[str, object]:
        created = await parse_and_signal()
        return {"ok": True, "created": created}

    @app.post("/jobs/detect")
    async def job_detect(latest: str, prev: str) -> dict[str, object]:
        created = await detect_turnarounds(latest, prev)
        return {"ok": True, "created": len(created)}

    @app.post("/dev/seed")
    async def seed_signals() -> dict[str, object]:
        async with AsyncSessionLocal() as session:
            companies = [
                Company(cik="0000000001", name="Seed Corp A", ticker="SEEDA", sic=None),
                Company(cik="0000000002", name="Seed Corp B", ticker="SEEDB", sic=None),
            ]
            session.add_all(companies)
            await session.flush()
            signal_rows = [
                Signal(company_id=companies[0].id, period_end=None, signal_type="PRELIM", score=60, evidence_link="https://example.com/prelim"),
                Signal(company_id=companies[1].id, period_end=None, signal_type="FINAL", score=100, evidence_link="https://example.com/final"),
            ]
            session.add_all(signal_rows)
            await session.commit()
        return {"ok": True, "inserted": 2}

    @app.get("/turnarounds/prelim")
    async def prelim_turnarounds(prev: str, from_days: int = 60, limit: int = 50) -> list[dict[str, object]]:
        results = await find_prelim_turnarounds(prev_frame=prev, from_days=from_days, limit=limit)
        return results

    return app


app = create_app()
