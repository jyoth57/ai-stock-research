"""
nse_downloader.py
-----------------
Downloads daily OHLCV data for ALL NSE-listed equities using NSE's publicly
available Bhavcopy archives (no login, no bot-bypass required).

How it works
------------
NSE publishes a daily full Bhavcopy CSV at:
    https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{DDMMYYYY}.csv

Each CSV contains OHLCV rows for every EQ-series stock traded that day.
This downloader iterates over every trading date in the requested window,
downloads and parses each file, then writes one Parquet file per stock
under data/raw/.

Public API
----------
    from src.ingestion.nse_downloader import download_all, download_stocks

CLI examples
------------
    # All NSE equities, last 3 months (default)
    python -m src.ingestion.nse_downloader

    # Specific symbols
    python -m src.ingestion.nse_downloader --symbols RELIANCE TCS INFY

    # Custom date range
    python -m src.ingestion.nse_downloader --start 2026-01-01 --end 2026-07-16

    # Limit total trading days downloaded (useful for testing)
    python -m src.ingestion.nse_downloader --limit-days 5
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from typing import Callable, Iterator, Optional

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = _PROJECT_ROOT / "data" / "raw"
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Full Bhavcopy (all EQ-series, all fields) — date encoded as DDMMYYYY
NSE_BHAV_URL = (
    "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv"
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

# Seconds to wait between day-file downloads
REQUEST_DELAY = 0.5

# Bhavcopy CSV column (stripped) -> canonical OHLCV name
_COL_MAP = {
    "SYMBOL": "Symbol",
    "SERIES": "Series",
    "DATE1": "Date",
    "OPEN_PRICE": "Open",
    "HIGH_PRICE": "High",
    "LOW_PRICE": "Low",
    "CLOSE_PRICE": "Close",
    "TTL_TRD_QNTY": "Volume",
}


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def _trading_days(start: date, end: date) -> Iterator[date]:
    """Yield every Mon-Fri between start and end (inclusive).

    NSE holidays are not filtered here; missing Bhavcopy files (404) are
    silently skipped by the downloader.
    """
    current = start
    while current <= end:
        if current.weekday() < 5:  # Mon=0 .. Fri=4
            yield current
        current += timedelta(days=1)


def _bhav_url(d: date) -> str:
    ddmmyyyy = d.strftime("%d%m%Y")          # e.g. 07072026
    return NSE_BHAV_URL.format(ddmmyyyy=ddmmyyyy)


# ---------------------------------------------------------------------------
# Single-day Bhavcopy fetch
# ---------------------------------------------------------------------------

def _fetch_bhav(d: date, session: requests.Session) -> pd.DataFrame | None:
    """Download and parse the Bhavcopy for one trading day.

    Returns a DataFrame with columns [Symbol, Series, Open, High, Low, Close,
    Volume, Date] or None if the file is unavailable (holiday / future date).
    """
    url = _bhav_url(d)
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code == 404:
            log.debug("No Bhavcopy for %s (holiday / non-trading day)", d)
            return None
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("Could not fetch Bhavcopy for %s: %s", d, exc)
        return None

    try:
        df = pd.read_csv(StringIO(resp.text))
    except Exception as exc:
        log.warning("Failed to parse Bhavcopy for %s: %s", d, exc)
        return None

    # Strip leading/trailing whitespace from column names
    df.columns = df.columns.str.strip()

    # Keep only EQ series
    if "SERIES" in df.columns:
        df = df[df["SERIES"].str.strip() == "EQ"].copy()

    # Rename to canonical names
    rename = {k: v for k, v in _COL_MAP.items() if k in df.columns}
    df = df.rename(columns=rename)

    # Parse the date column that comes from the CSV (e.g. "07-Jul-2026")
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], dayfirst=True)
    else:
        df["Date"] = pd.Timestamp(d)

    log.info("Bhavcopy %s  ->  %d EQ rows", d, len(df))
    return df


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def download_all(
    start: str,
    end: str | None = None,
    symbols: list[str] | None = None,
    interval: str = "1d",
    on_progress: Optional[Callable[[int, int, str], bool]] = None,
) -> dict[str, pd.DataFrame]:
    """Download OHLCV data from NSE Bhavcopy archives.

    Iterates over every trading day in [start, end], downloads the daily
    Bhavcopy, and writes one Parquet file per stock to data/raw/.

    Parameters
    ----------
    start:
        Start date in YYYY-MM-DD format.
    end:
        End date in YYYY-MM-DD format (default: today).
    symbols:
        Optional list of bare NSE symbols to keep.  When None every EQ-series
        stock in the Bhavcopy files is written.
    interval:
        Output candle interval.  ``"1d"`` writes daily Parquet files directly.
        ``"1w"`` resamples daily bars to weekly OHLCV before writing.
    on_progress:
        Optional callable ``(completed_days, total_days, current_date_str) -> bool``.
        Called after every day-file is processed.  Return ``False`` to cancel
        the download early; any other return value (including ``True`` or ``None``)
        continues the loop.

    Returns
    -------
    dict[str, pd.DataFrame]
        Mapping of symbol -> full OHLCV DataFrame for the requested window.
    """
    end_dt   = date.fromisoformat(end) if end else date.today()
    start_dt = date.fromisoformat(start)

    if symbols:
        symbols = [s.strip().upper() for s in symbols]

    session = requests.Session()
    session.headers.update(_HEADERS)

    daily_frames: list[pd.DataFrame] = []
    days = list(_trading_days(start_dt, end_dt))
    total = len(days)
    log.info(
        "Fetching Bhavcopy for %d potential trading days  [%s -> %s]",
        total, start_dt, end_dt,
    )

    for idx, d in enumerate(days, start=1):
        df = _fetch_bhav(d, session)
        if df is not None:
            daily_frames.append(df)
        time.sleep(REQUEST_DELAY)

        # Fire progress callback; abort if it returns False (cancel signal)
        if on_progress is not None:
            keep_going = on_progress(idx, total, d.isoformat())
            if keep_going is False:
                log.info("Download cancelled after %d / %d days.", idx, total)
                break

    if not daily_frames:
        log.warning("No Bhavcopy data retrieved for the requested window.")
        return {}

    all_data = pd.concat(daily_frames, ignore_index=True)

    # Filter to requested symbols if provided
    if symbols:
        all_data = all_data[all_data["Symbol"].isin(symbols)]

    # Ensure numeric OHLCV columns
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col in all_data.columns:
            all_data[col] = pd.to_numeric(all_data[col], errors="coerce")

    all_data["Date"] = pd.to_datetime(all_data["Date"])

    # Group by symbol and write per-symbol Parquet files
    results: dict[str, pd.DataFrame] = {}
    grouped = all_data.groupby("Symbol")
    log.info("Writing Parquet files for %d symbols …", len(grouped))

    for sym, sym_df in grouped:
        sym_df = (
            sym_df[["Date", "Open", "High", "Low", "Close", "Volume"]]
            .sort_values("Date")
            .set_index("Date")
        )

        # Resample to weekly if requested
        if interval == "1w":
            sym_df = (
                sym_df.resample("W")
                .agg({"Open": "first", "High": "max", "Low": "min",
                      "Close": "last", "Volume": "sum"})
                .dropna(subset=["Close"])
            )

        out_path = RAW_DATA_DIR / f"{sym}.parquet"

        # Merge with any existing Parquet so historical data is preserved
        if out_path.exists():
            try:
                existing = pd.read_parquet(out_path)
                existing.index = pd.to_datetime(existing.index)
                sym_df = (
                    pd.concat([existing, sym_df])
                    .loc[~pd.concat([existing, sym_df]).index.duplicated(keep="last")]
                    .sort_index()
                )
            except Exception:
                pass  # If existing file is corrupt, overwrite cleanly

        sym_df.to_parquet(out_path, engine="pyarrow", compression="snappy")
        results[str(sym)] = sym_df

    succeeded = len(results)
    log.info(
        "Done. Saved %d symbol Parquet files to %s",
        succeeded,
        RAW_DATA_DIR.relative_to(_PROJECT_ROOT),
    )
    return results


# Alias for backwards compatibility
def download_stocks(
    symbols: list[str],
    start: str,
    end: str | None = None,
    interval: str = "1d",
) -> dict[str, pd.DataFrame]:
    """Download OHLCV for a specific list of NSE symbols via Bhavcopy."""
    return download_all(start=start, end=end, symbols=symbols, interval=interval)


def download_stock(
    symbol: str,
    start: str,
    end: str | None = None,
    interval: str = "1d",
) -> pd.DataFrame:
    """Download OHLCV for a single NSE symbol via Bhavcopy."""
    results = download_all(start=start, end=end, symbols=[symbol], interval=interval)
    return results.get(symbol.strip().upper(), pd.DataFrame())


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    _default_end   = date.today().isoformat()
    _default_start = (date.today() - timedelta(days=90)).isoformat()

    parser = argparse.ArgumentParser(
        description=(
            "Download NSE OHLCV data from NSE Bhavcopy archives.\n"
            "Omit --symbols to download ALL listed equities."
        )
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        metavar="SYM",
        help="NSE symbols to keep (default: every EQ-series stock)",
    )
    parser.add_argument(
        "--start",
        default=_default_start,
        help=f"Start date YYYY-MM-DD  (default: {_default_start})",
    )
    parser.add_argument(
        "--end",
        default=_default_end,
        help=f"End date YYYY-MM-DD  (default: {_default_end})",
    )
    parser.add_argument(
        "--limit-days",
        type=int,
        default=None,
        metavar="N",
        help="Download only the first N trading days — useful for smoke-testing",
    )

    args = parser.parse_args()

    # Honour --limit-days by adjusting the end date
    if args.limit_days:
        days_iter = _trading_days(
            date.fromisoformat(args.start),
            date.fromisoformat(args.end),
        )
        capped = list(days_iter)[: args.limit_days]
        if capped:
            args.end = capped[-1].isoformat()
        log.info("Capped to first %d trading day(s)  end -> %s", args.limit_days, args.end)

    download_all(start=args.start, end=args.end, symbols=args.symbols)