# app/core/config.py - Environment configuration, logging, and HTTP client utilities
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Callable
from zoneinfo import ZoneInfo

import httpx
import logging
import structlog
from aiolimiter import AsyncLimiter

KST = ZoneInfo("Asia/Seoul")
UTC = ZoneInfo("UTC")


@dataclass(frozen=True)
class Settings:
    """Environment-backed configuration."""

    SEC_BASE: str = os.getenv("SEC_BASE", "https://data.sec.gov")
    SEC_USER_AGENT: str = os.getenv(
        "SEC_USER_AGENT", "your-email@example.com SEC Research"
    )
    DB_URL: str = os.getenv(
        "DB_URL", "sqlite+pysqlite:///:memory:"
    )
    POLL_INTERVAL_SEC: int = int(os.getenv("POLL_INTERVAL_SEC", "90"))
    RPS_LIMIT: int = int(os.getenv("RPS_LIMIT", "8"))


settings = Settings()


def configure_logging() -> None:
    """Configure structlog for structured output."""
    timestamper = structlog.processors.TimeStamper(fmt="iso")
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            timestamper,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


def to_utc(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware in UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def to_kst(dt: datetime) -> datetime:
    """Convert UTC datetime to Asia/Seoul timezone."""
    return to_utc(dt).astimezone(KST)


class LimitedRetryAsyncClient(httpx.AsyncClient):
    """HTTPX async client with rate limiting and exponential backoff retries."""

    def __init__(
        self,
        limiter: AsyncLimiter,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        should_retry: Callable[[httpx.Response | None, Exception | None], bool] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self.limiter = limiter
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.should_retry = should_retry or self._default_should_retry

    @staticmethod
    def _default_should_retry(response: httpx.Response | None, error: Exception | None) -> bool:
        if error:
            return True
        if response and (response.status_code >= 500 or response.status_code == 429):
            return True
        return False

    async def send(self, request: httpx.Request, **kwargs: object) -> httpx.Response:  # type: ignore[override]
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                async with self.limiter:
                    response = await super().send(request, **kwargs)
                if self.should_retry(response, None) and attempt < self.max_retries:
                    await asyncio.sleep(self.backoff_factor * (2**attempt))
                    continue
                return response
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if self.should_retry(None, exc) and attempt < self.max_retries:
                    await asyncio.sleep(self.backoff_factor * (2**attempt))
                    continue
                raise
        raise last_exc if last_exc else RuntimeError("Request failed without exception")


def get_http_client() -> LimitedRetryAsyncClient:
    """Create a configured HTTP client with rate limits, retries, and default headers."""
    limiter = AsyncLimiter(settings.RPS_LIMIT, 1)
    default_headers = {
        "User-Agent": settings.SEC_USER_AGENT,
        "Accept": "application/json",
    }
    return LimitedRetryAsyncClient(
        limiter=limiter,
        base_url=settings.SEC_BASE,
        headers=default_headers,
        timeout=httpx.Timeout(30.0),
    )
