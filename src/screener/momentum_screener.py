"""
momentum_screener.py
--------------------
Screens all downloaded NSE equities for momentum signals using only
OHLCV data stored in data/raw/*.parquet.

Signals computed per stock
--------------------------
  pct_1d          Last-session % change
  pct_5d          5-session % change
  pct_20d         20-session % change
  volume_ratio    Last volume / 20-day average volume
  above_50dma     Price > 50-day moving average
  near_52w_high   Last close within 5% of 52-week high
  breakout        Last close > 20-day resistance (prior 20-day high)
  big_mover       |pct_1d| > 8%
  volume_spike    volume_ratio > 2
  higher_lows     Last 5 sessions each low >= prior low (relative strength)
  momentum_score  Composite 0-100 score

CLI
---
    python -m src.screener.momentum_screener
    python -m src.screener.momentum_screener --top 50
    python -m src.screener.momentum_screener --min-volume-ratio 3 --near-high
    python -m src.screener.momentum_screener --export results.csv
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = _PROJECT_ROOT / "data" / "raw"
EXPORTS_DIR = _PROJECT_ROOT / "data" / "exports"
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

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
# Signal thresholds
# ---------------------------------------------------------------------------

BIG_MOVER_THRESHOLD = 8.0       # % move considered a big mover
VOLUME_SPIKE_THRESHOLD = 2.0    # volume ratio to qualify as a spike
NEAR_HIGH_THRESHOLD = 5.0       # % below 52-week high still "near"
MIN_ROWS = 10                    # skip stocks with too little history


# ---------------------------------------------------------------------------
# Per-stock signal computation
# ---------------------------------------------------------------------------

def compute_signals(df: pd.DataFrame) -> dict | None:
    """Compute momentum signals for one stock.

    Parameters
    ----------
    df:
        OHLCV DataFrame indexed by Date, sorted ascending.

    Returns
    -------
    dict of signal values, or None if data is insufficient.
    """
    df = df.sort_index()
    if len(df) < MIN_ROWS:
        return None

    close = df["Close"]
    volume = df["Volume"]
    low = df["Low"]

    last_close = float(close.iloc[-1])
    last_volume = float(volume.iloc[-1])

    # --- % changes ---
    pct_1d = float((close.iloc[-1] / close.iloc[-2] - 1) * 100) if len(df) >= 2 else 0.0
    pct_5d = float((close.iloc[-1] / close.iloc[-6] - 1) * 100) if len(df) >= 6 else 0.0
    pct_20d = float((close.iloc[-1] / close.iloc[-21] - 1) * 100) if len(df) >= 21 else 0.0

    # --- Volume ratio (today vs 20-day avg, excluding today) ---
    vol_avg_20 = float(volume.iloc[-21:-1].mean()) if len(df) >= 21 else float(volume.iloc[:-1].mean())
    volume_ratio = (last_volume / vol_avg_20) if vol_avg_20 > 0 else 0.0

    # --- 50-day moving average ---
    sma50 = float(close.rolling(50).mean().iloc[-1]) if len(df) >= 50 else float(close.mean())
    above_50dma = last_close > sma50

    # --- 52-week high (up to 252 sessions) ---
    lookback = min(252, len(df))
    high_52w = float(close.iloc[-lookback:].max())
    pct_from_52w_high = float((high_52w - last_close) / high_52w * 100)
    near_52w_high = pct_from_52w_high <= NEAR_HIGH_THRESHOLD

    # --- Breakout: last close above prior 20-session high (resistance) ---
    if len(df) >= 21:
        resistance = float(close.iloc[-21:-1].max())
        breakout = last_close > resistance
    else:
        breakout = False

    # --- Higher lows (relative strength proxy): last 5 sessions ---
    if len(df) >= 6:
        recent_lows = low.iloc[-5:].values
        higher_lows = all(recent_lows[i] >= recent_lows[i - 1] for i in range(1, len(recent_lows)))
    else:
        higher_lows = False

    # --- Big mover / volume spike ---
    big_mover = abs(pct_1d) >= BIG_MOVER_THRESHOLD
    volume_spike = volume_ratio >= VOLUME_SPIKE_THRESHOLD

    # --- Composite momentum score (0-100) ---
    score = 0.0
    # Trend alignment (40 pts)
    if pct_20d > 0:
        score += min(pct_20d, 20)          # up to 20 pts for 20d return
    if pct_5d > 0:
        score += min(pct_5d * 2, 10)       # up to 10 pts for 5d return
    if above_50dma:
        score += 10
    # Volume confirmation (25 pts)
    score += min((volume_ratio - 1) * 5, 15) if volume_ratio > 1 else 0
    if volume_spike:
        score += 10
    # Position (20 pts)
    if near_52w_high:
        score += 10
    if breakout:
        score += 10
    # Relative strength (15 pts)
    if higher_lows:
        score += 10
    if pct_1d > 0:
        score += min(pct_1d, 5)

    return {
        "last_close": round(last_close, 2),
        "pct_1d": round(pct_1d, 2),
        "pct_5d": round(pct_5d, 2),
        "pct_20d": round(pct_20d, 2),
        "volume_ratio": round(volume_ratio, 2),
        "above_50dma": above_50dma,
        "near_52w_high": near_52w_high,
        "pct_from_52w_high": round(pct_from_52w_high, 2),
        "breakout": breakout,
        "big_mover": big_mover,
        "volume_spike": volume_spike,
        "higher_lows": higher_lows,
        "momentum_score": round(min(score, 100), 1),
    }


# ---------------------------------------------------------------------------
# Full scan
# ---------------------------------------------------------------------------

def run_scan(
    data_dir: Path = RAW_DATA_DIR,
    min_volume_ratio: float = 0.0,
    only_above_50dma: bool = False,
    only_near_high: bool = False,
    only_breakout: bool = False,
    only_volume_spike: bool = False,
) -> pd.DataFrame:
    """Load all Parquet files and compute signals for every stock.

    Parameters
    ----------
    data_dir:
        Directory containing ``{SYMBOL}.parquet`` files.
    min_volume_ratio:
        Filter: keep only stocks with volume_ratio >= this value.
    only_above_50dma:
        Filter: keep only stocks trading above their 50-day MA.
    only_near_high:
        Filter: keep only stocks within 5% of their 52-week high.
    only_breakout:
        Filter: keep only breakout stocks.
    only_volume_spike:
        Filter: keep only stocks with volume_ratio > 2x average.

    Returns
    -------
    pd.DataFrame
        One row per stock, sorted by momentum_score descending.
    """
    parquet_files = sorted(data_dir.glob("*.parquet"))
    if not parquet_files:
        raise FileNotFoundError(f"No parquet files found in {data_dir}")

    log.info("Scanning %d stocks...", len(parquet_files))
    rows = []

    for path in parquet_files:
        symbol = path.stem
        try:
            df = pd.read_parquet(path)
            signals = compute_signals(df)
            if signals is None:
                continue
            signals["symbol"] = symbol
            rows.append(signals)
        except Exception as exc:
            log.debug("Skipping %s: %s", symbol, exc)

    if not rows:
        log.warning("No signals computed.")
        return pd.DataFrame()

    result = pd.DataFrame(rows).set_index("symbol")

    # Apply filters
    if min_volume_ratio > 0:
        result = result[result["volume_ratio"] >= min_volume_ratio]
    if only_above_50dma:
        result = result[result["above_50dma"]]
    if only_near_high:
        result = result[result["near_52w_high"]]
    if only_breakout:
        result = result[result["breakout"]]
    if only_volume_spike:
        result = result[result["volume_spike"]]

    result = result.sort_values("momentum_score", ascending=False)
    log.info("Scan complete. %d stocks match filters.", len(result))
    return result


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def print_summary(df: pd.DataFrame, top: int = 25) -> None:
    """Print a formatted summary table to stdout."""
    if df.empty:
        print("No stocks matched the criteria.")
        return

    display_cols = [
        "last_close", "pct_1d", "pct_5d", "pct_20d",
        "volume_ratio", "above_50dma", "near_52w_high",
        "breakout", "volume_spike", "big_mover", "momentum_score",
    ]
    display_cols = [c for c in display_cols if c in df.columns]

    subset = df.head(top)[display_cols].copy()

    # Friendly column headers
    subset.columns = [
        "Close", "1D%", "5D%", "20D%",
        "Vol/Avg", ">50DMA", "NearHigh",
        "Breakout", "VolSpike", "BigMover", "Score",
    ][: len(subset.columns)]

    print(f"\n{'='*80}")
    print(f"  NSE Momentum Screener  —  Top {min(top, len(df))} of {len(df)} stocks")
    print(f"{'='*80}")
    pd.set_option("display.max_rows", top)
    pd.set_option("display.width", 120)
    pd.set_option("display.float_format", "{:.2f}".format)
    print(subset.to_string())
    print(f"{'='*80}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="NSE Momentum Screener — scan all downloaded stocks"
    )
    parser.add_argument("--top", type=int, default=25, help="Show top N stocks (default: 25)")
    parser.add_argument("--min-volume-ratio", type=float, default=0.0,
                        help="Minimum volume/avg-volume ratio (e.g. 2 for spike)")
    parser.add_argument("--above-50dma", action="store_true",
                        help="Only show stocks above 50-day MA")
    parser.add_argument("--near-high", action="store_true",
                        help="Only show stocks within 5%% of 52-week high")
    parser.add_argument("--breakout", action="store_true",
                        help="Only show breakout stocks")
    parser.add_argument("--volume-spike", action="store_true",
                        help="Only show stocks with volume > 2x average")
    parser.add_argument("--export", default=None, metavar="FILE",
                        help="Export full results to CSV (e.g. results.csv)")
    parser.add_argument("--data-dir", default=str(RAW_DATA_DIR), metavar="DIR",
                        help="Directory containing *.parquet files")

    args = parser.parse_args()

    results = run_scan(
        data_dir=Path(args.data_dir),
        min_volume_ratio=args.min_volume_ratio,
        only_above_50dma=args.above_50dma,
        only_near_high=args.near_high,
        only_breakout=args.breakout,
        only_volume_spike=args.volume_spike,
    )

    print_summary(results, top=args.top)

    export_path = EXPORTS_DIR / args.export if args.export else EXPORTS_DIR / "momentum_scan.csv"
    results.to_csv(export_path)
    log.info("Full results exported -> %s", export_path.relative_to(_PROJECT_ROOT))
