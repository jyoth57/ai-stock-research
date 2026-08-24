# AI Stock Research

An AI-powered platform for researching NSE-listed stocks — combining fundamental analysis, technical indicators, valuation models, and LLM-driven research agents into a single unified system.

## Features

- **Data ingestion** — Daily OHLCV download via yfinance; financial statement CSV ingestion
- **Fundamentals** — ROE, ROCE, EPS Growth, Revenue CAGR, Debt/Equity, Free Cash Flow
- **Technicals** — Indicators, patterns, support/resistance, momentum, volume analysis
- **Valuation** — DCF, P/E, P/B, EV/EBITDA, PEG, intrinsic value models
- **Screening** — Rule-based stock screener with composable filters
- **Scoring** — Composite quality, growth, risk, and valuation scores
- **Portfolio** — Optimisation, allocation, backtesting, performance attribution
- **AI agents** — LangChain-powered agents per domain with a Chief Investment Officer orchestrator
- **Dashboard** — Streamlit UI with ranked tables, charts, and filters
- **API** — FastAPI REST layer for programmatic access

## Project Structure

```
ai-stock-research/
├── src/
│   ├── core/          # Config, logging, exceptions, utils
│   ├── data/          # Collectors, loaders, cleaners, transformers
│   ├── database/      # Connection, repository, schema, migrations
│   ├── market/        # OHLCV, corporate actions, indices
│   ├── financials/    # Income statement, balance sheet, ratios
│   ├── technicals/    # Indicators, patterns, momentum
│   ├── valuation/     # DCF, PE, PB, EV/EBITDA
│   ├── screener/      # Filters, rules, engine
│   ├── scoring/       # Quality, growth, risk, overall
│   ├── portfolio/     # Optimizer, backtest, performance
│   ├── research/      # Annual reports, concalls, news
│   ├── ai/            # RAG, embeddings, LLM, agents, chains
│   ├── agents/        # Domain agents + CIO orchestrator
│   ├── api/           # FastAPI routers, schemas, services
│   └── dashboard/     # Streamlit pages, charts, components
├── data/
│   ├── raw/           # Downloaded OHLCV parquet files
│   ├── processed/     # Computed fundamentals parquet files
│   └── reports/       # Generated PDF/HTML reports
├── tests/
├── notebooks/
├── configs/
├── docs/
└── scripts/
```

## Quick Start

```bash
# 1. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. Install dependencies
make install

# 3. Copy and configure environment
cp .env.example .env

# 4. Download stock data
make ingest SYMBOLS="RELIANCE TCS INFY HDFCBANK"

# 5. Run the dashboard
make run-dashboard

# 6. Run the API
make run-api
```

## Docker

```bash
make docker-up      # Start all services
make docker-logs    # Tail logs
make docker-down    # Stop all services
```

## Development

```bash
make test           # Run test suite
make test-cov       # Tests with coverage report
make lint           # Ruff linting
make format         # Ruff formatting
make type-check     # mypy
```

## License

MIT
