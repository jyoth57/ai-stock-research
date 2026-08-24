.PHONY: install install-dev run-api run-dashboard test test-cov lint format type-check clean docker-up docker-down docker-build migrate

# ── Setup ─────────────────────────────────────────────────────────────────────
install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements.txt
	pip install pytest pytest-cov pytest-asyncio ruff mypy

# ── Run ───────────────────────────────────────────────────────────────────────
run-api:
	uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload

run-dashboard:
	streamlit run src/dashboard/app.py --server.port 8501

# ── Data pipeline ─────────────────────────────────────────────────────────────
ingest:
	python -m src.data.collectors.nse_downloader $(SYMBOLS)

fundamentals:
	python -m src.financials.ratios

# ── Testing ───────────────────────────────────────────────────────────────────
test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=src --cov-report=html --cov-report=term-missing

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v

# ── Code quality ──────────────────────────────────────────────────────────────
lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

type-check:
	mypy src/

check: lint type-check

# ── Docker ────────────────────────────────────────────────────────────────────
docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

docker-reset:
	docker compose down -v

# ── Database ──────────────────────────────────────────────────────────────────
migrate:
	alembic upgrade head

migrate-rollback:
	alembic downgrade -1

migrate-new:
	alembic revision --autogenerate -m "$(MSG)"

# ── Cleanup ───────────────────────────────────────────────────────────────────
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache htmlcov .coverage .mypy_cache .ruff_cache

clean-data:
	rm -rf data/raw/*.parquet data/processed/*.parquet

help:
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:' Makefile | awk -F: '{print "  "$$1}'
