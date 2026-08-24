"""Shared utility functions used across the project."""

from __future__ import annotations

import functools
import time
import logging
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Generator, TypeVar

from .constants import NSE_SUFFIX

log = logging.getLogger(__name__)

_F = TypeVar("_F", bound=Callable)


# ── Symbol helpers ────────────────────────────────────────────────────────────

def nse_ticker(symbol: str) -> str:
    """Return the yfinance-compatible ticker string for an NSE symbol.

    >>> nse_ticker("reliance")
    'RELIANCE.NS'
    >>> nse_ticker("RELIANCE.NS")
    'RELIANCE.NS'
    """
    s = symbol.strip().upper()
    return s if s.endswith(NSE_SUFFIX) else s + NSE_SUFFIX


def strip_ns(symbol: str) -> str:
    """Remove the '.NS' suffix from a yfinance ticker.

    >>> strip_ns("RELIANCE.NS")
    'RELIANCE'
    """
    return symbol.strip().upper().removesuffix(NSE_SUFFIX)


# ── Date helpers ──────────────────────────────────────────────────────────────

def today_str() -> str:
    """Return today's date as YYYY-MM-DD."""
    return date.today().isoformat()


def days_ago(n: int) -> str:
    """Return the date n days ago as YYYY-MM-DD."""
    return (date.today() - timedelta(days=n)).isoformat()


def parse_date(value: str | date | datetime) -> date:
    """Normalise various date inputs to a date object."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


# ── Filesystem helpers ────────────────────────────────────────────────────────

def ensure_dir(path: str | Path) -> Path:
    """Create directory (and parents) if it does not exist; return Path."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── Retry decorator ───────────────────────────────────────────────────────────

def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
) -> Callable[[_F], _F]:
    """Retry decorator with exponential back-off.

    Usage::

        @retry(max_attempts=3, delay=1.0, exceptions=(requests.HTTPError,))
        def fetch_data(): ...
    """
    def decorator(fn: _F) -> _F:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            wait = delay
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:
                    if attempt == max_attempts:
                        raise
                    log.warning(
                        "%s failed (attempt %d/%d): %s — retrying in %.1fs",
                        fn.__name__, attempt, max_attempts, exc, wait,
                    )
                    time.sleep(wait)
                    wait *= backoff
        return wrapper  # type: ignore[return-value]
    return decorator


# ── Timer context manager ─────────────────────────────────────────────────────

@contextmanager
def timer(label: str = "") -> Generator[None, None, None]:
    """Log execution time of a code block.

    Usage::

        with timer("download RELIANCE"):
            df = yf.download(...)
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        log.info("%s completed in %.3fs", label or "block", elapsed)


# ── Chunking ──────────────────────────────────────────────────────────────────

def chunk_list(lst: list, size: int) -> list[list]:
    """Split a list into chunks of at most *size* items."""
    return [lst[i: i + size] for i in range(0, len(lst), size)]
