"""
build_db.py
-----------
One-time (or post-download) script that builds the DuckDB database from
the Parquet files in data/raw/.

Run after every nse_downloader run to keep the DB in sync:

    python -m scripts.build_db

Options:
    --raw-dir   PATH   Override the default data/raw directory
    --db-path   PATH   Override the default database path
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.database.duckdb_store import DuckDBStore, RAW_DATA_DIR, DB_PATH

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build DuckDB from NSE Parquet files")
    parser.add_argument("--raw-dir", default=str(RAW_DATA_DIR))
    parser.add_argument("--db-path", default=str(DB_PATH))
    args = parser.parse_args()

    raw_dir = Path(args.raw_dir)
    db_path = Path(args.db_path)

    parquet_count = len(list(raw_dir.glob("*.parquet")))
    if parquet_count == 0:
        log.error("No parquet files found in %s. Run nse_downloader first.", raw_dir)
        sys.exit(1)

    log.info("Found %d parquet files in %s", parquet_count, raw_dir)
    log.info("Target database: %s", db_path)

    t0 = time.perf_counter()
    store = DuckDBStore(db_path=db_path, raw_dir=raw_dir, read_only=False)
    store.build()

    con = store.connect()

    # ── Sector map ─────────────────────────────────────────────────────────
    sector_csv = raw_dir / "sector_map.csv"
    if sector_csv.exists():
        import pandas as pd
        log.info("Loading sector_map …")
        mapping = pd.read_csv(sector_csv)
        con.execute("CREATE OR REPLACE TABLE sector_map AS SELECT * FROM mapping")
        con.execute("""
            CREATE OR REPLACE TABLE signals AS
            SELECT s.*, COALESCE(sm.sector, 'Other') AS sector
            FROM signals s
            LEFT JOIN sector_map sm USING (symbol)
        """)
        n = con.execute("SELECT COUNT(DISTINCT sector) FROM signals").fetchone()[0]
        log.info("sector_map loaded — %d distinct sectors", n)

    # ── Python scoring engine ───────────────────────────────────────────────
    log.info("Running Python scoring engine …")
    from src.scoring.engine import compute_all_scores
    scored = compute_all_scores(con)

    con.execute("CREATE OR REPLACE TABLE features AS SELECT * FROM scored")

    # Detect ETFs / non-equity asset types
    con.execute("""
        CREATE OR REPLACE TABLE asset_types AS
        SELECT symbol,
            CASE
                WHEN symbol LIKE '%ETF%' OR symbol LIKE '%IETF%'
                  OR symbol LIKE '%BEES%' OR symbol LIKE '%NIFTY%'
                  OR symbol LIKE '%GOLD%' OR symbol LIKE '%SILVERBEES%'
                  OR symbol LIKE '%LICNETF%' OR symbol LIKE '%HDFCMFGETF%'
                  OR symbol LIKE '%NIPPON%' OR symbol LIKE '%AXISGOLD%'
                  OR symbol LIKE '%SBIETF%' OR symbol LIKE '%ITBEES%'
                  OR symbol LIKE '%SETF%' OR symbol LIKE '%UTIETF%'
                  OR symbol LIKE '%COMMOIETF%' OR symbol LIKE '%GSEC%'
                  OR symbol LIKE '%LIQUIDBEES%' OR symbol LIKE '%LIQUIDCASE%'
                  OR symbol LIKE '%IVZINGOLD%' OR symbol LIKE '%MAFANG%'
                  OR symbol LIKE '%FUND%'
                THEN 'ETF'
                ELSE 'Equity'
            END AS asset_type
        FROM (SELECT DISTINCT symbol FROM signals)
    """)

    # Final signals table — deduplicated, ETFs excluded from ranking
    con.execute("""
        CREATE OR REPLACE TABLE signals AS
        WITH ranked AS (
            SELECT
                s.symbol,
                s.sector,
                atype.asset_type,
                f.last_close,
                f.pct_1d, f.pct_5d, f.pct_20d,
                f.volume_ratio,
                CASE WHEN f.breakout = 1      THEN true ELSE false END AS breakout,
                CASE WHEN f.volume_ratio >= 2  THEN true ELSE false END AS volume_spike,
                CASE WHEN f.pct_above_50dma >= 0 THEN true ELSE false END AS above_50dma,
                CASE WHEN f.pct_from_52w_high <= 5 THEN true ELSE false END AS near_52w_high,
                CASE WHEN ABS(f.pct_1d) >= 8  THEN true ELSE false END AS big_mover,
                f.pct_above_50dma, f.pct_from_52w_high,
                f.rsi_14, f.green_days_5, f.gap_pct,
                f.breakout_age, f.atr_pct, f.range_position,
                f.momentum_score,
                f.continuation_prob,
                f.expected_return,
                f.downside_prob,
                f.historical_matches,
                f.confidence,
                f.exhaustion_score,
                f.risk_score,
                f.risk_liquidity,
                f.risk_volatility,
                f.risk_gap,
                f.risk_extension,
                f.final_score,
                f.top_positive_factors,
                f.top_negative_factors,
                -- Multi-period return stats from historical k-NN
                f.avg_ret_1d,
                f.avg_ret_10d,
                f.avg_ret_20d,
                f.avg_max_drawdown,
                f.win_rate_10d,
                f.win_rate_20d,
                -- New features
                f.rvol_5,
                f.atr_5_pct,
                f.atr_expanding,
                f.rel_strength_5d,
                f.breakout_extension,
                f.sma10_above_sma20,
                CASE WHEN f.downside_prob > 0
                     THEN ROUND(f.continuation_prob / f.downside_prob, 2)
                     ELSE ROUND(f.continuation_prob / 1.0, 2)
                END AS reward_risk_ratio,
                CASE
                    WHEN f.continuation_prob >= 50 AND f.risk_score < 25
                        THEN 'High Conviction'
                    WHEN f.momentum_score >= 55
                        THEN 'Momentum'
                    WHEN f.breakout_age <= 1 AND f.volume_ratio >= 2
                        THEN 'Early Breakout'
                    WHEN f.pct_5d < 0 AND f.momentum_score >= 35
                        THEN 'Pullback Candidate'
                    WHEN f.continuation_prob >= 35 AND f.risk_score >= 35
                        THEN 'High Risk / High Reward'
                    ELSE 'Watchlist'
                END AS trade_category,
                ROW_NUMBER() OVER (PARTITION BY s.symbol ORDER BY f.final_score DESC) AS _rn
            FROM signals s
            JOIN features     f     USING (symbol)
            JOIN asset_types  atype USING (symbol)
        )
        SELECT * EXCLUDE (_rn)
        FROM ranked
        WHERE _rn = 1
          AND asset_type = 'Equity'
        ORDER BY final_score DESC
    """)

    sig_n    = con.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    dup_n    = con.execute("SELECT COUNT(*) FROM (SELECT symbol, COUNT(*) n FROM signals GROUP BY symbol HAVING n>1)").fetchone()[0]
    etf_kept = con.execute("SELECT COUNT(*) FROM ranked WHERE asset_type != 'Equity' 2>&1").fetchone()[0] if False else 0
    log.info("Final signals table: %d equity rows, %d duplicates remaining", sig_n, dup_n)

    elapsed = time.perf_counter() - t0

    log.info("Database built in %.1f seconds", elapsed)
    log.info("Ready — query with:  SELECT * FROM signals ORDER BY momentum_score DESC LIMIT 20;")


if __name__ == "__main__":
    main()
