# app/collectors/submissions_watcher.py - Submissions monitor for 10-Q/10-K/8-K filings
from __future__ import annotations

import re
from datetime import datetime
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from structlog.stdlib import get_logger

from app.collectors.edgar_client import EdgarClient
from app.core import models
from app.core.config import to_utc
from app.core.db import AsyncSession, AsyncSessionLocal

logger = get_logger()

FORM_OK = {"10-Q", "10-K", "8-K"}
ITEM2202_RE = re.compile(r"\bitem\s*2\.02\b", re.IGNORECASE)


async def refresh_submissions(ciks: Iterable[str] | None = None) -> int:
    """Fetch latest submissions for companies and upsert filings."""
    client = EdgarClient()
    updated = 0

    async with AsyncSessionLocal() as session:
        if ciks is None:
            ciks = [cik for cik, in (await session.execute(select(models.Company.cik))).all()]

        cik_list = list(ciks)

        for cik in cik_list:
            data = await client.get_company_submissions(cik)
            recent = data.get("filings", {}).get("recent", {})
            records = _normalize_recent(recent, cik)

            for record in records:
                form = record["form"]
                if form not in FORM_OK:
                    continue

                has_item_2202 = record["has_item_2202"]
                stmt = (
                    insert(models.Filing)
                    .values(
                        company_id=await _id_by_cik(session, record["cik"]),
                        form_type=form,
                        filed_at=record["filed_at"],
                        accession=record["accession"],
                        link=record["link"],
                        has_item_2202=has_item_2202,
                    )
                    .on_conflict_do_update(
                        index_elements=["company_id", "accession"],
                        set_={
                            "form_type": form,
                            "filed_at": record["filed_at"],
                            "link": record["link"],
                            "has_item_2202": has_item_2202,
                        },
                    )
                )
                await session.execute(stmt)
                updated += 1

        await session.commit()

    logger.info("submissions.refresh.complete", updated=updated, count=len(cik_list))
    return updated


def _normalize_recent(recent: dict, cik: str) -> list[dict[str, object]]:
    accessions = recent.get("accessionNumber", [])
    forms = recent.get("form", [])
    filing_dates = recent.get("filingDate", []) or recent.get("filedAt", [])
    descriptions = recent.get("primaryDocDescription", [])

    normalized: list[dict[str, object]] = []
    for accession, form, filed_at_str, desc in zip(accessions, forms, filing_dates, descriptions):
        if not filed_at_str:
            continue
        filed_at = to_utc(datetime.fromisoformat(filed_at_str))
        link = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{accession}-index.html"
        has_item = bool(ITEM2202_RE.search(desc or ""))
        normalized.append(
            {
                "cik": str(cik).zfill(10),
                "accession": accession,
                "form": form,
                "filed_at": filed_at,
                "link": link,
                "has_item_2202": has_item and form == "8-K",
            }
        )
    return normalized


async def _id_by_cik(session: AsyncSession, cik: str) -> int:
    result = await session.execute(select(models.Company.id).where(models.Company.cik == str(cik).zfill(10)))
    company_id = result.scalar_one_or_none()
    if company_id is not None:
        return company_id

    company = models.Company(cik=str(cik).zfill(10), name=f"CIK {str(cik).zfill(10)}", ticker=None, sic=None)
    session.add(company)
    await session.flush()
    return company.id
