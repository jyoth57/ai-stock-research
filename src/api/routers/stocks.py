"""stocks router — OHLCV + signals + prediction object per symbol"""
from __future__ import annotations
import json
from fastapi import APIRouter, HTTPException
from src.database.duckdb_store import get_store

router = APIRouter(tags=["stocks"])


@router.get("/symbols")
def list_symbols():
    return get_store().get_symbols()


@router.get("/{symbol}/ohlcv")
def ohlcv(symbol: str):
    store = get_store()
    df = store.get_ohlcv(symbol)
    if df.empty:
        raise HTTPException(404, f"No data for {symbol}")
    df["Date"] = df["Date"].astype(str)
    return df.to_dict(orient="records")


@router.get("/{symbol}/signals")
def signals(symbol: str):
    row = get_store().get_signal_row(symbol)
    if row is None:
        raise HTTPException(404, f"No signals for {symbol}")
    return row


@router.get("/{symbol}/historical-patterns")
def historical_patterns(symbol: str):
    """
    Multi-period historical pattern analysis for one stock.
    Shows how similar past setups performed at 1d / 5d / 10d / 20d horizons.
    """
    row = get_store().get_signal_row(symbol.upper())
    if row is None:
        raise HTTPException(404, f"No data for {symbol}")

    n = int(row.get("historical_matches", 0) or 0)
    prob = float(row.get("continuation_prob", 0) or 0)
    successes = round(n * prob / 100)

    return {
        "symbol":              symbol.upper(),
        "similar_setups":      n,
        "confidence":          row.get("confidence", "Low"),
        "description": (
            f"Found {n} historical sessions across all NSE stocks with similar "
            f"volume ratio, price momentum, breakout status, and RSI."
        ),
        "returns": {
            "1d":  {"avg": row.get("avg_ret_1d"),  "label": "Next session"},
            "5d":  {"avg": row.get("expected_return"), "win_rate": prob,
                    "successes": successes, "total": n, "label": "5 sessions"},
            "10d": {"avg": row.get("avg_ret_10d"), "win_rate": row.get("win_rate_10d"),
                    "label": "10 sessions"},
            "20d": {"avg": row.get("avg_ret_20d"), "win_rate": row.get("win_rate_20d"),
                    "label": "20 sessions"},
        },
        "risk": {
            "avg_max_drawdown_5d": row.get("avg_max_drawdown"),
            "downside_prob":       row.get("downside_prob"),
            "description": (
                f"Median maximum drawdown over 5 sessions: "
                f"{row.get('avg_max_drawdown', 0):.1f}%"
            ),
        },
        "conclusion": (
            f"Of {n} similar historical setups, {successes} ({prob:.0f}%) "
            f"achieved ≥4% gain within 5 sessions. "
            f"Average 5-day return: {row.get('expected_return', 0):.1f}%. "
            f"Average 20-day return: {row.get('avg_ret_20d', 0):.1f}%."
        ),
    }


@router.get("/{symbol}/prediction")
def prediction(symbol: str):
    """Full structured prediction object for one stock."""
    row = get_store().get_signal_row(symbol.upper())
    if row is None:
        raise HTTPException(404, f"No prediction data for {symbol}")

    # Parse JSON factor strings
    pos = row.get("top_positive_factors", "[]")
    neg = row.get("top_negative_factors", "[]")
    try:
        pos = json.loads(pos) if isinstance(pos, str) else (pos or [])
        neg = json.loads(neg) if isinstance(neg, str) else (neg or [])
    except Exception:
        pos, neg = [], []

    return {
        "symbol":                   symbol.upper(),
        "sector":                   row.get("sector", "Other"),
        "last_close":               row.get("last_close"),
        # Probability & return
        "probability_next_5d_gt_4pct": row.get("continuation_prob"),
        "expected_return_5d_pct":      row.get("expected_return"),
        "downside_probability":        row.get("downside_prob"),
        "historical_matches":          row.get("historical_matches"),
        "confidence":                  row.get("confidence", "Low"),
        # Composite scores
        "momentum_score":          row.get("momentum_score"),
        "exhaustion_score":        row.get("exhaustion_score"),
        "final_score":             row.get("final_score"),
        # Risk decomposition
        "risk": {
            "total":      row.get("risk_score"),
            "liquidity":  row.get("risk_liquidity"),
            "volatility": row.get("risk_volatility"),
            "gap":        row.get("risk_gap"),
            "extension":  row.get("risk_extension"),
        },
        # Key metrics
        "pct_1d":             row.get("pct_1d"),
        "pct_5d":             row.get("pct_5d"),
        "pct_20d":            row.get("pct_20d"),
        "volume_ratio":       row.get("volume_ratio"),
        "rsi_14":             row.get("rsi_14"),
        "breakout_age":       row.get("breakout_age"),
        "pct_above_50dma":    row.get("pct_above_50dma"),
        "pct_from_52w_high":  row.get("pct_from_52w_high"),
        # Explanations
        "top_positive_factors": pos,
        "top_negative_factors": neg,
    }
