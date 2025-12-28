# Makefile - Convenience tasks for development and CI
PYTHON ?= python

.PHONY: install run up down lint typecheck test migrate

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e .[dev]

run:
	uvicorn api.main:app --reload --port 8000

up:
	docker-compose up --build

down:
	docker-compose down -v

lint:
	ruff check app tests

typecheck:
	mypy

test:
	pytest

migrate:
	alembic upgrade head
