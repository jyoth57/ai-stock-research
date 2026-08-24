"""
duckdb_store.py
---------------
Manages the DuckDB database for the QuantAI platform.

Schema
------
  ohlcv        — raw OHLCV rows loaded from data/raw/*.parquet
  signals      — pre-computed momentum signals (rebuilt via compute_signals())
  technicals   — full technical indicator snapshot per symbol (EMA/RSI/MACD/ADX/…)

  extended_signals (VIEW) — signals LEFT JOIN technicals

All signal computation runs as a single SQL query using window functions,
turning the ~37-second Python loop into a sub-second analytical query.
The technicals table is built using pandas-ta after the SQL step.

Usage
-----
    from src.database.duckdb_store import DuckDBStore

    store = DuckDBStore()
    store.build()                       # load Parquets + compute signals (once)
    df = store.get_signals()            # basic momentum signals
    df = store.get_full_scan()          # extended signals with all indicators
    ohlcv = store.get_ohlcv("RELIANCE")
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import duckdb
import pandas as pd

if TYPE_CHECKING:
    from src.technicals.indicators import TechnicalSignals

log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR  = _PROJECT_ROOT / "data" / "raw"
DB_PATH       = _PROJECT_ROOT / "database" / "duckdb" / "quant.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# SQL — load all Parquets as a single virtual OHLCV table
# ---------------------------------------------------------------------------

_LOAD_OHLCV_SQL = """
CREATE OR REPLACE TABLE ohlcv AS
SELECT
    replace(regexp_extract(filename, '[^/\\\\]+\\.parquet$', 0), '.parquet', '') AS symbol,
    CAST("Date"   AS DATE)    AS date,
    CAST("Open"   AS DOUBLE)  AS open,
    CAST("High"   AS DOUBLE)  AS high,
    CAST("Low"    AS DOUBLE)  AS low,
    CAST("Close"  AS DOUBLE)  AS close,
    CAST("Volume" AS BIGINT)  AS volume
FROM read_parquet('{glob}', filename=true, union_by_name=true)
WHERE "Close" IS NOT NULL
  AND "Close" > 0;
"""

# ---------------------------------------------------------------------------
# SQL — compute every momentum signal in one pass (window functions)
# ---------------------------------------------------------------------------

_COMPUTE_SIGNALS_SQL = """
CREATE OR REPLACE TABLE signals AS
WITH base AS (
    SELECT
        symbol,
        date,
        close,
        volume,
        LAG(close, 1)  OVER w AS prev_close,
        LAG(close, 5)  OVER w AS close_5d,
        LAG(close, 20) OVER w AS close_20d,
        AVG(volume)    OVER (PARTITION BY symbol ORDER BY date
                             ROWS BETWEEN 21 PRECEDING AND 1 PRECEDING) AS avg_vol_20,
        AVG(close)     OVER (PARTITION BY symbol ORDER BY date
                             ROWS BETWEEN 49 PRECEDING AND CURRENT ROW)  AS sma50,
        MAX(close)     OVER (PARTITION BY symbol ORDER BY date
                             ROWS BETWEEN 251 PRECEDING AND CURRENT ROW) AS high_52w,
        MAX(close)     OVER (PARTITION BY symbol ORDER BY date
                             ROWS BETWEEN 21 PRECEDING AND 1 PRECEDING)  AS resistance_20d,
        ROW_NUMBER()   OVER (PARTITION BY symbol ORDER BY date DESC)     AS rn
    FROM ohlcv
    WINDOW w AS (PARTITION BY symbol ORDER BY date)
),
latest AS (
    SELECT * FROM base WHERE rn = 1
      AND prev_close   IS NOT NULL
      AND close_20d    IS NOT NULL
      AND avg_vol_20   IS NOT NULL
      AND avg_vol_20   > 0
)
SELECT
    symbol,
    ROUND(close,  2)                                              AS last_close,
    ROUND((close / prev_close   - 1) * 100, 2)                   AS pct_1d,
    ROUND((close / NULLIF(close_5d,  0) - 1) * 100, 2)           AS pct_5d,
    ROUND((close / NULLIF(close_20d, 0) - 1) * 100, 2)           AS pct_20d,
    ROUND(volume / avg_vol_20, 2)                                 AS volume_ratio,
    close > sma50                                                 AS above_50dma,
    close > NULLIF(resistance_20d, 0)                            AS breakout,
    (high_52w - close) / NULLIF(high_52w, 0) * 100 <= 5         AS near_52w_high,
    ROUND((high_52w - close) / NULLIF(high_52w, 0) * 100, 2)    AS pct_from_52w_high,
    volume / avg_vol_20 >= 2                                      AS volume_spike,
    ABS((close / prev_close - 1) * 100) >= 8                    AS big_mover,
    ROUND(LEAST(100,
        GREATEST(0, LEAST((close / NULLIF(close_20d, 0) - 1) * 100, 20))
        + GREATEST(0, LEAST((close / NULLIF(close_5d,  0) - 1) * 100 * 2, 10))
        + CASE WHEN close > sma50 THEN 10 ELSE 0 END
        + GREATEST(0, LEAST((volume / avg_vol_20 - 1) * 5, 15))
        + CASE WHEN volume / avg_vol_20 >= 2 THEN 10 ELSE 0 END
        + CASE WHEN (high_52w - close) / NULLIF(high_52w, 0) * 100 <= 5 THEN 10 ELSE 0 END
        + CASE WHEN close > NULLIF(resistance_20d, 0) THEN 10 ELSE 0 END
        + GREATEST(0, LEAST((close / prev_close - 1) * 100, 5))
    ), 1)                                                          AS momentum_score
FROM latest
ORDER BY momentum_score DESC;
"""

# ---------------------------------------------------------------------------
# SQL — empirical continuation score
# For each symbol: of all past sessions where it had the breakout+vol+50dma
# setup, what % led to ≥5% gain in the following 5 sessions?
# ---------------------------------------------------------------------------

_CONTINUATION_SCORE_SQL = """
CREATE OR REPLACE TABLE continuation AS
WITH setup_days AS (
    SELECT
        symbol,
        date,
        close                                                          AS entry_close,
        LEAD(close, 5) OVER (PARTITION BY symbol ORDER BY date)       AS exit_close,
        -- setup conditions
        close > MAX(close) OVER (PARTITION BY symbol ORDER BY date
                                 ROWS BETWEEN 21 PRECEDING AND 1 PRECEDING)  AS is_breakout,
        volume >= 2 * AVG(volume) OVER (PARTITION BY symbol ORDER BY date
                                        ROWS BETWEEN 21 PRECEDING AND 1 PRECEDING) AS is_vol_spike,
        close > AVG(close) OVER (PARTITION BY symbol ORDER BY date
                                 ROWS BETWEEN 49 PRECEDING AND CURRENT ROW)  AS is_above_50dma,
        AVG(volume) OVER (PARTITION BY symbol ORDER BY date
                          ROWS BETWEEN 21 PRECEDING AND 1 PRECEDING)         AS avg_vol
    FROM ohlcv
),
qualified AS (
    SELECT
        symbol,
        date,
        entry_close,
        exit_close,
        CASE WHEN exit_close IS NOT NULL AND (exit_close - entry_close) / entry_close >= 0.05
             THEN 1 ELSE 0 END AS was_success
    FROM setup_days
    WHERE is_breakout   = true
      AND is_vol_spike  = true
      AND is_above_50dma = true
      AND avg_vol       > 0
      AND exit_close    IS NOT NULL
)
SELECT
    symbol,
    COUNT(*)                                   AS setup_count,
    SUM(was_success)                           AS success_count,
    ROUND(100.0 * SUM(was_success) / COUNT(*), 1) AS continuation_score
FROM qualified
GROUP BY symbol
HAVING COUNT(*) >= 2
ORDER BY continuation_score DESC;
"""


# ---------------------------------------------------------------------------
# Derived extended-row builder (rule-based — no LLM)
# ---------------------------------------------------------------------------

def _derive_extended_row(sig: "TechnicalSignals") -> dict:
    """Compute all derived technical fields from a TechnicalSignals object.

    These are deterministic rule-based derivations — entry/SL/targets,
    trend classification, confidence score, grade, holding period, etc.
    The LLM is not involved here; call the technical_analysis_chain for
    narrative explanations of individual stocks.
    """
    price      = sig.price
    atr        = sig.atr_14
    support    = sig.support
    resistance = sig.resistance

    # ── EMA alignment ───────────────────────────────────────────────────────
    ema_full_bull  = sig.ema20_above_ema50 and sig.ema50_above_ema200
    ema_full_bear  = (not sig.ema20_above_ema50) and (sig.ema50 < sig.ema200)

    # ── Trend classification ─────────────────────────────────────────────────
    if ema_full_bull and sig.adx_14 > 25 and sig.rsi_14 > 55:
        trend = "Strong Bullish"
    elif ema_full_bull:
        trend = "Bullish"
    elif ema_full_bear and sig.adx_14 > 25:
        trend = "Strong Bearish"
    elif ema_full_bear:
        trend = "Bearish"
    else:
        trend = "Neutral"

    # ── Breakout quality ─────────────────────────────────────────────────────
    if sig.breakout:
        if sig.volume_ratio > 2.5 and sig.adx_14 > 30 and sig.breakout_type != "None":
            bq = "Excellent"
        elif sig.volume_ratio > 1.8 and sig.adx_14 > 20:
            bq = "Good"
        elif sig.volume_ratio > 1.2:
            bq = "Average"
        else:
            bq = "Poor"
    else:
        bq = "None"

    # ── Entry / Stop-Loss / Targets ──────────────────────────────────────────
    entry = round(price if not sig.breakout else max(price, resistance * 1.001), 2)
    sl    = round(max(support, price - 2.0 * atr), 2) if atr > 0 else round(price * 0.95, 2)
    risk  = entry - sl

    t1 = round(entry + 1.5 * atr, 2) if atr > 0 else round(entry * 1.03, 2)
    t2 = round(resistance if resistance > entry else entry + 3.0 * atr, 2)
    t3 = round(t2 + (t2 - entry) * 0.5, 2)
    rr = round((t1 - entry) / risk, 2) if risk > 0 else 0.0

    # ── Institutional behaviour ──────────────────────────────────────────────
    if sig.volume_ratio > 3.0 and sig.rsi_14 > 55:
        institutional = "Accumulation"
    elif sig.volume_ratio > 3.0 and sig.rsi_14 < 45:
        institutional = "Distribution"
    elif sig.volume_ratio > 2.0:
        institutional = "Elevated Interest"
    else:
        institutional = "Normal"

    # ── Confidence score (0–100) ─────────────────────────────────────────────
    conf = 0
    if ema_full_bull:             conf += 25
    elif sig.ema20_above_ema50:   conf += 12
    if sig.adx_14 > 30:           conf += 20
    elif sig.adx_14 > 20:         conf += 12
    if 50 < sig.rsi_14 <= 70:     conf += 20
    elif 45 < sig.rsi_14 <= 50:   conf += 10
    elif sig.rsi_14 > 70:         conf += 8   # overbought — slightly penalised
    if sig.volume_ratio > 2.0:    conf += 15
    elif sig.volume_ratio > 1.2:  conf += 8
    if sig.breakout:              conf += 10
    if sig.rs_vs_nifty_20d is not None and sig.rs_vs_nifty_20d > 1.0:
        conf += 10
    conf = min(100, conf)

    # ── Technical grade ──────────────────────────────────────────────────────
    if conf >= 80:   grade = "A"
    elif conf >= 65: grade = "B"
    elif conf >= 50: grade = "C"
    elif conf >= 35: grade = "D"
    else:            grade = "F"

    # ── Holding period ───────────────────────────────────────────────────────
    if sig.adx_14 > 30 and ema_full_bull and bq in ("Good", "Excellent"):
        holding = "Positional (1-3 mo)"
    elif sig.adx_14 > 20 and sig.ema20_above_ema50:
        holding = "Swing (1-4 wk)"
    elif sig.volume_ratio > 2.0 and sig.rsi_14 > 50:
        holding = "Short-term (2-5 d)"
    else:
        holding = "Wait / Avoid"

    # ── Maximum drawdown estimate (ATR-based 3σ worst-case) ─────────────────
    max_dd_pct = round(3.0 * atr / price * 100, 2) if price > 0 and atr > 0 else 0.0

    # ── Probability estimate (%) ─────────────────────────────────────────────
    prob = int(conf * 0.60)
    if sig.breakout:                                                 prob += 15
    if sig.rs_vs_nifty_20d is not None and sig.rs_vs_nifty_20d > 1.2: prob += 10
    prob = min(95, max(5, prob))

    # ── Rule-based verdict (one-liner) ───────────────────────────────────────
    parts: list[str] = []
    if trend in ("Strong Bullish", "Bullish"):
        parts.append(f"{trend.lower()} trend")
    if sig.breakout:
        bt = sig.breakout_type if sig.breakout_type != "None" else "breakout"
        parts.append(f"{bt.lower()} on {sig.volume_ratio:.1f}× volume")
    if sig.adx_14 > 25:
        parts.append(f"ADX {sig.adx_14:.0f} confirms momentum")
    if sig.hh_hl:
        parts.append("HH+HL structure intact")
    if not parts:
        parts.append("no clear setup — wait for confirmation")
    verdict = "; ".join(parts).capitalize() + "."
    if resistance > price:
        verdict += f" Watch ₹{resistance:.0f} resistance."

    return {
        "symbol":               sig.symbol,
        "as_of":                str(sig.as_of),
        "price":                price,
        "ema20":                sig.ema20,
        "ema50":                sig.ema50,
        "ema200":               sig.ema200,
        "ema20_above_ema50":    sig.ema20_above_ema50,
        "ema50_above_ema200":   sig.ema50_above_ema200,
        "hh_hl":                sig.hh_hl,
        "rsi_14":               sig.rsi_14,
        "macd_signal":          sig.macd_signal,
        "adx_14":               sig.adx_14,
        "atr_14":               sig.atr_14,
        "volume_ratio":         sig.volume_ratio,
        "high_52w":             sig.high_52w,
        "low_52w":              sig.low_52w,
        "dist_52w_high_pct":    sig.distance_52w_high_pct,
        "support":              support,
        "resistance":           resistance,
        "breakout":             sig.breakout,
        "breakout_type":        sig.breakout_type,
        "breakout_quality":     bq,
        "breakout_age":         sig.breakout_age,
        "pattern":              sig.pattern,
        "dist_from_ema20_pct":  sig.dist_from_ema20_pct,
        "rs_vs_nifty_20d":      sig.rs_vs_nifty_20d,
        "trend_classification": trend,
        "entry":                entry,
        "stop_loss":            sl,
        "target_1":             t1,
        "target_2":             t2,
        "target_3":             t3,
        "risk_reward":          rr,
        "institutional":        institutional,
        "confidence_score":     conf,
        "technical_grade":      grade,
        "holding_period":       holding,
        "max_drawdown_pct":     max_dd_pct,
        "probability_pct":      prob,
        "verdict":              verdict,
    }


# ---------------------------------------------------------------------------
# SQL — create the extended_signals view (signals LEFT JOIN technicals)
# ---------------------------------------------------------------------------

_EXTENDED_VIEW_SQL = """
CREATE OR REPLACE VIEW extended_signals AS
SELECT
    s.symbol,
    s.last_close,
    s.pct_1d,
    s.pct_5d,
    s.pct_20d,
    s.volume_ratio       AS vol_ratio,
    s.above_50dma,
    s.near_52w_high,
    s.breakout           AS raw_breakout,
    s.volume_spike,
    s.big_mover,
    s.momentum_score,
    s.continuation_score,
    s.historical_setups,
    s.historical_wins,
    -- full technicals
    t.as_of,
    t.price,
    t.ema20,
    t.ema50,
    t.ema200,
    t.ema20_above_ema50,
    t.ema50_above_ema200,
    t.hh_hl,
    t.rsi_14,
    t.macd_signal,
    t.adx_14,
    t.atr_14,
    t.volume_ratio,
    t.high_52w,
    t.low_52w,
    t.dist_52w_high_pct,
    t.support,
    t.resistance,
    t.breakout,
    t.breakout_type,
    t.breakout_quality,
    t.breakout_age,
    t.pattern,
    t.dist_from_ema20_pct,
    t.rs_vs_nifty_20d,
    t.trend_classification,
    t.entry,
    t.stop_loss,
    t.target_1,
    t.target_2,
    t.target_3,
    t.risk_reward,
    t.institutional,
    t.confidence_score,
    t.technical_grade,
    t.holding_period,
    t.max_drawdown_pct,
    t.probability_pct,
    t.verdict
FROM signals s
LEFT JOIN technicals t ON s.symbol = t.symbol
"""

# ---------------------------------------------------------------------------
# Store class
# ---------------------------------------------------------------------------

# One lock per database path guards the single write-connection window
_write_locks: dict[str, threading.Lock] = {}
_write_locks_guard = threading.Lock()


def _get_write_lock(db_path: str) -> threading.Lock:
    with _write_locks_guard:
        if db_path not in _write_locks:
            _write_locks[db_path] = threading.Lock()
        return _write_locks[db_path]


class DuckDBStore:
    def __init__(self, db_path: Path = DB_PATH, raw_dir: Path = RAW_DATA_DIR, read_only: bool = True):
        self.db_path = db_path
        self.raw_dir = raw_dir
        self._read_only = read_only
        # Each OS thread gets its own DuckDB connection handle.
        self._local = threading.local()

    # ── Connection ─────────────────────────────────────────────────────────

    def connect(self) -> duckdb.DuckDBPyConnection:
        con = getattr(self._local, "con", None)
        if con is None:
            self._local.con = duckdb.connect(str(self.db_path), read_only=self._read_only)
        return self._local.con

    def close(self):
        """Close the current thread's connection."""
        con = getattr(self._local, "con", None)
        if con is not None:
            con.close()
            self._local.con = None

    # ── Build ──────────────────────────────────────────────────────────────

    def build(self) -> None:
        """Load all Parquet files and compute signals. Run this once after
        downloading new data (takes ~5 seconds for 2,675 stocks)."""
        con = self.connect()
        glob = str(self.raw_dir / "*.parquet").replace("\\", "/")

        log.info("Loading OHLCV from %s …", glob)
        con.execute(_LOAD_OHLCV_SQL.format(glob=glob))
        rows = con.execute("SELECT COUNT(*) FROM ohlcv").fetchone()[0]
        symbols = con.execute("SELECT COUNT(DISTINCT symbol) FROM ohlcv").fetchone()[0]
        log.info("ohlcv table: %d rows across %d symbols", rows, symbols)

        log.info("Computing signals …")
        con.execute(_COMPUTE_SIGNALS_SQL)

        log.info("Computing continuation scores (historical breakout win-rate) …")
        con.execute(_CONTINUATION_SCORE_SQL)

        # Join continuation score into signals table
        con.execute("""
            CREATE OR REPLACE TABLE signals AS
            SELECT s.*,
                   COALESCE(c.continuation_score, 0)  AS continuation_score,
                   COALESCE(c.setup_count, 0)          AS historical_setups,
                   COALESCE(c.success_count, 0)        AS historical_wins
            FROM signals s
            LEFT JOIN continuation c USING (symbol)
        """)

        sig_rows = con.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        cs_rows  = con.execute("SELECT COUNT(*) FROM continuation").fetchone()[0]
        log.info("signals table: %d rows  |  continuation scores: %d symbols", sig_rows, cs_rows)

        log.info("Computing extended technical indicators (EMA/RSI/MACD/ADX/…) …")
        self.build_technicals()

    def build_technicals(self) -> None:
        """Compute full pandas-ta indicators for every symbol in the signals table.

        Reads the OHLCV data already loaded in DuckDB, runs pandas-ta per symbol,
        derives all extended fields (trend classification, entry/SL/targets, grade,
        verdict, etc.) and writes results to the ``technicals`` table.

        An ``extended_signals`` view is also created that left-joins ``signals``
        with ``technicals`` so downstream queries get everything in one place.

        Safe to call standalone after ``build()`` has been run at least once.
        """
        import numpy as np
        from src.technicals.indicators import compute_technicals_from_df, TechnicalSignals

        con = self.connect()

        # ── Fetch every symbol present in the signals table ─────────────────
        symbols: list[str] = [
            r[0] for r in con.execute("SELECT symbol FROM signals ORDER BY momentum_score DESC").fetchall()
        ]
        if not symbols:
            log.warning("build_technicals: signals table is empty — run build() first.")
            return

        # ── Load Nifty once for relative strength ────────────────────────────
        nifty_df: pd.DataFrame | None = None
        nifty_rows = con.execute(
            "SELECT date, close FROM ohlcv WHERE symbol = '^NSEI' ORDER BY date"
        ).df()
        if not nifty_rows.empty:
            nifty_df = nifty_rows.rename(columns={"close": "Close"})
            nifty_df["Date"] = pd.to_datetime(nifty_df["date"])
            nifty_df = nifty_df.set_index("Date")

        # ── Fetch all OHLCV at once and group by symbol ──────────────────────
        log.info("build_technicals: loading all OHLCV from DuckDB …")
        raw = con.execute(
            "SELECT symbol, date, "
            "open AS Open, high AS High, low AS Low, close AS Close, volume AS Volume "
            "FROM ohlcv ORDER BY symbol, date"
        ).df()
        raw["Date"] = pd.to_datetime(raw["date"])

        rows: list[dict] = []
        skipped = 0

        log.info("build_technicals: computing indicators for %d symbols …", len(symbols))
        for symbol in symbols:
            try:
                grp = raw.loc[raw["symbol"] == symbol].copy()
                grp = grp.set_index("Date")
                if len(grp) < 250:
                    skipped += 1
                    continue
                sig: TechnicalSignals = compute_technicals_from_df(symbol, grp, nifty_df=nifty_df)
                rows.append(_derive_extended_row(sig))
            except Exception as exc:
                log.debug("build_technicals: skipping %s — %s", symbol, exc)
                skipped += 1

        if not rows:
            log.warning("build_technicals: no rows produced — check OHLCV data.")
            return

        log.info(
            "build_technicals: computed %d rows  (skipped %d with < 250 bars)",
            len(rows), skipped,
        )

        tech_df = pd.DataFrame(rows)

        # Register as a DuckDB relation and persist as a table
        con.register("_tech_df", tech_df)
        con.execute("CREATE OR REPLACE TABLE technicals AS SELECT * FROM _tech_df")
        con.unregister("_tech_df")

        # ── Build the extended_signals view ──────────────────────────────────
        con.execute(_EXTENDED_VIEW_SQL)

        tech_rows = con.execute("SELECT COUNT(*) FROM technicals").fetchone()[0]
        log.info("technicals table: %d rows  |  extended_signals view ready", tech_rows)

    def _ensure_extended_view(self) -> None:
        """Recreate the extended_signals view if it is missing.

        Acquires a per-database write lock, closes the current thread's
        read-only handle, opens a write connection, creates the view, then
        restores the read-only handle for this thread.

        Raises RuntimeError if the technicals table does not exist.
        """
        lock = _get_write_lock(str(self.db_path))
        with lock:
            # Close THIS thread's read-only connection so the write
            # connection can open.  Other threads' connections are separate.
            self.close()
            try:
                write_con = duckdb.connect(str(self.db_path))
                tables = {r[0] for r in write_con.execute("SHOW TABLES").fetchall()}
                if "technicals" not in tables:
                    write_con.close()
                    raise RuntimeError(
                        "technicals table not found — run build_technicals() or "
                        "rebuild the database with: python -m scripts.build_db"
                    )
                write_con.execute(_EXTENDED_VIEW_SQL)
                write_con.close()
                log.info("_ensure_extended_view: extended_signals view recreated")
            except RuntimeError:
                raise
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to recreate extended_signals view: {exc}"
                ) from exc
            finally:
                self.connect()  # reopen this thread's read-only handle

    def is_ready(self) -> bool:
        """Return True if the signals table exists and has rows."""
        try:
            con = self.connect()
            n = con.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
            return n > 0
        except Exception:
            return False

    # ── Queries ────────────────────────────────────────────────────────────

    def get_signals(
        self,
        volume_spike:  bool  = False,
        above_50dma:   bool  = False,
        near_high:     bool  = False,
        breakout:      bool  = False,
        big_mover:     bool  = False,
        min_score:     float = 0.0,
        min_vol_ratio: float = 0.0,
    ) -> pd.DataFrame:
        """Return the signals table as a DataFrame with optional filters."""
        con = self.connect()

        clauses: list[str] = []
        if volume_spike:   clauses.append("volume_spike = true")
        if above_50dma:    clauses.append("above_50dma  = true")
        if near_high:      clauses.append("near_52w_high = true")
        if breakout:       clauses.append("breakout     = true")
        if big_mover:      clauses.append("big_mover    = true")
        if min_score > 0:  clauses.append(f"momentum_score >= {min_score}")
        if min_vol_ratio:  clauses.append(f"volume_ratio >= {min_vol_ratio}")

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT * FROM signals {where} ORDER BY momentum_score DESC"
        return con.execute(sql).df()

    def get_full_scan(
        self,
        trend: str | None = None,
        grade: str | None = None,
        breakout: bool = False,
        min_confidence: int = 0,
        min_rsi: float = 0.0,
        max_rsi: float = 100.0,
        min_adx: float = 0.0,
        volume_confirmed: bool = False,
        hh_hl: bool = False,
        min_probability: int = 0,
    ) -> pd.DataFrame:
        """Return the extended_signals view with optional filters.

        Returns all columns from both the momentum signals table and the
        full technical indicators table (EMA, RSI, MACD, ADX, ATR, entry,
        SL, targets, risk/reward, grade, verdict, etc.).

        Parameters
        ----------
        trend:            Filter by trend_classification (e.g. "Strong Bullish").
        grade:            Filter by technical_grade (e.g. "A", "B").
        breakout:         If True, only return confirmed breakout stocks.
        min_confidence:   Minimum confidence_score (0-100).
        min_rsi / max_rsi: RSI range filter.
        min_adx:          Minimum ADX value.
        volume_confirmed: If True, require volume_ratio > 1.5.
        hh_hl:            If True, require Higher High + Higher Low structure.
        min_probability:  Minimum probability_pct.
        """
        con = self.connect()
        clauses: list[str] = []

        if trend:               clauses.append(f"trend_classification = '{trend}'")
        if grade:               clauses.append(f"technical_grade = '{grade}'")
        if breakout:            clauses.append("breakout = true")
        if min_confidence > 0:  clauses.append(f"confidence_score >= {min_confidence}")
        if min_rsi > 0:         clauses.append(f"rsi_14 >= {min_rsi}")
        if max_rsi < 100:       clauses.append(f"rsi_14 <= {max_rsi}")
        if min_adx > 0:         clauses.append(f"adx_14 >= {min_adx}")
        if volume_confirmed:    clauses.append("volume_ratio >= 1.5")
        if hh_hl:               clauses.append("hh_hl = true")
        if min_probability > 0: clauses.append(f"probability_pct >= {min_probability}")

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT * FROM extended_signals {where} ORDER BY confidence_score DESC"
        try:
            return con.execute(sql).df()
        except duckdb.CatalogException:
            log.warning("get_full_scan: extended_signals view missing — attempting recreation …")
            self._ensure_extended_view()
            con = self.connect()
            return con.execute(sql).df()

    def get_ohlcv(self, symbol: str) -> pd.DataFrame:
        """Return full OHLCV history for one symbol, sorted by date."""
        con = self.connect()
        return con.execute(
            "SELECT date AS Date, open AS Open, high AS High, low AS Low, "
            "close AS Close, volume AS Volume "
            "FROM ohlcv WHERE symbol = ? ORDER BY date",
            [symbol.upper()],
        ).df()

    def get_symbols(self) -> list[str]:
        """Return all symbols in the database."""
        con = self.connect()
        return [r[0] for r in con.execute(
            "SELECT DISTINCT symbol FROM ohlcv ORDER BY symbol"
        ).fetchall()]

    def execute_sql(self, sql: str) -> pd.DataFrame:
        """Run arbitrary SQL — used by the Workbench."""
        con = self.connect()
        return con.execute(sql).df()

    def get_signal_row(self, symbol: str) -> dict | None:
        """Return the signals row for one symbol as a dict."""
        con = self.connect()
        row = con.execute(
            "SELECT * FROM signals WHERE symbol = ?", [symbol.upper()]
        ).df()
        if row.empty:
            return None
        return row.iloc[0].to_dict()

    # ── Context manager ────────────────────────────────────────────────────

    def __enter__(self):  return self
    def __exit__(self, *_): self.close()


# Module-level singleton used by the API
_store: DuckDBStore | None = None


def get_store() -> DuckDBStore:
    global _store
    if _store is None:
        _store = DuckDBStore()
    return _store
