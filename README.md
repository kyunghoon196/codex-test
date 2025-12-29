# codex-test
to test codex feature
# codex-test

FastAPI-based collector for SEC EDGAR filings with PostgreSQL persistence.

## Features
- FastAPI with structured logging via `structlog`.
- Async SQLAlchemy + Alembic migrations targeting PostgreSQL.
- HTTPX client with retries, rate limiting (<=8 RPS by default), and required `User-Agent`.
- Dataclass settings loaded from `.env` for secrets and endpoints.

## Getting started
1. Copy `.env.example` to `.env` and update credentials (note: use the async SQLAlchemy driver scheme `postgresql+asyncpg://`). Key variables:
   - `SEC_USER_AGENT` (required)
   - `SEC_BASE` (default: `https://data.sec.gov`)
   - `DB_URL` (default: `postgresql+asyncpg://postgres:postgres@db:5432/secdb`)
   - `POLL_INTERVAL_SEC` (default: `90`)
   - `RPS_LIMIT` (default: `8`)
2. Build and start services:
   ```bash
   make up
   ```
3. Run database migrations:
   ```bash
   make migrate
   ```
4. Launch the API locally:
   ```bash
   make run
   ```

## Tooling
- **Linting:** `make lint` (ruff)
- **Type checking:** `make typecheck` (mypy)
- **Tests:** `make test` (pytest)

## API
The app exposes the API under `/api`. Health check lives at `/api/health`; filings can be listed via `/api/filings`.
