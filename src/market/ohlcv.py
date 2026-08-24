"""OHLCVStore — unified read/write interface for daily price data.

All data lives as per-symbol Parquet files under data/raw/.
Use this class instead of accessing the filesystem directly so that
the rest of the codebase is insulated from storage decisions.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

from src.core.settings import settings
from src.core.utils import strip_ns, today_str
from src.core.exceptions import DataNotFoundError
from src.core.constants import OHLCV_COLUMNS

log = logging.getLogger(__name__)


class OHLCVStore:
    """Read and write OHLCV Parquet files for NSE stocks.

    Parameters
    ----------
    data_dir:
        Root directory that holds ``<SYMBOL>.parquet`` files.
        Defaults to ``settings.raw_data_dir``.
    """

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self._dir = data_dir or settings.raw_data_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------

    def _path(self, symbol: str) -> Path:
        return self._dir / f"{strip_ns(symbol)}.parquet"

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def read(
        self,
        symbol: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        """Load OHLCV data for *symbol*, optionally sliced by date range.

        Parameters
        ----------
        symbol:  Bare NSE symbol (e.g. ``"RELIANCE"``)
        start:   Inclusive start date ``YYYY-MM-DD``
        end:     Inclusive end date   ``YYYY-MM-DD``

        Returns
        -------
        pd.DataFrame
            DatetimeIndex, columns: Open High Low Close Volume

        Raises
        ------
        DataNotFoundError
            If no Parquet file exists for the symbol.
        """
        path = self._path(symbol)
        if not path.exists():
            raise DataNotFoundError(
                f"No OHLCV data found for {strip_ns(symbol)}. "
                "Run the downloader first."
            )

        df = pd.read_parquet(path)
        df.index = pd.to_datetime(df.index)
        df.index.name = "Date"

        if start:
            df = df[df.index >= start]
        if end:
            df = df[df.index <= end]

        return df

    def read_multi(
        self,
        symbols: list[str],
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> dict[str, pd.DataFrame]:
        """Read OHLCV for multiple symbols; skip missing ones with a warning."""
        result = {}
        for sym in symbols:
            try:
                result[strip_ns(sym)] = self.read(sym, start=start, end=end)
            except DataNotFoundError:
                log.warning("Skipping %s — no local data", strip_ns(sym))
        return result

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def write(self, df: pd.DataFrame, symbol: str) -> Path:
        """Persist a OHLCV DataFrame as Parquet.

        The DataFrame must have a DatetimeIndex and at minimum the
        columns listed in ``OHLCV_COLUMNS``.
        """
        if df.empty:
            log.warning("write(%s): DataFrame is empty — skipping", symbol)
            return self._path(symbol)

        path = self._path(symbol)
        df = df[[c for c in OHLCV_COLUMNS if c in df.columns]].copy()
        df.index = pd.to_datetime(df.index)
        df.index.name = "Date"
        df.sort_index(inplace=True)
        df.to_parquet(path, engine="pyarrow", compression="snappy")
        log.debug("Wrote %d rows → %s", len(df), path.name)
        return path

    def append(self, df: pd.DataFrame, symbol: str) -> Path:
        """Append new rows to an existing Parquet, deduplicating by date."""
        try:
            existing = self.read(symbol)
            combined = pd.concat([existing, df])
            combined = combined[~combined.index.duplicated(keep="last")]
            combined.sort_index(inplace=True)
        except DataNotFoundError:
            combined = df
        return self.write(combined, symbol)

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def list_symbols(self) -> list[str]:
        """Return bare symbols that have local Parquet files."""
        return sorted(p.stem for p in self._dir.glob("*.parquet"))

    def latest_date(self, symbol: str) -> Optional[date]:
        """Return the most recent date in the local data, or None."""
        try:
            df = self.read(symbol)
            return df.index.max().date() if not df.empty else None
        except DataNotFoundError:
            return None

    def needs_update(self, symbol: str) -> bool:
        """Return True if there is no data or the last row is not today."""
        last = self.latest_date(symbol)
        if last is None:
            return True
        # Markets close on weekdays; treat Friday as up to date until Monday
        today = date.today()
        return last < today and today.weekday() not in (5, 6) or last < today

    def info(self) -> pd.DataFrame:
        """Return a summary DataFrame: symbol, rows, first_date, last_date."""
        rows = []
        for sym in self.list_symbols():
            try:
                df = self.read(sym)
                rows.append({
                    "symbol": sym,
                    "rows": len(df),
                    "first_date": df.index.min().date(),
                    "last_date": df.index.max().date(),
                })
            except Exception:
                pass
        return pd.DataFrame(rows)
