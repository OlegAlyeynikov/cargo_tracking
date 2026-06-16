.PHONY: help install dev run test lint format clean docker-up docker-down docker-logs redis env ui-install ui-build ui-dev

UV := uv

help:
	@echo "Cargo Tracking API"
	@echo ""
	@echo "  make install      Install all dependencies"
	@echo "  make env          Copy .env.example -> .env (if not exists)"
	@echo "  make dev          Run dev server with auto-reload"
	@echo "  make run          Run production server"
	@echo "  make test         Run all tests"
	@echo "  make test-v       Run tests (verbose)"
	@echo "  make lint         Run ruff linter"
	@echo "  make format       Run ruff formatter"
	@echo "  make redis        Start Redis in Docker (local dev)"
	@echo "  make docker-up    Start full stack with Docker Compose"
	@echo "  make docker-down  Stop Docker Compose stack"
	@echo "  make docker-logs  Tail Docker Compose logs"
	@echo "  make clean        Remove cache and build artifacts"
	@echo ""
	@echo "  make ui-install   Install frontend npm dependencies"
	@echo "  make ui-build     Build frontend (output: app/static/ui/)"
	@echo "  make ui-dev       Start Vite dev server on :3000 (proxies API to :8000)"

install:
	$(UV) sync

env:
	@if [ ! -f .env ]; then cp .env.example .env && echo ".env created from .env.example"; else echo ".env already exists, skipping"; fi

dev: env
	$(UV) run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

run: env
	$(UV) run uvicorn app.main:app --host 0.0.0.0 --port 8000

test:
	$(UV) run pytest

test-v:
	$(UV) run pytest -v

lint:
	$(UV) run ruff check app/ tests/

format:
	$(UV) run ruff format app/ tests/

redis:
	docker run --rm -d --name cargo-redis -p 6379:6379 redis:7-alpine
	@echo "Redis started on localhost:6379. Stop with: docker stop cargo-redis"

docker-up: env
	docker compose up --build -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

ui-install:
	cd frontend && npm install

ui-build:
	cd frontend && npm run build

ui-dev:
	cd frontend && npm run dev

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null; true
	find . -name "*.pyc" -delete 2>/dev/null; true
	@echo "Cleaned."
