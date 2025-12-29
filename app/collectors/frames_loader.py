# app/collectors/frames_loader.py - XBRL frames ingestion for quarterly facts
from __future__ import annotations

from datetime import date
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from structlog.stdlib import get_logger

from app.collectors.edgar_client import EdgarClient
from app.core.db import AsyncSessionLocal
from app.core.models import Company, FactQuarterly

logger = get_logger()


class FramesLoader:
    """Load XBRL frames and upsert quarterly fact data."""

    def __init__(self, client: EdgarClient | None) -> None:
        self.client = client or EdgarClient()

    async def load_frames(self, frames: Iterable[str], concept: str = "us-gaap/NetIncomeLoss") -> None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                for frame in frames:
                    data = await self.client.get_frames(concept=concept, frame=frame)
                    for item in data.get("data", []):
                        cik = item.get("cik")
                        value = item.get("val")
                        period_end = item.get("end")
                        fy = item.get("fy")
                        fp = item.get("fp")

                        if not cik or value is None or not period_end or fy is None or not fp:
                            continue

                        company = await self._get_or_create_company(session=session, cik=str(cik).zfill(10))

                        stmt = insert(FactQuarterly).values(
                            company_id=company.id,
                            frame=frame,
                            fy=int(fy),
                            fp=str(fp),
                            concept="us-gaap:NetIncomeLoss",
                            unit="USD",
                            value=value,
                            is_gaap=True,
                            period_end=date.fromisoformat(period_end),
                        ).on_conflict_do_update(
                            index_elements=["company_id", "concept", "frame"],
                            set_={
                                "value": value,
                                "period_end": date.fromisoformat(period_end),
                                "fy": int(fy),
                                "fp": str(fp),
                                "unit": "USD",
                                "is_gaap": True,
                            },
                        )
                        await session.execute(stmt)
                        logger.info(
                            "frames_loader.upsert_fact",
                            cik=company.cik,
                            frame=frame,
                            value=value,
                            period_end=period_end,
                        )

    async def _get_or_create_company(self, session: AsyncSession, cik: str) -> Company:
        result = await session.execute(select(Company).where(Company.cik == cik))
        company = result.scalars().first()
        if company:
            return company

        company = Company(cik=cik, name=f"CIK {cik}", ticker=None, sic=None)
        session.add(company)
        await session.flush()
        return company
