# Dockerfile - Container image for the SEC collector API
FROM python:3.11-slim-bullseye

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y build-essential libpq-dev && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .[dev]

COPY app /app/app
COPY api /app/api

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
