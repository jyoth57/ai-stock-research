"""Valuation score: attractiveness based on FCF efficiency and ROCE spread.

Note: Call ``valuation_score_with_price()`` when market price is available
for a proper P/E / PEG-based score.
"""

from __future__ import annotations
from typing import Optional
import pandas as pd


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def valuation_score(row: pd.Series) -> dict:
    """Score valuation attractiveness 0-100 without market price.

    Weights: FCF/Revenue proxy 35% | ROCE spread 35% | Growth quality 30%
    Penalty: High leverage (up to -20 pts)
    """
    fcf      = float(row.get("free_cash_flow")     or 0)
    revenue  = float(row.get("revenue")            or 1)
    roce     = float(row.get("roce_pct")           or 0)
    rev_cagr = float(row.get("revenue_cagr_pct")   or 0)
    de       = float(row.get("debt_to_equity")     or 0)

    fcf_pct = fcf / revenue * 100
    fcf_proxy = _clamp(fcf_pct / 15 * 100) if fcf_pct > 0 else 0.0

    roce_spread = _clamp(max(0, roce - 10) / 20 * 100)

    if roce >= 15 and rev_cagr >= 10:   gq = _clamp(rev_cagr / 20 * 100)
    elif roce >= 10 and rev_cagr >= 5:  gq = _clamp(rev_cagr / 20 * 70)
    else:                               gq = 20.0

    debt_penalty = _clamp((de - 0.5) / 1.0 * 20, 0, 20) if de > 0.5 else 0.0

    score = _clamp(
        fcf_proxy * 0.35 + roce_spread * 0.35 + gq * 0.30 - debt_penalty
    )
    return {
        "score": round(score, 1),
        "fcf_proxy_score": round(fcf_proxy, 1),
        "roce_spread_score": round(roce_spread, 1),
        "growth_quality_score": round(gq, 1),
        "debt_adjustment": round(-debt_penalty, 1),
        "needs_market_price": True,
    }


def valuation_score_with_price(
    row: pd.Series,
    current_price: float,
) -> dict:
    """P/E and PEG-based valuation score when market price is available."""
    eps      = float(row.get("eps") or 0)
    eps_g    = float(row.get("eps_growth_pct") or 0)

    if eps <= 0:
        return valuation_score(row)

    pe  = current_price / eps
    peg = pe / max(eps_g, 1.0) if eps_g > 0 else None

    pe_score  = 100.0 if pe <= 15 else _clamp((40 - pe) / 25 * 100) if pe <= 40 else 0.0
    peg_score = (
        100.0 if (peg and peg <= 0.8)
        else _clamp((2.5 - peg) / 1.7 * 100) if (peg and peg <= 1.5)
        else _clamp(max(0, 100 - (peg - 1.5) * 30)) if peg
        else 40.0
    )

    return {
        "score": round((pe_score + peg_score) / 2, 1),
        "pe_ratio": round(pe, 1),
        "peg_ratio": round(peg, 2) if peg else None,
        "pe_score": round(pe_score, 1),
        "peg_score": round(peg_score, 1),
        "needs_market_price": False,
    }
