# app/collectors/prelim_turnaround.py - On-demand turnaround discovery without persistence
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from structlog.stdlib import get_logger

from app.collectors.edgar_client import EdgarClient
from app.core.config import to_utc

logger = get_logger()

ITEM_2202_RE = re.compile(r"item\s*2\.?02", re.IGNORECASE)
NI_RE = re.compile(r"(gaap\s+)?net income(?:\s*\(loss\))?.{0,50}?([+-]?\$?\d[\d,.,]*)", re.IGNORECASE | re.DOTALL)
EPS_RE = re.compile(r"diluted\s+eps.{0,50}?([+-]?\$?\d[\d,.,]*)", re.IGNORECASE | re.DOTALL)
NON_GAAP_RE = re.compile(r"non[-\s]?gaap|adjusted", re.IGNORECASE)


async def find_prelim_turnarounds(
    prev_frame: str,
    from_days: int = 60,
    limit: int = 50,
    client: EdgarClient | None = None,
) -> list[dict[str, Any]]:
    """Identify companies with prior-quarter losses and recent 8-K prelim positives."""
    edgar = client or EdgarClient()
    results: list[dict[str, Any]] = []

    frame_payload = await edgar.get_frames(frame=prev_frame)
    loss_ciks = _loss_ciks_from_frame(frame_payload)
    cutoff = datetime.now(timezone.utc) - timedelta(days=from_days)

    for cik, prev_value, period_end in loss_ciks:
        submissions = await edgar.get_submissions(cik)
        recent = submissions.get("filings", {}).get("recent", {})
        accessions = recent.get("accessionNumber", [])
        forms = recent.get("form", [])
        filed_list = recent.get("filedAt", []) or recent.get("filingDate", [])
        doc_descriptions = recent.get("primaryDocDescription", [])

        for accession, form, filed_at_str, desc in zip(accessions, forms, filed_list, doc_descriptions):
            if form != "8-K":
                continue
            if not filed_at_str:
                continue
            filed_at = to_utc(datetime.fromisoformat(filed_at_str))
            if filed_at < cutoff:
                continue

            index_link = _build_index_link(cik, accession)
            try:
                index_html = await edgar.download_url(index_link)
            except Exception as exc:  # noqa: BLE001
                logger.warning("prelim.fetch_index_failed", cik=cik, accession=accession, error=str(exc))
                continue

            if not ITEM_2202_RE.search(index_html) and not ITEM_2202_RE.search(desc or ""):
                continue

            exhibit_link = _find_exhibit_99(index_link, index_html)
            text_source_link = exhibit_link or index_link
            try:
                target_html = await edgar.download_url(text_source_link)
            except Exception as exc:  # noqa: BLE001
                logger.warning("prelim.fetch_exhibit_failed", cik=cik, accession=accession, error=str(exc))
                continue

            parsed_income, parsed_eps = _parse_gaap_numbers(target_html)
            if parsed_income is None and parsed_eps is None:
                continue
            if (parsed_income is not None and parsed_income > 0) or (parsed_eps is not None and parsed_eps > 0):
                results.append(
                    {
                        "cik": str(cik).zfill(10),
                        "filed_at": filed_at.isoformat(),
                        "prev_net_income": prev_value,
                        "evidence_link": text_source_link,
                        "parsed_gaap_net_income": parsed_income,
                        "parsed_diluted_eps": parsed_eps,
                    }
                )
            if len(results) >= limit:
                return results

    return results


def _loss_ciks_from_frame(payload: dict[str, Any]) -> list[tuple[str, float, str]]:
    entries = []
    for item in payload.get("data", []):
        val = item.get("val")
        if val is None:
            continue
        try:
            numeric_val = float(val)
        except Exception:
            continue
        if numeric_val < 0:
            entries.append((str(item.get("cik", "")).zfill(10), numeric_val, item.get("end", "")))
    return entries


def _build_index_link(cik: str, accession: str) -> str:
    clean_acc = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{clean_acc}/{accession}-index.html"


def _find_exhibit_99(base_url: str, html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.find_all("a"):
        text = (link.get_text() or "").lower()
        href = link.get("href") or ""
        if "99.1" in text or "99.1" in href:
            return urljoin(base_url, href)
    return None


def _parse_gaap_numbers(html: str) -> tuple[float | None, float | None]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    if NON_GAAP_RE.search(text):
        # Prefer GAAP; if non-GAAP dominates, continue to seek matches but allow GAAP regex to proceed.
        pass
    net_income = _extract_number(NI_RE, text)
    eps = _extract_number(EPS_RE, text)
    return net_income, eps


def _extract_number(rx: re.Pattern[str], text: str) -> float | None:
    match = rx.search(text)
    if not match:
        return None
    candidate = match.group(match.lastindex or 1)
    if not candidate:
        return None
    cleaned = candidate.replace("$", "").replace(",", "")
    try:
        return float(cleaned)
    except Exception:
        return None
