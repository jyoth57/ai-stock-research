"""
engine.py  —  Prediction Object scoring engine for NSE stocks.

Produces a structured PredictionObject per stock:
  momentum_score, continuation_prob, expected_return, downside_prob,
  historical_matches, confidence, exhaustion_score, risk (decomposed),
  final_score, top_positive_factors, top_negative_factors

Architecture: DuckDB SQL features → Python scoring → written back to DuckDB
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# SQL — rich feature table (latest session per stock)
# ---------------------------------------------------------------------------

FEATURE_SQL = """
WITH daily AS (
    SELECT
        symbol, date, open, high, low, close, volume,
        close - LAG(close,1) OVER w                                         AS delta,
        LAG(close,1)  OVER w                                                AS prev_close,
        LAG(close,5)  OVER w                                                AS close_5d,
        LAG(close,20) OVER w                                                AS close_20d,
        LAG(volume,1) OVER w                                                AS vol_1d,
        LAG(volume,2) OVER w                                                AS vol_2d,
        LAG(volume,3) OVER w                                                AS vol_3d,
        AVG(volume) OVER (PARTITION BY symbol ORDER BY date
                          ROWS BETWEEN 21 PRECEDING AND 1 PRECEDING)        AS avg_vol_20,
        AVG(volume) OVER (PARTITION BY symbol ORDER BY date
                          ROWS BETWEEN 5  PRECEDING AND 1 PRECEDING)        AS avg_vol_5,
        AVG(close)  OVER (PARTITION BY symbol ORDER BY date
                          ROWS BETWEEN 49 PRECEDING AND CURRENT ROW)        AS sma50,
        AVG(close)  OVER (PARTITION BY symbol ORDER BY date
                          ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)        AS sma20,
        AVG(close)  OVER (PARTITION BY symbol ORDER BY date
                          ROWS BETWEEN 9  PRECEDING AND CURRENT ROW)        AS sma10,
        MAX(close)  OVER (PARTITION BY symbol ORDER BY date
                          ROWS BETWEEN 251 PRECEDING AND CURRENT ROW)       AS high_52w,
        MIN(close)  OVER (PARTITION BY symbol ORDER BY date
                          ROWS BETWEEN 251 PRECEDING AND CURRENT ROW)       AS low_52w,
        MAX(close)  OVER (PARTITION BY symbol ORDER BY date
                          ROWS BETWEEN 21 PRECEDING AND 1 PRECEDING)        AS resistance_20d,
        -- true range components
        high - low                                                           AS hl,
        ABS(high - LAG(close,1) OVER w)                                     AS hpc,
        ABS(low  - LAG(close,1) OVER w)                                     AS lpc,
        CASE WHEN close >= open THEN 1 ELSE 0 END                           AS is_green,
        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC)          AS rn
    FROM ohlcv
    WINDOW w AS (PARTITION BY symbol ORDER BY date)
),
true_range AS (
    SELECT symbol, date, GREATEST(hl, hpc, lpc) AS tr FROM daily
),
atr_raw AS (
    SELECT symbol, date,
        AVG(tr) OVER (PARTITION BY symbol ORDER BY date
                      ROWS BETWEEN 13 PRECEDING AND CURRENT ROW)            AS atr_14,
        AVG(tr) OVER (PARTITION BY symbol ORDER BY date
                      ROWS BETWEEN 4  PRECEDING AND CURRENT ROW)            AS atr_5
    FROM true_range
),
atr_calc AS (
    SELECT symbol, date, atr_14, atr_5,
        LAG(atr_14, 5) OVER (PARTITION BY symbol ORDER BY date)             AS atr_14_5d_ago
    FROM atr_raw
),
rsi_base AS (
    SELECT symbol, date,
        AVG(CASE WHEN delta > 0 THEN delta ELSE 0 END)
            OVER (PARTITION BY symbol ORDER BY date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS avg_gain,
        AVG(CASE WHEN delta < 0 THEN ABS(delta) ELSE 0 END)
            OVER (PARTITION BY symbol ORDER BY date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS avg_loss
    FROM daily
),
green_count AS (
    SELECT symbol, date,
        SUM(is_green) OVER (PARTITION BY symbol ORDER BY date
                            ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS green_days_5
    FROM daily
),
bo_hist AS (
    SELECT symbol, date,
        LAG(CASE WHEN close > resistance_20d THEN 1 ELSE 0 END,1) OVER w AS bo_1d,
        LAG(CASE WHEN close > resistance_20d THEN 1 ELSE 0 END,2) OVER w AS bo_2d,
        LAG(CASE WHEN close > resistance_20d THEN 1 ELSE 0 END,3) OVER w AS bo_3d
    FROM daily
    WINDOW w AS (PARTITION BY symbol ORDER BY date)
),
-- Market proxy: median daily return across all stocks (simple Nifty proxy)
-- Pre-compute daily returns, then aggregate
daily_returns AS (
    SELECT symbol, date,
        (close / NULLIF(LAG(close,1) OVER (PARTITION BY symbol ORDER BY date), 0) - 1) * 100
            AS pct_1d_raw
    FROM ohlcv
),
market_proxy AS (
    SELECT date, MEDIAN(pct_1d_raw) AS market_pct_1d
    FROM daily_returns
    WHERE pct_1d_raw IS NOT NULL
    GROUP BY date
)
SELECT
    d.symbol, d.date,
    d.close AS last_close, d.volume, d.open, d.high, d.low,
    ROUND((d.close/NULLIF(d.prev_close,0)-1)*100,3)                        AS pct_1d,
    ROUND((d.close/NULLIF(d.close_5d,0)-1)*100,3)                          AS pct_5d,
    ROUND((d.close/NULLIF(d.close_20d,0)-1)*100,3)                         AS pct_20d,
    ROUND(d.volume/NULLIF(d.avg_vol_20,0),3)                               AS volume_ratio,
    ROUND(d.volume/NULLIF(d.avg_vol_5,0),3)                                AS rvol_5,
    CASE WHEN d.volume > d.vol_1d THEN 1 ELSE 0 END                        AS vol_up_1d,
    CASE WHEN d.vol_1d > d.vol_2d THEN 1 ELSE 0 END                        AS vol_up_2d,
    CASE WHEN d.vol_2d > d.vol_3d THEN 1 ELSE 0 END                        AS vol_up_3d,
    d.sma50, d.sma20, d.sma10, d.avg_vol_20,
    ROUND((d.close/NULLIF(d.sma50,0)-1)*100,2)                             AS pct_above_50dma,
    ROUND((d.close/NULLIF(d.sma20,0)-1)*100,2)                             AS pct_above_20dma,
    ROUND((d.sma10/NULLIF(d.sma20,0)-1)*100,2)                             AS sma10_above_sma20,
    d.high_52w, d.low_52w,
    ROUND((d.high_52w-d.close)/NULLIF(d.high_52w,0)*100,2)                AS pct_from_52w_high,
    ROUND((d.close-d.low_52w)/NULLIF(d.high_52w-d.low_52w,0)*100,2)       AS range_position,
    CASE WHEN d.close > d.resistance_20d THEN 1 ELSE 0 END                 AS breakout,
    d.resistance_20d,
    ROUND((d.close/NULLIF(d.resistance_20d,0)-1)*100,2)                   AS breakout_extension,
    CASE WHEN d.close > d.resistance_20d THEN 0
         WHEN bh.bo_1d = 1 THEN 1
         WHEN bh.bo_2d = 1 THEN 2
         WHEN bh.bo_3d = 1 THEN 3
         ELSE 99 END                                                        AS breakout_age,
    ROUND((d.open/NULLIF(d.prev_close,0)-1)*100,2)                        AS gap_pct,
    CASE WHEN r.avg_loss = 0 THEN 100
         ELSE ROUND(100-100.0/(1+r.avg_gain/r.avg_loss),1) END             AS rsi_14,
    gc.green_days_5,
    ROUND(atr.atr_14/NULLIF(d.close,0)*100,3)                             AS atr_pct,
    ROUND(atr.atr_5/NULLIF(d.close,0)*100,3)                              AS atr_5_pct,
    CASE WHEN atr.atr_5 > NULLIF(atr.atr_14_5d_ago,0) THEN 1 ELSE 0 END  AS atr_expanding,
    ROUND((d.close/NULLIF(d.close_5d,0)-1)*100
          - COALESCE(mp.market_pct_1d,0)*5, 2)                             AS rel_strength_5d,
    d.rn
FROM daily d
JOIN rsi_base  r   USING (symbol, date)
JOIN green_count gc USING (symbol, date)
JOIN bo_hist   bh  USING (symbol, date)
JOIN atr_calc  atr USING (symbol, date)
LEFT JOIN market_proxy mp USING (date)
WHERE d.rn = 1
  AND d.prev_close IS NOT NULL
  AND d.close_20d  IS NOT NULL
  AND d.avg_vol_20 IS NOT NULL
  AND d.avg_vol_20 > 0
"""

HISTORY_SQL = """
WITH daily AS (
    SELECT symbol, date, close, high, low, volume,
        LAG(close,1)  OVER w                                                AS prev_close,
        LAG(close,5)  OVER w                                                AS close_5d_ago,
        close - LAG(close,1) OVER w                                         AS delta,
        AVG(volume)   OVER (PARTITION BY symbol ORDER BY date
                            ROWS BETWEEN 21 PRECEDING AND 1 PRECEDING)      AS avg_vol_20,
        AVG(volume)   OVER (PARTITION BY symbol ORDER BY date
                            ROWS BETWEEN 5  PRECEDING AND 1 PRECEDING)      AS avg_vol_5,
        AVG(close)    OVER (PARTITION BY symbol ORDER BY date
                            ROWS BETWEEN 49 PRECEDING AND CURRENT ROW)      AS sma50,
        MAX(close)    OVER (PARTITION BY symbol ORDER BY date
                            ROWS BETWEEN 21 PRECEDING AND 1 PRECEDING)      AS resistance_20d,
        LEAD(close,1)  OVER (PARTITION BY symbol ORDER BY date)             AS close_1d_future,
        LEAD(close,5)  OVER (PARTITION BY symbol ORDER BY date)             AS close_5d_future,
        LEAD(close,10) OVER (PARTITION BY symbol ORDER BY date)             AS close_10d_future,
        LEAD(close,20) OVER (PARTITION BY symbol ORDER BY date)             AS close_20d_future,
        MIN(close)     OVER (PARTITION BY symbol ORDER BY date
                            ROWS BETWEEN 1 FOLLOWING AND 5 FOLLOWING)       AS min_close_5d
    FROM ohlcv
    WINDOW w AS (PARTITION BY symbol ORDER BY date)
),
rsi_calc AS (
    SELECT symbol, date,
        AVG(CASE WHEN delta > 0 THEN delta ELSE 0 END)
            OVER (PARTITION BY symbol ORDER BY date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS avg_gain,
        AVG(CASE WHEN delta < 0 THEN ABS(delta) ELSE 0 END)
            OVER (PARTITION BY symbol ORDER BY date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS avg_loss
    FROM daily
)
SELECT
    d.symbol, d.date,
    ROUND(d.volume/NULLIF(d.avg_vol_20,0),2)                               AS volume_ratio,
    ROUND(d.volume/NULLIF(d.avg_vol_5,0),2)                                AS rvol_5,
    ROUND((d.close/NULLIF(d.prev_close,0)-1)*100,2)                        AS pct_1d,
    ROUND((d.close/NULLIF(d.close_5d_ago,0)-1)*100,2)                      AS pct_5d,
    CASE WHEN d.close > d.resistance_20d THEN 1 ELSE 0 END                 AS breakout,
    CASE WHEN d.close > d.sma50          THEN 1 ELSE 0 END                 AS above_50dma,
    CASE WHEN r.avg_loss = 0 THEN 100
         ELSE ROUND(100-100.0/(1+r.avg_gain/r.avg_loss),1) END             AS rsi_14,
    ROUND((d.close_1d_future/NULLIF(d.close,0)-1)*100,2)                   AS ret_1d,
    ROUND((d.close_5d_future/NULLIF(d.close,0)-1)*100,2)                   AS ret_5d,
    ROUND((d.close_10d_future/NULLIF(d.close,0)-1)*100,2)                  AS ret_10d,
    ROUND((d.close_20d_future/NULLIF(d.close,0)-1)*100,2)                  AS ret_20d,
    ROUND((d.min_close_5d/NULLIF(d.close,0)-1)*100,2)                      AS max_dd_5d
FROM daily d
JOIN rsi_calc r USING (symbol, date)
WHERE d.prev_close IS NOT NULL
  AND d.avg_vol_20 IS NOT NULL AND d.avg_vol_20 > 0
  AND d.close_5d_future IS NOT NULL
"""


# ---------------------------------------------------------------------------
# Momentum Score (0-100) — gradual, no binary flags
# ---------------------------------------------------------------------------

def _score_momentum(f: pd.Series) -> tuple[float, list[str], list[str]]:
    score = 0.0
    pos: list[str] = []
    neg: list[str] = []

    vr = float(f.get("volume_ratio", 0) or 0)
    if   vr >= 5:   score += 25; pos.append(f"Volume {vr:.1f}× average — exceptional buying pressure")
    elif vr >= 4:   score += 22; pos.append(f"Volume {vr:.1f}× average — very high institutional interest")
    elif vr >= 3:   score += 18; pos.append(f"Volume {vr:.1f}× average — strong accumulation")
    elif vr >= 2:   score += 12; pos.append(f"Volume {vr:.1f}× average — notable spike")
    elif vr >= 1.5: score +=  6; pos.append(f"Volume {vr:.1f}× average — above-average activity")
    elif vr >= 1.0: score +=  2
    else:           neg.append(f"Volume {vr:.1f}× — below average, weak conviction")

    # RVOL (relative to 5-day avg — captures very recent surge)
    rvol = float(f.get("rvol_5", 0) or 0)
    if   rvol >= 3: score += 5; pos.append(f"RVOL {rvol:.1f}× (5-day avg) — unusual recent activity")
    elif rvol >= 2: score += 3

    acc = ((f.get("vol_up_1d",0) or 0)*4 + (f.get("vol_up_2d",0) or 0)*3 + (f.get("vol_up_3d",0) or 0)*2)
    score += acc
    if acc >= 7: pos.append("Volume rising 3 consecutive days — accumulation")

    age = int(f.get("breakout_age", 99) or 99)
    if   age == 0: score += 20; pos.append("Fresh breakout today above 20-day resistance")
    elif age == 1: score += 14; pos.append("Breakout yesterday — momentum continuing")
    elif age == 2: score +=  8; pos.append("2-day-old breakout — holding above resistance")
    elif age == 3: score +=  3
    else:          neg.append("No recent breakout above resistance")

    d50 = float(f.get("pct_above_50dma", 0) or 0)
    if   d50 < 0:    neg.append(f"Trading {abs(d50):.1f}% below 50-day MA — downtrend")
    elif d50 <= 3:   score += 15; pos.append(f"Just above 50-day MA (+{d50:.1f}%) — early in trend")
    elif d50 <= 7:   score += 12; pos.append(f"Above 50-day MA (+{d50:.1f}%)")
    elif d50 <= 12:  score +=  7
    elif d50 <= 20:  score +=  2; neg.append(f"+{d50:.1f}% above 50-day MA — somewhat extended")
    else:            neg.append(f"+{d50:.1f}% above 50-day MA — significantly overextended")

    r20 = float(f.get("pct_20d", 0) or 0)
    if   r20 >= 40: score +=  4; neg.append(f"+{r20:.0f}% in 20 days — parabolic, mean-reversion risk")
    elif r20 >= 20: score += 10; pos.append(f"+{r20:.0f}% in 20 days — strong uptrend")
    elif r20 >= 10: score += 12; pos.append(f"+{r20:.0f}% in 20 days — healthy momentum sweet spot")
    elif r20 >=  5: score +=  7
    elif r20 >=  0: score +=  2
    else:           neg.append(f"{r20:.0f}% in 20 days — downtrend")

    r5 = float(f.get("pct_5d", 0) or 0)
    if   r5 > 30:  score +=  1; neg.append(f"+{r5:.0f}% in 5 days — already extended short-term")
    elif r5 > 15:  score +=  4
    elif r5 >  8:  score +=  8
    elif r5 >  3:  score += 10; pos.append(f"+{r5:.0f}% in 5 days — recent momentum")
    elif r5 >  0:  score +=  5
    else:          neg.append(f"{r5:.0f}% in 5 days — short-term fading")

    rng = float(f.get("range_position", 50) or 50)
    if   rng >= 90: score += 9; pos.append(f"Near 52-week high (top {100-rng:.0f}% of annual range)")
    elif rng >= 75: score += 7; pos.append(f"Upper portion of 52-week range ({rng:.0f}%)")
    elif rng >= 50: score += 4
    elif rng >= 25: score += 1

    # Relative strength vs market
    rs = float(f.get("rel_strength_5d", 0) or 0)
    if   rs > 10: score += 5; pos.append(f"Outperforming market by +{rs:.1f}% over 5 days")
    elif rs > 5:  score += 3; pos.append(f"Outperforming market by +{rs:.1f}% over 5 days")
    elif rs < -5: neg.append(f"Underperforming market by {rs:.1f}% over 5 days")

    # ATR expansion: volatility expanding = breakout has energy
    if int(f.get("atr_expanding", 0) or 0): score += 3; pos.append("ATR expanding — volatility confirming breakout")

    # SMA10 > SMA20 = short-term trend up
    if float(f.get("sma10_above_sma20", 0) or 0) > 0: score += 3; pos.append("Short-term MA above medium-term MA — uptrend alignment")

    return round(min(score, 100), 1), pos, neg


# ---------------------------------------------------------------------------
# Exhaustion Score (0-100) — reversal risk
# ---------------------------------------------------------------------------

def _score_exhaustion(f: pd.Series) -> tuple[float, list[str]]:
    score = 0.0
    flags: list[str] = []

    rsi = float(f.get("rsi_14", 50) or 50)
    if   rsi > 85: score += 35; flags.append(f"RSI {rsi:.0f} — extremely overbought")
    elif rsi > 80: score += 25; flags.append(f"RSI {rsi:.0f} — overbought, reversal risk")
    elif rsi > 75: score += 14; flags.append(f"RSI {rsi:.0f} — approaching overbought")
    elif rsi > 70: score +=  6; flags.append(f"RSI {rsi:.0f} — elevated")
    elif rsi > 65: score +=  2

    gd = int(f.get("green_days_5", 0) or 0)
    score += min(gd * 4, 20)
    if gd >= 4: flags.append(f"{gd} consecutive green days — may need consolidation")

    r5 = float(f.get("pct_5d", 0) or 0)
    if   r5 > 40: score += 20; flags.append(f"+{r5:.0f}% in 5 days — parabolic")
    elif r5 > 30: score += 15; flags.append(f"+{r5:.0f}% in 5 days — very extended")
    elif r5 > 20: score += 10; flags.append(f"+{r5:.0f}% in 5 days — extended")
    elif r5 > 12: score +=  5

    gap = abs(float(f.get("gap_pct", 0) or 0))
    if   gap > 8:  score += 15; flags.append(f"Gap up {gap:.1f}% — exhaustion candle risk")
    elif gap > 5:  score += 10; flags.append(f"Gap up {gap:.1f}%")
    elif gap > 3:  score +=  5

    d20 = float(f.get("pct_above_20dma", 0) or 0)
    if   d20 > 20: score += 10; flags.append(f"+{d20:.1f}% above 20-day MA — very stretched")
    elif d20 > 12: score +=  6
    elif d20 >  7: score +=  3

    return round(min(score, 100), 1), flags


# ---------------------------------------------------------------------------
# Risk Score — 4 components
# ---------------------------------------------------------------------------

def _score_risk(f: pd.Series) -> dict[str, float]:
    vr  = float(f.get("volume_ratio", 1) or 1)
    liq = 80 if vr < 0.3 else 55 if vr < 0.5 else 30 if vr < 0.8 else 10 if vr < 1.0 else 0

    atr   = float(f.get("atr_pct", 2) or 2)
    vol_r = 80 if atr > 6 else 60 if atr > 4 else 35 if atr > 3 else 15 if atr > 2 else 0

    gap   = abs(float(f.get("gap_pct", 0) or 0))
    gap_r = 80 if gap > 8 else 55 if gap > 5 else 30 if gap > 3 else 10 if gap > 1 else 0

    d50   = float(f.get("pct_above_50dma", 0) or 0)
    ext_r = (70 if d50 < -10 else 50 if d50 < -5 else 25 if d50 < 0
             else 60 if d50 > 25 else 35 if d50 > 15 else 0)

    total = round(liq * 0.30 + vol_r * 0.30 + gap_r * 0.20 + ext_r * 0.20, 1)
    return {
        "risk_score":      min(total, 100),
        "risk_liquidity":  round(liq, 1),
        "risk_volatility": round(vol_r, 1),
        "risk_gap":        round(gap_r, 1),
        "risk_extension":  round(ext_r, 1),
    }


# ---------------------------------------------------------------------------
# Calibrated k-NN continuation probability
# ---------------------------------------------------------------------------

def compute_continuation_stats(
    features: pd.DataFrame,
    history: pd.DataFrame,
    target_return: float = 4.0,
    downside_threshold: float = -2.0,
    min_matches: int = 3,
) -> pd.DataFrame:
    """
    Per stock: find historical sessions with similar features (5-feature k-NN).
    Uses: (vol_bin, rvol_bin, pct_1d_bin, breakout, above_50dma).
    Returns: continuation_prob, expected_return, downside_prob, historical_matches,
             confidence, ret_1d/5d/10d/20d stats, avg_max_drawdown.
    """
    hist = history.copy()
    # 5 features — finer binning with more features → wider probability distribution
    hist["vol_bin"]    = (hist["volume_ratio"] / 0.5).apply(np.floor) * 0.5
    hist["rvol_bin"]   = pd.cut(hist["rvol_5"].clip(0, 10),
                                bins=[0,1,1.5,2,3,5,10,100],
                                labels=[0,1,2,3,4,5,6]).astype(float)
    hist["pct_bin"]    = (hist["pct_1d"] / 2.0).apply(np.floor) * 2.0
    hist["rsi_bin"]    = pd.cut(hist["rsi_14"].clip(20, 90),
                                bins=[20,50,60,70,80,90],
                                labels=[0,1,2,3,4]).astype(float)

    grp_cols = ["vol_bin", "rvol_bin", "pct_bin", "breakout", "above_50dma", "rsi_bin"]

    agg = (
        hist.groupby(grp_cols).agg(
            n_matches    =("ret_5d", "count"),
            cont_prob    =("ret_5d", lambda x: (x >= target_return).mean() * 100),
            exp_return   =("ret_5d", "mean"),
            dn_prob      =("ret_5d", lambda x: (x <= downside_threshold).mean() * 100),
            avg_ret_1d   =("ret_1d",  "mean"),
            avg_ret_10d  =("ret_10d", "mean"),
            avg_ret_20d  =("ret_20d", "mean"),
            avg_max_dd   =("max_dd_5d", "mean"),
            win_rate_10d =("ret_10d", lambda x: (x >= target_return).mean() * 100),
            win_rate_20d =("ret_20d", lambda x: (x >= 8.0).mean() * 100),
        )
        .reset_index()
    )
    agg = agg[agg["n_matches"] >= min_matches]

    # Build lookup with primary and fallback search
    # Build lookup: key = tuple of group values → row dict
    lookup = {}
    for r in agg.itertuples(index=False):
        key = tuple(getattr(r, c) for c in grp_cols)
        lookup[key] = r

    def _get_stats(row: pd.Series) -> dict:
        vb   = np.floor((float(row.get("volume_ratio", 0) or 0)) / 0.5) * 0.5
        rvol = float(row.get("rvol_5", 0) or 0)
        rb   = float(pd.cut([rvol], bins=[0,1,1.5,2,3,5,10,100], labels=[0,1,2,3,4,5,6])[0] or 0)
        pb   = np.floor((float(row.get("pct_1d", 0) or 0)) / 2.0) * 2.0
        bo   = int(row.get("breakout", 0) or 0)
        ab   = int(row.get("above_50dma", 0) or (1 if (row.get("pct_above_50dma", 0) or 0) >= 0 else 0))
        rsi  = float(row.get("rsi_14", 50) or 50)
        rsib = float(pd.cut([rsi], bins=[20,50,60,70,80,90], labels=[0,1,2,3,4])[0] or 1)

        # Progressive fallback: try 5-feature match, then relax rsi, then relax vol
        rec = None
        for dv in [0, -0.5, 0.5]:
            for dp in [0, -2, 2]:
                key = (vb+dv, rb, pb+dp, bo, ab, rsib)
                if key in lookup: rec = lookup[key]; break
            if rec: break
        if not rec:  # relax rsi_bin
            for dv in [0, -0.5, 0.5]:
                for dp in [0, -2, 2]:
                    for rsib2 in [rsib, rsib-1, rsib+1]:
                        key = (vb+dv, rb, pb+dp, bo, ab, rsib2)
                        if key in lookup: rec = lookup[key]; break
                    if rec: break
                if rec: break

        if rec is not None:
            n    = int(rec.n_matches)
            conf = "High" if n >= 100 else "Medium" if n >= 30 else "Low"
            return {
                "continuation_prob":  round(float(rec.cont_prob), 1),
                "expected_return":    round(float(rec.exp_return), 2),
                "downside_prob":      round(float(rec.dn_prob), 1),
                "historical_matches": n,
                "confidence":         conf,
                "avg_ret_1d":         round(float(rec.avg_ret_1d), 2),
                "avg_ret_10d":        round(float(rec.avg_ret_10d), 2),
                "avg_ret_20d":        round(float(rec.avg_ret_20d), 2),
                "avg_max_drawdown":   round(float(rec.avg_max_dd), 2),
                "win_rate_10d":       round(float(rec.win_rate_10d), 1),
                "win_rate_20d":       round(float(rec.win_rate_20d), 1),
            }
        return {"continuation_prob": 0.0, "expected_return": 0.0, "downside_prob": 0.0,
                "historical_matches": 0, "confidence": "Low",
                "avg_ret_1d": 0.0, "avg_ret_10d": 0.0, "avg_ret_20d": 0.0,
                "avg_max_drawdown": 0.0, "win_rate_10d": 0.0, "win_rate_20d": 0.0}

    results = [_get_stats(row) for _, row in features.iterrows()]
    return pd.DataFrame(results, index=features.index)


# ---------------------------------------------------------------------------
# Final composite score
# ---------------------------------------------------------------------------

def _final_score(row: pd.Series) -> float:
    """35% cont_prob + 20% momentum + 20% inv_risk + 15% inv_exhaustion + 10% expected_return"""
    cont  = float(row.get("continuation_prob", 0) or 0)
    mom   = float(row.get("momentum_score",    0) or 0)
    risk  = float(row.get("risk_score",       50) or 50)
    exh   = float(row.get("exhaustion_score",  0) or 0)
    er    = float(max(0, min(row.get("expected_return", 0) or 0, 20)))
    score = (cont * 0.35 + mom * 0.20 + (100-risk) * 0.20
             + (100-exh) * 0.15 + er * 5 * 0.10)
    return round(min(score, 100), 1)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_all_scores(con) -> pd.DataFrame:
    log.info("Extracting features …")
    features = con.execute(FEATURE_SQL).df()
    log.info("  → %d stocks", len(features))

    log.info("Building historical outcomes for k-NN calibration …")
    history = con.execute(HISTORY_SQL).df()
    log.info("  → %d historical data points", len(history))

    log.info("Scoring …")

    mom_results = features.apply(_score_momentum, axis=1)
    features["momentum_score"]  = [r[0] for r in mom_results]
    features["_pos_factors"]    = [r[1] for r in mom_results]
    features["_neg_factors"]    = [r[2] for r in mom_results]

    exh_results = features.apply(_score_exhaustion, axis=1)
    features["exhaustion_score"] = [r[0] for r in exh_results]
    features["_exh_flags"]       = [r[1] for r in exh_results]

    risk_results = features.apply(_score_risk, axis=1)
    for col in ["risk_score","risk_liquidity","risk_volatility","risk_gap","risk_extension"]:
        features[col] = [r[col] for r in risk_results]

    cont_df = compute_continuation_stats(features, history)
    for col in ["continuation_prob","expected_return","downside_prob","historical_matches",
                "confidence","avg_ret_1d","avg_ret_10d","avg_ret_20d",
                "avg_max_drawdown","win_rate_10d","win_rate_20d"]:
        features[col] = cont_df[col].values

    features["final_score"] = features.apply(_final_score, axis=1)

    features["top_positive_factors"] = features["_pos_factors"].apply(
        lambda x: json.dumps(x[:3] if x else []))
    features["top_negative_factors"] = features.apply(
        lambda r: json.dumps((r["_neg_factors"] + r["_exh_flags"])[:3]), axis=1)

    log.info("Score ranges:")
    for col in ["momentum_score","continuation_prob","expected_return",
                "exhaustion_score","risk_score","final_score"]:
        s = features[col]
        log.info("  %-22s min=%5.1f max=%5.1f avg=%5.1f std=%5.1f",
                 col, s.min(), s.max(), s.mean(), s.std())
    log.info("  Confidence: %s", features["confidence"].value_counts().to_dict())

    return features
