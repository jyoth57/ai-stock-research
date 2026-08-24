"""
fundamentals.py
---------------
Reads company financial statement CSVs into DuckDB and computes
key fundamental metrics:

    • ROE            – Net Income / Shareholders' Equity
    • ROCE           – EBIT / Capital Employed
    • EPS Growth     – Year-on-year % change in EPS
    • Revenue CAGR   – Annualised revenue growth over the full date range
    • Debt / Equity  – Total Debt / Shareholders' Equity
    • Free Cash Flow – Operating Cash Flow − |CapEx|

Expected CSV files (place under data/processed/)
-------------------------------------------------
income_statement.csv
    symbol, date, revenue, net_income, eps, ebit

balance_sheet.csv
    symbol, date, total_equity, total_assets, total_debt, current_liabilities

cash_flow.csv
    symbol, date, operating_cash_flow, capex

All monetary columns should be in the same unit (e.g. INR crores).
Dates must be parseable by DuckDB (YYYY-MM-DD recommended).

Usage
-----
    from src.fundamentals import FundamentalsEngine

    engine = FundamentalsEngine()                  # in-memory DuckDB
    engine.load_csvs()                             # reads from data/processed/
    df = engine.compute_metrics()                  # returns combined DataFrame
    df_tcs = engine.compute_metrics(symbol="TCS")  # filter by symbol
    engine.save_to_parquet()                       # writes data/processed/fundamentals.parquet
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PROCESSED_DIR = _PROJECT_ROOT / "data" / "processed"
_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

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
# Expected CSV columns (used for validation on load)
# ---------------------------------------------------------------------------

_REQUIRED_COLUMNS: dict[str, list[str]] = {
    "income_statement": ["symbol", "date", "revenue", "net_income", "eps", "ebit"],
    "balance_sheet": [
        "symbol",
        "date",
        "total_equity",
        "total_assets",
        "total_debt",
        "current_liabilities",
    ],
    "cash_flow": ["symbol", "date", "operating_cash_flow", "capex"],
}


# ---------------------------------------------------------------------------
# DuckDB SQL templates
# ---------------------------------------------------------------------------

# Metrics computed per (symbol, date) row
_METRICS_SQL = """
WITH base AS (
    SELECT
        i.symbol,
        i.date,

        -- Raw financials
        i.revenue,
        i.net_income,
        i.eps,
        i.ebit,
        b.total_equity,
        b.total_assets,
        b.total_debt,
        b.current_liabilities,
        cf.operating_cash_flow,
        cf.capex,

        -- Derived: Capital Employed = Total Assets − Current Liabilities
        (b.total_assets - b.current_liabilities)  AS capital_employed,

        -- Free Cash Flow = OCF − |CapEx|  (CapEx stored as negative in most sources)
        (cf.operating_cash_flow - ABS(cf.capex))  AS free_cash_flow

    FROM income_statement   i
    JOIN balance_sheet      b  USING (symbol, date)
    JOIN cash_flow          cf USING (symbol, date)
),
with_ratios AS (
    SELECT
        *,

        -- ROE  (%)
        CASE WHEN total_equity  <> 0
             THEN ROUND(net_income / total_equity  * 100, 2) END  AS roe_pct,

        -- ROCE  (%)
        CASE WHEN capital_employed <> 0
             THEN ROUND(ebit / capital_employed * 100, 2) END     AS roce_pct,

        -- Debt / Equity
        CASE WHEN total_equity <> 0
             THEN ROUND(total_debt / total_equity, 4) END          AS debt_to_equity,

        -- EPS YoY growth  (%)
        CASE WHEN LAG(eps) OVER w <> 0
             THEN ROUND(
                    (eps - LAG(eps) OVER w) / ABS(LAG(eps) OVER w) * 100,
                  2) END                                            AS eps_growth_pct,

        -- Revenue CAGR over full window for this symbol  (%)
        ROUND(
            (
                POWER(
                    LAST_VALUE(revenue) OVER w
                    / NULLIF(FIRST_VALUE(revenue) OVER w, 0),
                    1.0 / NULLIF(COUNT(*) OVER w - 1, 0)
                ) - 1
            ) * 100,
        2)                                                          AS revenue_cagr_pct

    FROM base
    WINDOW w AS (PARTITION BY symbol ORDER BY date
                 ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
)
SELECT
    symbol,
    date,
    revenue,
    net_income,
    eps,
    ebit,
    total_equity,
    total_assets,
    total_debt,
    capital_employed,
    free_cash_flow,
    roe_pct,
    roce_pct,
    debt_to_equity,
    eps_growth_pct,
    revenue_cagr_pct
FROM with_ratios
ORDER BY symbol, date
"""


# ---------------------------------------------------------------------------
# Engine class
# ---------------------------------------------------------------------------


class FundamentalsEngine:
    """Load financial statement CSVs into DuckDB and compute key ratios.

    Parameters
    ----------
    db_path:
        Path to a persistent DuckDB file.  Pass ``None`` (default) for an
        in-memory database.
    data_dir:
        Directory that contains ``income_statement.csv``, ``balance_sheet.csv``
        and ``cash_flow.csv``.  Defaults to ``data/processed/``.
    """

    def __init__(
        self,
        db_path: Optional[str | Path] = None,
        data_dir: Optional[str | Path] = None,
    ) -> None:
        self._db_path = str(db_path) if db_path else ":memory:"
        self._data_dir = Path(data_dir) if data_dir else _PROCESSED_DIR
        self._con = duckdb.connect(self._db_path)
        log.info("DuckDB connected  (%s)", self._db_path)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_csvs(self) -> None:
        """Read and register all three statement CSVs as DuckDB tables."""
        for table, required_cols in _REQUIRED_COLUMNS.items():
            csv_path = self._data_dir / f"{table}.csv"
            if not csv_path.exists():
                raise FileNotFoundError(
                    f"Expected CSV not found: {csv_path}\n"
                    f"Required columns: {required_cols}"
                )
            self._load_single(table, csv_path, required_cols)

    def _load_single(
        self,
        table: str,
        csv_path: Path,
        required_cols: list[str],
    ) -> None:
        df = pd.read_csv(csv_path, parse_dates=["date"])
        df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

        missing = set(required_cols) - set(df.columns)
        if missing:
            raise ValueError(
                f"[{table}] CSV is missing required columns: {sorted(missing)}"
            )

        df["symbol"] = df["symbol"].str.strip().str.upper()
        df["date"] = pd.to_datetime(df["date"])

        # Register as a DuckDB view backed by the DataFrame
        self._con.register(f"_tmp_{table}", df)
        self._con.execute(
            f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM _tmp_{table}"
        )
        self._con.unregister(f"_tmp_{table}")
        log.info("Loaded %-22s  %d rows, %d symbols",
                 f"{table}.csv", len(df), df["symbol"].nunique())

    # ------------------------------------------------------------------
    # Computation
    # ------------------------------------------------------------------

    def compute_metrics(
        self,
        symbol: Optional[str] = None,
    ) -> pd.DataFrame:
        """Compute and return all fundamental metrics.

        Parameters
        ----------
        symbol:
            Filter to a single NSE symbol (case-insensitive).
            If ``None``, returns metrics for all symbols.

        Returns
        -------
        pd.DataFrame
            One row per (symbol, date) with columns:
            symbol, date, revenue, net_income, eps, ebit,
            total_equity, total_assets, total_debt, capital_employed,
            free_cash_flow, roe_pct, roce_pct, debt_to_equity,
            eps_growth_pct, revenue_cagr_pct
        """
        df: pd.DataFrame = self._con.execute(_METRICS_SQL).df()

        if symbol:
            df = df[df["symbol"] == symbol.strip().upper()].reset_index(drop=True)

        log.info(
            "compute_metrics → %d rows, %d symbols",
            len(df),
            df["symbol"].nunique(),
        )
        return df

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_to_parquet(
        self,
        out_path: Optional[str | Path] = None,
        symbol: Optional[str] = None,
    ) -> Path:
        """Write computed metrics to a Parquet file.

        Parameters
        ----------
        out_path:
            Destination file.  Defaults to ``data/processed/fundamentals.parquet``.
        symbol:
            Optional symbol filter forwarded to :meth:`compute_metrics`.

        Returns
        -------
        Path
            Absolute path of the written file.
        """
        resolved = (
            Path(out_path) if out_path else _PROCESSED_DIR / "fundamentals.parquet"
        )
        df = self.compute_metrics(symbol=symbol)
        df.to_parquet(resolved, engine="pyarrow", compression="snappy", index=False)
        log.info("Saved fundamentals → %s", resolved.relative_to(_PROJECT_ROOT))
        return resolved

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._con.close()

    def __enter__(self) -> "FundamentalsEngine":
        return self

    def __exit__(self, *_) -> None:
        self.close()


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Compute fundamental metrics from financial statement CSVs"
    )
    parser.add_argument(
        "--data-dir",
        default=str(_PROCESSED_DIR),
        help="Directory containing income_statement.csv, balance_sheet.csv, cash_flow.csv",
    )
    parser.add_argument(
        "--symbol", default=None, help="Filter output to a single NSE symbol"
    )
    parser.add_argument(
        "--out", default=None, help="Output Parquet path (default: data/processed/fundamentals.parquet)"
    )
    args = parser.parse_args()

    with FundamentalsEngine(data_dir=args.data_dir) as eng:
        eng.load_csvs()
        out = eng.save_to_parquet(out_path=args.out, symbol=args.symbol)
        print(f"Written: {out}")
