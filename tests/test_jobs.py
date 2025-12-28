# tests/test_jobs.py - Integration-style tests for loaders and signal detection
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.collectors.eightk_parser import NI_RE, _first_group, _to_number
from app.collectors.frames_loader import FramesLoader
from app.core.models import Company, FactQuarterly, Signal
from app.core.signals import detect_turnarounds


class DummyFramesClient:
    async def get_frames(self, concept: str, frame: str) -> dict[str, object]:
        return {
            "data": [
                {
                    "cik": "1234567",
                    "val": 100,
                    "end": "2024-12-31",
                    "fy": 2024,
                    "fp": "Q4",
                }
            ]
        }


@pytest.mark.asyncio
async def test_frames_loader_inserts_fact(db_session) -> None:
    loader = FramesLoader(client=DummyFramesClient())
    await loader.load_frames(["CY2024Q4"])

    async with db_session() as session:
        result = await session.execute(select(FactQuarterly))
        fact = result.scalars().one()
        assert fact.value == 100
        company = await session.get(Company, fact.company_id)
        assert company is not None
        assert company.cik == "0001234567"


@pytest.mark.asyncio
async def test_detect_turnaround_creates_signal(db_session) -> None:
    async with db_session() as session:
        company = Company(cik="0001111111", name="Test Co", ticker=None, sic=None)
        session.add(company)
        await session.flush()

        session.add_all(
            [
                FactQuarterly(
                    company_id=company.id,
                    frame="CY2024Q3",
                    fy=2024,
                    fp="Q3",
                    concept="us-gaap:NetIncomeLoss",
                    unit="USD",
                    value=-10,
                    is_gaap=True,
                    period_end=date(2024, 9, 30),
                ),
                FactQuarterly(
                    company_id=company.id,
                    frame="CY2024Q4",
                    fy=2024,
                    fp="Q4",
                    concept="us-gaap:NetIncomeLoss",
                    unit="USD",
                    value=50,
                    is_gaap=True,
                    period_end=date(2024, 12, 31),
                ),
            ]
        )
        await session.commit()

    signals = await detect_turnarounds(latest_frame="CY2024Q4", prev_frame="CY2024Q3")
    assert len(signals) == 1

    async with db_session() as session:
        result = await session.execute(select(Signal))
        signal = result.scalars().one()
        assert signal.signal_type == "FINAL"
        assert signal.score == 100


def test_eightk_parser_regex_extracts_net_income() -> None:
    text = "GAAP net income was $123,456 in the quarter."
    value = _to_number(_first_group(NI_RE, text))
    assert value == 123456.0
