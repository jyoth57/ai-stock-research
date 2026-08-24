"""Composite scoring engine — aggregates all sub-scores into a ScoreCard."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from src.core.constants import SCORING_WEIGHTS
from .quality import quality_score
from .growth import growth_score
from .risk import risk_score
from .valuation import valuation_score


@dataclass
class ScoreCard:
    symbol: str
    date: str
    quality: float
    growth: float
    risk: float
    valuation: float
    composite: float
    grade: str
    verdict: str
    quality_detail: dict = field(default_factory=dict)
    growth_detail: dict = field(default_factory=dict)
    risk_detail: dict = field(default_factory=dict)
    valuation_detail: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return (
            f"{self.symbol} ({self.date})  Grade: {self.grade}  "
            f"Score: {self.composite:.0f}/100  {self.verdict}\n"
            f"  Quality:{self.quality:.0f}  Growth:{self.growth:.0f}  "
            f"Risk:{self.risk:.0f}  Valuation:{self.valuation:.0f}"
        )

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol, "date": self.date,
            "composite_score": self.composite, "grade": self.grade,
            "quality": self.quality, "growth": self.growth,
            "risk": self.risk, "valuation": self.valuation,
            "verdict": self.verdict,
        }


def _grade(score: float) -> tuple[str, str]:
    if score >= 80: return "A", "High-conviction candidate — strong across all dimensions"
    if score >= 65: return "B", "Good quality business — worth deeper research"
    if score >= 50: return "C", "Average — some positives but meaningful concerns"
    if score >= 35: return "D", "Below average — significant weaknesses"
    return "F", "Poor fundamentals — avoid unless special situation"


def score_stock(row: pd.Series, weights: Optional[dict] = None) -> ScoreCard:
    """Compute a full ScoreCard for a single fundamentals row."""
    w = weights or SCORING_WEIGHTS
    q = quality_score(row)
    g = growth_score(row)
    r = risk_score(row)
    v = valuation_score(row)
    tech = float(row.get("technical_score", 50.0))

    composite = (
        q["score"] * w.get("quality",    0.30)
        + g["score"] * w.get("growth",     0.25)
        + v["score"] * w.get("valuation",  0.25)
        + tech       * w.get("technical",  0.10)
        + r["score"] * w.get("risk",       0.10)
    )
    grade, verdict = _grade(composite)
    return ScoreCard(
        symbol=str(row.get("symbol", "?")),
        date=str(row.get("date", ""))[:10],
        quality=q["score"], growth=g["score"],
        risk=r["score"],    valuation=v["score"],
        composite=round(composite, 1),
        grade=grade, verdict=verdict,
        quality_detail=q, growth_detail=g,
        risk_detail=r,    valuation_detail=v,
    )


def score_universe(df: pd.DataFrame) -> pd.DataFrame:
    """Score all symbols (latest year each) and return ranked DataFrame."""
    latest = df.sort_values("date").groupby("symbol").last().reset_index()
    return (
        pd.DataFrame([score_stock(row).to_dict() for _, row in latest.iterrows()])
        .sort_values("composite_score", ascending=False)
        .reset_index(drop=True)
    )
