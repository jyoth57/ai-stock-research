"""Technical analysis package.

Step 1 of the two-stage pipeline:
  indicators.py  — pure Python / pandas-ta calculations (deterministic)

Usage
-----
    from src.technicals.indicators import compute_technicals
    signals = compute_technicals("RELIANCE")
"""

from src.technicals.indicators import TechnicalSignals, compute_technicals, compute_technicals_from_df

__all__ = ["compute_technicals", "compute_technicals_from_df", "TechnicalSignals"]
