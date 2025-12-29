# app/core/schemas.py - Pydantic schemas for request and response data
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, computed_field

from app.core.config import to_kst, to_utc


class Submission(BaseModel):
    """Minimal representation of an EDGAR submission entry."""

    cik: str = Field(..., description="Company CIK")
    company_name: str = Field(..., description="Company name as reported")
    form_type: str = Field(..., description="SEC form type")
    accession_number: str = Field(..., description="Accession number for the filing")
    filed_at: datetime = Field(..., description="Filing datetime (UTC)")

    @computed_field
    @property
    def filed_at_kst(self) -> datetime:
        return to_kst(self.filed_at)

    @computed_field
    @property
    def display_name(self) -> str:
        return f"{self.company_name} ({self.cik})"

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "Submission":
        filings = payload.get("filings", {})
        recent = filings.get("recent", {})
        accession_numbers = recent.get("accessionNumber", [])
        forms = recent.get("form", [])
        filings_dates = recent.get("filingDate", [])
        company_name = payload.get("name", "Unknown")
        cik = payload.get("cik", "").zfill(10)

        if not accession_numbers or not forms or not filings_dates:
            msg = "Submission payload is missing required fields"
            raise ValueError(msg)

        accession_number = accession_numbers[0]
        form_type = forms[0]
        filed_at = to_utc(datetime.fromisoformat(filings_dates[0]))

        return cls(
            cik=cik,
            company_name=company_name,
            form_type=form_type,
            accession_number=accession_number,
            filed_at=filed_at,
        )
