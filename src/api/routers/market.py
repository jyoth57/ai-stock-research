"""market router — overview and sector summaries"""
from __future__ import annotations
from fastapi import APIRouter
from src.database.duckdb_store import get_store

router = APIRouter(tags=["market"])


@router.get("/overview")
def overview():
    df = get_store().get_signals()
    return {
        "total":        len(df),
        "advancing":    int((df["pct_1d"] > 0).sum()),
        "declining":    int((df["pct_1d"] < 0).sum()),
        "volume_spikes":int(df["volume_spike"].sum()),
        "breakouts":    int(df["breakout"].sum()),
        "avg_score":    round(float(df["momentum_score"].mean()), 1),
    }


@router.get("/sectors")
def sectors():
    # Placeholder — returns empty list until sector mapping is added
    return []
