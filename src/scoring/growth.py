"""Growth score: measures revenue and earnings momentum."""

from __future__ import annotations
import pandas as pd


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def growth_score(row: pd.Series) -> dict:
    """Score growth quality 0-100.

    Weights: Revenue CAGR 45% | EPS growth 40% | Net margin proxy 15%
    """
    rev_cagr = float(row.get("revenue_cagr_pct") or 0)
    eps_g    = float(row.get("eps_growth_pct")   or 0)
    margin   = float(row.get("net_margin")        or 0)

    rev_score = _clamp(rev_cagr / 20 * 100) if rev_cagr > 0 else _clamp(50 + rev_cagr * 2)
    eps_score = _clamp(eps_g   / 25 * 100) if eps_g > 0   else _clamp(40 + eps_g)

    if margin >= 15:   margin_score = 100.0
    elif margin >= 8:  margin_score = 70.0
    elif margin >= 0:  margin_score = 40.0
    else:              margin_score = 0.0

    score = rev_score * 0.45 + eps_score * 0.40 + margin_score * 0.15
    return {
        "score": round(score, 1),
        "revenue_cagr_score": round(rev_score, 1),
        "eps_growth_score": round(eps_score, 1),
        "margin_score": round(margin_score, 1),
    }
