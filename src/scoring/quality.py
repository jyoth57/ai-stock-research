"""Quality score: measures business durability and capital efficiency."""

from __future__ import annotations
import pandas as pd


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def quality_score(row: pd.Series) -> dict:
    """Score business quality 0-100 from a single fundamentals row.

    Weights: ROCE 30% | ROE 25% | FCF 20% | Debt/Equity 15% | Earnings quality 10%
    """
    roce = float(row.get("roce_pct") or 0)
    roe  = float(row.get("roe_pct")  or 0)
    fcf  = float(row.get("free_cash_flow") or 0)
    de   = float(row.get("debt_to_equity") or 0)
    eq   = float(row.get("earnings_quality_ratio") or 0)

    roce_score = _clamp((roce - 5) / (25 - 5) * 100)
    roe_score  = _clamp((roe  - 5) / (18 - 5) * 100)
    fcf_score  = 80.0 if fcf > 0 else 10.0
    debt_score = _clamp((2.5 - max(de, 0)) / 2.5 * 100) if de < 2.5 else 0.0
    eq_score   = _clamp(eq / 0.9 * 100) if eq > 0 else 0.0

    score = (
        roce_score * 0.30 + roe_score * 0.25 + fcf_score  * 0.20
        + debt_score * 0.15 + eq_score * 0.10
    )
    return {
        "score": round(score, 1),
        "roce_score": round(roce_score, 1),
        "roe_score": round(roe_score, 1),
        "fcf_score": round(fcf_score, 1),
        "debt_score": round(debt_score, 1),
        "earnings_quality_score": round(eq_score, 1),
    }
