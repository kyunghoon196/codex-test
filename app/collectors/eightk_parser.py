# app/collectors/eightk_parser.py - 8-K press release parser to emit preliminary signals
from __future__ import annotations

import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from structlog.stdlib import get_logger

from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.core.models import Filing, Signal

logger = get_logger()

NI_RE = re.compile(r"\bgaap\b.*\bnet income\b.*?([+-]?\$?\d[\d,\.]*)", re.IGNORECASE | re.DOTALL)
EPS_RE = re.compile(r"\bdiluted\s+eps\b.*?([+-]?\$?\d[\d,\.]*)", re.IGNORECASE | re.DOTALL)


async def parse_and_signal() -> int:
    """Download 8-K press releases and upsert PRELIM signals based on GAAP NI or EPS."""
    created = 0
    headers = {
        "User-Agent": settings.SEC_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
    }

    async with AsyncSessionLocal() as session:
        filings_result = await session.execute(
            select(Filing).where(Filing.form_type == "8-K", Filing.has_item_2202.is_(True))
        )
        filings = filings_result.scalars().all()

        async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
            for filing in filings:
                try:
                    response = await client.get(filing.link)
                    response.raise_for_status()
                    text = _extract_text(response.text)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("eightk_parser.fetch_failed", link=filing.link, error=str(exc))
                    continue

                ni = _to_number(_first_group(NI_RE, text))
                eps = _to_number(_first_group(EPS_RE, text))

                if (ni is not None and ni > 0) or (eps is not None and eps > 0):
                    evidence_link = filing.link
                    stmt = (
                        insert(Signal)
                        .values(
                            company_id=filing.company_id,
                            period_end=filing.filed_at.date() if filing.filed_at else None,
                            signal_type="PRELIM",
                            score=60,
                            evidence_link=evidence_link,
                        )
                        .on_conflict_do_update(
                            index_elements=["company_id", "period_end", "signal_type"],
                            set_={"score": 60, "evidence_link": evidence_link},
                        )
                    )
                    await session.execute(stmt)
                    created += 1
                    logger.info("eightk_parser.prelim_signal", filing_id=filing.id, ni=ni, eps=eps)

        await session.commit()

    return created


def _extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(" ", strip=True)


def _first_group(rx: re.Pattern[str], text: str) -> Optional[str]:
    match = rx.search(text)
    return match.group(1) if match else None


def _to_number(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        cleaned = value.replace("$", "").replace(",", "")
        return float(cleaned)
    except Exception:  # noqa: BLE001
        return None
