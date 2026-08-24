"""
main.py — FastAPI backend for QuantAI Research Platform
Serves data for the React frontend on http://localhost:8000
"""

from __future__ import annotations

import sys
from pathlib import Path

# Project root on path
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio

from src.api.routers import screener, stocks, market, chat as chat_router
from src.api.routers import downloader
from src.database.duckdb_store import get_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = get_store()
    if not store.is_ready():
        import logging
        logging.getLogger(__name__).warning(
            "DuckDB not ready. Run:  python -m scripts.build_db"
        )
    yield


app = FastAPI(title="QuantAI Research API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(screener.router,     prefix="/api/screener")
app.include_router(stocks.router,       prefix="/api/stocks")
app.include_router(market.router,       prefix="/api/market")
app.include_router(chat_router.router,  prefix="/api/chat")
app.include_router(downloader.router,   prefix="/api/downloader")


@app.get("/api/health")
def health():
    return {"status": "ok"}
