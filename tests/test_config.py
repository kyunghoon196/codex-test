# tests/test_config.py - Configuration loading unit tests
from typing import TYPE_CHECKING

from app.core.config import Settings, to_kst, to_utc
from app.core.schemas import Submission

if TYPE_CHECKING:
    import pytest


def test_settings_load_from_env(monkeypatch: "pytest.MonkeyPatch") -> None:
    monkeypatch.setenv("SEC_USER_AGENT", "test-agent")
    monkeypatch.setenv("SEC_BASE", "https://example.test")
    monkeypatch.setenv("DB_URL", "postgresql+asyncpg://user:pass@localhost:5432/dbname")
    monkeypatch.setenv("POLL_INTERVAL_SEC", "45")
    monkeypatch.setenv("RPS_LIMIT", "6")
    env_settings = Settings()
    assert env_settings.SEC_USER_AGENT == "test-agent"
    assert env_settings.SEC_BASE == "https://example.test"
    assert env_settings.DB_URL.endswith("/dbname")
    assert env_settings.POLL_INTERVAL_SEC == 45
    assert env_settings.RPS_LIMIT == 6


def test_submission_from_payload() -> None:
    payload = {
        "cik": "1234567",
        "name": "Test Corp",
        "filings": {
            "recent": {
                "accessionNumber": ["0000000000-24-000001"],
                "form": ["8-K"],
                "filingDate": ["2024-01-15T00:00:00"],
            }
        },
    }
    submission = Submission.from_payload(payload)
    assert submission.cik == "0001234567"
    assert submission.form_type == "8-K"
    assert to_utc(submission.filed_at).tzinfo is not None
    assert to_kst(submission.filed_at).tzinfo is not None
