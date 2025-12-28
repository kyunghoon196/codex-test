# app/collectors/edgar_client.py - SEC EDGAR API wrapper with rate limiting and retries
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, Optional

import httpx
from structlog.stdlib import get_logger

from app.core.config import LimitedRetryAsyncClient, get_http_client, settings

logger = get_logger()


class EdgarClient:
    """HTTP client wrapper enforcing rate limits, user agent, and 429 backoff for SEC calls."""

    def __init__(
        self,
        client: Optional[LimitedRetryAsyncClient] = None,
        max_429_retries: int = 5,
        backoff_factor: float = 0.5,
    ) -> None:
        self._client = client or get_http_client()
        self.settings = settings
        self.max_429_retries = max_429_retries
        self.backoff_factor = backoff_factor

    async def __aenter__(self) -> "EdgarClient":
        await self._client.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self._client.__aexit__(exc_type, exc, tb)

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: Optional[dict[str, str]] = None) -> dict[str, Any]:
        for attempt in range(self.max_429_retries):
            response = await self._client.get(path, params=params)
            if response.status_code == 429 and attempt < self.max_429_retries - 1:
                sleep_for = self.backoff_factor * (2**attempt)
                logger.warning("edgar.rate_limit", path=path, attempt=attempt, sleep=sleep_for)
                await asyncio.sleep(sleep_for)
                continue
            response.raise_for_status()
            logger.info("edgar.get", path=path, status=response.status_code)
            return response.json()
        msg = f"EDGAR GET failed after retries: {path}"
        raise RuntimeError(msg)

    async def get_company_submissions(self, cik: str) -> dict[str, Any]:
        normalized_cik = cik.zfill(10)
        path = f"/submissions/CIK{normalized_cik}.json"
        return await self._get(path)

    async def get_company_facts(self, cik: str) -> dict[str, Any]:
        normalized_cik = cik.zfill(10)
        path = f"/api/xbrl/companyfacts/CIK{normalized_cik}.json"
        return await self._get(path)

    async def get_frames(self, concept: str = "us-gaap/NetIncomeLoss", frame: str = "CY2025Q2") -> dict[str, Any]:
        path = f"/api/xbrl/frames/{concept}/USD/{frame}"
        return await self._get(path)

    async def stream_file(self, url: str) -> AsyncIterator[bytes]:
        response = await self._client.stream("GET", url)
        response.raise_for_status()
        async for chunk in response.aiter_bytes():
            yield chunk
