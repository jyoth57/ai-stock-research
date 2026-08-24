"""technical_analysis_chain.py
------------------------------
Step 2 of the two-stage technical pipeline.

Receives only the pre-calculated indicator dict from Step 1 and asks the LLM to:
  1. Explain the setup in plain English
  2. Classify the trend
  3. Estimate breakout probability
  4. Recommend entry / stop-loss / targets
  5. Write a one-paragraph verdict

The LLM never touches raw price data — all maths are done in indicators.py.

Usage
-----
    from src.technicals.indicators import compute_technicals
    from src.ai.chains.technical_analysis_chain import run_technical_analysis

    signals = compute_technicals("RELIANCE")
    analysis = run_technical_analysis(signals)
    print(analysis.verdict)
"""

from __future__ import annotations

import json
import logging
from typing import Literal, Optional

from pydantic import BaseModel, Field

from src.ai.llm.client import LLMClient, SYSTEM_PROMPTS
from src.technicals.indicators import TechnicalSignals

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------

class TechnicalAnalysis(BaseModel):
    """Structured LLM output for a single stock's technical picture."""

    symbol: str
    as_of: str

    trend_classification: Literal[
        "Strong Uptrend",
        "Uptrend",
        "Sideways / Consolidation",
        "Downtrend",
        "Strong Downtrend",
    ]

    setup_description: str = Field(
        description="Plain-English explanation of what the chart is showing."
    )

    breakout_probability_pct: int = Field(
        ge=0, le=100,
        description="Estimated probability (0-100) that a bullish breakout sustains.",
    )

    entry_price: float = Field(description="Suggested entry price or zone midpoint.")
    stop_loss: float   = Field(description="Suggested stop-loss level.")
    target_1: float    = Field(description="First profit target.")
    target_2: float    = Field(description="Second profit target.")
    target_3: float    = Field(description="Third (extended) profit target.")
    risk_reward_ratio: float = Field(description="(T1 - Entry) / (Entry - SL), rounded to 1 dp.")

    key_risks: list[str] = Field(
        default_factory=list,
        description="2-3 specific risks that could invalidate this setup.",
    )

    verdict: str = Field(
        description=(
            "One concise paragraph: overall assessment, conviction level, "
            "and what to watch for."
        )
    )

    confidence: Literal["High", "Medium", "Low"] = Field(
        description="Analyst's confidence in this setup."
    )


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

_USER_TEMPLATE = """\
Analyse the following pre-calculated technical indicators for {symbol} as of {as_of}.
All numbers are already computed — do NOT recalculate them.

--- TECHNICAL SNAPSHOT ---
{snapshot_json}
--------------------------

Respond ONLY with a JSON object that exactly matches this schema (no markdown fences):
{{
  "symbol": string,
  "as_of": string,
  "trend_classification": "Strong Uptrend"|"Uptrend"|"Sideways / Consolidation"|"Downtrend"|"Strong Downtrend",
  "setup_description": string,
  "breakout_probability_pct": integer 0-100,
  "entry_price": number,
  "stop_loss": number,
  "target_1": number,
  "target_2": number,
  "target_3": number,
  "risk_reward_ratio": number,
  "key_risks": [string, string],
  "verdict": string,
  "confidence": "High"|"Medium"|"Low"
}}

Guidelines:
- Base entry/SL/targets on the provided support, resistance, ATR, and price.
- SL should be ATR-based or just below the nearest support — never more than 2×ATR below entry.
- T1 = entry + 1.5×ATR, T2 = resistance level, T3 = extended move (use your judgement).
- risk_reward_ratio = (target_1 - entry_price) / (entry_price - stop_loss), rounded to 1 dp.
- breakout_probability_pct must reflect ADX trend strength, RSI momentum, volume confirmation, and pattern quality.
- If breakout is false, breakout_probability_pct should be low (< 40) unless the setup is building toward one.
- key_risks: exactly 2-3 items, each one sentence, specific to this stock's current signals.
- verdict: one paragraph, mention the 2-3 most important signals driving the view.
"""


def _build_snapshot(signals: TechnicalSignals) -> dict:
    """Flatten TechnicalSignals into the exact dict we send to the LLM."""
    return {
        "EMA20_above_EMA50":   signals.ema20_above_ema50,
        "EMA50_above_EMA200":  signals.ema50_above_ema200,
        "EMA20":               signals.ema20,
        "EMA50":               signals.ema50,
        "EMA200":              signals.ema200,
        "Price":               signals.price,
        "RSI_14":              signals.rsi_14,
        "MACD":                signals.macd_signal,
        "MACD_Histogram":      signals.macd_histogram,
        "ADX_14":              signals.adx_14,
        "ATR_14":              signals.atr_14,
        "VolumeRatio":         signals.volume_ratio,
        "Breakout":            signals.breakout,
        "BreakoutType":        signals.breakout_type,
        "Pattern":             signals.pattern,
        "Distance_52w_High":   f"{signals.distance_52w_high_pct:.1f}%",
        "Distance_52w_Low":    f"{signals.distance_52w_low_pct:.1f}%",
        "High_52w":            signals.high_52w,
        "Low_52w":             signals.low_52w,
        "Support_S1":          signals.support,
        "Resistance_R1":       signals.resistance,
        "RS_vs_Nifty_20d":     signals.rs_vs_nifty_20d,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_technical_analysis(
    signals: TechnicalSignals,
    llm: Optional[LLMClient] = None,
) -> TechnicalAnalysis:
    """Feed pre-computed indicator signals to the LLM and return structured analysis.

    Parameters
    ----------
    signals:
        Output of ``compute_technicals(symbol)``.
    llm:
        Optional pre-built LLMClient. A default client is created if not provided.

    Returns
    -------
    TechnicalAnalysis
        Fully validated Pydantic model with setup description, entry/SL/targets,
        and verdict.
    """
    if llm is None:
        llm = LLMClient()

    snapshot = _build_snapshot(signals)
    user_msg = _USER_TEMPLATE.format(
        symbol=signals.symbol,
        as_of=str(signals.as_of),
        snapshot_json=json.dumps(snapshot, indent=2),
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPTS["technical"]},
        {"role": "user",   "content": user_msg},
    ]

    log.info("Running LLM technical analysis for %s", signals.symbol)
    raw = llm.chat(messages, temperature=0.1)

    # Strip accidental markdown fences if the model wraps the JSON
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"LLM returned non-JSON response for {signals.symbol}:\n{raw}"
        ) from exc

    return TechnicalAnalysis(**data)
