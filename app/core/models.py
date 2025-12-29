# app/core/models.py - SQLAlchemy ORM models for company, filings, facts, and signals
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Company(Base):
    """Tracked company metadata."""

    __tablename__ = "company"

    id: Mapped[int] = mapped_column(primary_key=True)
    cik: Mapped[str] = mapped_column(String, unique=True, index=True)
    ticker: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String)
    sic: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    filings: Mapped[list["Filing"]] = relationship(back_populates="company")
    facts: Mapped[list["FactQuarterly"]] = relationship(back_populates="company")
    signals: Mapped[list["Signal"]] = relationship(back_populates="company")


class Filing(Base):
    """SEC filing metadata."""

    __tablename__ = "filing"
    __table_args__ = (
        UniqueConstraint("company_id", "accession", name="uq_filing_company_accession"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"))
    form_type: Mapped[str] = mapped_column(String, index=True)
    filed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    accession: Mapped[str] = mapped_column(String, index=True)
    link: Mapped[str] = mapped_column(String)
    has_item_2202: Mapped[bool] = mapped_column(Boolean, default=False)

    company: Mapped["Company"] = relationship(back_populates="filings")


class FactQuarterly(Base):
    """Quarterly fact values extracted from filings."""

    __tablename__ = "fact_quarterly"
    __table_args__ = (
        UniqueConstraint("company_id", "concept", "frame", name="uq_fact_company_concept_frame"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"))
    frame: Mapped[str] = mapped_column(String, index=True)
    fy: Mapped[int] = mapped_column(Integer)
    fp: Mapped[str] = mapped_column(String)
    concept: Mapped[str] = mapped_column(String, index=True)
    unit: Mapped[str] = mapped_column(String)
    value: Mapped[Numeric] = mapped_column(Numeric(20, 4))
    is_gaap: Mapped[bool] = mapped_column(Boolean, default=True)
    period_end: Mapped[date] = mapped_column(Date, index=True)

    company: Mapped["Company"] = relationship(back_populates="facts")


class Signal(Base):
    """Computed signal summarizing filing-derived insights."""

    __tablename__ = "signal"
    __table_args__ = (
        UniqueConstraint("company_id", "period_end", "signal_type", name="uq_signal_company_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"))
    period_end: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)
    signal_type: Mapped[str] = mapped_column(String)
    score: Mapped[int] = mapped_column(Integer, default=0)
    evidence_link: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    company: Mapped["Company"] = relationship(back_populates="signals")
