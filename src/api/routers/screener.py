"""screener router — instant SQL query against DuckDB signals table"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException, Query
from src.database.duckdb_store import get_store

router = APIRouter(tags=["screener"])


@router.get("/scan")
def scan(
    volume_spike:  bool  = Query(False),
    above_50dma:   bool  = Query(False),
    near_high:     bool  = Query(False),
    breakout:      bool  = Query(False),
    big_mover:     bool  = Query(False),
    min_score:     float = Query(0),
    min_vol_ratio: float = Query(0),
):
    df = get_store().get_signals(
        volume_spike=volume_spike,
        above_50dma=above_50dma,
        near_high=near_high,
        breakout=breakout,
        big_mover=big_mover,
        min_score=min_score,
        min_vol_ratio=min_vol_ratio,
    )
    return df.to_dict(orient="records")


@router.get("/scan/extended")
def scan_extended(
    trend:            str   = Query(None, description="Filter by trend_classification"),
    grade:            str   = Query(None, description="Filter by technical_grade (A/B/C/D/F)"),
    breakout:         bool  = Query(False),
    min_confidence:   int   = Query(0,   ge=0, le=100),
    min_rsi:          float = Query(0.0, ge=0, le=100),
    max_rsi:          float = Query(100.0, ge=0, le=100),
    min_adx:          float = Query(0.0, ge=0),
    volume_confirmed: bool  = Query(False, description="Require volume_ratio >= 1.5"),
    hh_hl:            bool  = Query(False, description="Require Higher High + Higher Low"),
    min_probability:  int   = Query(0,   ge=0, le=100),
):
    """Return the full technical snapshot for every stock.

    This endpoint joins the momentum signals table with the pandas-ta derived
    indicators (EMA/RSI/MACD/ADX/ATR, entry/SL/targets, trend classification,
    grade, verdict, etc.).  Requires ``build_technicals()`` to have been run.
    """
    try:
        df = get_store().get_full_scan(
            trend=trend or None,
            grade=grade or None,
            breakout=breakout,
            min_confidence=min_confidence,
            min_rsi=min_rsi,
            max_rsi=max_rsi,
            min_adx=min_adx,
            volume_confirmed=volume_confirmed,
            hh_hl=hh_hl,
            min_probability=min_probability,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc
    return df.to_dict(orient="records")

