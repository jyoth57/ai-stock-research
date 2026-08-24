"""Risk score: 100 = safest, 0 = highest risk."""

from __future__ import annotations
import pandas as pd


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def risk_score(row: pd.Series) -> dict:
    """Score financial risk 0-100 (100 = lowest risk).

    Weights: Leverage 40% | FCF cover 25% | Earnings quality 20% | Profitability 15%
    """
    de  = float(row.get("debt_to_equity")         or 0)
    fcf = float(row.get("free_cash_flow")          or 0)
    ni  = float(row.get("net_income")              or 0)
    eq  = float(row.get("earnings_quality_ratio")  or 0)

    leverage_score = _clamp((3.0 - max(de, 0)) / (3.0 - 0.3) * 100) if de < 3.0 else 0.0

    if fcf > 0 and ni > 0:
        fcf_cover = _clamp((fcf / ni) / 1.2 * 100)
    elif fcf > 0: fcf_cover = 60.0
    else:         fcf_cover = 10.0

    if eq >= 1.0:  eq_score = 100.0
    elif eq >= 0.7: eq_score = 70.0
    elif eq >= 0:   eq_score = 35.0
    else:           eq_score = 0.0

    prof_score = 100.0 if ni > 0 else 0.0

    score = (
        leverage_score * 0.40 + fcf_cover * 0.25
        + eq_score * 0.20 + prof_score * 0.15
    )
    return {
        "score": round(score, 1),
        "leverage_score": round(leverage_score, 1),
        "fcf_cover_score": round(fcf_cover, 1),
        "earnings_quality_score": round(eq_score, 1),
        "profitability_score": round(prof_score, 1),
    }
