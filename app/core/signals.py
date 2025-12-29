# app/core/signals.py - Turnaround detection logic for quarterly NetIncomeLoss signals
from __future__ import annotations

from typing import List

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from structlog.stdlib import get_logger

from app.core.db import AsyncSessionLocal
from app.core.models import Company, FactQuarterly, Signal

logger = get_logger()


async def detect_turnarounds(latest_frame: str, prev_frame: str) -> list[Signal]:
    """Detect companies moving from negative to positive NetIncomeLoss between frames."""
    created_signals: list[Signal] = []

    async with AsyncSessionLocal() as session:
        prev_result = await session.execute(
            select(FactQuarterly).where(
                FactQuarterly.frame == prev_frame, FactQuarterly.concept == "us-gaap:NetIncomeLoss"
            )
        )
        prev_map = {fact.company_id: fact for fact in prev_result.scalars()}

        curr_result = await session.execute(
            select(FactQuarterly).where(
                FactQuarterly.frame == latest_frame, FactQuarterly.concept == "us-gaap:NetIncomeLoss"
            )
        )

        for fact in curr_result.scalars():
            prev = prev_map.get(fact.company_id)
            if not prev:
                continue

            prev_val = float(prev.value or 0)
            curr_val = float(fact.value or 0)
            if prev_val < 0 and curr_val > 0:
                cik = await _cik_of(session=session, company_id=fact.company_id)
                evidence_link = f"https://www.sec.gov/edgar/browse/?CIK={cik}"

                stmt = (
                    insert(Signal)
                    .values(
                        company_id=fact.company_id,
                        period_end=fact.period_end,
                        signal_type="FINAL",
                        score=100,
                        evidence_link=evidence_link,
                    )
                    .on_conflict_do_update(
                        index_elements=["company_id", "period_end", "signal_type"],
                        set_={"score": 100, "evidence_link": evidence_link},
                    )
                    .returning(Signal)
                )
                result = await session.execute(stmt)
                created_signal = result.scalar_one()
                created_signals.append(created_signal)
                logger.info(
                    "signals.turnaround_detected",
                    company_id=fact.company_id,
                    latest_frame=latest_frame,
                    prev_frame=prev_frame,
                    score=100,
                )

        await session.commit()

    return created_signals


async def _cik_of(session, company_id: int) -> str:
    result = await session.execute(select(Company.cik).where(Company.id == company_id))
    return result.scalar_one()
