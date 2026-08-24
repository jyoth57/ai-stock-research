"""technical_pipeline.py
------------------------
Orchestrates the two-stage technical analysis pipeline:

  Stage 1  (Python / deterministic)
    compute_technicals(symbol) → TechnicalSignals

  Stage 2  (LLM / interpretive)
    run_technical_analysis(signals) → TechnicalAnalysis

Usage
-----
    # Single stock
    from src.research.technical_pipeline import run_pipeline

    result = run_pipeline("RELIANCE")
    print(result.signals.model_dump())   # raw indicators
    print(result.analysis.verdict)       # LLM narrative

    # Batch
    from src.research.technical_pipeline import run_pipeline_batch

    results = run_pipeline_batch(["RELIANCE", "TCS", "HDFCBANK"])
    for r in results:
        if r.error:
            print(f"{r.symbol}: ERROR — {r.error}")
        else:
            print(f"{r.symbol}: {r.analysis.trend_classification}")

CLI
---
    python -m src.research.technical_pipeline RELIANCE TCS HDFCBANK
    python -m src.research.technical_pipeline RELIANCE --no-llm
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from typing import Optional

from src.ai.chains.technical_analysis_chain import TechnicalAnalysis, run_technical_analysis
from src.ai.llm.client import LLMClient
from src.technicals.indicators import TechnicalSignals, compute_technicals

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class PipelineResult:
    symbol: str
    signals: Optional[TechnicalSignals] = None
    analysis: Optional[TechnicalAnalysis] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Single-stock pipeline
# ---------------------------------------------------------------------------

def run_pipeline(
    symbol: str,
    llm: Optional[LLMClient] = None,
    run_llm: bool = True,
) -> PipelineResult:
    """Full two-stage pipeline for one symbol.

    Parameters
    ----------
    symbol:
        Bare NSE symbol, e.g. ``"RELIANCE"``.
    llm:
        Optional shared LLMClient (avoids rebuilding the client per symbol in batch mode).
    run_llm:
        Set to False to only run Stage 1 (indicators) without calling the LLM.
    """
    result = PipelineResult(symbol=symbol.upper())

    # ------------------------------------------------------------------
    # Stage 1 — deterministic indicators
    # ------------------------------------------------------------------
    try:
        result.signals = compute_technicals(symbol)
        log.info(
            "[%s] Stage 1 complete: price=%.2f  RSI=%.1f  ADX=%.1f  breakout=%s",
            symbol,
            result.signals.price,
            result.signals.rsi_14,
            result.signals.adx_14,
            result.signals.breakout,
        )
    except Exception as exc:
        result.error = f"Stage 1 failed: {exc}"
        log.error("[%s] %s", symbol, result.error)
        return result

    if not run_llm:
        return result

    # ------------------------------------------------------------------
    # Stage 2 — LLM interpretation
    # ------------------------------------------------------------------
    try:
        if llm is None:
            llm = LLMClient()
        result.analysis = run_technical_analysis(result.signals, llm=llm)
        log.info(
            "[%s] Stage 2 complete: %s  confidence=%s  prob=%d%%",
            symbol,
            result.analysis.trend_classification,
            result.analysis.confidence,
            result.analysis.breakout_probability_pct,
        )
    except Exception as exc:
        result.error = f"Stage 2 failed: {exc}"
        log.error("[%s] %s", symbol, result.error)

    return result


# ---------------------------------------------------------------------------
# Batch pipeline
# ---------------------------------------------------------------------------

def run_pipeline_batch(
    symbols: list[str],
    run_llm: bool = True,
) -> list[PipelineResult]:
    """Run the pipeline for multiple symbols, sharing one LLMClient instance."""
    llm = LLMClient() if run_llm else None
    results = []
    for sym in symbols:
        results.append(run_pipeline(sym, llm=llm, run_llm=run_llm))
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_result(r: PipelineResult, verbose: bool = False) -> None:
    sep = "─" * 60
    print(f"\n{sep}")
    print(f"  {r.symbol}")
    print(sep)

    if r.error:
        print(f"  ERROR: {r.error}")
        return

    s = r.signals
    print(f"  Price        : {s.price:.2f}")
    print(f"  Trend EMAs   : EMA20={s.ema20:.2f}  EMA50={s.ema50:.2f}  EMA200={s.ema200:.2f}")
    print(f"  EMA stack    : 20>50={s.ema20_above_ema50}  50>200={s.ema50_above_ema200}")
    print(f"  RSI (14)     : {s.rsi_14:.1f}")
    print(f"  MACD         : {s.macd_signal}  (hist {s.macd_histogram:+.4f})")
    print(f"  ADX (14)     : {s.adx_14:.1f}")
    print(f"  ATR (14)     : {s.atr_14:.2f}")
    print(f"  Volume ratio : {s.volume_ratio:.2f}x")
    print(f"  52w High     : {s.high_52w:.2f}  ({s.distance_52w_high_pct:.1f}% away)")
    print(f"  52w Low      : {s.low_52w:.2f}  ({s.distance_52w_low_pct:.1f}% above)")
    print(f"  Support S1   : {s.support:.2f}   Resistance R1: {s.resistance:.2f}")
    print(f"  Breakout     : {s.breakout}  ({s.breakout_type})")
    print(f"  Pattern      : {s.pattern}")
    if s.rs_vs_nifty_20d is not None:
        print(f"  RS vs Nifty  : {s.rs_vs_nifty_20d:.4f}")

    if r.analysis:
        a = r.analysis
        print()
        print(f"  Trend        : {a.trend_classification}")
        print(f"  Confidence   : {a.confidence}")
        print(f"  Breakout Prob: {a.breakout_probability_pct}%")
        print(f"  Entry        : {a.entry_price:.2f}")
        print(f"  Stop-Loss    : {a.stop_loss:.2f}")
        print(f"  Targets      : T1={a.target_1:.2f}  T2={a.target_2:.2f}  T3={a.target_3:.2f}")
        print(f"  R:R          : 1:{a.risk_reward_ratio:.1f}")
        print()
        print("  Setup:")
        print(f"    {a.setup_description}")
        if a.key_risks:
            print()
            print("  Risks:")
            for risk in a.key_risks:
                print(f"    • {risk}")
        print()
        print("  Verdict:")
        print(f"    {a.verdict}")

    if verbose and r.signals:
        print()
        print("  Raw signals JSON:")
        print(json.dumps(r.signals.model_dump(mode="json"), indent=4))


def _main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Two-stage technical analysis pipeline (indicators → LLM)"
    )
    parser.add_argument("symbols", nargs="+", help="NSE symbol(s), e.g. RELIANCE TCS")
    parser.add_argument("--no-llm", action="store_true", help="Run Stage 1 only (no LLM call)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Dump raw JSON signals")
    parser.add_argument(
        "--json-out", metavar="FILE",
        help="Write all results to a JSON file instead of printing"
    )
    args = parser.parse_args()

    results = run_pipeline_batch(args.symbols, run_llm=not args.no_llm)

    if args.json_out:
        out = []
        for r in results:
            row: dict = {"symbol": r.symbol}
            if r.error:
                row["error"] = r.error
            else:
                row["signals"] = r.signals.model_dump(mode="json") if r.signals else None
                row["analysis"] = r.analysis.model_dump(mode="json") if r.analysis else None
            out.append(row)
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, default=str)
        print(f"Results written to {args.json_out}")
    else:
        for r in results:
            _print_result(r, verbose=args.verbose)


if __name__ == "__main__":
    _main()
