"""ratios.py
-----------
Extended financial ratios on top of the base FundamentalsEngine output.

Adds:
 - Modified Piotroski F-Score  (7-signal version from available data)
 - DuPont decomposition        (ROE = Net Margin x Asset Turnover x Leverage)
 - Working capital metrics
 - Earnings quality ratio       (OCF / Net Income)

Usage
-----
    from src.financials import RatiosEngine

    engine = RatiosEngine()
    df = engine.load()          # returns enriched fundamentals DataFrame
    piotroski = compute_piotroski(df, symbol="TCS")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from src.core.settings import settings
from src.core.logging import get_logger
from src.core.exceptions import DataNotFoundError, InsufficientDataError

log = get_logger(__name__)

_FUNDAMENTALS_PARQUET = settings.processed_data_dir / "fundamentals.parquet"


# ---------------------------------------------------------------------------
# Piotroski F-Score (modified 7-signal version using available data)
# ---------------------------------------------------------------------------

def compute_piotroski(df: pd.DataFrame, symbol: str) -> dict:
    """Compute a modified Piotroski F-Score for *symbol*.

    Uses 7 of the original 9 signals (signals requiring gross margin and
    current ratio are omitted; ROCE trend replaces them).

    Score:  6-7 = Strong   |  4-5 = Average   |  0-3 = Weak

    Parameters
    ----------
    df:     Fundamentals DataFrame (output of FundamentalsEngine.compute_metrics)
    symbol: Bare NSE symbol

    Returns
    -------
    dict with keys: score (int), signals (dict), interpretation (str)
    """
    s = df[df["symbol"] == symbol.upper()].sort_values("date")

    if len(s) < 2:
        raise InsufficientDataError(
            f"Need at least 2 years of data for Piotroski; {symbol} has {len(s)}."
        )

    latest = s.iloc[-1]
    prev = s.iloc[-2]

    signals: dict[str, int] = {}

    # ── Profitability signals (3) ────────────────────────────────────────────
    # F1: Net income positive
    signals["net_income_positive"] = int(latest.get("net_income", 0) > 0)

    # F2: Free cash flow positive
    signals["fcf_positive"] = int(latest.get("free_cash_flow", 0) > 0)

    # F3: ROE improving year-over-year
    roe_now = latest.get("roe_pct") or 0
    roe_prev = prev.get("roe_pct") or 0
    signals["roe_improving"] = int(roe_now > roe_prev)

    # F4: Earnings quality — FCF > Net Income (OCF proxy)
    ni = latest.get("net_income") or 0
    fcf = latest.get("free_cash_flow") or 0
    signals["earnings_quality"] = int(fcf > 0 and ni > 0 and fcf >= ni * 0.7)

    # ── Leverage / Liquidity signals (2) ────────────────────────────────────
    # F5: Debt/Equity decreasing
    de_now = latest.get("debt_to_equity") or 999
    de_prev = prev.get("debt_to_equity") or 999
    signals["debt_decreasing"] = int(de_now < de_prev)

    # F6: ROCE improving (proxy for efficiency improvement)
    roce_now = latest.get("roce_pct") or 0
    roce_prev = prev.get("roce_pct") or 0
    signals["roce_improving"] = int(roce_now > roce_prev)

    # ── Operating efficiency signal (1) ─────────────────────────────────────
    # F7: Revenue growing (asset turnover proxy)
    rev_now = latest.get("revenue") or 0
    rev_prev = prev.get("revenue") or 0
    signals["revenue_growing"] = int(rev_now > rev_prev)

    score = sum(signals.values())

    if score >= 6:
        interpretation = "Strong (6-7) — Financially healthy, positive signals"
    elif score >= 4:
        interpretation = "Average (4-5) — Mixed signals, requires deeper review"
    else:
        interpretation = "Weak (0-3) — Multiple red flags, high caution warranted"

    return {"score": score, "max_score": 7, "signals": signals, "interpretation": interpretation}


# ---------------------------------------------------------------------------
# DuPont decomposition
# ---------------------------------------------------------------------------

def compute_dupont(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Decompose ROE into its three DuPont components.

    ROE = Net Profit Margin  x  Asset Turnover  x  Financial Leverage
        = (Net Income / Revenue)  x  (Revenue / Assets)  x  (Assets / Equity)

    Returns a DataFrame with columns added: net_margin, asset_turnover, leverage_ratio
    """
    s = df[df["symbol"] == symbol.upper()].copy().sort_values("date")

    s["net_margin"] = (s["net_income"] / s["revenue"].replace(0, float("nan")) * 100).round(2)
    s["asset_turnover"] = (s["revenue"] / s["total_assets"].replace(0, float("nan"))).round(3)
    s["leverage_ratio"] = (s["total_assets"] / s["total_equity"].replace(0, float("nan"))).round(2)
    s["dupont_roe_check"] = (
        s["net_margin"] / 100 * s["asset_turnover"] * s["leverage_ratio"] * 100
    ).round(2)

    return s[["symbol", "date", "roe_pct", "net_margin", "asset_turnover", "leverage_ratio", "dupont_roe_check"]]


# ---------------------------------------------------------------------------
# RatiosEngine
# ---------------------------------------------------------------------------

class RatiosEngine:
    """Load fundamentals and enrich with extended ratios.

    Parameters
    ----------
    parquet_path: Path to ``fundamentals.parquet``. Defaults to
                  ``data/processed/fundamentals.parquet``.
    """

    def __init__(self, parquet_path: Optional[Path] = None) -> None:
        self._path = parquet_path or _FUNDAMENTALS_PARQUET

    def load(self, symbol: Optional[str] = None) -> pd.DataFrame:
        """Load and enrich the fundamentals parquet with additional ratios.

        Parameters
        ----------
        symbol: If provided, filter to a single symbol.

        Returns
        -------
        pd.DataFrame with original columns plus:
            earnings_quality_ratio, net_margin, asset_turnover, leverage_ratio
        """
        if not self._path.exists():
            raise DataNotFoundError(
                f"Fundamentals parquet not found at {self._path}. "
                "Run FundamentalsEngine().save_to_parquet() first."
            )

        df = pd.read_parquet(self._path)
        df["date"] = pd.to_datetime(df["date"])

        if symbol:
            df = df[df["symbol"] == symbol.strip().upper()]

        # Earnings quality: FCF / Net Income (>0.8 is healthy)
        df["earnings_quality_ratio"] = (
            df["free_cash_flow"]
            / df["net_income"].replace(0, float("nan"))
        ).round(3)

        # DuPont components
        df["net_margin"] = (
            df["net_income"] / df["revenue"].replace(0, float("nan")) * 100
        ).round(2)
        df["asset_turnover"] = (
            df["revenue"] / df["total_assets"].replace(0, float("nan"))
        ).round(3)
        df["leverage_ratio"] = (
            df["total_assets"] / df["total_equity"].replace(0, float("nan"))
        ).round(2)

        log.info(
            "RatiosEngine loaded %d rows for %d symbols",
            len(df), df["symbol"].nunique()
        )
        return df

    def piotroski_all(self, df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """Compute Piotroski score for every symbol and return a summary."""
        if df is None:
            df = self.load()

        rows = []
        for sym in df["symbol"].unique():
            try:
                p = compute_piotroski(df, sym)
                rows.append({"symbol": sym, "piotroski_score": p["score"], "interpretation": p["interpretation"]})
            except InsufficientDataError:
                rows.append({"symbol": sym, "piotroski_score": None, "interpretation": "Insufficient data"})

        return pd.DataFrame(rows).sort_values("piotroski_score", ascending=False)
