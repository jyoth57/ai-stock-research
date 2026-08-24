"""downloader.py
---------------
FastAPI router for triggering and monitoring live NSE data downloads.

Endpoints
---------
  POST /api/downloader/start      Start a background download job
  GET  /api/downloader/status     Poll job progress (percentage, current date, etc.)
  POST /api/downloader/cancel     Request cancellation of a running job

The download runs in a daemon thread so it never blocks the API event loop.
Progress is stored in a module-level dict that the /status endpoint reads.

Universe options
----------------
  large_cap   Nifty 50      (50 stocks)
  mid_cap     Nifty Next 50 (50 stocks, rank 51-100)
  large_mid   Nifty 100     (100 stocks)
  all         Every EQ-series stock in Bhavcopy (~2 600+ symbols)

Interval options
----------------
  1d   Daily OHLCV (default)
  1w   Weekly OHLCV (resampled from daily before writing Parquet)
"""

from __future__ import annotations

import threading
import time
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.core.constants import NIFTY_50, NIFTY_NEXT_50

router = APIRouter(tags=["downloader"])

# ---------------------------------------------------------------------------
# Universe definitions
# ---------------------------------------------------------------------------

UNIVERSES: dict[str, list[str] | None] = {
    "large_cap": NIFTY_50,
    "mid_cap":   NIFTY_NEXT_50,
    "large_mid": NIFTY_50 + NIFTY_NEXT_50,
    "all":       None,   # passes symbols=None to download_all → every EQ stock
}

UNIVERSE_LABELS: dict[str, str] = {
    "large_cap": f"Large Cap — Nifty 50 ({len(NIFTY_50)} stocks)",
    "mid_cap":   f"Mid Cap — Nifty Next 50 ({len(NIFTY_NEXT_50)} stocks)",
    "large_mid": f"Large + Mid — Nifty 100 ({len(NIFTY_50) + len(NIFTY_NEXT_50)} stocks)",
    "all":       "All NSE — every EQ-series stock (~2 600+)",
}

# ---------------------------------------------------------------------------
# Shared job state (single-job model: one download at a time)
# ---------------------------------------------------------------------------

_state: dict = {
    "status":          "idle",   # idle | running | building_db | done | error | cancelled
    "total_days":      0,
    "completed_days":  0,
    "symbols_saved":   0,
    "current_date":    None,
    "error":           None,
    "started_at":      None,
    "universe_label":  None,
    "interval":        None,
    "cancelled":       False,
}
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class DownloadRequest(BaseModel):
    universe:   Literal["large_cap", "mid_cap", "large_mid", "all"] = "large_cap"
    start:      str = Field(description="Start date YYYY-MM-DD")
    end:        str | None = Field(None, description="End date YYYY-MM-DD (default: today)")
    interval:   Literal["1d", "1w"] = "1d"
    rebuild_db: bool = Field(True, description="Rebuild DuckDB signals after download")


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

def _run_download(req: DownloadRequest) -> None:
    """Runs in a daemon thread; updates _state throughout."""
    from src.ingestion.nse_downloader import download_all

    symbols  = UNIVERSES[req.universe]
    end_date = req.end or date.today().isoformat()

    def _on_progress(completed: int, total: int, current_date: str) -> bool:
        with _lock:
            if _state["cancelled"]:
                return False          # abort signal to download_all
            _state["completed_days"] = completed
            _state["total_days"]     = total
            _state["current_date"]   = current_date
        return True

    try:
        results = download_all(
            start=req.start,
            end=end_date,
            symbols=symbols,
            interval=req.interval,
            on_progress=_on_progress,
        )

        # Check if we were cancelled mid-way
        with _lock:
            if _state["cancelled"]:
                _state["status"] = "cancelled"
                return
            _state["symbols_saved"] = len(results)

        # ── Rebuild DuckDB if requested ──────────────────────────────────
        if req.rebuild_db:
            with _lock:
                _state["status"] = "building_db"
                _state["current_date"] = "Rebuilding signals database…"

            from src.database.duckdb_store import DuckDBStore, DB_PATH, RAW_DATA_DIR
            store = DuckDBStore(db_path=DB_PATH, raw_dir=RAW_DATA_DIR, read_only=False)
            try:
                store.build()
            finally:
                store.close()

        with _lock:
            _state["status"] = "done"
            _state["current_date"] = None

    except Exception as exc:
        with _lock:
            _state["status"] = "error"
            _state["error"] = str(exc)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/universes")
def list_universes() -> dict:
    """Return available universe options with stock counts."""
    return {
        key: {
            "label":       UNIVERSE_LABELS[key],
            "stock_count": len(syms) if syms is not None else "~2 600+",
        }
        for key, syms in UNIVERSES.items()
    }


@router.post("/start")
def start_download(req: DownloadRequest) -> dict:
    """Start a background data download.  Only one job runs at a time."""
    with _lock:
        if _state["status"] in ("running", "building_db"):
            raise HTTPException(
                status_code=409,
                detail="A download is already running. Cancel it first.",
            )

        # Validate dates
        try:
            start_dt = date.fromisoformat(req.start)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid start date: {req.start}")

        end_dt = date.fromisoformat(req.end) if req.end else date.today()
        if start_dt > end_dt:
            raise HTTPException(status_code=422, detail="start must be before end")

        # Estimate trading days for progress bar
        from src.ingestion.nse_downloader import _trading_days
        est_days = sum(1 for _ in _trading_days(start_dt, end_dt))

        # Reset state
        _state.update({
            "status":         "running",
            "total_days":     est_days,
            "completed_days": 0,
            "symbols_saved":  0,
            "current_date":   req.start,
            "error":          None,
            "started_at":     time.time(),
            "universe_label": UNIVERSE_LABELS[req.universe],
            "interval":       req.interval,
            "cancelled":      False,
        })

    thread = threading.Thread(target=_run_download, args=(req,), daemon=True)
    thread.start()

    return {
        "message":      "Download started",
        "universe":     UNIVERSE_LABELS[req.universe],
        "interval":     req.interval,
        "start":        req.start,
        "end":          req.end or date.today().isoformat(),
        "trading_days": est_days,
    }


@router.get("/status")
def get_status() -> dict:
    """Return current download job state for progress bar polling."""
    with _lock:
        snap = dict(_state)

    pct = 0
    if snap["total_days"] > 0:
        pct = round(snap["completed_days"] / snap["total_days"] * 100, 1)
    elif snap["status"] in ("building_db", "building_technicals"):
        pct = 99.0   # Show "almost done" while rebuilding DB / computing indicators
    elif snap["status"] == "done":
        pct = 100.0

    elapsed: float | None = None
    if snap["started_at"]:
        elapsed = round(time.time() - snap["started_at"], 1)

    return {
        "status":         snap["status"],
        "pct":            pct,
        "completed_days": snap["completed_days"],
        "total_days":     snap["total_days"],
        "symbols_saved":  snap["symbols_saved"],
        "current_date":   snap["current_date"],
        "universe_label": snap["universe_label"],
        "interval":       snap["interval"],
        "error":          snap["error"],
        "elapsed_sec":    elapsed,
    }


@router.post("/cancel")
def cancel_download() -> dict:
    """Request cancellation of the running download."""
    with _lock:
        if _state["status"] not in ("running", "building_db"):
            raise HTTPException(
                status_code=409,
                detail=f"No active download to cancel (status: {_state['status']})",
            )
        _state["cancelled"] = True

    return {"message": "Cancellation requested — download will stop after the current day."}


def _run_build_technicals() -> None:
    """Background thread: rebuild technicals table + extended_signals view."""
    from src.database.duckdb_store import DuckDBStore, DB_PATH, RAW_DATA_DIR
    store = DuckDBStore(db_path=DB_PATH, raw_dir=RAW_DATA_DIR, read_only=False)
    try:
        store.build_technicals()
        with _lock:
            _state["status"] = "done"
            _state["current_date"] = None
    except Exception as exc:
        with _lock:
            _state["status"] = "error"
            _state["error"] = str(exc)
    finally:
        store.close()


@router.post("/build-technicals")
def build_technicals_endpoint() -> dict:
    """Compute the technicals table and recreate the extended_signals view.

    Runs ``build_technicals()`` in a background thread within this process so
    DuckDB's in-process write lock is respected on Windows.
    Poll ``GET /api/downloader/status`` to track progress.
    """
    with _lock:
        if _state["status"] in ("running", "building_db", "building_technicals"):
            raise HTTPException(
                status_code=409,
                detail=f"A job is already running (status: {_state['status']}). Wait for it to finish.",
            )
        _state.update({
            "status":      "building_technicals",
            "error":       None,
            "started_at":  time.time(),
            "current_date": "Computing technical indicators…",
        })

    threading.Thread(target=_run_build_technicals, daemon=True).start()
    return {
        "message": "build_technicals started. Poll GET /api/downloader/status for progress.",
    }
