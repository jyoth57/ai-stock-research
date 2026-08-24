"""indicators.py
--------------
Step 1 of the two-stage technical pipeline.

All calculations are deterministic and reproducible — no LLM involved.

Computed signals
----------------
  Trend
    ema20, ema50, ema200
    ema20_above_ema50, ema50_above_ema200

  Momentum
    rsi_14
    macd_signal          ("Bullish" | "Bearish" | "Neutral")
    macd_histogram

  Trend Strength
    adx_14

  Volatility
    atr_14

  Volume
    volume_ratio          last volume / 20-session average

  Price Context
    distance_52w_high_pct   % below 52-week high  (positive = below)
    distance_52w_low_pct    % above 52-week low   (positive = above)
    support                 classic pivot support S1
    resistance              classic pivot resistance R1

  Breakout / Pattern
    breakout              bool — close > 20-day prior high
    breakout_type         "Ascending Triangle" | "Bullish Flag" | "Range Breakout" | "None"
    pattern               detected candle/chart pattern label or "None"

  Relative Strength
    rs_vs_nifty_20d       20-session return of stock / 20-session return of Nifty
                          > 1 means outperforming; None if Nifty data unavailable

Usage
-----
    from src.technicals.indicators import compute_technicals

    signals = compute_technicals("RELIANCE")
    print(signals.model_dump())
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from src.core.exceptions import DataNotFoundError
from src.market.ohlcv import OHLCVStore

log = logging.getLogger(__name__)

_store = OHLCVStore()

# Nifty 50 benchmark symbol stored in the same OHLCVStore
_NIFTY_SYMBOL = "^NSEI"


# ---------------------------------------------------------------------------
# Pure pandas/numpy indicator helpers (replaces pandas_ta dependency)
# ---------------------------------------------------------------------------

def _ema(series: pd.Series, length: int) -> pd.Series:
    """Exponential moving average (standard, span-based)."""
    return series.ewm(span=length, adjust=False).mean()


def _wilder_smooth(series: pd.Series, length: int) -> pd.Series:
    """Wilder's smoothing — alpha = 1/length (used for RSI, ADX, ATR)."""
    return series.ewm(alpha=1.0 / length, adjust=False).mean()


def _rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    avg_gain = _wilder_smooth(delta.clip(lower=0), length)
    avg_loss = _wilder_smooth((-delta).clip(lower=0), length)
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    return 100.0 - (100.0 / (1.0 + rs))


def _macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """Returns DataFrame with columns [MACD, MACDh (histogram), MACDs (signal)].

    Column order matches pandas_ta: iloc[:,0]=MACD, iloc[:,1]=histogram, iloc[:,2]=signal.
    """
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    histogram = macd_line - signal_line
    return pd.DataFrame(
        {"MACD": macd_line, "MACDh": histogram, "MACDs": signal_line},
        index=close.index,
    )


def _atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    length: int = 14,
) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return _wilder_smooth(tr, length)


def _adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    length: int = 14,
) -> pd.DataFrame:
    """Returns DataFrame with ADX_{length} as the first column (matches pandas_ta iloc[:,0])."""
    prev_high = high.shift(1)
    prev_low = low.shift(1)
    prev_close = close.shift(1)

    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)

    up_move = high - prev_high
    down_move = prev_low - low

    dm_plus = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=close.index,
    )
    dm_minus = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=close.index,
    )

    tr_s = _wilder_smooth(tr, length)
    di_plus = 100.0 * _wilder_smooth(dm_plus, length) / tr_s
    di_minus = 100.0 * _wilder_smooth(dm_minus, length) / tr_s

    denom = (di_plus + di_minus).replace(0, float("nan"))
    dx = 100.0 * (di_plus - di_minus).abs() / denom
    adx_series = _wilder_smooth(dx, length)

    return pd.DataFrame(
        {f"ADX_{length}": adx_series, f"DMP_{length}": di_plus, f"DMN_{length}": di_minus},
        index=close.index,
    )


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------

class TechnicalSignals(BaseModel):
    """Structured output from Step 1 — pure Python indicator calculations."""

    symbol: str
    as_of: date
    price: float

    # EMA
    ema20: float
    ema50: float
    ema200: float
    ema20_above_ema50: bool
    ema50_above_ema200: bool

    # Momentum
    rsi_14: float = Field(ge=0, le=100)
    macd_signal: str          # "Bullish" | "Bearish" | "Neutral"
    macd_histogram: float

    # Trend strength
    adx_14: float

    # Volatility
    atr_14: float

    # Volume
    volume_ratio: float       # last / 20-day average

    # Price context
    distance_52w_high_pct: float   # % below 52-week high (positive = below)
    distance_52w_low_pct: float    # % above 52-week low  (positive = above)
    high_52w: float
    low_52w: float
    support: float             # pivot S1
    resistance: float          # pivot R1

    # Breakout / Pattern
    breakout: bool
    breakout_type: str         # "Ascending Triangle" | "Bullish Flag" | "Range Breakout" | "None"
    pattern: str               # detected pattern label or "None"

    # Higher High / Higher Low (last 5 consecutive bars all printing HH + HL)
    hh_hl: bool

    # Distance of last close from EMA20 as a percentage (+ = above, - = below)
    dist_from_ema20_pct: float

    # Sessions elapsed since the most recent breakout bar (None if > 60 bars ago)
    breakout_age: Optional[int] = None

    # Relative strength vs benchmark
    rs_vs_nifty_20d: Optional[float] = None   # None if Nifty data unavailable


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _last(series: pd.Series) -> float:
    """Return the last non-NaN scalar value from a Series."""
    val = series.dropna()
    if val.empty:
        return float("nan")
    return float(val.iloc[-1])


def _pivot_sr(df: pd.DataFrame) -> tuple[float, float]:
    """Classic floor pivot S1 / R1 from the most recent completed session."""
    if len(df) < 2:
        return float("nan"), float("nan")
    prev = df.iloc[-2]
    pivot = (prev["High"] + prev["Low"] + prev["Close"]) / 3.0
    s1 = 2 * pivot - prev["High"]
    r1 = 2 * pivot - prev["Low"]
    return round(s1, 2), round(r1, 2)


def _detect_breakout_type(df: pd.DataFrame, window: int = 20) -> str:
    """
    Simple heuristic chart-pattern classification on the last *window* bars.

    Ascending Triangle  — roughly flat resistance, higher lows
    Bullish Flag        — sharp prior up-move followed by a tight consolidation
    Range Breakout      — last close > prior window high, no clear ascending-triangle
    None                — price did not break out
    """
    if len(df) < window + 5:
        return "None"

    recent = df.iloc[-(window + 5):-1]   # exclude today
    last_close = float(df["Close"].iloc[-1])
    prior_high = float(recent["High"].max())

    if last_close <= prior_high:
        return "None"

    # Check for ascending triangle: resistance is flat, lows are rising
    highs = recent["High"].values
    lows = recent["Low"].values
    high_range = highs.max() - highs.min()
    high_mean = highs.mean()

    # Resistance is "flat" if high_range < 2% of mean
    flat_resistance = high_range / high_mean < 0.02

    # Higher lows: fit a linear trend; positive slope = rising lows
    x = np.arange(len(lows), dtype=float)
    slope_lows = float(np.polyfit(x, lows, 1)[0])

    if flat_resistance and slope_lows > 0:
        return "Ascending Triangle"

    # Bullish flag: prior 5-bar move was > 5%, last window was tight (<3% range)
    pre_move = df.iloc[-(window + 10):-(window + 5)]
    if not pre_move.empty:
        pre_return = (float(pre_move["Close"].iloc[-1]) - float(pre_move["Close"].iloc[0])) / float(
            pre_move["Close"].iloc[0]
        )
        flag_range = (recent["High"].max() - recent["Low"].min()) / recent["Close"].mean()
        if pre_return > 0.05 and flag_range < 0.03:
            return "Bullish Flag"

    return "Range Breakout"


def _detect_candle_pattern(df: pd.DataFrame) -> str:
    """
    Detect basic candlestick patterns from the last few bars using pure numpy.
    Returns the name of the first detected pattern, or "None".
    """
    if len(df) < 3:
        return "None"

    o = df["Open"].values
    h = df["High"].values
    l = df["Low"].values
    c = df["Close"].values

    body = c - o
    candle_range = h - l

    def _body_pct(i: int) -> float:
        return abs(body[i]) / candle_range[i] if candle_range[i] > 0 else 0.0

    i = len(df) - 1  # last bar

    # Doji: very small body (< 10% of range)
    if _body_pct(i) < 0.10:
        return "Doji"

    # Hammer / Hanging Man: small body at top, long lower wick (>= 2x body)
    lower_wick = min(o[i], c[i]) - l[i]
    upper_wick = h[i] - max(o[i], c[i])
    if _body_pct(i) < 0.35 and lower_wick >= 2 * abs(body[i]) and upper_wick < abs(body[i]):
        return "Hammer" if c[i] > o[i] else "Hanging Man"

    # Shooting Star / Inverted Hammer: small body at bottom, long upper wick
    if _body_pct(i) < 0.35 and upper_wick >= 2 * abs(body[i]) and lower_wick < abs(body[i]):
        return "Shooting Star" if c[i] < o[i] else "Inverted Hammer"

    # Bullish Engulfing: prior bar bearish, current bar bullish and engulfs it
    if i >= 1 and body[i] > 0 and body[i - 1] < 0:
        if c[i] > o[i - 1] and o[i] < c[i - 1]:
            return "Bullish Engulfing"

    # Bearish Engulfing: prior bar bullish, current bar bearish and engulfs it
    if i >= 1 and body[i] < 0 and body[i - 1] > 0:
        if c[i] < o[i - 1] and o[i] > c[i - 1]:
            return "Bearish Engulfing"

    # Morning Star (3-bar): bearish, small body, bullish
    if i >= 2 and body[i - 2] < 0 and _body_pct(i - 1) < 0.25 and body[i] > 0:
        if c[i] > (o[i - 2] + c[i - 2]) / 2:
            return "Morning Star"

    # Evening Star (3-bar): bullish, small body, bearish
    if i >= 2 and body[i - 2] > 0 and _body_pct(i - 1) < 0.25 and body[i] < 0:
        if c[i] < (o[i - 2] + c[i - 2]) / 2:
            return "Evening Star"

    return "None"


def _relative_strength(stock_df: pd.DataFrame, nifty_df: pd.DataFrame, window: int = 20) -> Optional[float]:
    """
    20-session price return of the stock divided by the 20-session return of Nifty.
    > 1.0 means the stock outperformed the index.
    Returns None if insufficient data.
    """
    if len(stock_df) < window + 1 or len(nifty_df) < window + 1:
        return None

    stock_ret = float(stock_df["Close"].iloc[-1]) / float(stock_df["Close"].iloc[-(window + 1)]) - 1.0
    nifty_ret = float(nifty_df["Close"].iloc[-1]) / float(nifty_df["Close"].iloc[-(window + 1)]) - 1.0

    if nifty_ret == 0.0:
        return None

    return round(stock_ret / abs(nifty_ret), 4)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_technicals_from_df(
    symbol: str,
    df: pd.DataFrame,
    nifty_df: Optional[pd.DataFrame] = None,
) -> TechnicalSignals:
    """Core computation — accepts a pre-loaded OHLCV DataFrame.

    Parameters
    ----------
    symbol:
        Bare NSE symbol string (used only for labelling).
    df:
        OHLCV DataFrame with DatetimeIndex and columns Open/High/Low/Close/Volume,
        sorted ascending, containing at least 250 rows.
    nifty_df:
        Optional Nifty OHLCV DataFrame for relative-strength calculation.

    Returns
    -------
    TechnicalSignals
    """
    # ------------------------------------------------------------------
    # EMAs
    # ------------------------------------------------------------------
    df = df.copy()
    df["EMA20"]  = _ema(df["Close"], 20)
    df["EMA50"]  = _ema(df["Close"], 50)
    df["EMA200"] = _ema(df["Close"], 200)

    # ------------------------------------------------------------------
    # RSI
    # ------------------------------------------------------------------
    df["RSI"] = _rsi(df["Close"], 14)

    # ------------------------------------------------------------------
    # MACD
    # ------------------------------------------------------------------
    macd_df = _macd(df["Close"], fast=12, slow=26, signal=9)
    df["MACD_hist"] = macd_df.iloc[:, 1]  # histogram column (index 1 = MACDh)

    # ------------------------------------------------------------------
    # ADX
    # ------------------------------------------------------------------
    adx_df = _adx(df["High"], df["Low"], df["Close"], 14)
    df["ADX"] = adx_df.iloc[:, 0]  # ADX_14 column

    # ------------------------------------------------------------------
    # ATR
    # ------------------------------------------------------------------
    df["ATR"] = _atr(df["High"], df["Low"], df["Close"], 14)

    # ------------------------------------------------------------------
    # Volume ratio
    # ------------------------------------------------------------------
    df["VolAvg20"] = df["Volume"].rolling(20).mean()
    last_vol = float(df["Volume"].iloc[-1])
    avg_vol = float(df["VolAvg20"].iloc[-1])
    volume_ratio = round(last_vol / avg_vol, 2) if avg_vol else float("nan")

    # ------------------------------------------------------------------
    # 52-week high / low and distances
    # ------------------------------------------------------------------
    df_252 = df.iloc[-252:]
    high_52w = float(df_252["High"].max())
    low_52w  = float(df_252["Low"].min())
    last_close = float(df["Close"].iloc[-1])

    dist_52w_high = round((high_52w - last_close) / high_52w * 100, 2)
    dist_52w_low  = round((last_close - low_52w)  / low_52w  * 100, 2)

    # ------------------------------------------------------------------
    # Pivot support / resistance
    # ------------------------------------------------------------------
    support, resistance = _pivot_sr(df)

    # ------------------------------------------------------------------
    # Breakout (simple: close > 20-day prior high)
    # ------------------------------------------------------------------
    prior_20_high = float(df["High"].iloc[-21:-1].max()) if len(df) >= 21 else float("nan")
    breakout = last_close > prior_20_high if not np.isnan(prior_20_high) else False

    breakout_type = _detect_breakout_type(df)
    pattern = _detect_candle_pattern(df)

    # ------------------------------------------------------------------
    # Higher High / Higher Low (5 consecutive bars)
    # ------------------------------------------------------------------
    hh_hl = False
    if len(df) >= 6:
        recent_highs = df["High"].iloc[-6:].values
        recent_lows  = df["Low"].iloc[-6:].values
        hh = all(recent_highs[i] > recent_highs[i - 1] for i in range(1, len(recent_highs)))
        hl = all(recent_lows[i]  > recent_lows[i - 1]  for i in range(1, len(recent_lows)))
        hh_hl = bool(hh and hl)

    # ------------------------------------------------------------------
    # Distance from EMA20 (%)
    # ------------------------------------------------------------------
    ema20_val = _last(df["EMA20"])
    dist_from_ema20_pct = (
        round((last_close - ema20_val) / ema20_val * 100, 2)
        if ema20_val and not np.isnan(ema20_val) else 0.0
    )

    # ------------------------------------------------------------------
    # Breakout Age (sessions since the last breakout bar fired)
    # ------------------------------------------------------------------
    breakout_age: Optional[int] = None
    if len(df) >= 22:
        prior_high_series = df["High"].shift(1).rolling(20).max()
        bo_series = df["Close"] > prior_high_series
        # Search within the last 60 bars so stale breakouts are ignored
        recent_bo = bo_series.iloc[-60:]
        true_positions = recent_bo[recent_bo].index
        if len(true_positions) > 0:
            last_bo_idx = true_positions[-1]
            loc = df.index.get_loc(last_bo_idx)
            breakout_age = len(df) - 1 - (loc if isinstance(loc, int) else int(loc.start))

    # ------------------------------------------------------------------
    # Relative strength vs Nifty
    # ------------------------------------------------------------------
    rs: Optional[float] = None
    if nifty_df is not None:
        rs = _relative_strength(df, nifty_df)

    # ------------------------------------------------------------------
    # MACD signal label
    # ------------------------------------------------------------------
    hist_val = _last(df["MACD_hist"])
    if np.isnan(hist_val):
        macd_signal = "Neutral"
    elif hist_val > 0:
        macd_signal = "Bullish"
    else:
        macd_signal = "Bearish"

    return TechnicalSignals(
        symbol=symbol.upper(),
        as_of=date.fromisoformat(str(df.index[-1].date())),
        price=round(last_close, 2),

        ema20=round(_last(df["EMA20"]), 2),
        ema50=round(_last(df["EMA50"]), 2),
        ema200=round(_last(df["EMA200"]), 2),
        ema20_above_ema50=bool(_last(df["EMA20"]) > _last(df["EMA50"])),
        ema50_above_ema200=bool(_last(df["EMA50"]) > _last(df["EMA200"])),

        rsi_14=round(_last(df["RSI"]), 1),
        macd_signal=macd_signal,
        macd_histogram=round(hist_val, 4) if not np.isnan(hist_val) else 0.0,

        adx_14=round(_last(df["ADX"]), 1),

        atr_14=round(_last(df["ATR"]), 2),

        volume_ratio=volume_ratio,

        distance_52w_high_pct=dist_52w_high,
        distance_52w_low_pct=dist_52w_low,
        high_52w=round(high_52w, 2),
        low_52w=round(low_52w, 2),
        support=support,
        resistance=resistance,

        breakout=breakout,
        breakout_type=breakout_type,
        pattern=pattern,
        hh_hl=hh_hl,
        dist_from_ema20_pct=dist_from_ema20_pct,
        breakout_age=breakout_age,

        rs_vs_nifty_20d=rs,
    )


def compute_technicals(symbol: str, min_rows: int = 250) -> TechnicalSignals:
    """Calculate all technical indicators for *symbol* (loads from OHLCVStore).

    Parameters
    ----------
    symbol:
        Bare NSE symbol, e.g. ``"RELIANCE"``.
    min_rows:
        Minimum candles required; raises ``ValueError`` if fewer exist.

    Returns
    -------
    TechnicalSignals
        Fully populated Pydantic model ready to be fed into the LLM chain.

    Raises
    ------
    DataNotFoundError
        If no local OHLCV data exists for the symbol.
    ValueError
        If fewer than *min_rows* candles are available.
    """
    df = _store.read(symbol)
    df = df.sort_index()

    if len(df) < min_rows:
        raise ValueError(
            f"{symbol} has only {len(df)} rows; need at least {min_rows}."
        )

    nifty_df: Optional[pd.DataFrame] = None
    try:
        nifty_df = _store.read(_NIFTY_SYMBOL).sort_index()
    except DataNotFoundError:
        log.debug("Nifty data not available; skipping relative strength.")

    return compute_technicals_from_df(symbol, df, nifty_df=nifty_df)
