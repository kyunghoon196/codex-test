# app/api/routers.py - Route definitions for the FastAPI application
from collections.abc import Iterable

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import models, schemas
from app.core.db import get_session

router = APIRouter()


@router.get("/health", summary="Health check")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/filings", response_model=list[schemas.Submission], summary="List filings")
async def list_filings(session: AsyncSession = Depends(get_session)) -> list[schemas.Submission]:
    result = await session.execute(select(models.Filing))
    filings: Iterable[models.Filing] = result.scalars().all()
    return [
        schemas.Submission(
            cik=filing.company.cik if filing.company else "",
            company_name=filing.company.name if filing.company else "",
            form_type=filing.form_type,
            accession_number=filing.accession,
            filed_at=filing.filed_at,
        )
        for filing in filings
    ]
